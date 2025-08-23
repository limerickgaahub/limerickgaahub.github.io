#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scrape Limerick GAA fixtures/results for:
- Senior Hurling Championship (SHC)
- Premier Intermediate Hurling Championship (PIHC)
- Intermediate Hurling Championship (IHC)

Sources (fixed):
- SHC fixtures:  https://limerickgaa.ie/senior-hurling-fixtures/
- SHC results:   https://limerickgaa.ie/senior-hurling-results/
- PI+I fixtures: https://limerickgaa.ie/intermediate-hurling-fixtures/
- PI+I results:  https://limerickgaa.ie/intermediate-hurling-results/

Outputs (JSON):
- data/senior.json
- data/premier_intermediate.json
- data/intermediate.json
"""

import re
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

# ------------- Config -------------

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LimerickGAAHub/1.0)"}

URLS = {
    "SHC_FIX": "https://limerickgaa.ie/senior-hurling-fixtures/",
    "SHC_RES": "https://limerickgaa.ie/senior-hurling-results/",
    "PI_I_FIX": "https://limerickgaa.ie/intermediate-hurling-fixtures/",
    "PI_I_RES": "https://limerickgaa.ie/intermediate-hurling-results/",
}

# Headings / dropdown labels we expect to find on each page:
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

# ------------- Helpers -------------

ORD_RE = re.compile(r'(\d+)(st|nd|rd|th)', re.I)

def strip_ordinals(s: str) -> str:
    return ORD_RE.sub(lambda m: m.group(1), s)

DATE_PATTERNS = [
    "%d %B %Y",   # 24 August 2025
    "%d %b %Y",   # 24 Aug 2025
]

WEEKDAYS = r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"

def parse_date(date_line: str) -> Optional[datetime]:
    # Remove weekday and commas/ordinals
    s = strip_ordinals(date_line).replace(",", " ").strip()
    s = re.sub(rf"^{WEEKDAYS}\s+", "", s, flags=re.I).strip()
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=None)
        except ValueError:
            pass
    return None

TIME_RE = re.compile(r'\b(\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm)?\b', re.I)

def parse_time(time_line: Optional[str], base_date: Optional[datetime]):
    if not time_line or not base_date:
        return None, None  # time_local, datetime_iso
    s = time_line.strip().lower().replace(".", ":")
    m = TIME_RE.search(s)
    if not m:
        return None, None
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hh < 12:
        hh += 12
    if ampm == "am" and hh == 12:
        hh = 0
    time_local = f"{hh:02d}:{mm:02d}"
    # Europe/Dublin offset shifts with DST; we store local time and leave datetime_iso naive here.
    # If you want full timezone-aware ISO, integrate zoneinfo and localise.
    dt_local = base_date.replace(hour=hh, minute=mm, second=0, microsecond=0)
    # Store ISO without TZ to avoid wrong offsets; front-end can treat tz="Europe/Dublin"
    return time_local, dt_local.isoformat()

SCORE_RE = re.compile(r'(\d+)\s*-\s*(\d+)\s*(?:to|–|—|-)\s*(\d+)\s*-\s*(\d+)', re.I)

def parse_score(text: str):
    m = SCORE_RE.search(text.replace("—","-").replace("–","-"))
    if not m:
        return None
    return {
        "home_goals": int(m.group(1)),
        "home_points": int(m.group(2)),
        "away_goals": int(m.group(3)),
        "away_points": int(m.group(4)),
    }

SLUG_RE = re.compile(r'[^a-z0-9]+')

def slug3(s: str) -> str:
    return SLUG_RE.sub('-', s.lower()).strip('-')[:3].upper()

def group_code_from_label(label: str) -> str:
    m = re.search(r'Group\s*(\d)', label, flags=re.I)
    return m.group(1) if m else "X"

def tidy_group_for_output(comp: str, raw_group: str) -> str:
    # Compress verbose headings to concise labels for UI
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
    r = round_name.replace("Round","R").replace(" ","")
    return f"{date_iso[:4]}-{comp_short}-G{gcode}-{r}-{slug3(home)}-{slug3(away)}"

# ------------- Core parsing -------------

def fetch_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def textlines(el):
    raw = el.get_text("\n", strip=True)
    for line in raw.split("\n"):
        t = line.strip()
        if t:
            yield t

def parse_blocks_from_page(url: str, allowed_groups: List[str], mode: str, comp_key: str) -> List[Dict]:
    """
    Walk the page, find headings that match allowed_groups, then parse ordered lines beneath.
    mode: "fixtures" or "results"
    comp_key: "SHC" | "PIHC" | "IHC"
    """
    soup = fetch_soup(url)
    body = soup.select_one("main") or soup.body or soup
    out: List[Dict] = []

    current_group = None
    bucket: List[str] = []

    def flush_group(glabel: str, lines: List[str]):
        if not glabel or not lines:
            return []
        return parse_group_lines(lines, mode, comp_key, glabel, url)

    # Scan through headings and content; switch buckets when we hit a group heading
    for el in body.find_all(["h1","h2","h3","h4","section","div","p","li"], recursive=True):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        matched = None
        for g in allowed_groups:
            if g.lower() in text.lower():
                matched = g
                break
        if matched:
            if current_group and bucket:
                out.extend(flush_group(current_group, bucket))
            current_group = matched
            bucket = []
            continue
        if current_group:
            bucket.extend(list(textlines(el)))

    if current_group and bucket:
        out.extend(flush_group(current_group, bucket))

    return out

def parse_group_lines(lines: List[str], mode: str, comp_key: str, group_label: str, source_url: str) -> List[Dict]:
    """
    Keep a 'current' match open; attach Venue/Referee whenever they appear (even after time).
    Flush only when a new match/round starts or at the end.
    """
    results: List[Dict] = []
    status_default = "SCHEDULED" if mode == "fixtures" else "FT"

    cur = {
        "round": None,
        "date_line": None,
        "team_a": None,
        "team_b": None,
        "time_line": None,
        "venue": "TBC",
        "referee": "TBC",
        "score_text": None,
    }

    def ready(c):  # minimum viable record
        return c["round"] and c["date_line"] and c["team_a"] and c["team_b"]

    def flush(c):
        nonlocal results
        if not ready(c):
            # reset but don't append
            return {
                "round": c["round"],
                "date_line": None, "team_a": None, "team_b": None,
                "time_line": None, "venue": "TBC", "referee": "TBC", "score_text": None
            }
        d = parse_date(c["date_line"])
        date_iso = d.strftime("%Y-%m-%d") if d else None
        time_local, dt_iso = parse_time(c["time_line"], d)
        rid = make_id(comp_key, date_iso or "0000-00-00", c["round"], group_label, c["team_a"], c["team_b"])
        rec = {
            "id": rid,
            "round": c["round"].replace("Round","R").strip(),
            "group": tidy_group_for_output(comp_key, group_label),
            "date": date_iso,
            "time_local": time_local,        # may be None
            "tz": "Europe/Dublin",
            "datetime_iso": dt_iso,          # may be None
            "home": c["team_a"],
            "away": c["team_b"],
            "venue": c["venue"] or "TBC",
            "referee": c["referee"] or "TBC",
            "status": status_default,
            "source_url": source_url
        }
        if mode == "results" and c["score_text"]:
            rec["score_text"] = c["score_text"]
            sc = parse_score(c["score_text"])
            if sc: rec.update(sc)
        results.append(rec)
        return {
            "round": c["round"],
            "date_line": None, "team_a": None, "team_b": None,
            "time_line": None, "venue": "TBC", "referee": "TBC", "score_text": None
        }

    for ln in lines:
        s = ln.strip()

        # Round header
        if re.match(r'^Round\s+\d+', s, flags=re.I):
            if cur["team_a"] and cur["team_b"] and cur["date_line"]:
                cur = flush(cur)
            cur["round"] = s
            continue

        # Date line
        if re.match(rf'^{WEEKDAYS}\s+\d{{1,2}}\w{{0,2}}\s+\w+.*\d{{4}}$', s, flags=re.I) or \
           re.match(r'^\d{1,2}\s+\w+\s+\d{4}$', s):
            if cur["team_a"] and cur["team_b"] and cur["date_line"]:
                cur = flush(cur)
            cur["date_line"] = s
            continue

        # Score text (results)
        if mode == "results" and parse_score(s):
            cur["score_text"] = s
            continue

        # Venue / Referee metadata (attach to current)
        if s.lower().startswith("venue:"):
            cur["venue"] = s.split(":", 1)[1].strip() or "TBC"
            continue
        if s.lower().startswith("referee:"):
            cur["referee"] = s.split(":", 1)[1].strip() or "TBC"
            continue

        # Time
        if TIME_RE.search(s):
            cur["time_line"] = s
            continue

        # Divider
        if s.upper() in ("V","VS"):
            continue

        # Otherwise assume team names
        if not cur["team_a"]:
            cur["team_a"] = s
            continue
        elif not cur["team_b"]:
            cur["team_b"] = s
            continue
        else:
            # New unexpected content → flush and start a new record with this as team_a
            cur = flush(cur)
            cur["team_a"] = s
            cur["team_b"] = None
            continue

    # End of group
    if cur["date_line"] and cur["team_a"] and cur["team_b"]:
        flush(cur)

    return results

# ------------- Orchestration -------------

def scrape():
    # Senior
    shc_fix = parse_blocks_from_page(URLS["SHC_FIX"], GROUPS["SHC"], "fixtures", "SHC")
    shc_res = parse_blocks_from_page(URLS["SHC_RES"], GROUPS["SHC"], "results",  "SHC")

    # Premier Intermediate (from shared PI/I pages)
    pih_fix = parse_blocks_from_page(URLS["PI_I_FIX"], GROUPS["PIHC"], "fixtures", "PIHC")
    pih_res = parse_blocks_from_page(URLS["PI_I_RES"], GROUPS["PIHC"], "results",  "PIHC")

    # Intermediate (from shared PI/I pages)
    ihc_fix = parse_blocks_from_page(URLS["PI_I_FIX"], GROUPS["IHC"], "fixtures", "IHC")
    ihc_res = parse_blocks_from_page(URLS["PI_I_RES"], GROUPS["IHC"], "results",  "IHC")

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

    # Write files
    for path, obj in payloads.items():
        ensure_parent(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    print("Done: wrote data/senior.json, data/premier_intermediate.json, data/intermediate.json")

def ensure_parent(path: str):
    import os
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)

if __name__ == "__main__":
    scrape()
