#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scrape Limerick GAA fixtures/results for:
- Senior Hurling Championship (SHC)
- Premier Intermediate Hurling Championship (PIHC)
- Intermediate Hurling Championship (IHC)

Sources (frontend URLs for reference):
- SHC fixtures:  https://limerickgaa.ie/senior-hurling-fixtures/
- SHC results:   https://limerickgaa.ie/senior-hurling-results/
- PI+I fixtures: https://limerickgaa.ie/intermediate-hurling-fixtures/
- PI+I results:  https://limerickgaa.ie/intermediate-hurling-results/

We fetch page bodies via the WP REST API:
- GET /wp-json/wp/v2/pages?slug=<slug>&_fields=id
- GET /wp-json/wp/v2/pages/<id>?_fields=content.rendered
(Falls back to HTML if REST fails)

Outputs:
- data/senior.json
- data/premier_intermediate.json
- data/intermediate.json
- data/hurling_2025.json   (combined: {updated, matches[]})
"""

import re
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup

# ---------- Config ----------
BASE = "https://limerickgaa.ie"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LimerickGAAHub/1.0)"}

URLS = {
    "SHC_FIX": f"{BASE}/senior-hurling-fixtures/",
    "SHC_RES": f"{BASE}/senior-hurling-results/",
    "PI_I_FIX": f"{BASE}/intermediate-hurling-fixtures/",
    "PI_I_RES": f"{BASE}/intermediate-hurling-results/",
}

SLUGS = {
    "SHC_FIX": "senior-hurling-fixtures",
    "SHC_RES": "senior-hurling-results",
    "PI_I_FIX": "intermediate-hurling-fixtures",
    "PI_I_RES": "intermediate-hurling-results",
}

# Group labels exactly as they appear on the pages
GROUPS = {
    "SHC": [
        "White BOX County Senior Hurling Championship Group 1",
        "White BOX County Senior Hurling Championship Group 2",
    ],
    "PIHC": [
        "Lyons of Limerick County Premier Intermediate Hurling Championship",
    ],
    "IHC": [
        "County Intermediate Hurling Championship Group 1",
        "County Intermediate Hurling Championship Group 2",
    ],
}

COMP_NAMES = {
    "SHC": "Senior Hurling Championship",
    "PIHC": "Premier Intermediate Hurling Championship",
    "IHC": "Intermediate Hurling Championship",
}

# ---------- Helpers (dates/times/regex) ----------
ORD_RE = re.compile(r'(\d+)(?:\^\{)?(st|nd|rd|th)(?:\})?', re.I)
ORD_TOKEN_RE = re.compile(r'^\s*(?:\^\{\s*)?(st|nd|rd|th)(?:\s*\})?\s*$', re.I)
SCORE_ONLY_RE = re.compile(r'^\s*(\d+)\s*-\s*(\d+)\s*$')
RESULT_TEAM_RE = re.compile(r'^(?P<team>.+?)\s+(?P<g>\d+)\s*-\s*(?P<p>\d+)\s*$')
TIME_RE = re.compile(r'\b(\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm)?\b', re.I)

DATE_PATTERNS = ["%d %B %Y", "%d %b %Y"]  # e.g., 24 August 2025 / 24 Aug 2025
WEEKDAYS = r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"

SLUG_RE = re.compile(r'[^a-z0-9]+')

def strip_ordinals(s: str) -> str:
    return ORD_RE.sub(lambda m: m.group(1), s)

def parse_date(date_line: str) -> Optional[datetime]:
    s = strip_ordinals(date_line).replace(",", " ").strip()
    s = re.sub(rf"^{WEEKDAYS}\s+", "", s, flags=re.I).strip()
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=None)
        except ValueError:
            pass
    return None

def parse_time(time_line: Optional[str], base_date: Optional[datetime]) -> Tuple[Optional[str], Optional[str]]:
    if not time_line or not base_date:
        return None, None
    s = time_line.strip().lower().replace(".", ":")
    m = TIME_RE.search(s)
    if not m:
        return None, None
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hh < 12: hh += 12
    if ampm == "am" and hh == 12: hh = 0
    time_local = f"{hh:02d}:{mm:02d}"
    dt_local = base_date.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return time_local, dt_local.isoformat()  # naive ISO; UI uses Europe/Dublin

def slug3(s: str) -> str:
    return SLUG_RE.sub('-', s.lower()).strip('-')[:3].upper()

def group_code_from_label(label: str) -> str:
    m = re.search(r'Group\s*(\d)', label, flags=re.I)
    return m.group(1) if m else "X"

def tidy_group_for_output(comp: str, raw_group: str) -> str:
    if comp == "SHC":
        return re.sub(r'^White BOX County Senior Hurling Championship\s*', '', raw_group).strip()
    if comp == "PIHC":
        return "Premier Intermediate"
    if comp == "IHC":
        return re.sub(r'^County Intermediate Hurling Championship\s*', '', raw_group).strip()
    return raw_group.strip()

def make_id(comp: str, date_iso: str, round_name: str, group_label: str, home: str, away: str) -> str:
    comp_short = comp
    gcode = group_code_from_label(group_label)
    r = (round_name or "").replace("Round", "R").replace(" ", "")
    return f"{(date_iso or '0000-00-00')[:4]}-{comp_short}-G{gcode}-{r}-{slug3(home)}-{slug3(away)}"

# ---------- IO utils ----------
def ensure_parent(path: str):
    import os
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)

def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

# ---------- WordPress REST helpers (by slug) ----------
# Official WP REST pages endpoint: GET /wp/v2/pages (supports slug & _fields). :contentReference[oaicite:1]{index=1}
def wp_page_id_by_slug(slug: str) -> Optional[int]:
    url = f"{BASE}/wp-json/wp/v2/pages"
    r = requests.get(url, params={"slug": slug, "_fields": "id"}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    arr = r.json()
    return arr[0]["id"] if arr else None

def wp_get_page_html_by_id(page_id: int) -> str:
    url = f"{BASE}/wp-json/wp/v2/pages/{page_id}"
    r = requests.get(url, params={"_fields": "content.rendered"}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j.get("content", {}).get("rendered", "") or ""

def flatten_to_lines(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    lines: List[str] = []
    for el in soup.find_all(True, recursive=True):
        if el.name in {"script", "style", "noscript"}: continue
        txt = el.get_text("\n", strip=True)
        if not txt: continue
        lines.extend([ln.strip() for ln in txt.split("\n") if ln.strip()])
    return lines

def lines_from_rest_or_html(url: str, slug_hint: str) -> List[str]:
    html = ""
    try:
        if slug_hint:
            pid = wp_page_id_by_slug(slug_hint)
            if pid:
                html = wp_get_page_html_by_id(pid)
    except Exception:
        html = ""
    if not html:
        # Fallback to full HTML
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text
    return flatten_to_lines(html)

# ---------- Page parsing ----------
def parse_blocks_from_page(url: str, allowed_groups: List[str], mode: str, comp_key: str) -> List[Dict]:
    """
    Get page lines via REST (preferred) or HTML fallback; detect allowed group blocks;
    parse each block into match records. Adds a PIHC-specific guard to stop on 'League' headings.
    """
    # choose slug from URL
    slug = ""
    for key, s in SLUGS.items():
        if URLS.get(key) == url:
            slug = s
            break

    all_lines = lines_from_rest_or_html(url, slug)

    # DEBUG snapshot
    try:
        ensure_parent("data/_debug/")
        sample = "\n".join(all_lines[:200])
        keyname = ("SHC_FIX" if "senior-hurling-fixtures" in url else
                   "SHC_RES" if "senior-hurling-results" in url else
                   "PI_I_FIX" if "intermediate-hurling-fixtures" in url else
                   "PI_I_RES")
        with open(f"data/_debug/lines_{keyname}.txt", "w", encoding="utf-8") as df:
            df.write(sample)
    except Exception:
        pass

    norm_allowed = {normalize(g): g for g in allowed_groups}

    out: List[Dict] = []
    current_group: Optional[str] = None
    bucket: List[str] = []

    def flush_bucket():
        nonlocal bucket, current_group, out
        if current_group and bucket:
            out.extend(parse_group_lines(bucket, mode, comp_key, current_group, url))
        bucket = []

    for ln in all_lines:
        n = normalize(ln)

        # --- NEW: If we're inside PIHC and hit any '... League ...' section heading, end that block.
        # This stops league content (e.g. "Bons Secours ... Intermediate Hurling League") from being
        # appended to the Premier Intermediate Championship bucket.
        if current_group and comp_key == "PIHC" and re.search(r'\bleague\b', n, flags=re.I):
            flush_bucket()
            current_group = None
            continue

        # If inside a group and we hit a different '* Championship *' line, stop that group.
        if current_group and ("championship" in n) and not any(k in n for k in norm_allowed.keys()):
            flush_bucket()
            current_group = None
            continue

        # Start a new group when an allowed label appears in the line
        matched_label = None
        for k_norm, raw in norm_allowed.items():
            if k_norm in n:
                matched_label = raw
                break
        if matched_label:
            flush_bucket()
            current_group = matched_label
            continue

        if current_group:
            bucket.append(ln)

    flush_bucket()
    return out



def parse_group_lines(lines: List[str], mode: str, comp_key: str, group_label: str, source_url: str) -> List[Dict]:
    """
    Handles:
      - split dates: 'Saturday 23' + 'rd' + 'August, 2025'
      - split metadata: 'Venue:' + next line is the value; same for 'Referee'
      - results: team lines 'Team 1 - 20' or separate score lines
      - (NEW) skip any '... league ...' headings so they never become team names
    """
    # --- Pre-stitch dates and metadata ---
    stitched: List[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()

        # Join split date "Weekday DD" + ("st"/"nd"/"rd"/"th" or "^{rd}") + "Month, YYYY"
        weekday_day = re.match(rf'^{WEEKDAYS}\s+\d{{1,2}}$', s, flags=re.I)
        if weekday_day and i + 2 < len(lines):
            suf = lines[i+1].strip()
            month_yr = lines[i+2].strip()
            if re.fullmatch(r'(\^{\s*(st|nd|rd|th)\s*}|st|nd|rd|th)', suf, flags=re.I) and re.search(r'\b\d{4}\b', month_yr):
                s = f"{s}{suf if suf.startswith('^') else suf} {month_yr}"
                i += 3
                stitched.append(s)
                continue

        # Join split metadata: "Venue:" then value on next line
        if s.lower() == "venue:" and i + 1 < len(lines):
            val = lines[i+1].strip()
            stitched.append(f"Venue: {val}")
            i += 2
            continue

        if s.lower() == "referee:" and i + 1 < len(lines):
            val = lines[i+1].strip()
            stitched.append(f"Referee: {val}")
            i += 2
            continue

        stitched.append(s)
        i += 1

    results: List[Dict] = []
    status_default = "SCHEDULED" if mode == "fixtures" else "FT"

    cur = {
        "round": None, "date_line": None,
        "team_a": None, "team_b": None,
        "time_line": None, "venue": "TBC", "referee": "TBC",
        "home_goals": None, "home_points": None,
        "away_goals": None, "away_points": None,
    }

    def ready(c): return c["round"] and c["date_line"] and c["team_a"] and c["team_b"]

    def flush(c):
        nonlocal results
        if not ready(c):
            return {
                "round": c["round"], "date_line": None, "team_a": None, "team_b": None,
                "time_line": None, "venue": "TBC", "referee": "TBC",
                "home_goals": None, "home_points": None, "away_goals": None, "away_points": None,
            }
        d = parse_date(c["date_line"])
        date_iso = d.strftime("%Y-%m-%d") if d else None
        time_local, dt_iso = parse_time(c["time_line"], d)
        rid = make_id(comp_key, date_iso or "0000-00-00", c["round"], group_label, c["team_a"], c["team_b"])
        rec = {
            "id": rid,
            "round": c["round"].replace("Round","R").strip() if c["round"] else "",
            "group": tidy_group_for_output(comp_key, group_label),
            "date": date_iso,
            "time_local": time_local,
            "tz": "Europe/Dublin",
            "datetime_iso": dt_iso,
            "home": c["team_a"],
            "away": c["team_b"],
            "venue": c["venue"] or "TBC",
            "referee": c["referee"] or "TBC",
            "status": status_default,
            "source_url": source_url
        }
        if mode == "results":
            if c["home_goals"] is not None and c["home_points"] is not None:
                rec["home_goals"] = c["home_goals"]; rec["home_points"] = c["home_points"]
            if c["away_goals"] is not None and c["away_points"] is not None:
                rec["away_goals"] = c["away_goals"]; rec["away_points"] = c["away_points"]
        results.append(rec)
        return {
            "round": c["round"], "date_line": None, "team_a": None, "team_b": None,
            "time_line": None, "venue": "TBC", "referee": "TBC",
            "home_goals": None, "home_points": None, "away_goals": None, "away_points": None,
        }

    # --- Main parse ---
    for s in stitched:
        low = s.strip().lower()

        # NEW: never let '... league ...' lines become teams/metadata
        if "league" in low:
            continue

        # ignore standalone ordinal fragments
        if ORD_TOKEN_RE.match(s):
            continue

        # Round
        if re.match(r'^Round\s+\d+', s, flags=re.I):
            if cur["team_a"] and cur["team_b"] and cur["date_line"]:
                cur = flush(cur)
            cur["round"] = s
            continue

        # Date
        if (re.match(rf'^{WEEKDAYS}\s+\d{{1,2}}(?:\^\{{\s*(?:st|nd|rd|th)\s*\}}|st|nd|rd|th)?\s+\w+.*\d{{4}}$', s, flags=re.I)
            or re.match(r'^\d{1,2}\s+\w+\s+\d{4}$', s)):
            if cur["team_a"] and cur["team_b"] and cur["date_line"]:
                cur = flush(cur)
            cur["date_line"] = s
            continue

        # Results: team + inline score
        mres = RESULT_TEAM_RE.match(s)
        if mres and mode == "results":
            team = mres.group("team").strip()
            g = int(mres.group("g")); p = int(mres.group("p"))
            if not cur["team_a"]:
                cur["team_a"] = team
                cur["home_goals"], cur["home_points"] = g, p
                continue
            elif not cur["team_b"]:
                cur["team_b"] = team
                cur["away_goals"], cur["away_points"] = g, p
                continue

        # Results: separate score line (e.g. "0 - 18")
        if mode == "results":
            ms = SCORE_ONLY_RE.match(s)
            if ms:
                g = int(ms.group(1)); p = int(ms.group(2))
                if cur["team_b"] is not None:
                    cur["away_goals"], cur["away_points"] = g, p
                elif cur["team_a"] is not None and cur["home_goals"] is None:
                    cur["home_goals"], cur["home_points"] = g, p
                continue
            if s.upper() in {"V", "VS"}:
                continue

        # Metadata
        if low.startswith("venue:"):
            cur["venue"] = s.split(":", 1)[1].strip() or "TBC"; continue
        if low.startswith("referee:"):
            cur["referee"] = s.split(":", 1)[1].strip() or "TBC"; continue

        # Time
        if TIME_RE.search(s):
            cur["time_line"] = s; continue

        # Divider
        if s.upper() in ("V","VS"):
            continue

        # Teams
        if not cur["team_a"]:
            cur["team_a"] = s; continue
        elif not cur["team_b"]:
            cur["team_b"] = s; continue
        else:
            cur = flush(cur)
            cur["team_a"] = s; cur["team_b"] = None; continue

    if cur["date_line"] and cur["team_a"] and cur["team_b"]:
        flush(cur)

    return results

# ---------- De-duplication (within each grade) ----------
def _mk_key(rec):
    return (
        rec.get("round") or "",
        rec.get("group") or "",
        rec.get("date") or "",
        rec.get("home") or "",
        rec.get("away") or "",
    )

def _prefer(a, b):
    out = dict(a)
    for k in ["time_local", "datetime_iso", "venue", "referee", "status",
              "home_goals", "home_points", "away_goals", "away_points", "source_url"]:
        av, bv = a.get(k), b.get(k)
        if (av in (None, "", "TBC") and bv not in (None, "", "TBC")):
            out[k] = bv
        elif k in ("home_goals","home_points","away_goals","away_points"):
            if av is None and bv is not None:
                out[k] = bv
    return out

def dedupe_merge(records):
    merged = {}
    for r in records:
        key = _mk_key(r)
        if key in merged:
            merged[key] = _prefer(merged[key], r)
        else:
            merged[key] = r
    return list(merged.values())

# ---------- Combined file ----------
def write_combined_hurling(payloads: Dict[str, Dict]):
    """
    Build data/hurling_2025.json in the app's expected format.
    De-duplicate across fixtures/results: prefer results.
    """
    updated_ts = None
    buckets = []  # (is_result, match_dict)

    for obj in payloads.values():
        if not updated_ts:
            updated_ts = obj.get("updated_at")
        comp = obj["competition"]

        # Fixtures
        for r in obj.get("fixtures", []):
            buckets.append((False, {
                "competition": comp,
                "group": r.get("group") or "",
                "round": r.get("round") or "",
                "date": r.get("date") or "",
                "time": r.get("time_local") or "",
                "home": r.get("home") or "",
                "away": r.get("away") or "",
                "venue": r.get("venue") or "",
                "status": "",
                "home_goals": r.get("home_goals"),
                "home_points": r.get("home_points"),
                "away_goals": r.get("away_goals"),
                "away_points": r.get("away_points"),
            }))

        # Results
        for r in obj.get("results", []):
            buckets.append((True, {
                "competition": comp,
                "group": r.get("group") or "",
                "round": r.get("round") or "",
                "date": r.get("date") or "",
                "time": r.get("time_local") or "",
                "home": r.get("home") or "",
                "away": r.get("away") or "",
                "venue": r.get("venue") or "",
                "status": "Result",
                "home_goals": r.get("home_goals"),
                "home_points": r.get("home_points"),
                "away_goals": r.get("away_goals"),
                "away_points": r.get("away_points"),
            }))

    # de-dupe by key; prefer results
    by_key: Dict[Tuple[str,str,str,str,str], Dict] = {}
    for is_result, m in buckets:
        key = (m["competition"], m["group"], m["date"], m["home"], m["away"])
        if key not in by_key or is_result:
            by_key[key] = m

    combined = {"updated": updated_ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "matches": list(by_key.values())}

    ensure_parent("data/hurling_2025.json")
    with open("data/hurling_2025.json", "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

# ---------- Orchestration ----------
def scrape():
    # Senior
    shc_fix = dedupe_merge(parse_blocks_from_page(URLS["SHC_FIX"], GROUPS["SHC"], "fixtures", "SHC"))
    shc_res = dedupe_merge(parse_blocks_from_page(URLS["SHC_RES"], GROUPS["SHC"], "results",  "SHC"))

    # Premier Intermediate (from shared PI/I pages)
    pih_fix = dedupe_merge(parse_blocks_from_page(URLS["PI_I_FIX"], GROUPS["PIHC"], "fixtures", "PIHC"))
    pih_res = dedupe_merge(parse_blocks_from_page(URLS["PI_I_RES"], GROUPS["PIHC"], "results",  "PIHC"))

    # Intermediate (from shared PI/I pages)
    ihc_fix = dedupe_merge(parse_blocks_from_page(URLS["PI_I_FIX"], GROUPS["IHC"], "fixtures", "IHC"))
    ihc_res = dedupe_merge(parse_blocks_from_page(URLS["PI_I_RES"], GROUPS["IHC"], "results",  "IHC"))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payloads = {
        "data/senior.json": {
            "competition": COMP_NAMES["SHC"], "updated_at": now,
            "fixtures": shc_fix, "results": shc_res
        },
        "data/premier_intermediate.json": {
            "competition": COMP_NAMES["PIHC"], "updated_at": now,
            "fixtures": pih_fix, "results": pih_res
        },
        "data/intermediate.json": {
            "competition": COMP_NAMES["IHC"], "updated_at": now,
            "fixtures": ihc_fix, "results": ihc_res
        },
    }

    # Write per‑grade files
    for path, obj in payloads.items():
        ensure_parent(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    # Write combined file for the existing frontend
    write_combined_hurling(payloads)

    print("Done: wrote data/senior.json, data/premier_intermediate.json, data/intermediate.json and data/hurling_2025.json")

if __name__ == "__main__":
    scrape()
