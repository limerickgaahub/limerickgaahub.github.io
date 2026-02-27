#!/usr/bin/env python3
"""
Scrape County Hurling League Division 1–12 fixtures from:
  https://limerickgaa.ie/senior-hurling-fixtures/

Outputs:
  data/league.json

This script is intentionally separate from any existing fixture/results scrapers.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, date, time
from typing import List, Optional, Dict, Any, Tuple

import requests
from bs4 import BeautifulSoup


URL = "https://limerickgaa.ie/senior-hurling-fixtures/"
WP_API_PAGE_BY_SLUG = "https://limerickgaa.ie/wp-json/wp/v2/pages?slug=senior-hurling-fixtures"
TZ = "Europe/Dublin"

# Matches "County Hurling League Division 7" and also the typo "Divsion 7"
DIV_RE = re.compile(r"^County Hurling League\s+Div(?:ision|sion)\s*(\d{1,2})\s*$", re.IGNORECASE)
ROUND_RE = re.compile(r"^Round\s*(\d+)\s*$", re.IGNORECASE)
V_RE = re.compile(r"^V\s*$", re.IGNORECASE)
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")  # 19:30
VENUE_RE = re.compile(r"^Venue:\s*(.*)\s*$", re.IGNORECASE)
REF_RE = re.compile(r"^Referee:\s*(.*)\s*$", re.IGNORECASE)

WEEKDAYS = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
ORD_TOKEN_RE = re.compile(r"^(st|nd|rd|th)$", re.IGNORECASE)

# Example: "Saturday 23^{rd} August, 2025"
DATE_RE = re.compile(
    rf"^{WEEKDAYS}\s+(\d{{1,2}})(?:\^\{{(st|nd|rd|th)\}})?\s+([A-Za-z]+),\s*(\d{{4}})\s*$",
    re.IGNORECASE
)


@dataclass
class LeagueFixture:
    competition: str
    group: str
    round: str
    date: str  # YYYY-MM-DD
    time_local: Optional[str]  # HH:MM
    tz: str
    datetime_iso: Optional[str]  # YYYY-MM-DDTHH:MM:SS+00:00 (we don't compute offset; leave local ISO)
    home: str
    away: str
    venue: str
    referee: str
    status: str
    source_url: str
    id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "competition": self.competition,
            "group": self.group,
            "round": self.round,
            "date": self.date,
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
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "limerickgaahub-league-scraper/1.0"})
    r.raise_for_status()
    return r


def get_page_html() -> str:
    """
    Prefer WP REST (stable, clean HTML in content.rendered). Fall back to direct fetch.
    """
    try:
        r = http_get(WP_API_PAGE_BY_SLUG)
        data = r.json()
        if isinstance(data, list) and data:
            rendered = data[0].get("content", {}).get("rendered")
            if rendered and isinstance(rendered, str):
                return rendered
    except Exception:
        pass

    # Fallback: fetch the page
    r = http_get(URL)
    return r.text


def normalize_lines(html: str) -> List[str]:
    """
    Convert HTML to a list of meaningful text lines.
    Also stitches split ordinal dates:
      "Saturday 23" + "rd" + "August, 2025"  -> "Saturday 23^{rd} August, 2025"
    """
    soup = BeautifulSoup(html, "html.parser")

    # If full page was fetched, focus on main content if possible
    main = soup.select_one("main") or soup.select_one("article") or soup
    text = main.get_text("\n")

    raw = [ln.strip() for ln in text.splitlines()]
    raw = [ln for ln in raw if ln]  # drop blanks

    stitched: List[str] = []
    i = 0
    while i < len(raw):
        s = raw[i]

        # stitch date ordinal split
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


def parse_time_line(s: str) -> Optional[time]:
    m = TIME_RE.search(s)
    if not m:
        return None
    hh = int(m.group(1))
    mi = int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mi <= 59):
        return None
    return time(hh, mi)


def slugify_team(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def make_id(div: str, round_s: str, d_iso: str, home: str, away: str) -> str:
    # Deterministic id
    return f"league-{div}-{round_s}-{d_iso}-{slugify_team(home)}-vs-{slugify_team(away)}"


def is_plausible_team(s: str) -> bool:
    # Avoid picking up obvious non-team noise lines
    if len(s.strip()) < 2:
        return False
    bad = {"venue", "referee", "round", "fixtures", "results"}
    if s.strip().lower() in bad:
        return False
    return True


def parse_league(lines: List[str]) -> List[LeagueFixture]:
    fixtures: List[LeagueFixture] = []
    i = 0

    while i < len(lines):
        div_m = DIV_RE.match(lines[i])
        if not div_m:
            i += 1
            continue

        div_no = int(div_m.group(1))
        if not (1 <= div_no <= 12):
            i += 1
            continue

        group = f"Division {div_no}"
        competition = "County Hurling League"

        # Scan forward within a reasonable window for the match block
        j = i + 1

        round_txt: Optional[str] = None
        d: Optional[date] = None
        home: Optional[str] = None
        away: Optional[str] = None
        t: Optional[time] = None
        venue: str = "TBC"
        referee: str = "TBC"

        # round
        while j < len(lines) and j < i + 20:
            rm = ROUND_RE.match(lines[j])
            if rm:
                round_txt = f"R {rm.group(1)}"
                j += 1
                break
            if DIV_RE.match(lines[j]):  # next division starts
                break
            j += 1

        # date
        while j < len(lines) and j < i + 35 and d is None:
            if DIV_RE.match(lines[j]):
                break
            dd = parse_date_line(lines[j])
            if dd:
                d = dd
                j += 1
                break
            j += 1

        # teams: locate "V"
        while j < len(lines) and j < i + 55:
            if DIV_RE.match(lines[j]):
                break
            if V_RE.match(lines[j]):
                # previous non-empty line is home
                k = j - 1
                while k > i and not lines[k].strip():
                    k -= 1
                cand_home = lines[k].strip()
                # next non-empty line is away
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

        # time
        while j < len(lines) and j < i + 70 and t is None:
            if DIV_RE.match(lines[j]):
                break
            tt = parse_time_line(lines[j])
            if tt:
                t = tt
                j += 1
                break
            j += 1

        # venue/referee
        while j < len(lines) and j < i + 90:
            if DIV_RE.match(lines[j]):
                break

            vm = VENUE_RE.match(lines[j])
            if vm:
                v = (vm.group(1) or "").strip()
                # sometimes venue is on the next line
                if not v and j + 1 < len(lines) and not REF_RE.match(lines[j + 1]) and not DIV_RE.match(lines[j + 1]):
                    v = lines[j + 1].strip()
                    j += 1
                if v:
                    venue = v

            rf = REF_RE.match(lines[j])
            if rf:
                r = (rf.group(1) or "").strip()
                if r:
                    referee = r
                j += 1
                break

            j += 1

        # build fixture only if core fields exist
        if round_txt and d and home and away:
            d_iso = d.strftime("%Y-%m-%d")
            time_local = t.strftime("%H:%M") if t else None
            # Keep datetime_iso simple/local; you can compute offsets later if needed
            dt_iso = f"{d_iso}T{time_local}:00" if time_local else None
            fid = make_id(str(div_no), round_txt.replace(" ", ""), d_iso, home, away)

            fixtures.append(
                LeagueFixture(
                    competition=competition,
                    group=group,
                    round=round_txt,
                    date=d_iso,
                    time_local=time_local,
                    tz=TZ,
                    datetime_iso=dt_iso,
                    home=home,
                    away=away,
                    venue=venue,
                    referee=referee,
                    status="SCHEDULED",
                    source_url=URL,
                    id=fid,
                )
            )

        i = max(i + 1, j)

    return fixtures


def write_json(out_path: str, fixtures: List[LeagueFixture]) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    payload = {
        "competition": "County Hurling League",
        "season": datetime.now().year,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "fixtures": [f.to_dict() for f in fixtures],
    }
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def main():
    out_path = os.environ.get("LGH_LEAGUE_OUT", "data/league.json")
    html = get_page_html()
    lines = normalize_lines(html)
    fixtures = parse_league(lines)

    # Basic sanity: keep only Div 1–12
    fixtures = [f for f in fixtures if 1 <= int(f.group.split()[-1]) <= 12]

    write_json(out_path, fixtures)
    print(f"[league] wrote {len(fixtures)} fixtures -> {out_path}")


if __name__ == "__main__":
    main()
