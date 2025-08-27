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

# -------- Group heading matching (SPONSOR-PROOF) --------
# We strip sponsor tokens from headings and then match against scoped regexes per competition.
SPONSOR_TOKENS = [
    r"white\s*box",
    r"lyons\s+of\s+limerick",
    r"woodlands\s+house\s+hotel",
    r"county",        # often inserted before the competition name
]

# Group patterns: only the stable, competition-specific words.
GROUP_PATTERNS: Dict[str, List[re.Pattern]] = {
    "SHC": [
        re.compile(r"senior hurling championship\s+group\s*1$", re.I),
        re.compile(r"senior hurling championship\s+group\s*2$", re.I),
    ],
    "PIHC": [
        re.compile(r"premier intermediate hurling championship$", re.I),  # site presents as a single block (no explicit group N)
    ],
    "IHC": [
        re.compile(r"intermediate hurling championship\s+group\s*1$", re.I),
        re.compile(r"intermediate hurling championship\s+group\s*2$", re.I),
    ],
    "PJAHC": [
        re.compile(r"premier junior a hurling championship\s+group\s*1$", re.I),
        re.compile(r"premier junior a hurling championship\s+group\s*2$", re.I),
    ],
    "JAHC": [
        re.compile(r"junior a hurling championship\s+group\s*1$", re.I),
        re.compile(r"junior a hurling championship\s+group\s*2$", re.I),
    ],
    "JCHC": [
        re.compile(r"junior c hurling championship\s+group\s*1$", re.I),
        re.compile(r"junior c hurling championship\s+group\s*2$", re.I),
    ],
}

def normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def strip_sponsors(s: str) -> str:
    t = normalize(s)
    for tok in SPONSOR_TOKENS:
        t = re.sub(rf"\b{tok}\b", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def is_group_heading_for_comp(line: str, comp_key: str) -> bool:
    core = strip_sponsors(line)
    for pat in GROUP_PATTERNS.get(comp_key, []):
        if pat.search(core):
            return True
    return False

def tidy_group_for_output(comp: str, raw_heading: str) -> str:
    """
    Turn a long heading into the short label used by the UI.
    - SHC/IHC/Juniors: "Group 1"/"Group 2"
    - PIHC: "Premier Intermediate"
    """
    core = strip_sponsors(raw_heading)
    if comp == "PIHC":
        return "Premier Intermediate"
    # Try to extract group number
    m = re.search(r"group\s*(\d)", core, flags=re.I)
    if m:
        return f"Group {m.group(1)}"
    return raw_heading.strip() or raw_heading  # fallback

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

def is_plausible_team(name: str) -> bool:
    t = (name or "").strip()
    if not t:
        return False
    # never treat these as teams
    if BYE_RE.match(t) or WO_RE.match(t) or LABEL_LIKE_RE.match(t):
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
def parse_blocks_from_page(url: str, comp_key: str, mode: str) -> List[Dict]:
    """
    Fetch lines (REST-first), detect competition-scoped group headings using sponsor-stripped regex,
    and parse each block into match records. 'League' headings end any open bucket.
    """
    # choose slug
    slug = ""
    for key, s in SLUGS.items():
        if URLS.get(key) == url:
            slug = s
            break

    all_lines = lines_from_rest_or_html(url, slug)

    # Bucket by detected group headings
    out: List[Dict] = []
    current_group_heading: Optional[str] = None
    bucket: List[str] = []

    def flush_bucket():
        nonlocal bucket, current_group_heading, out
        if current_group_heading and bucket:
            out.extend(parse_group_lines(bucket, mode, comp_key, current_group_heading, url))
        bucket = []

    for ln in all_lines:
        n = normalize(ln)

        # End any open bucket on a 'league' heading (safest guard)
        if current_group_heading and re.search(r'\bleague\b', n, flags=re.I):
            flush_bucket()
            current_group_heading = None
            continue

        # Start a group when this line matches comp-scoped pattern (after sponsor stripping)
        if is_group_heading_for_comp(ln, comp_key):
            flush_bucket()
            current_group_heading = ln  # keep the original for provenance
            continue

        # If inside a group and we hit a different competition heading, end the group
        # (i.e., matches any other competition's pattern)
        if current_group_heading:
            # If this line looks like *another* competition heading, stop.
            other_comp_hit = False
            for other_comp in GROUP_PATTERNS.keys():
                if other_comp != comp_key and is_group_heading_for_comp(ln, other_comp):
                    other_comp_hit = True
                    break
            if other_comp_hit:
                flush_bucket()
                current_group_heading = None
                continue

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
      - skips 'league' lines and stage labels
      - recognises W/O (walkover) and BYE as statuses (not team names)
      - blocks code-like tokens (e.g. SJBHCG1) from becoming team names
    """
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
        if not ready(c):
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
        if c["is_bye"]:
            status = "Bye"
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

        if mode == "results":
            if c["wo_winner"] in ("home", "away"):
                # Leave scores blank for walkovers; UI can render "W/O"
                rec["home_goals"] = None; rec["home_points"] = None
                rec["away_goals"] = None; rec["away_points"] = None
            else:
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

        # BYE marker as special status
        if BYE_RE.match(s.strip()):
            if not cur["team_a"]:
                cur["team_a"] = "BYE"
            elif not cur["team_b"]:
                cur["team_b"] = "BYE"
            cur["is_bye"] = True
            continue

        # Skip stage labels & codes so they don't become teams
        if LABEL_LIKE_RE.match(s):
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
                "status": r.get("status") or "",  # SCHEDULED typically
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
