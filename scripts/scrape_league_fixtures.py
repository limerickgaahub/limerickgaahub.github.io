#!/usr/bin/env python3
"""
Scrape County Hurling League Division 1-12 fixtures and results from:
  https://limerickgaa.ie/senior-hurling-fixtures/
  https://limerickgaa.ie/senior-hurling-results/

Outputs:
  <outdir>/league.json   (default: data/league.json)

This script is intentionally separate from any existing fixture/results scrapers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, date, time
from typing import List, Optional, Dict, Any

import requests
from bs4 import BeautifulSoup


FIXTURES_URL = "https://limerickgaa.ie/senior-hurling-fixtures/"
RESULTS_URL = "https://limerickgaa.ie/senior-hurling-results/"

WP_API_FIXTURES = "https://limerickgaa.ie/wp-json/wp/v2/pages?slug=senior-hurling-fixtures"
WP_API_RESULTS = "https://limerickgaa.ie/wp-json/wp/v2/pages?slug=senior-hurling-results"

TZ = "Europe/Dublin"

# Hard limit: County Hurling League Division 1..12 only
DIV_RE = re.compile(
    r"^County Hurling League\s+Div(?:ision|sion)\s*(\d{1,2})\s*$",
    re.IGNORECASE
)
ALLOWED_DIVISIONS = {str(i) for i in range(1, 13)}

ROUND_RE = re.compile(r"^Round\s*(\d+)\s*$", re.IGNORECASE)
V_RE = re.compile(r"^V\s*$", re.IGNORECASE)

TIME_RE = re.compile(
    r"\b(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?\b|\b(\d{1,2}):(\d{2})\b",
    re.IGNORECASE
)
VENUE_RE = re.compile(r"^Venue:\s*(.*)\s*$", re.IGNORECASE)
REF_RE = re.compile(r"^Referee:\s*(.*)\s*$", re.IGNORECASE)

WEEKDAYS = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
ORD_TOKEN_RE = re.compile(r"^(st|nd|rd|th)$", re.IGNORECASE)

DATE_RE = re.compile(
    rf"^{WEEKDAYS}\s+(\d{{1,2}})(?:\^\{{(st|nd|rd|th)\}})?\s+([A-Za-z]+),\s*(\d{{4}})\s*$",
    re.IGNORECASE
)

SCORE_ONLY_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
RESULT_TEAM_RE = re.compile(r"^(?P<team>.+?)\s+(?P<g>\d+)\s*-\s*(?P<p>\d+)\s*$")
WO_RE = re.compile(r"^(W\/O|Walkover)$", re.IGNORECASE)
BYE_RE = re.compile(r"^BYE$", re.IGNORECASE)


@dataclass
class LeagueFixture:
    competition: str
    group: str
    round: str
    date: str  # YYYY-MM-DD
    time_local: Optional[str]  # HH:MM
    tz: str
    datetime_iso: Optional[str]  # local ISO only (no offset computation)
    home: str
    away: str
    venue: str
    referee: str
    status: str
    source_url: str
    id: str
    home_goals: Optional[int] = None
    home_points: Optional[int] = None
    away_goals: Optional[int] = None
    away_points: Optional[int] = None

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
            "home_goals": self.home_goals,
            "home_points": self.home_points,
            "away_goals": self.away_goals,
            "away_points": self.away_points,
        }


def http_get(url: str, timeout: int = 30) -> requests.Response:
    r = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "limerickgaahub-league-scraper/1.0"},
    )
    r.raise_for_status()
    return r


def get_page_html(page_url: str, wp_api_slug_url: str) -> str:
    """
    Prefer WP REST (stable, clean HTML in content.rendered). Fall back to direct fetch.
    """
    try:
        r = http_get(wp_api_slug_url)
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
      "Saturday 23" + "rd" + "August, 2025" -> "Saturday 23^{rd} August, 2025"
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
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    mm = month_map.get(month_name.lower())
    if not mm:
        return None

    return date(year, mm, day)


def parse_time_line(s: str) -> Optional[time]:
    m = TIME_RE.search(s)
    if not m:
        return None

    # Case 1: 12-hour format with am/pm
    if m.group(1) is not None:
        hh = int(m.group(1))
        mi = int(m.group(2))
        ap = m.group(3).lower()

        if not (1 <= hh <= 12 and 0 <= mi <= 59):
            return None

        if ap == "a":
            hh = 0 if hh == 12 else hh
        else:
            hh = 12 if hh == 12 else hh + 12

        return time(hh, mi)

    # Case 2: 24-hour format
    hh = int(m.group(4))
    mi = int(m.group(5))

    if not (0 <= hh <= 23 and 0 <= mi <= 59):
        return None

    return time(hh, mi)


def slugify_team(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def make_id(div: str, round_s: str, d_iso: str, home: str, away: str) -> str:
    return f"league-{div}-{round_s}-{d_iso}-{slugify_team(home)}-vs-{slugify_team(away)}"

def match_key(f: LeagueFixture) -> tuple[str, str, str, str, str]:
    return (
        f.group.strip().lower(),
        f.round.strip().upper(),
        f.date,
        slugify_team(f.home),
        slugify_team(f.away),
    )

def parse_division_heading(s: str) -> Optional[str]:
    m = DIV_RE.match(s.strip())
    if not m:
        return None

    div = m.group(1)
    if div not in ALLOWED_DIVISIONS:
        return None

    return div


def parse_result_side(s: str) -> tuple[Optional[str], Optional[int], Optional[int]]:
    s = s.strip()
    m = RESULT_TEAM_RE.match(s)
    if m:
        return m.group("team").strip(), int(m.group("g")), int(m.group("p"))
    return None, None, None


def is_plausible_team(s: str) -> bool:
    t = s.strip()
    if len(t) < 2:
        return False

    low = t.lower()
    bad = {
        "venue",
        "referee",
        "round",
        "fixtures",
        "results",
        "county hurling league",
        "walkover",
        "w/o",
        "bye",
    }
    if low in bad:
        return False

    if DIV_RE.match(t):
        return False
    if ROUND_RE.match(t):
        return False
    if VENUE_RE.match(t):
        return False
    if REF_RE.match(t):
        return False
    if TIME_RE.search(t):
        return False
    if DATE_RE.match(t):
        return False
    if V_RE.match(t):
        return False
    if SCORE_ONLY_RE.match(t):
        return False
    if WO_RE.match(t):
        return False
    if BYE_RE.match(t):
        return False

    return True

def parse_league(lines: List[str]) -> List[LeagueFixture]:
    fixtures: List[LeagueFixture] = []
    i = 0

    while i < len(lines):
        div = parse_division_heading(lines[i])
        if not div:
            i += 1
            continue

        div_no = int(div)
        group = f"Division {div_no}"
        competition = "County Hurling League"

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
                round_txt = f"R{rm.group(1)}"
                j += 1
                break
            if parse_division_heading(lines[j]):
                break
            j += 1

        # date
        while j < len(lines) and j < i + 35 and d is None:
            if parse_division_heading(lines[j]):
                break
            dd = parse_date_line(lines[j])
            if dd:
                d = dd
                j += 1
                break
            j += 1

        # teams: locate "V"
        while j < len(lines) and j < i + 55:
            if parse_division_heading(lines[j]):
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

        # time
        while j < len(lines) and j < i + 70 and t is None:
            if parse_division_heading(lines[j]):
                break
            tt = parse_time_line(lines[j])
            if tt:
                t = tt
                j += 1
                break
            j += 1

        # venue/referee
        while j < len(lines) and j < i + 90:
            if parse_division_heading(lines[j]):
                break

            vm = VENUE_RE.match(lines[j])
            if vm:
                v = (vm.group(1) or "").strip()
                if not v and j + 1 < len(lines) and not REF_RE.match(lines[j + 1]) and not parse_division_heading(lines[j + 1]):
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

        if round_txt and d and home and away:
            d_iso = d.strftime("%Y-%m-%d")
            time_local = t.strftime("%H:%M") if t else None
            dt_iso = f"{d_iso}T{time_local}:00" if time_local else None
            fid = make_id(str(div_no), round_txt, d_iso, home, away)

            if slugify_team(home) == slugify_team(away):
                i = max(i + 1, j)
                continue

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
                    source_url=FIXTURES_URL,
                    id=fid,
                )
            )

        i = max(i + 1, j)

    return fixtures


def parse_league_results(lines: List[str]) -> List[LeagueFixture]:
    fixtures: List[LeagueFixture] = []
    i = 0

    while i < len(lines):
        div = parse_division_heading(lines[i])
        if not div:
            i += 1
            continue

        div_no = int(div)
        group = f"Division {div_no}"
        competition = "County Hurling League"

        j = i + 1
        round_txt: Optional[str] = None
        d: Optional[date] = None
        home: Optional[str] = None
        away: Optional[str] = None
        t: Optional[time] = None
        venue: str = "TBC"
        referee: str = "TBC"
        home_goals: Optional[int] = None
        home_points: Optional[int] = None
        away_goals: Optional[int] = None
        away_points: Optional[int] = None
        status = "Result"

        while j < len(lines):
            if parse_division_heading(lines[j]):
                break

            rm = ROUND_RE.match(lines[j])
            if rm and round_txt is None:
                round_txt = f"R{rm.group(1)}"
                j += 1
                continue

            dd = parse_date_line(lines[j])
            if dd and d is None:
                d = dd
                j += 1
                continue

            team, g, p = parse_result_side(lines[j])
            if team and home is None and is_plausible_team(team):
                home = team
                home_goals = g
                home_points = p
                j += 1
                continue

            if V_RE.match(lines[j]):
                j += 1
                continue

            team, g, p = parse_result_side(lines[j])
            if team and away is None and is_plausible_team(team):
                away = team
                away_goals = g
                away_points = p
                j += 1
                continue

            sm = SCORE_ONLY_RE.match(lines[j].strip())
            if sm:
                g = int(sm.group(1))
                p = int(sm.group(2))
                if home is not None and home_goals is None:
                    home_goals = g
                    home_points = p
                    j += 1
                    continue
                if away is not None and away_goals is None:
                    away_goals = g
                    away_points = p
                    j += 1
                    continue

            if WO_RE.match(lines[j].strip()):
                if home is not None and away is not None and d is not None:
                    status = "Walkover"
                j += 1
                continue

            if BYE_RE.match(lines[j].strip()):
                j += 1
                continue

            vm = VENUE_RE.match(lines[j])
            if vm:
                v = (vm.group(1) or "").strip()
                if not v and j + 1 < len(lines):
                    nxt = lines[j + 1].strip()
                    if nxt and not REF_RE.match(nxt) and not parse_division_heading(nxt):
                        v = nxt
                        j += 1
                if v:
                    venue = v
                j += 1
                continue

            rf = REF_RE.match(lines[j])
            if rf:
                r = (rf.group(1) or "").strip()
                if r:
                    referee = r
                j += 1
                continue

            tt = parse_time_line(lines[j])
            if tt and t is None:
                t = tt
                j += 1
                continue

            if home is None and is_plausible_team(lines[j]):
                home = lines[j].strip()
                j += 1
                continue

            if away is None and is_plausible_team(lines[j]):
                away = lines[j].strip()
                j += 1
                continue

            j += 1

        if round_txt and d and home and away:
            d_iso = d.strftime("%Y-%m-%d")
            time_local = t.strftime("%H:%M") if t else None
            dt_iso = f"{d_iso}T{time_local}:00" if time_local else None
            fid = make_id(str(div_no), round_txt, d_iso, home, away)

            if slugify_team(home) == slugify_team(away):
                i = max(i + 1, j)
                continue

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
                    status=status,
                    source_url=RESULTS_URL,
                    id=fid,
                    home_goals=home_goals,
                    home_points=home_points,
                    away_goals=away_goals,
                    away_points=away_points,
                )
            )

        i = max(i + 1, j)

    return fixtures

def merge_fixtures_and_results(
    fixtures: List[LeagueFixture],
    results: List[LeagueFixture],
) -> List[LeagueFixture]:
    by_id: Dict[str, LeagueFixture] = {f.id: f for f in fixtures}
    by_key: Dict[tuple[str, str, str, str, str], LeagueFixture] = {
        match_key(f): f for f in fixtures
    }

    matched_id = 0
    matched_key = 0
    unmatched = 0

    for r in results:
        target = by_id.get(r.id)

        if target is not None:
            matched_id += 1
        else:
            target = by_key.get(match_key(r))
            if target is not None:
                matched_key += 1
            else:
                unmatched += 1
                print(f"[league] unmatched result skipped: {r.id}")
                continue

        target.status = r.status or target.status
        target.home_goals = r.home_goals
        target.home_points = r.home_points
        target.away_goals = r.away_goals
        target.away_points = r.away_points

        if (not target.time_local) and r.time_local:
            target.time_local = r.time_local
            target.datetime_iso = r.datetime_iso

        if (not target.venue or target.venue == "TBC") and r.venue:
            target.venue = r.venue

        if (not target.referee or target.referee == "TBC") and r.referee:
            target.referee = r.referee

    print(f"[league] results matched by id: {matched_id}")
    print(f"[league] results matched by key: {matched_key}")
    print(f"[league] results unmatched: {unmatched}")

    merged = list(by_id.values())
    merged.sort(key=lambda x: (x.date, x.group, x.round, x.home, x.away))
    return merged


def write_json(out_path: str, fixtures: List[LeagueFixture]) -> None:
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    payload = {
        "competition": "County Hurling League",
        "season": datetime.now().year,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "fixtures": [f.to_dict() for f in fixtures],
    }

    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def resolve_out_path(args_outdir: str, args_out: Optional[str]) -> str:
    # Precedence:
    # 1) explicit --out
    # 2) env var LGH_LEAGUE_OUT
    # 3) --outdir/league.json
    if args_out:
        return args_out

    env = os.environ.get("LGH_LEAGUE_OUT")
    if env:
        return env

    return os.path.join(args_outdir, "league.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data", help="Directory to write league.json into (default: data)")
    ap.add_argument("--out", default=None, help="Full output path. Overrides --outdir and LGH_LEAGUE_OUT.")
    args = ap.parse_args()

    out_path = resolve_out_path(args.outdir, args.out)

    fixtures_html = get_page_html(FIXTURES_URL, WP_API_FIXTURES)
    results_html = get_page_html(RESULTS_URL, WP_API_RESULTS)

    fixture_lines = normalize_lines(fixtures_html)
    result_lines = normalize_lines(results_html)

    fixtures = parse_league(fixture_lines)
    results = parse_league_results(result_lines)

    print(f"[league] fixture rows parsed: {len(fixtures)}")
    print(f"[league] raw result rows parsed: {len(results)}")

    today = date.today()
    results = [r for r in results if date.fromisoformat(r.date) <= today]

    print(f"[league] result rows after date filter: {len(results)}")

    merged = merge_fixtures_and_results(fixtures, results)
    merged = [f for f in merged if 1 <= int(f.group.split()[-1]) <= 12]

    write_json(out_path, merged)
    print(f"[league] wrote {len(merged)} merged fixtures/results -> {out_path}")


if __name__ == "__main__":
    main()
