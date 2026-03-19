#!/usr/bin/env python3
"""
Scrape 2026 Limerick county hurling championship fixtures from:
  https://limerickgaa.ie/senior-hurling-fixtures/
  https://limerickgaa.ie/intermediate-hurling-fixtures/

Outputs:
  <outdir>/hurling_2026.json   (default: data/hurling_2026.json)

Design choices:
- Separate from league scraper.
- Pulls from WP REST first, then falls back to direct page fetch.
- Keeps real fixture date in YYYY-MM-DD for sorting/filtering.
- Does NOT trust placeholder championship times like 12:00pm.
- Adds a neat display label, e.g. "Week of Thu 3rd Sep".
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Optional, Dict, Any

import requests
from bs4 import BeautifulSoup


TZ = "Europe/Dublin"

SENIOR_URL = "https://limerickgaa.ie/senior-hurling-fixtures/"
INTERMEDIATE_URL = "https://limerickgaa.ie/intermediate-hurling-fixtures/"

SENIOR_WP_API = "https://limerickgaa.ie/wp-json/wp/v2/pages?slug=senior-hurling-fixtures"
INTERMEDIATE_WP_API = "https://limerickgaa.ie/wp-json/wp/v2/pages?slug=intermediate-hurling-fixtures"

TARGET_COMPETITIONS = {
    "Whitebox County Senior Hurling Championship Group 1",
    "Whitebox County Senior Hurling Championship Group 2",
    "Lyons of Limerick County Premier Intermediate Hurling Championship",
    "Nick Grene Sportsground County Intermediate Hurling Championship Group 1",
    "Nick Grene Sportsground County Intermediate Hurling Championship Group 2",
}

ROUND_RE = re.compile(r"^Round\s*(\d+)\s*$", re.IGNORECASE)
V_RE = re.compile(r"^V\s*$", re.IGNORECASE)
VENUE_RE = re.compile(r"^Venue:\s*(.*)\s*$", re.IGNORECASE)
REF_RE = re.compile(r"^Referee:\s*(.*)\s*$", re.IGNORECASE)

WEEKDAYS = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
ORD_TOKEN_RE = re.compile(r"^(st|nd|rd|th)$", re.IGNORECASE)

# Example: "Thursday 3^{rd} September, 2026"
DATE_RE = re.compile(
    rf"^{WEEKDAYS}\s+(\d{{1,2}})(?:\^\{{(st|nd|rd|th)\}})?\s+([A-Za-z]+),\s*(\d{{4}})\s*$",
    re.IGNORECASE
)

MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}

WEEKDAY_ABBR = {
    0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu",
    4: "Fri", 5: "Sat", 6: "Sun"
}


@dataclass
class ChampionshipFixture:
    id: str
    competition: str
    competition_label_raw: str
    grade: str
    group: Optional[str]
    round: str
    date: str                     # YYYY-MM-DD
    date_label: str               # e.g. "Week of Thu 3rd Sep"
    time_local: Optional[str]     # intentionally None for now
    tz: str
    datetime_iso: Optional[str]   # intentionally None for now
    home: str
    away: str
    venue: str
    referee: str
    status: str
    source_url: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "competition": self.competition,
            "competition_label_raw": self.competition_label_raw,
            "grade": self.grade,
            "group": self.group,
            "round": self.round,
            "date": self.date,
            "date_label": self.date_label,
            "time_local": self.time_local,
            "tz": self.tz,
            "datetime_iso": self.datetime_iso,
            "home": self.home,
            "away": self.away,
            "venue": self.venue,
            "referee": self.referee,
            "status": self.status,
            "source_url": self.source_url,
        }


def http_get(url: str, timeout: int = 30) -> requests.Response:
    r = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "limerickgaahub-championship-scraper/1.0"},
    )
    r.raise_for_status()
    return r


def get_page_html(page_url: str, wp_api_url: str) -> str:
    try:
        r = http_get(wp_api_url)
        data = r.json()
        if isinstance(data, list) and data:
            rendered = data[0].get("content", {}).get("rendered")
            if rendered and isinstance(rendered, str):
                return rendered
    except Exception:
        pass

    r = http_get(page_url)
    return r.text


def normalize_lines(html: str) -> List[str]:
    """
    Convert HTML to a list of meaningful text lines.
    Also stitches split ordinal dates:
      "Thursday 3" + "rd" + "September, 2026"
      -> "Thursday 3^{rd} September, 2026"
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup.select_one("article") or soup
    text = main.get_text("\n")

    raw = [ln.strip() for ln in text.splitlines()]
    raw = [ln for ln in raw if ln]

    stitched: List[str] = []
    i = 0
    while i < len(raw):
        s = raw[i]

        if i + 2 < len(raw) and re.match(rf"^{WEEKDAYS}\s+\d{{1,2}}$", s, flags=re.IGNORECASE):
            t1 = raw[i + 1]
            t2 = raw[i + 2]
            if ORD_TOKEN_RE.match(t1) and re.match(r"^[A-Za-z]+", t2):
                stitched.append(f"{s}^{{{t1}}} {t2}")
                i += 3
                continue

        stitched.append(s)
        i += 1

    return stitched


def parse_date_line(s: str) -> Optional[date]:
    m = DATE_RE.match(s.strip())
    if not m:
        return None

    day = int(m.group(2))
    month_name = m.group(4)
    year = int(m.group(5))

    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }
    mm = month_map.get(month_name.lower())
    if not mm:
        return None

    return date(year, mm, day)


def ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def make_date_label(d: date) -> str:
    # Example: "Week of Thu 3rd Sep"
    wd = WEEKDAY_ABBR[d.weekday()]
    return f"Week of {wd} {ordinal(d.day)} {MONTH_ABBR[d.month]}"


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def is_plausible_team(s: str) -> bool:
    s = s.strip()
    if len(s) < 2:
        return False

    bad = {
        "venue", "referee", "round", "fixtures", "results",
        "senior hurling fixtures", "premier intermediate & intermediate hurling fixtures"
    }
    return s.lower() not in bad


def map_competition(raw: str) -> Optional[Dict[str, Optional[str]]]:
    if raw == "Whitebox County Senior Hurling Championship Group 1":
        return {
            "competition": "County Senior Hurling Championship",
            "grade": "Senior",
            "group": "Group 1",
        }
    if raw == "Whitebox County Senior Hurling Championship Group 2":
        return {
            "competition": "County Senior Hurling Championship",
            "grade": "Senior",
            "group": "Group 2",
        }
    if raw == "Lyons of Limerick County Premier Intermediate Hurling Championship":
        return {
            "competition": "County Premier Intermediate Hurling Championship",
            "grade": "Premier Intermediate",
            "group": None,
        }
    if raw == "Nick Grene Sportsground County Intermediate Hurling Championship Group 1":
        return {
            "competition": "County Intermediate Hurling Championship",
            "grade": "Intermediate",
            "group": "Group 1",
        }
    if raw == "Nick Grene Sportsground County Intermediate Hurling Championship Group 2":
        return {
            "competition": "County Intermediate Hurling Championship",
            "grade": "Intermediate",
            "group": "Group 2",
        }
    return None


def make_id(grade: str, group: Optional[str], round_s: str, d_iso: str, home: str, away: str) -> str:
    grp = slugify(group) if group else "na"
    return f"championship-{slugify(grade)}-{grp}-{slugify(round_s)}-{d_iso}-{slugify(home)}-vs-{slugify(away)}"


def parse_competition_blocks(lines: List[str], source_url: str) -> List[ChampionshipFixture]:
    fixtures: List[ChampionshipFixture] = []
    i = 0

    while i < len(lines):
        raw_comp = lines[i].strip()

        if raw_comp not in TARGET_COMPETITIONS:
            i += 1
            continue

        mapped = map_competition(raw_comp)
        if not mapped:
            i += 1
            continue

        competition = mapped["competition"]
        grade = mapped["grade"]
        group = mapped["group"]

        j = i + 1
        round_txt: Optional[str] = None
        d: Optional[date] = None
        home: Optional[str] = None
        away: Optional[str] = None
        venue: str = "TBC"
        referee: str = "TBC"

        # round
        while j < len(lines) and j < i + 20:
            if lines[j] in TARGET_COMPETITIONS:
                break
            rm = ROUND_RE.match(lines[j])
            if rm:
                round_txt = f"R {rm.group(1)}"
                j += 1
                break
            j += 1

        # date
        while j < len(lines) and j < i + 35 and d is None:
            if lines[j] in TARGET_COMPETITIONS:
                break
            dd = parse_date_line(lines[j])
            if dd:
                d = dd
                j += 1
                break
            j += 1

        # teams: locate V
        while j < len(lines) and j < i + 55:
            if lines[j] in TARGET_COMPETITIONS:
                break

            if V_RE.match(lines[j]):
                k = j - 1
                while k > i and not lines[k].strip():
                    k -= 1
                cand_home = lines[k].strip()

                k = j + 1
                while k < len(lines) and not lines[k].strip():
                    k += 1
                cand_away = lines[k].strip() if k < len(lines) else ""

                if is_plausible_team(cand_home) and is_plausible_team(cand_away):
                    home = cand_home
                    away = cand_away

                j = k + 1
                break

            j += 1

        # venue / referee
        while j < len(lines) and j < i + 80:
            if lines[j] in TARGET_COMPETITIONS:
                break

            vm = VENUE_RE.match(lines[j])
            if vm:
                v = (vm.group(1) or "").strip()
                if not v:
                    v = "TBC"
                venue = v

            rf = REF_RE.match(lines[j])
            if rf:
                r = (rf.group(1) or "").strip()
                referee = r if r else "TBC"
                j += 1
                break

            j += 1

        if round_txt and d and home and away:
            d_iso = d.strftime("%Y-%m-%d")
            date_label = make_date_label(d)
            fid = make_id(grade, group, round_txt, d_iso, home, away)

            fixtures.append(
                ChampionshipFixture(
                    id=fid,
                    competition=competition,
                    competition_label_raw=raw_comp,
                    grade=grade,
                    group=group,
                    round=round_txt,
                    date=d_iso,
                    date_label=date_label,
                    time_local=None,
                    tz=TZ,
                    datetime_iso=None,
                    home=home,
                    away=away,
                    venue=venue,
                    referee=referee,
                    status="SCHEDULED",
                    source_url=source_url,
                )
            )

        i = max(i + 1, j)

    return fixtures


def dedupe_fixtures(fixtures: List[ChampionshipFixture]) -> List[ChampionshipFixture]:
    seen = set()
    out: List[ChampionshipFixture] = []

    for f in fixtures:
        key = (f.competition_label_raw, f.round, f.date, f.home, f.away)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)

    out.sort(key=lambda x: (x.date, x.grade or "", x.group or "", x.round, x.home, x.away))
    return out


def write_json(out_path: str, fixtures: List[ChampionshipFixture]) -> None:
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    payload = {
        "competition": "Limerick Hurling Championship",
        "season": 2026,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "fixtures": [f.to_dict() for f in fixtures],
    }

    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def resolve_out_path(args_outdir: str, args_out: Optional[str]) -> str:
    # Precedence:
    # 1) explicit --out
    # 2) env var LGH_CHAMPIONSHIP_OUT
    # 3) --outdir/hurling_2026.json
    if args_out:
        return args_out
    env = os.environ.get("LGH_CHAMPIONSHIP_OUT")
    if env:
        return env
    return os.path.join(args_outdir, "hurling_2026.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data", help="Directory to write hurling_2026.json into (default: data)")
    ap.add_argument("--out", default=None, help="Full output path. Overrides --outdir and LGH_CHAMPIONSHIP_OUT.")
    args = ap.parse_args()

    out_path = resolve_out_path(args.outdir, args.out)

    senior_html = get_page_html(SENIOR_URL, SENIOR_WP_API)
    intermediate_html = get_page_html(INTERMEDIATE_URL, INTERMEDIATE_WP_API)

    senior_lines = normalize_lines(senior_html)
    intermediate_lines = normalize_lines(intermediate_html)

    fixtures = []
    fixtures.extend(parse_competition_blocks(senior_lines, SENIOR_URL))
    fixtures.extend(parse_competition_blocks(intermediate_lines, INTERMEDIATE_URL))
    fixtures = dedupe_fixtures(fixtures)

    write_json(out_path, fixtures)
    print(f"[championship] wrote {len(fixtures)} fixtures -> {out_path}")


if __name__ == "__main__":
    main()
