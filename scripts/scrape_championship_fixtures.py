#!/usr/bin/env python3
"""
Scrape 2026 Limerick county hurling championship fixtures from:
  https://limerickgaa.ie/senior-hurling-fixtures/
  https://limerickgaa.ie/intermediate-hurling-fixtures/

Output:
  <outdir>/hurling_2026.json   (default: data/hurling_2026.json)

Schema:
- Matches the existing 2025 championship JSON shape used by the frontend.
- Uses top-level "updated" and "matches".
- Uses per-match fields already expected by the site.
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

# Example accepted:
# "Thursday 3^{rd} September, 2026"
DATE_RE = re.compile(
    rf"^{WEEKDAYS}\s+(\d{{1,2}})(?:\^\{{(st|nd|rd|th)\}})?\s+([A-Za-z]+),\s*(\d{{4}})\s*$",
    re.IGNORECASE
)


@dataclass
class ChampionshipMatch:
    competition: str
    group: Optional[str]
    round: str
    date: str
    time: str
    home: str
    away: str
    venue: str
    status: str
    home_goals: Optional[int]
    home_points: Optional[int]
    away_goals: Optional[int]
    away_points: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "competition": self.competition,
            "group": self.group,
            "round": self.round,
            "date": self.date,
            "time": self.time,
            "home": self.home,
            "away": self.away,
            "venue": self.venue,
            "status": self.status,
            "home_goals": self.home_goals,
            "home_points": self.home_points,
            "away_goals": self.away_goals,
            "away_points": self.away_points,
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
    Convert HTML to useful text lines.
    Also stitches split ordinals:
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
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    mm = month_map.get(month_name.lower())
    if not mm:
        return None

    return date(year, mm, day)


def is_plausible_team(s: str) -> bool:
    s = s.strip()
    if len(s) < 2:
        return False

    bad = {
        "venue",
        "referee",
        "round",
        "fixtures",
        "results",
        "senior hurling fixtures",
        "premier intermediate & intermediate hurling fixtures",
    }
    return s.lower() not in bad


def map_competition(raw: str) -> Optional[Dict[str, Optional[str]]]:
    if raw == "Whitebox County Senior Hurling Championship Group 1":
        return {
            "competition": "Senior Hurling Championship",
            "group": "Group 1",
        }
    if raw == "Whitebox County Senior Hurling Championship Group 2":
        return {
            "competition": "Senior Hurling Championship",
            "group": "Group 2",
        }
    if raw == "Lyons of Limerick County Premier Intermediate Hurling Championship":
        return {
            "competition": "Premier Intermediate Hurling Championship",
            "group": None,
        }
    if raw == "Nick Grene Sportsground County Intermediate Hurling Championship Group 1":
        return {
            "competition": "Intermediate Hurling Championship",
            "group": "Group 1",
        }
    if raw == "Nick Grene Sportsground County Intermediate Hurling Championship Group 2":
        return {
            "competition": "Intermediate Hurling Championship",
            "group": "Group 2",
        }
    return None


def dedupe_matches(matches: List[ChampionshipMatch]) -> List[ChampionshipMatch]:
    seen = set()
    out: List[ChampionshipMatch] = []

    for m in matches:
        key = (m.competition, m.group or "", m.round, m.date, m.home, m.away)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)

    out.sort(key=lambda x: (x.date, x.competition, x.group or "", x.round, x.home, x.away))
    return out


def parse_competition_blocks(lines: List[str]) -> List[ChampionshipMatch]:
    matches: List[ChampionshipMatch] = []
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
        group = mapped["group"]

        j = i + 1
        round_txt: Optional[str] = None
        d: Optional[date] = None
        home: Optional[str] = None
        away: Optional[str] = None
        venue: str = "TBC"

        # round
        while j < len(lines) and j < i + 20:
            if lines[j] in TARGET_COMPETITIONS:
                break
            rm = ROUND_RE.match(lines[j])
            if rm:
                round_txt = f"Round {rm.group(1)}"
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

        # teams
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
                venue = v if v else "TBC"

            # referee is deliberately ignored in output schema,
            # but still used as a useful marker for end of block
            rf = REF_RE.match(lines[j])
            if rf:
                j += 1
                break

            j += 1

        if round_txt and d and home and away:
            matches.append(
                ChampionshipMatch(
                    competition=competition,
                    group=group,
                    round=round_txt,
                    date=d.strftime("%Y-%m-%d"),
                    time="",
                    home=home,
                    away=away,
                    venue=venue,
                    status="Fixture",
                    home_goals=None,
                    home_points=None,
                    away_goals=None,
                    away_points=None,
                )
            )

        i = max(i + 1, j)

    return matches


def write_json(out_path: str, matches: List[ChampionshipMatch]) -> None:
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    payload = {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "matches": [m.to_dict() for m in matches],
    }

    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def resolve_out_path(args_outdir: str, args_out: Optional[str]) -> str:
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

    matches: List[ChampionshipMatch] = []
    matches.extend(parse_competition_blocks(senior_lines))
    matches.extend(parse_competition_blocks(intermediate_lines))
    matches = dedupe_matches(matches)

    write_json(out_path, matches)
    print(f"[championship] wrote {len(matches)} matches -> {out_path}")


if __name__ == "__main__":
    main()
