#!/usr/bin/env python3
"""
Scrape Limerick divisional hurling championship fixtures/results.

Reads the existing senior/intermediate/junior hurling fixtures/results pages,
but only keeps selected divisional championship competitions.

Output:
  data/divisional_championship.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, date, time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup


TZ = "Europe/Dublin"

SENIOR_FIXTURES_URL = "https://limerickgaa.ie/senior-hurling-fixtures/"
SENIOR_RESULTS_URL = "https://limerickgaa.ie/senior-hurling-results/"

INTERMEDIATE_FIXTURES_URL = "https://limerickgaa.ie/intermediate-hurling-fixtures/"
INTERMEDIATE_RESULTS_URL = "https://limerickgaa.ie/intermediate-hurling-results/"

JUNIOR_FIXTURES_URL = "https://limerickgaa.ie/junior-hurling-fixtures/"
JUNIOR_RESULTS_URL = "https://limerickgaa.ie/junior-hurling-results/"


TARGET_COMPETITIONS = [
    # Senior
    {
        "name": "City Senior Hurling Championship",
        "division": "City",
        "grade": "Senior",
        "fixtures_url": SENIOR_FIXTURES_URL,
        "results_url": SENIOR_RESULTS_URL,
    },
    {
        "name": "South Senior Hurling Championship",
        "division": "South",
        "grade": "Senior",
        "fixtures_url": SENIOR_FIXTURES_URL,
        "results_url": SENIOR_RESULTS_URL,
    },
    {
        "name": "East Senior Hurling Championship",
        "division": "East",
        "grade": "Senior",
        "fixtures_url": SENIOR_FIXTURES_URL,
        "results_url": SENIOR_RESULTS_URL,
    },

    # Intermediate
    {
        "name": "City Intermediate Hurling Championship",
        "division": "City",
        "grade": "Intermediate",
        "fixtures_url": INTERMEDIATE_FIXTURES_URL,
        "results_url": INTERMEDIATE_RESULTS_URL,
    },
    {
        "name": "East Intermediate Hurling Championship",
        "division": "East",
        "grade": "Intermediate",
        "fixtures_url": INTERMEDIATE_FIXTURES_URL,
        "results_url": INTERMEDIATE_RESULTS_URL,
    },
    {
        "name": "South Intermediate Hurling Championship",
        "division": "South",
        "grade": "Intermediate",
        "fixtures_url": INTERMEDIATE_FIXTURES_URL,
        "results_url": INTERMEDIATE_RESULTS_URL,
    },
    {
        "name": "West Intermediate Hurling Championship",
        "division": "West",
        "grade": "Intermediate",
        "fixtures_url": INTERMEDIATE_FIXTURES_URL,
        "results_url": INTERMEDIATE_RESULTS_URL,
    },

    # Junior A
    {
        "name": "City Junior A Hurling Championship",
        "division": "City",
        "grade": "Junior A",
        "fixtures_url": JUNIOR_FIXTURES_URL,
        "results_url": JUNIOR_RESULTS_URL,
    },
    {
        "name": "East Junior A Hurling Championship",
        "division": "East",
        "grade": "Junior A",
        "fixtures_url": JUNIOR_FIXTURES_URL,
        "results_url": JUNIOR_RESULTS_URL,
    },
    {
        "name": "South Junior A Hurling Championship",
        "division": "South",
        "grade": "Junior A",
        "fixtures_url": JUNIOR_FIXTURES_URL,
        "results_url": JUNIOR_RESULTS_URL,
    },
    {
        "name": "West Junior A Hurling Championship",
        "division": "West",
        "grade": "Junior A",
        "fixtures_url": JUNIOR_FIXTURES_URL,
        "results_url": JUNIOR_RESULTS_URL,
    },

    # Junior B
    {
        "name": "City Junior B Hurling Championship",
        "division": "City",
        "grade": "Junior B",
        "fixtures_url": JUNIOR_FIXTURES_URL,
        "results_url": JUNIOR_RESULTS_URL,
    },
    {
        "name": "East Junior B Hurling Championship",
        "division": "East",
        "grade": "Junior B",
        "fixtures_url": JUNIOR_FIXTURES_URL,
        "results_url": JUNIOR_RESULTS_URL,
    },
    {
        "name": "South Junior B Hurling Championship",
        "division": "South",
        "grade": "Junior B",
        "fixtures_url": JUNIOR_FIXTURES_URL,
        "results_url": JUNIOR_RESULTS_URL,
    },
    {
        "name": "West Junior B Hurling Championship",
        "division": "West",
        "grade": "Junior B",
        "fixtures_url": JUNIOR_FIXTURES_URL,
        "results_url": JUNIOR_RESULTS_URL,
    },
]

COMP_BY_NAME = {c["name"].strip().lower(): c for c in TARGET_COMPETITIONS}


SESSION = requests.Session()
RETRY = Retry(
    total=4,
    connect=4,
    read=4,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
SESSION.mount("https://", HTTPAdapter(max_retries=RETRY))
SESSION.mount("http://", HTTPAdapter(max_retries=RETRY))


ROUND_RE = re.compile(r"^Round\s*(\d+)\s*$", re.IGNORECASE)
KNOCKOUT_ROUND_RE = re.compile(r"^(Quarter\s*Final|Semi\s*Final|Final)$", re.IGNORECASE)
V_RE = re.compile(r"^V\s*$", re.IGNORECASE)

TIME_RE = re.compile(
    r"\b(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?\b|\b(\d{1,2}):(\d{2})\b",
    re.IGNORECASE,
)

VENUE_RE = re.compile(r"^Venue:\s*(.*)\s*$", re.IGNORECASE)
REF_RE = re.compile(r"^Referee:\s*(.*)\s*$", re.IGNORECASE)

WEEKDAYS = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
ORD_TOKEN_RE = re.compile(r"^(st|nd|rd|th)$", re.IGNORECASE)

DATE_RE = re.compile(
    rf"^{WEEKDAYS}\s+(\d{{1,2}})(?:\^\{{(st|nd|rd|th)\}})?\s+([A-Za-z]+),\s*(\d{{4}})\s*$",
    re.IGNORECASE,
)

SCORE_ONLY_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
RESULT_TEAM_RE = re.compile(r"^(?P<team>.+?)\s+(?P<g>\d+)\s*-\s*(?P<p>\d+)\s*$")
WO_RE = re.compile(r"^(W\/O|Walkover)$", re.IGNORECASE)
BYE_RE = re.compile(r"^BYE$", re.IGNORECASE)


@dataclass
class DivisionalFixture:
    competition: str
    competition_key: str
    section: str
    subsection: str
    division: str
    grade: str
    group: str
    round: str
    date: str
    time_local: Optional[str]
    tz: str
    datetime_iso: Optional[str]
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
    walkover_winner: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "competition": self.competition,
            "competition_key": self.competition_key,
            "section": self.section,
            "subsection": self.subsection,
            "division": self.division,
            "grade": self.grade,
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
            "walkover_winner": self.walkover_winner,
        }


def http_get(url: str, timeout: tuple[int, int] = (20, 90)) -> requests.Response:
    r = SESSION.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "limerickgaahub-divisional-championship-scraper/1.0"},
    )
    r.raise_for_status()
    return r


def wp_api_url_from_page_url(page_url: str) -> str:
    slug = page_url.rstrip("/").split("/")[-1]
    return f"https://limerickgaa.ie/wp-json/wp/v2/pages?slug={slug}"


def get_page_html(page_url: str) -> str:
    """
    Prefer WP REST content.rendered. Fall back to direct page HTML.
    """
    wp_api_url = wp_api_url_from_page_url(page_url)

    try:
        r = http_get(wp_api_url)
        data = r.json()
        if isinstance(data, list) and data:
            rendered = data[0].get("content", {}).get("rendered")
            if rendered and isinstance(rendered, str):
                return rendered
        print(f"[divisional] WP API returned no usable rendered content: {wp_api_url}")
    except Exception as e:
        print(f"[divisional] WP API fetch failed: {wp_api_url} :: {e}")

    r = http_get(page_url)
    return r.text


def normalize_lines(html: str) -> List[str]:
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

    hh = int(m.group(4))
    mi = int(m.group(5))

    if not (0 <= hh <= 23 and 0 <= mi <= 59):
        return None

    return time(hh, mi)


def normalize_round(s: str) -> Optional[str]:
    s = re.sub(r"\s+", " ", s.strip())

    m = ROUND_RE.match(s)
    if m:
        return f"R{m.group(1)}"

    m = KNOCKOUT_ROUND_RE.match(s)
    if m:
        low = m.group(1).lower().replace("  ", " ")
        if low.startswith("quarter"):
            return "Quarter Final"
        if low.startswith("semi"):
            return "Semi Final"
        if low == "final":
            return "Final"

    return None


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def competition_key(cfg: Dict[str, str]) -> str:
    return slugify(cfg["name"])


def make_id(cfg: Dict[str, str], round_s: str, d_iso: str, home: str, away: str) -> str:
    return (
        f"championship-divisional-{competition_key(cfg)}-"
        f"{slugify(round_s)}-{d_iso}-{slugify(home)}-vs-{slugify(away)}"
    )


def parse_competition_heading(s: str) -> Optional[Dict[str, str]]:
    return COMP_BY_NAME.get(s.strip().lower())


def looks_like_any_competition_heading(s: str) -> bool:
    low = s.strip().lower()
    return (
        low in COMP_BY_NAME
        or "hurling championship" in low
        or "hurling league" in low
    )


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

    bad_exact = {
        "venue",
        "referee",
        "round",
        "fixtures",
        "results",
        "walkover",
        "w/o",
        "bye",
        "table",
        "×",
    }

    if low in bad_exact:
        return False

    if looks_like_any_competition_heading(t):
        return False
    if normalize_round(t):
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


def has_full_score(f: DivisionalFixture) -> bool:
    return (
        f.home_goals is not None
        and f.home_points is not None
        and f.away_goals is not None
        and f.away_points is not None
    )


def match_key(f: DivisionalFixture) -> tuple[str, str, str, str, str]:
    return (
        f.competition_key,
        f.round.strip().upper(),
        f.date,
        slugify(f.home),
        slugify(f.away),
    )


def row_priority(f: DivisionalFixture) -> int:
    if has_full_score(f):
        return 3
    if f.status == "Walkover":
        return 2
    return 1


def is_real_result_row(f: DivisionalFixture) -> bool:
    if not f.home or not f.away:
        return False
    if slugify(f.home) == slugify(f.away):
        return False
    if f.status == "Walkover":
        return True
    return has_full_score(f)


def parse_one_block(
    lines: List[str],
    start_idx: int,
    source_url: str,
    is_result_page: bool,
) -> tuple[Optional[DivisionalFixture], int]:
    cfg = parse_competition_heading(lines[start_idx])
    if not cfg:
        return None, start_idx + 1

    j = start_idx + 1

    round_txt: Optional[str] = None
    d: Optional[date] = None
    t: Optional[time] = None
    home: Optional[str] = None
    away: Optional[str] = None
    venue = "TBC"
    referee = "TBC"

    home_goals: Optional[int] = None
    home_points: Optional[int] = None
    away_goals: Optional[int] = None
    away_points: Optional[int] = None
    walkover_winner: Optional[str] = None

    status = "Result" if is_result_page else "SCHEDULED"

    # Conservative scan window. Enough for these blocks, avoids wandering into tables.
    max_j = min(len(lines), start_idx + 45)

    while j < max_j:
        line = lines[j].strip()

        # Stop if we accidentally hit another competition before finishing this one.
        if j > start_idx + 1 and looks_like_any_competition_heading(line):
            break

        r = normalize_round(line)
        if r and round_txt is None:
            round_txt = r
            j += 1
            continue

        dd = parse_date_line(line)
        if dd and d is None:
            d = dd
            j += 1
            continue

        tt = parse_time_line(line)
        if tt and t is None:
            t = tt
            j += 1
            continue

        vm = VENUE_RE.match(line)
        if vm:
            v = (vm.group(1) or "").strip()
            if not v and j + 1 < len(lines):
                nxt = lines[j + 1].strip()
                if nxt and not REF_RE.match(nxt) and not looks_like_any_competition_heading(nxt):
                    v = nxt
                    j += 1
            if v:
                venue = v
            j += 1
            continue

        rf = REF_RE.match(line)
        if rf:
            rtext = (rf.group(1) or "").strip()
            if rtext:
                referee = rtext
            j += 1
            break

        if V_RE.match(line):
            j += 1
            continue

        team, g, p = parse_result_side(line)
        if team and is_plausible_team(team):
            if home is None:
                home = team
                home_goals = g
                home_points = p
            elif away is None:
                away = team
                away_goals = g
                away_points = p
            j += 1
            continue

        sm = SCORE_ONLY_RE.match(line)
        if sm:
            g = int(sm.group(1))
            p = int(sm.group(2))
            if home is not None and home_goals is None:
                home_goals = g
                home_points = p
            elif away is not None and away_goals is None:
                away_goals = g
                away_points = p
            j += 1
            continue

        if WO_RE.match(line):
            status = "Walkover"
            if away is not None and away_goals is None and away_points is None:
                walkover_winner = "away"
            elif home is not None and home_goals is None and home_points is None:
                walkover_winner = "home"
            j += 1
            continue

        if BYE_RE.match(line):
            j += 1
            continue

        if is_plausible_team(line):
            if home is None:
                home = line
            elif away is None:
                away = line
            j += 1
            continue

        j += 1

    if not (d and home and away):
        print(f"[divisional] skipped incomplete block: {cfg['name']} around line {start_idx}")
        return None, max(start_idx + 1, j)

    if slugify(home) == slugify(away):
        print(f"[divisional] skipped same-team block: {cfg['name']} {home}")
        return None, max(start_idx + 1, j)

    d_iso = d.strftime("%Y-%m-%d")
    time_local = t.strftime("%H:%M") if t else None
    datetime_iso = f"{d_iso}T{time_local}:00" if time_local else None

    # Some divisional fixtures have no explicit round text.
    if not round_txt:
        round_txt = "Knockout"

    ck = competition_key(cfg)

    fixture = DivisionalFixture(
        competition=cfg["name"],
        competition_key=ck,
        section="Championship",
        subsection="Divisional",
        division=cfg["division"],
        grade=cfg["grade"],
        group=cfg["division"],
        round=round_txt,
        date=d_iso,
        time_local=time_local,
        tz=TZ,
        datetime_iso=datetime_iso,
        home=home,
        away=away,
        venue=venue,
        referee=referee,
        status=status,
        source_url=source_url,
        id=make_id(cfg, round_txt, d_iso, home, away),
        home_goals=home_goals,
        home_points=home_points,
        away_goals=away_goals,
        away_points=away_points,
        walkover_winner=walkover_winner,
    )

    return fixture, max(start_idx + 1, j)


def parse_page(
    lines: List[str],
    source_url: str,
    is_result_page: bool,
) -> List[DivisionalFixture]:
    fixtures: List[DivisionalFixture] = []
    i = 0

    while i < len(lines):
        if parse_competition_heading(lines[i]):
            fixture, next_i = parse_one_block(lines, i, source_url, is_result_page)
            if fixture:
                fixtures.append(fixture)
            i = max(i + 1, next_i)
        else:
            i += 1

    return fixtures


def merge_fixtures_and_results(
    fixtures: List[DivisionalFixture],
    results: List[DivisionalFixture],
) -> List[DivisionalFixture]:
    by_id: Dict[str, DivisionalFixture] = {f.id: f for f in fixtures}
    by_key: Dict[tuple[str, str, str, str, str], DivisionalFixture] = {
        match_key(f): f for f in fixtures
    }

    matched_id = 0
    matched_key = 0
    inserted = 0
    skipped = 0

    for r in results:
        target = by_id.get(r.id)

        if target is None:
            target = by_key.get(match_key(r))
            if target is not None:
                matched_key += 1
            elif is_real_result_row(r):
                by_id[r.id] = r
                inserted += 1
                continue
            else:
                skipped += 1
                print(f"[divisional] unmatched result skipped: {r.id}")
                continue
        else:
            matched_id += 1

        if has_full_score(r):
            target.status = "Result"
            target.home_goals = r.home_goals
            target.home_points = r.home_points
            target.away_goals = r.away_goals
            target.away_points = r.away_points
            target.walkover_winner = None

        elif r.status == "Walkover" and not has_full_score(target):
            target.status = "Walkover"
            target.walkover_winner = r.walkover_winner

        if (not target.time_local) and r.time_local:
            target.time_local = r.time_local
            target.datetime_iso = r.datetime_iso

        if (not target.venue or target.venue == "TBC") and r.venue:
            target.venue = r.venue

        if (not target.referee or target.referee == "TBC") and r.referee:
            target.referee = r.referee

    print(f"[divisional] results matched by id: {matched_id}")
    print(f"[divisional] results matched by key: {matched_key}")
    print(f"[divisional] results inserted directly: {inserted}")
    print(f"[divisional] unmatched/skipped: {skipped}")

    merged = list(by_id.values())

    deduped: Dict[tuple[str, str, str, str, str], DivisionalFixture] = {}
    for f in merged:
        k = match_key(f)
        existing = deduped.get(k)
        if existing is None or row_priority(f) > row_priority(existing):
            deduped[k] = f

    merged = list(deduped.values())
    merged.sort(key=lambda x: (x.date, x.grade, x.division, x.round, x.home, x.away))
    return merged


def unique_urls(key: str) -> List[str]:
    seen = set()
    urls: List[str] = []

    for cfg in TARGET_COMPETITIONS:
        url = cfg[key]
        if url not in seen:
            seen.add(url)
            urls.append(url)

    return urls


def write_json(out_path: str, fixtures: List[DivisionalFixture]) -> None:
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    payload = {
        "competition": "Divisional Hurling Championships",
        "section": "Championship",
        "subsection": "Divisional",
        "season": datetime.now().year,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "fixtures": [f.to_dict() for f in fixtures],
    }

    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def resolve_out_path(args_outdir: str, args_out: Optional[str]) -> str:
    if args_out:
        return args_out

    env = os.environ.get("LGH_DIVISIONAL_CHAMPIONSHIP_OUT")
    if env:
        return env

    return os.path.join(args_outdir, "divisional_championship.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--out", default=None)
    ap.add_argument(
        "--skip-results",
        action="store_true",
        help="Only scrape fixtures. Useful before results pages are populated.",
    )
    args = ap.parse_args()

    out_path = resolve_out_path(args.outdir, args.out)

    fixtures: List[DivisionalFixture] = []
    results: List[DivisionalFixture] = []

    for url in unique_urls("fixtures_url"):
        html = get_page_html(url)
        lines = normalize_lines(html)
        parsed = parse_page(lines, source_url=url, is_result_page=False)
        print(f"[divisional] fixtures parsed from {url}: {len(parsed)}")
        fixtures.extend(parsed)

    if not args.skip_results:
        for url in unique_urls("results_url"):
            try:
                html = get_page_html(url)
                lines = normalize_lines(html)
                parsed = parse_page(lines, source_url=url, is_result_page=True)
                print(f"[divisional] results parsed from {url}: {len(parsed)}")
                results.extend(parsed)
            except Exception as e:
                print(f"[divisional] result page skipped: {url} :: {e}")

    today = date.today()
    results = [
        r for r in results
        if date.fromisoformat(r.date) <= today or r.status == "Walkover"
    ]

    merged = merge_fixtures_and_results(fixtures, results)
    write_json(out_path, merged)

    print(f"[divisional] wrote {len(merged)} fixtures/results -> {out_path}")


if __name__ == "__main__":
    main()
