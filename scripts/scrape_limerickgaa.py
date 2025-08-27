#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scrape Limerick GAA fixtures/results for:
- Senior Hurling Championship (SHC)
- Premier Intermediate Hurling Championship (PIHC)
- Intermediate Hurling Championship (IHC)
- Premier Junior A / Junior A / Junior C Hurling (PJAHC, JAHC, JCHC)

REST-first (WP):
  /wp-json/wp/v2/pages?slug=<slug>&_fields=id
  /wp-json/wp/v2/pages/<id>?_fields=content.rendered
Falls back to HTML parse if REST fails.

Outputs (to --outdir, default "data"):
- senior.json
- premier_intermediate.json
- intermediate.json
- premier_junior_a.json
- junior_a.json
- junior_c.json
- hurling_2025.json   ({updated, matches[]})
"""

import re
import os
import json
import argparse
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
    "JNR_FIX": f"{BASE}/junior-hurling-fixtures/",
    "JNR_RES": f"{BASE}/junior-hurling-results/",
}

SLUGS = {
    "SHC_FIX": "senior-hurling-fixtures",
    "SHC_RES": "senior-hurling-results",
    "PI_I_FIX": "intermediate-hurling-fixtures",
    "PI_I_RES": "intermediate-hurling-results",
    "JNR_FIX": "junior-hurling-fixtures",
    "JNR_RES": "junior-hurling-results",
}

# Display names (unchanged)
COMP_NAMES = {
    "SHC":   "Senior Hurling Championship",
    "PIHC":  "Premier Intermediate Hurling Championship",
    "IHC":   "Intermediate Hurling Championship",
    "PJAHC": "Premier Junior A Hurling Championship",
    "JAHC":  "Junior A Hurling Championship",
    "JCHC":  "Junior C Hurling Championship",
}

# ---- STRICT GROUP HEADINGS (exact as on site; normalized for case/spacing) ----
GROUPS_STRICT = {
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
    "PJAHC": [
        "Woodlands House Hotel County Premier Junior A Hurling Championship Group 1",
        "Woodlands House Hotel County Premier Junior A Hurling Championship Group 2",
    ],
    "JAHC": [
        "Woodlands House Hotel County Junior A Hurling Championship Group 1",
        "Woodlands House Hotel County Junior A Hurling Championship Group 2",
    ],
    "JCHC": [
        "Woodlands House Hotel County Junior C Hurling Championship Group 1",
        "Woodlands House Hotel County Junior C Hurling Championship Group 2",
    ],
}

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().strip())

# Normalized sets for strict detection
STRICT_ALLOWED = {k: {norm(x) for x in v} for k, v in GROUPS_STRICT.items()}
STRICT_ALL = set().union(*STRICT_ALLOWED.values())

# ---------- Helpers (dates/times/regex) ----------
ORD_RE = re.compile(r'(\d+)(?:\^\{)?(st|nd|rd|th)(?:\})?', re.I)
ORD_TOKEN_RE = re.compile(r'^\s*(?:\^\{\s*)?(st|nd|rd|th)(?:\s*\})?\s*$', re.I)
SCORE_ONLY_RE = re.compile(r'^\s*(\d+)\s*-\s*(\d+)\s*$')
RESULT_TEAM_RE = re.compile(r'^(?P<team>.+?)\s+(?P<g>\d+)\s*-\s*(?P<p>\d+)\s*$')
TIME_RE = re.compile(r'\b(\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm)?\b', re.I)
SLUG_RE = re.compile(r'[^a-z0-9]+')
WEEKDAYS = r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"

# Label / W/O / BYE classifiers
LABEL_LIKE_RE = re.compile(
    r'^(final|semi[-\s]?finals?|quarter[-\s]?finals?|round\s*\d+|play[-\s]?off|relegation|.*\bcup\b|league)$',
    re.I
)
WO_RE = re.compile(r'^(W\/O|Walkover)$', re.I)
BYE_RE = re.compile(r'^BYE$', re.I)

CODE_WITH_DIGITS_RE = re.compile(r'^[A-Z]{2,}\d+[A-Z0-9]*$')  # e.g., SJBHCG1

# Generic header-ish lines that should never be teams and should close buckets
HEADLINE_BAD_RE = re.compile(
    r'\b(championship|fixtures?|results?|final|semi[-\s]?finals?|quarter[-\s]?finals?|cup)\b',
    re.I
)
REGION_RE = re.compile(r'\b(city|east|west|south)\b', re.I)

def is_plausible_team(name: str) -> bool:
    t = (name or "").strip()
    if not t:
        return False
    # never treat these as teams
    if BYE_RE.match(t) or WO_RE.match(t) or LABEL_LIKE_RE.match(t):
        return False
    # reject lines that look like section/competition headers
    if HEADLINE_BAD_RE.search(t):
        return False
    # reject short ALL-CAPS tokens with digits and no spaces (competition/stage codes)
    if " " not in t and t.upper() == t and CODE_WITH_DIGITS_RE.match(t):
        return False
    return True

def ensure_parent(path: str):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)

def strip_ordinals(s: str) -> str:
    return ORD_RE.sub(lambda m: m.group(1), s)

def parse_date(date_line: str) -> Optional[datetime]:
    s = strip_ordinals(date_line).replace(",", " ").strip()
    s = re.sub(rf"^{WEEKDAYS}\s+", "", s, flags=re.I).strip()
    for fmt in ("%d %B %Y", "%d %b %Y"):
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
    return SLUG_RE.sub('-', (s or "").lower()).strip('-')[:3].upper()

def group_code_from_label(label: str) -> str:
    m = re.search(r'Group\s*(\d)', label or "", flags=re.I)
    return m.group(1) if m else "X"

def make_id(comp: str, date_iso: str, round_name: str, group_heading: str, home: str, away: str) -> str:
    comp_short = comp
    gcode = group_code_from_label(group_heading)
    r = (round_name or "").replace("Round", "R").replace(" ", "")
    return f"{(date_iso or '0000-00-00')[:4]}-{comp_short}-G{gcode}-{r}-{slug3(home)}-{slug3(away)}"

# ---------- WordPress REST helpers ----------
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
    soup = BeautifulSoup(html or "", "html.parser")
    lines: List[str] = []
    for el in soup.find_all(True, recursive=True):
        if el.name in {"script", "style", "noscript"}:
            continue
        txt = el.get_text("\n", strip=True)
        if not txt:
            continue
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
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text
    return flatten_to_lines(html)

# ---------- Parsing ----------
def tidy_group_for_output(comp: str, raw_heading: str) -> str:
    """
    Turn a long heading into the short label used by the UI.
    - SHC/IHC/Juniors: "Group 1"/"Group 2"
    - PIHC: "Premier Intermediate"
    """
    if comp == "PIHC":
        return "Premier Intermediate"
    m = re.search(r"Group\s*(\d)", raw_heading or "", flags=re.I)
    if m:
        return f"Group {m.group(1)}"
    return raw_heading.strip() if raw_heading else ""

def parse_blocks_from_page(url: str, comp_key: str, mode: str) -> List[Dict]:
    """
    Fetch lines (REST-first), detect ONLY the exact group headings for the given
    competition, and parse each block. While inside a block, we hard-stop when we hit:
      - any other known competition heading,
      - football sections,
      - generic section headers (fixtures/results/final/etc),
      - regional comps (City/East/West/South ... Hurling ...),
      - 'league' headings,
      - ALL-CAPS+digits code banners (e.g. SJBHCG1) — unless that token is explicitly
        whitelisted in GROUPS_STRICT (future-proof).
    """
    # pick slug for REST
    slug = ""
    for key, s in SLUGS.items():
        if URLS.get(key) == url:
            slug = s
            break

    all_lines = lines_from_rest_or_html(url, slug)

    out: List[Dict] = []
    current_group_heading: Optional[str] = None
    bucket: List[str] = []

    def flush_bucket():
        nonlocal bucket, current_group_heading, out
        if current_group_heading and bucket:
            out.extend(
                parse_group_lines(bucket, mode, comp_key, current_group_heading, url)
            )
        bucket = []

    allowed_here = STRICT_ALLOWED.get(comp_key, set())   # normalized allowed headings for this comp

    for ln in all_lines:
        n = norm(ln)

        # If we are inside this comp's block, detect boundaries
        if current_group_heading:
            # 1) football sections
            if "football" in n:
                flush_bucket(); current_group_heading = None; continue

            # 2) another known comp heading (strict match), or generic header not ours
            if n in STRICT_ALL and n not in allowed_here:
                flush_bucket(); current_group_heading = None; continue
            if HEADLINE_BAD_RE.search(n) and n not in allowed_here:
                flush_bucket(); current_group_heading = None; continue

            # 3) regional comps like City/East/West/South ... Hurling ...
            if REGION_RE.search(n) and "hurling" in n:
                flush_bucket(); current_group_heading = None; continue

            # 4) league boundary
            if re.search(r"\bleague\b", n, flags=re.I):
                flush_bucket(); current_group_heading = None; continue

            # 5) CODE BANNERS (e.g., SJBHCG1) — treat as boundary
            #    BUT only if that exact token is NOT whitelisted anywhere.
            tok = ln.strip()
            if CODE_WITH_DIGITS_RE.match(tok) and tok.upper() == tok and " " not in tok:
                if norm(tok) not in STRICT_ALL:
                    flush_bucket(); current_group_heading = None; continue

        # Start a bucket only if the line is an exact allowed heading for this comp
        if n in allowed_here:
            flush_bucket()
            current_group_heading = ln  # keep original case for provenance
            continue

        # Otherwise, if currently in a bucket, accumulate content lines
        if current_group_heading:
            bucket.append(ln)

    flush_bucket()
    return out



def parse_group_lines(lines: List[str], mode: str, comp_key: str, group_heading: str, source_url: str) -> List[Dict]:
    """
    Handles:
      - split dates: 'Saturday 23' + 'rd' + 'August, 2025'
      - robust metadata: 'Venue:' / 'Referee:' inline or next-line, default TBC
      - results: team lines 'Team 1 - 20' or separate score lines
      - skips 'league' lines and section/stage labels
      - recognises W/O (walkover) and BYE as statuses (not team names)
      - blocks code-like tokens (e.g. SJBHCG1) from becoming team names
    """
    # absolute safety: only emit if heading is one of the allowed exact headings
    if norm(group_heading) not in STRICT_ALLOWED.get(comp_key, set()):
        return []

    FIELD_LABEL_RE = re.compile(r'^(venue|referee|throw[\s\-]*in|time|date|round|group)\s*:?\s*$', re.I)

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

        # Venue (inline or next line)
        if s.lower().startswith("venue:"):
            inline = s.split(":", 1)[1].strip()
            if inline:
                stitched.append(f"Venue: {inline}")
                i += 1
                continue
            if i + 1 < len(lines):
                nxt = lines[i+1].strip()
                if not nxt or FIELD_LABEL_RE.match(nxt) or re.search(r'\bleague\b', nxt, flags=re.I):
                    stitched.append("Venue: TBC")
                    i += 1
                    continue
                stitched.append(f"Venue: {nxt}")
                i += 2
                continue
            stitched.append("Venue: TBC")
            i += 1
            continue

        # Referee (inline or next line)
        if s.lower().startswith("referee:"):
            inline = s.split(":", 1)[1].strip()
            if inline:
                stitched.append(f"Referee: {inline}")
                i += 1
                continue
            if i + 1 < len(lines):
                nxt = lines[i+1].strip()
                if not nxt or FIELD_LABEL_RE.match(nxt) or re.search(r'\bleague\b', nxt, flags=re.I):
                    stitched.append("Referee: TBC")
                    i += 1
                    continue
                stitched.append(f"Referee: {nxt}")
                i += 2
                continue
            stitched.append("Referee: TBC")
            i += 1
            continue

        stitched.append(s)
        i += 1

    results: List[Dict] = []
    status_default = "SCHEDULED" if mode == "fixtures" else "Result"

    cur = {
        "round": None, "date_line": None,
        "team_a": None, "team_b": None,
        "time_line": None, "venue": "TBC", "referee": "TBC",
        "home_goals": None, "home_points": None,
        "away_goals": None, "away_points": None,
        "wo_winner": None,     # "home" | "away" | None
        "is_bye": False,
    }

    def ready(c):
        return c["round"] and c["date_line"] and c["team_a"] and c["team_b"]

    def flush(c):
        nonlocal results
        # Discard incomplete
        if not ready(c):
            return {
                "round": c["round"], "date_line": None, "team_a": None, "team_b": None,
                "time_line": None, "venue": "TBC", "referee": "TBC",
                "home_goals": None, "home_points": None, "away_goals": None, "away_points": None,
                "wo_winner": None, "is_bye": False,
            }
        # Discard BYE fixtures/results outright
        if (
            c["is_bye"] or
            (c["team_a"] and c["team_a"].strip().lower() == "bye") or
            (c["team_b"] and c["team_b"].strip().lower() == "bye")
        ):
            return {
                "round": c["round"], "date_line": None, "team_a": None, "team_b": None,
                "time_line": None, "venue": "TBC", "referee": "TBC",
                "home_goals": None, "home_points": None, "away_goals": None, "away_points": None,
                "wo_winner": None, "is_bye": False,
            }

        d = parse_date(c["date_line"])
        date_iso = d.strftime("%Y-%m-%d") if d else None
        time_local, dt_iso = parse_time(c["time_line"], d)
        rid = make_id(comp_key, date_iso or "0000-00-00", c["round"], group_heading, c["team_a"], c["team_b"])

        status = status_default
        if c["wo_winner"] in ("home", "away"):
            status = "Walkover"

        rec = {
            "id": rid,
            "round": c["round"].replace("Round", "R").strip() if c["round"] else "",
            "group": tidy_group_for_output(comp_key, group_heading),
            "date": date_iso,
            "time_local": time_local,
            "tz": "Europe/Dublin",
            "datetime_iso": dt_iso,
            "home": c["team_a"],
            "away": c["team_b"],
            "venue": c["venue"] or "TBC",
            "referee": c["referee"] or "TBC",
            "status": status,
            "source_url": source_url
        }

        if mode == "results" and c["wo_winner"] not in ("home", "away"):
            if c["home_goals"] is not None and c["home_points"] is not None:
                rec["home_goals"] = c["home_goals"]; rec["home_points"] = c["home_points"]
            if c["away_goals"] is not None and c["away_points"] is not None:
                rec["away_goals"] = c["away_goals"]; rec["away_points"] = c["away_points"]

        results.append(rec)
        return {
            "round": c["round"], "date_line": None, "team_a": None, "team_b": None,
            "time_line": None, "venue": "TBC", "referee": "TBC",
            "home_goals": None, "home_points": None, "away_goals": None, "away_points": None,
            "wo_winner": None, "is_bye": False,
        }

    # --- Main parse over stitched lines ---
    for s in stitched:
        low = s.strip().lower()

        # Never let '... league ...' lines become teams/metadata
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
                if is_plausible_team(team):
                    cur["team_a"] = team
                    cur["home_goals"], cur["home_points"] = g, p
                continue
            elif not cur["team_b"]:
                if is_plausible_team(team):
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
            # treat "V"/"VS" as divider
            if s.upper() in {"V","VS"}:
                continue

        # Metadata
        if low.startswith("venue:"):
            cur["venue"] = s.split(":", 1)[1].strip() or "TBC"; continue
        if low.startswith("referee:"):
            cur["referee"] = s.split(":", 1)[1].strip() or "TBC"; continue

        # Time
        if TIME_RE.search(s):
            cur["time_line"] = s; continue

        # Walkover marker (results pages only) as status
        if mode == "results" and WO_RE.match(s.strip()):
            if cur["team_a"] and not cur["team_b"]:
                cur["wo_winner"] = "home";  continue
            if cur["team_a"] and cur["team_b"]:
                cur["wo_winner"] = "away";  continue

        # BYE marker as special status (we'll discard on flush)
        if BYE_RE.match(s.strip()):
            if not cur["team_a"]:
                cur["team_a"] = "BYE"
            elif not cur["team_b"]:
                cur["team_b"] = "BYE"
            cur["is_bye"] = True
            continue

        # Skip stage/section labels so they don't become teams
        if LABEL_LIKE_RE.match(s) or HEADLINE_BAD_RE.search(s):
            continue

        # Divider tokens already handled above; skip
        if s.upper() in {"V", "VS"}:
            continue

        # Teams (guarded by plausibility)
        if not cur["team_a"]:
            if is_plausible_team(s):
                cur["team_a"] = s
            continue
        elif not cur["team_b"]:
            if is_plausible_team(s):
                cur["team_b"] = s
            continue
        else:
            cur = flush(cur)
            if is_plausible_team(s):
                cur["team_a"] = s
                cur["team_b"] = None
            continue

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
def write_combined_hurling(payloads: Dict[str, Dict], outdir: str):
    """
    Build hurling_2025.json in the app's expected format.
    De-duplicate across fixtures/results: prefer results; pass through status.
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
                "status": r.get("status") or "",
                "home_goals": r.get("home_goals"),
                "home_points": r.get("home_points"),
                "away_goals": r.get("away_goals"),
                "away_points": r.get("away_points"),
            }))

        # Results (pass through status: Result/Walkover/Bye)
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
                "status": (r.get("status") or "Result"),
                "home_goals": r.get("home_goals"),
                "home_points": r.get("home_points"),
                "away_goals": r.get("away_goals"),
                "away_points": r.get("away_points"),
            }))

    # De-dupe by (comp, group, date, home, away); prefer results
    by_key: Dict[Tuple[str,str,str,str,str], Dict] = {}
    for is_result, m in buckets:
        key = (m["competition"], m["group"], m["date"], m["home"], m["away"])
        if key not in by_key or is_result:
            by_key[key] = m

    combined = {
        "updated": updated_ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matches": list(by_key.values())
    }

    out_path = os.path.join(outdir, "hurling_2025.json")
    ensure_parent(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

# ---------- Orchestration ----------
def scrape_to(outdir: str = "data"):
    # Senior
    shc_fix = dedupe_merge(parse_blocks_from_page(URLS["SHC_FIX"], "SHC", "fixtures"))
    shc_res = dedupe_merge(parse_blocks_from_page(URLS["SHC_RES"], "SHC", "results"))

    # Premier Intermediate (shared PI/I pages)
    pih_fix = dedupe_merge(parse_blocks_from_page(URLS["PI_I_FIX"], "PIHC", "fixtures"))
    pih_res = dedupe_merge(parse_blocks_from_page(URLS["PI_I_RES"], "PIHC", "results"))

    # Intermediate (shared PI/I pages)
    ihc_fix = dedupe_merge(parse_blocks_from_page(URLS["PI_I_FIX"], "IHC", "fixtures"))
    ihc_res = dedupe_merge(parse_blocks_from_page(URLS["PI_I_RES"], "IHC", "results"))

    # Juniors (junior pages)
    pjahc_fix = dedupe_merge(parse_blocks_from_page(URLS["JNR_FIX"], "PJAHC", "fixtures"))
    pjahc_res = dedupe_merge(parse_blocks_from_page(URLS["JNR_RES"], "PJAHC", "results"))

    jahc_fix  = dedupe_merge(parse_blocks_from_page(URLS["JNR_FIX"], "JAHC",  "fixtures"))
    jahc_res  = dedupe_merge(parse_blocks_from_page(URLS["JNR_RES"], "JAHC",  "results"))

    jchc_fix  = dedupe_merge(parse_blocks_from_page(URLS["JNR_FIX"], "JCHC",  "fixtures"))
    jchc_res  = dedupe_merge(parse_blocks_from_page(URLS["JNR_RES"], "JCHC",  "results"))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payloads = {
        os.path.join(outdir, "senior.json"): {
            "competition": COMP_NAMES["SHC"], "updated_at": now,
            "fixtures": shc_fix, "results": shc_res
        },
        os.path.join(outdir, "premier_intermediate.json"): {
            "competition": COMP_NAMES["PIHC"], "updated_at": now,
            "fixtures": pih_fix, "results": pih_res
        },
        os.path.join(outdir, "intermediate.json"): {
            "competition": COMP_NAMES["IHC"], "updated_at": now,
            "fixtures": ihc_fix, "results": ihc_res
        },
        os.path.join(outdir, "premier_junior_a.json"): {
            "competition": COMP_NAMES["PJAHC"], "updated_at": now,
            "fixtures": pjahc_fix, "results": pjahc_res
        },
        os.path.join(outdir, "junior_a.json"): {
            "competition": COMP_NAMES["JAHC"], "updated_at": now,
            "fixtures": jahc_fix, "results": jahc_res
        },
        os.path.join(outdir, "junior_c.json"): {
            "competition": COMP_NAMES["JCHC"], "updated_at": now,
            "fixtures": jchc_fix, "results": jchc_res
        },
    }

    # Write per-grade files
    for path, obj in payloads.items():
        ensure_parent(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    # Write combined file for the existing frontend
    write_combined_hurling({k: v for k, v in payloads.items()}, outdir)

    print("Done: wrote data files to", outdir)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data", help="Output directory for JSON files (default: data)")
    args = ap.parse_args()
    scrape_to(args.outdir)

if __name__ == "__main__":
    main()
