#!/usr/bin/env python3
"""
Scrape the 2026 Limerick county hurling championships from LimerickGAA.ie.

Fixture pages:
  https://limerickgaa.ie/senior-hurling-fixtures/
  https://limerickgaa.ie/intermediate-hurling-fixtures/
  https://limerickgaa.ie/junior-hurling-fixtures/

Result pages:
  https://limerickgaa.ie/senior-hurling-results/
  https://limerickgaa.ie/intermediate-hurling-results/
  https://limerickgaa.ie/junior-hurling-results/

Output:
  <outdir>/hurling_2026.json   (default: data/hurling_2026.json)

The output schema matches the championship JSON already used by the frontend:
  {"updated": "...", "matches": [...]}

Safety:
- Only explicitly listed county hurling championship headings are accepted.
- League, divisional and football competitions are ignored.
- The script refuses to write if an expected championship grade disappears.
- When data/hurling_2026.json exists, the new scrape is compared with it and a
  severe unexplained reduction causes the run to fail rather than overwrite it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SEASON = 2026
BASE = "https://limerickgaa.ie"
TZ = "Europe/Dublin"

PAGES: Tuple[Tuple[str, str, str], ...] = (
    ("senior fixtures", f"{BASE}/senior-hurling-fixtures/", "senior-hurling-fixtures"),
    ("senior results", f"{BASE}/senior-hurling-results/", "senior-hurling-results"),
    ("intermediate fixtures", f"{BASE}/intermediate-hurling-fixtures/", "intermediate-hurling-fixtures"),
    ("intermediate results", f"{BASE}/intermediate-hurling-results/", "intermediate-hurling-results"),
    ("junior fixtures", f"{BASE}/junior-hurling-fixtures/", "junior-hurling-fixtures"),
    ("junior results", f"{BASE}/junior-hurling-results/", "junior-hurling-results"),
)

EXPECTED_COMPETITIONS = {
    "Senior Hurling Championship",
    "Premier Intermediate Hurling Championship",
    "Intermediate Hurling Championship",
    "Premier Junior A Hurling Championship",
    "Junior A Hurling Championship",
    "Premier Junior B Hurling Championship",
    "Junior B Hurling Championship",
    "Premier Junior C Hurling Championship",
    "Junior C Hurling Championship",
}


def norm(value: str) -> str:
    """Normalise heading text while retaining punctuation significant to team names."""
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip().casefold()


# Exact headings currently used on LimerickGAA.ie, plus harmless aliases for the
# obvious inconsistent Junior B sponsor wording and omitted "Group 1" labels.
# The values are (frontend competition name, frontend group label).
_RAW_HEADING_ALIASES: Dict[str, Tuple[str, Optional[str]]] = {
    # Senior
    "Whitebox County Senior Hurling Championship Group 1":
        ("Senior Hurling Championship", "Group 1"),
    "Whitebox County Senior Hurling Championship Group 2":
        ("Senior Hurling Championship", "Group 2"),

    # Premier Intermediate / Intermediate
    "Lyons of Limerick County Premier Intermediate Hurling Championship":
        ("Premier Intermediate Hurling Championship", None),
    "Nick Grene Sportsground County Intermediate Hurling Championship Group 1":
        ("Intermediate Hurling Championship", "Group 1"),
    "Nick Grene Sportsground County Intermediate Hurling Championship Group 2":
        ("Intermediate Hurling Championship", "Group 2"),

    # Premier Junior A
    "Woodlands House Hotel County Premier Junior A Hurling Championship Group 1":
        ("Premier Junior A Hurling Championship", "Group 1"),
    "Woodlands House Hotel County Premier Junior A Hurling Championship Group 2":
        ("Premier Junior A Hurling Championship", "Group 2"),

    # Junior A. The live site omits "Group 1" from the Group 1 heading.
    "Woodlands House Hotel County Junior A Hurling Championship":
        ("Junior A Hurling Championship", "Group 1"),
    "Woodlands House Hotel County Junior A Hurling Championship Group 1":
        ("Junior A Hurling Championship", "Group 1"),
    "Woodlands House Hotel County Junior A Hurling Championship Group 2":
        ("Junior A Hurling Championship", "Group 2"),

    # Premier Junior B. The live Group 1 heading currently omits "Junior B".
    "Woodlands Hotel House County Premier Hurling Championship Group 1":
        ("Premier Junior B Hurling Championship", "Group 1"),
    "Woodlands Hotel House County Premier Junior B Hurling Championship Group 1":
        ("Premier Junior B Hurling Championship", "Group 1"),
    "Woodlands Hotel House County Premier Junior B Hurling Championship Group 2":
        ("Premier Junior B Hurling Championship", "Group 2"),
    "Woodlands House Hotel County Premier Hurling Championship Group 1":
        ("Premier Junior B Hurling Championship", "Group 1"),
    "Woodlands House Hotel County Premier Junior B Hurling Championship Group 1":
        ("Premier Junior B Hurling Championship", "Group 1"),
    "Woodlands House Hotel County Premier Junior B Hurling Championship Group 2":
        ("Premier Junior B Hurling Championship", "Group 2"),

    # Junior B
    "County Junior B Hurling Championship Group 1":
        ("Junior B Hurling Championship", "Group 1"),
    "County Junior B Hurling Championship Group 2":
        ("Junior B Hurling Championship", "Group 2"),

    # Premier Junior C
    "County Premier Junior C Hurling Championship Group 1":
        ("Premier Junior C Hurling Championship", "Group 1"),
    "County Premier Junior C Hurling Championship Group 2":
        ("Premier Junior C Hurling Championship", "Group 2"),

    # Junior C. The live site omits "Group 1" from the Group 1 heading.
    "County Junior C Hurling Championship":
        ("Junior C Hurling Championship", "Group 1"),
    "County Junior C Hurling Championship Group 1":
        ("Junior C Hurling Championship", "Group 1"),
    "County Junior C Hurling Championship Group 2":
        ("Junior C Hurling Championship", "Group 2"),
}
HEADING_ALIASES = {norm(k): v for k, v in _RAW_HEADING_ALIASES.items()}
TARGET_HEADINGS = set(HEADING_ALIASES)

ROUND_RE = re.compile(r"^Round\s*(\d+)\s*$", re.IGNORECASE)
STAGE_RE = re.compile(
    r"^(Final|Semi[ -]?Finals?|Quarter[ -]?Finals?|Relegation(?:[ -]?Final)?|Play[ -]?Off)\s*$",
    re.IGNORECASE,
)
V_RE = re.compile(r"^(?:V|VS)\.?$", re.IGNORECASE)
VENUE_RE = re.compile(r"^Venue\s*:\s*(.*)$", re.IGNORECASE)
REF_RE = re.compile(r"^Referee\s*:\s*(.*)$", re.IGNORECASE)
SCORE_ONLY_RE = re.compile(r"^(\d+)\s*[-–]\s*(\d+)$")
RESULT_TEAM_RE = re.compile(r"^(?P<team>.+?)\s+(?P<goals>\d+)\s*[-–]\s*(?P<points>\d+)$")
WO_RE = re.compile(r"^(?:W/O|Walkover)$", re.IGNORECASE)
BYE_RE = re.compile(r"^BYE$", re.IGNORECASE)

WEEKDAYS = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
ORD_TOKEN_RE = re.compile(r"^(?:\^\{\s*)?(st|nd|rd|th)(?:\s*\})?$", re.IGNORECASE)
DATE_RE = re.compile(
    rf"^(?:{WEEKDAYS}\s+)?(?P<day>\d{{1,2}})"
    r"(?:\^\{\s*(?:st|nd|rd|th)\s*\}|(?:st|nd|rd|th))?\s+"
    r"(?P<month>[A-Za-z]+),?\s+(?P<year>\d{4})$",
    re.IGNORECASE,
)
TIME_RE = re.compile(
    r"\b(?P<hour>\d{1,2})(?:[:.](?P<minute>\d{2}))\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?\b",
    re.IGNORECASE,
)

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LimerickGAAHub-Championship/2.0)"})
RETRY = Retry(
    total=4,
    connect=4,
    read=4,
    backoff_factor=1.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
)
SESSION.mount("https://", HTTPAdapter(max_retries=RETRY))
SESSION.mount("http://", HTTPAdapter(max_retries=RETRY))


@dataclass(frozen=True)
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
    home_goals: Optional[int] = None
    home_points: Optional[int] = None
    away_goals: Optional[int] = None
    away_points: Optional[int] = None

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


@dataclass(frozen=True)
class ParsedSide:
    team: Optional[str]
    goals: Optional[int]
    points: Optional[int]
    walkover: bool = False
    bye: bool = False


def clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def http_get(url: str, timeout: Tuple[int, int] = (15, 75)) -> requests.Response:
    response = SESSION.get(url, timeout=timeout)
    response.raise_for_status()
    return response


def get_page_html(page_url: str, slug: str) -> str:
    """Prefer the WordPress REST content; fall back to the public HTML page."""
    rest_url = f"{BASE}/wp-json/wp/v2/pages"
    try:
        print(f"[championship] fetching REST page: {slug}", flush=True)
        response = SESSION.get(
            rest_url,
            params={"slug": slug, "_fields": "content.rendered"},
            timeout=(15, 75),
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload:
            rendered = payload[0].get("content", {}).get("rendered", "")
            if isinstance(rendered, str) and rendered.strip():
                return rendered
        print(f"[championship] REST returned no rendered content for {slug}", flush=True)
    except Exception as exc:
        print(f"[championship] REST failed for {slug}: {exc}", flush=True)

    print(f"[championship] falling back to page HTML: {page_url}", flush=True)
    return http_get(page_url).text


def normalize_lines(html: str) -> List[str]:
    """Convert WordPress content/page HTML to ordered text lines."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    main = soup.select_one("main") or soup.select_one("article") or soup
    raw = [clean_line(line) for line in main.get_text("\n").splitlines()]
    raw = [line for line in raw if line]

    # WordPress often renders 30 + superscript "th" + July as three text lines.
    stitched: List[str] = []
    i = 0
    while i < len(raw):
        current = raw[i]
        if (
            i + 2 < len(raw)
            and re.match(rf"^(?:{WEEKDAYS})\s+\d{{1,2}}$", current, re.IGNORECASE)
            and ORD_TOKEN_RE.match(raw[i + 1])
            and re.match(r"^[A-Za-z]+,?\s+\d{4}$", raw[i + 2])
        ):
            ordinal = ORD_TOKEN_RE.match(raw[i + 1])
            assert ordinal is not None
            stitched.append(f"{current}^{{{ordinal.group(1)}}} {raw[i + 2]}")
            i += 3
            continue
        stitched.append(current)
        i += 1

    return stitched


def parse_date_line(value: str) -> Optional[date]:
    match = DATE_RE.match(clean_line(value))
    if not match:
        return None
    month = MONTHS.get(match.group("month").casefold())
    if not month:
        return None
    try:
        return date(int(match.group("year")), month, int(match.group("day")))
    except ValueError:
        return None


def parse_time_line(value: str) -> Optional[str]:
    value = clean_line(value)
    # Reject dates and scores before applying the deliberately compact time regex.
    if parse_date_line(value) or SCORE_ONLY_RE.match(value):
        return None
    match = TIME_RE.search(value)
    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    ampm = (match.group("ampm") or "").replace(".", "").casefold()
    if minute > 59:
        return None

    if ampm:
        if not 1 <= hour <= 12:
            return None
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    elif not 0 <= hour <= 23:
        return None

    return f"{hour:02d}:{minute:02d}"


def parse_round_or_stage(value: str) -> Optional[str]:
    value = clean_line(value)
    round_match = ROUND_RE.match(value)
    if round_match:
        return f"Round {round_match.group(1)}"
    stage_match = STAGE_RE.match(value)
    if stage_match:
        return clean_line(stage_match.group(1)).title().replace("Semi-Final", "Semi Final").replace("Quarter-Final", "Quarter Final")
    return None


def is_metadata(value: str) -> bool:
    return bool(
        VENUE_RE.match(value)
        or REF_RE.match(value)
        or parse_time_line(value)
        or parse_date_line(value)
        or parse_round_or_stage(value)
    )


def is_plausible_team(value: str) -> bool:
    value = clean_line(value)
    if len(value) < 2:
        return False
    if norm(value) in TARGET_HEADINGS:
        return False
    if V_RE.match(value) or SCORE_ONLY_RE.match(value) or WO_RE.match(value) or BYE_RE.match(value):
        return False
    if is_metadata(value):
        return False
    low = value.casefold()
    if any(word in low for word in ("fixtures", "results", "table")):
        return False
    if any(word in low for word in ("football", "county hurling league")):
        return False
    if "championship" in low:
        return False
    return True


def parse_side(lines: Sequence[str]) -> ParsedSide:
    team: Optional[str] = None
    goals: Optional[int] = None
    points: Optional[int] = None
    walkover = False
    bye = False

    for raw in lines:
        value = clean_line(raw)
        if not value:
            continue
        if WO_RE.match(value):
            walkover = True
            continue
        if BYE_RE.match(value):
            bye = True
            continue

        inline = RESULT_TEAM_RE.match(value)
        if inline:
            candidate = clean_line(inline.group("team"))
            if is_plausible_team(candidate):
                team = candidate
                goals = int(inline.group("goals"))
                points = int(inline.group("points"))
            continue

        score = SCORE_ONLY_RE.match(value)
        if score:
            goals = int(score.group(1))
            points = int(score.group(2))
            continue

        if is_plausible_team(value):
            team = value

    return ParsedSide(team=team, goals=goals, points=points, walkover=walkover, bye=bye)


def venue_from_block(block: Sequence[str]) -> str:
    for index, raw in enumerate(block):
        match = VENUE_RE.match(clean_line(raw))
        if not match:
            continue
        inline = clean_line(match.group(1) or "")
        if inline:
            return inline
        if index + 1 < len(block):
            candidate = clean_line(block[index + 1])
            if (
                candidate
                and not REF_RE.match(candidate)
                and norm(candidate) not in TARGET_HEADINGS
                and not parse_round_or_stage(candidate)
                and not parse_date_line(candidate)
                and not V_RE.match(candidate)
            ):
                return candidate
        return "TBC"
    return "TBC"


def parse_match_block(
    heading: str,
    block: Sequence[str],
    mode: str,
    page_name: str,
) -> Optional[ChampionshipMatch]:
    mapped = HEADING_ALIASES.get(norm(heading))
    if not mapped:
        return None
    competition, group = mapped

    round_text: Optional[str] = None
    match_date: Optional[date] = None
    date_index: Optional[int] = None
    divider_index: Optional[int] = None

    for index, raw in enumerate(block):
        value = clean_line(raw)
        if round_text is None:
            round_text = parse_round_or_stage(value)
        if match_date is None:
            parsed_date = parse_date_line(value)
            if parsed_date:
                match_date = parsed_date
                date_index = index
        if divider_index is None and V_RE.match(value):
            divider_index = index

    if not round_text or not match_date or match_date.year != SEASON or divider_index is None:
        return None

    left_start = (date_index + 1) if date_index is not None else 0
    left = parse_side(block[left_start:divider_index])

    right_end = len(block)
    for index in range(divider_index + 1, len(block)):
        value = clean_line(block[index])
        if parse_time_line(value) or VENUE_RE.match(value) or REF_RE.match(value):
            right_end = index
            break
    right = parse_side(block[divider_index + 1:right_end])

    if left.bye or right.bye:
        return None
    if not left.team or not right.team or norm(left.team) == norm(right.team):
        print(
            f"[championship] skipped malformed {page_name} block: "
            f"{competition} | {group} | {round_text} | home={left.team!r} away={right.team!r}",
            flush=True,
        )
        return None

    match_time = ""
    for raw in block[divider_index + 1:]:
        parsed_time = parse_time_line(raw)
        if parsed_time:
            match_time = parsed_time
            break

    status = "Fixture"
    home_goals = home_points = away_goals = away_points = None

    if mode == "results":
        full_score = None not in (left.goals, left.points, right.goals, right.points)
        all_zero = full_score and not any((left.goals, left.points, right.goals, right.points))
        if left.walkover or right.walkover:
            status = "Walkover"
        elif full_score and not all_zero and match_date <= date.today():
            status = "Result"
            home_goals, home_points = left.goals, left.points
            away_goals, away_points = right.goals, right.points
        else:
            # Results pages can contain future placeholders and incomplete rows. Do
            # not let those overwrite a good fixture row.
            return None

    return ChampionshipMatch(
        competition=competition,
        group=group,
        round=round_text,
        date=match_date.isoformat(),
        time=match_time,
        home=left.team,
        away=right.team,
        venue=venue_from_block(block),
        status=status,
        home_goals=home_goals,
        home_points=home_points,
        away_goals=away_goals,
        away_points=away_points,
    )


def parse_page(lines: Sequence[str], mode: str, page_name: str) -> List[ChampionshipMatch]:
    """Parse one record from each explicitly recognised competition heading block."""
    heading_indexes = [index for index, line in enumerate(lines) if norm(line) in TARGET_HEADINGS]
    matches: List[ChampionshipMatch] = []

    for position, start in enumerate(heading_indexes):
        end = heading_indexes[position + 1] if position + 1 < len(heading_indexes) else len(lines)
        heading = clean_line(lines[start])
        block = lines[start + 1:end]
        match = parse_match_block(heading, block, mode, page_name)
        if match:
            matches.append(match)

    print(f"[championship] {page_name}: {len(matches)} parsed", flush=True)
    return matches


def match_key(match: ChampionshipMatch) -> Tuple[str, str, str, str, str]:
    return (
        norm(match.competition),
        norm(match.group or ""),
        match.date,
        norm(match.home),
        norm(match.away),
    )


def completeness(match: ChampionshipMatch) -> int:
    score = 0
    if match.status == "Result":
        score += 100
    elif match.status == "Walkover":
        score += 80
    if match.time:
        score += 5
    if match.venue and match.venue != "TBC":
        score += 3
    if match.round:
        score += 1
    return score


def merge_pair(existing: ChampionshipMatch, incoming: ChampionshipMatch) -> ChampionshipMatch:
    """Merge duplicate fixture/result records, preferring result and populated metadata."""
    preferred, other = (incoming, existing) if completeness(incoming) >= completeness(existing) else (existing, incoming)
    return replace(
        preferred,
        round=preferred.round or other.round,
        time=preferred.time or other.time,
        venue=(
            preferred.venue
            if preferred.venue and preferred.venue != "TBC"
            else (other.venue or "TBC")
        ),
    )


def merge_matches(fixtures: Iterable[ChampionshipMatch], results: Iterable[ChampionshipMatch]) -> List[ChampionshipMatch]:
    merged: Dict[Tuple[str, str, str, str, str], ChampionshipMatch] = {}
    for match in list(fixtures) + list(results):
        key = match_key(match)
        if key in merged:
            merged[key] = merge_pair(merged[key], match)
        else:
            merged[key] = match

    out = list(merged.values())
    out.sort(key=lambda item: (item.date, item.time or "99:99", item.competition, item.group or "", item.home, item.away))
    return out


def competition_counts(matches: Iterable[ChampionshipMatch]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for match in matches:
        counts[match.competition] = counts.get(match.competition, 0) + 1
    return counts


def load_baseline(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        matches = payload.get("matches", [])
        return matches if isinstance(matches, list) else []
    except (OSError, ValueError, TypeError) as exc:
        print(f"[championship] baseline ignored ({path}): {exc}", flush=True)
        return []


def validate_scrape(
    fixtures: Sequence[ChampionshipMatch],
    merged: Sequence[ChampionshipMatch],
    baseline_path: Optional[str],
    guard_enabled: bool,
) -> None:
    if not fixtures:
        raise RuntimeError("No 2026 championship fixtures were parsed")

    fixture_counts = competition_counts(fixtures)
    missing = sorted(EXPECTED_COMPETITIONS - set(fixture_counts))
    if missing:
        raise RuntimeError(
            "Expected championship grades were not found: " + ", ".join(missing)
        )

    for match in merged:
        if not match.home or not match.away or norm(match.home) == norm(match.away):
            raise RuntimeError(f"Malformed match in output: {match}")
        if not match.date.startswith(f"{SEASON}-"):
            raise RuntimeError(f"Non-{SEASON} match in output: {match}")

    if not guard_enabled:
        return

    baseline = load_baseline(baseline_path)
    if not baseline:
        return

    old_total = len(baseline)
    new_total = len(merged)
    if old_total >= 20 and new_total < int(old_total * 0.60):
        raise RuntimeError(
            f"Safety check failed: scrape fell from {old_total} to {new_total} matches"
        )

    old_counts: Dict[str, int] = {}
    for row in baseline:
        comp = clean_line(row.get("competition", "")) if isinstance(row, dict) else ""
        if comp:
            old_counts[comp] = old_counts.get(comp, 0) + 1

    new_counts = competition_counts(merged)
    for comp, old_count in old_counts.items():
        new_count = new_counts.get(comp, 0)
        if old_count >= 6 and new_count < int(old_count * 0.50):
            raise RuntimeError(
                f"Safety check failed for {comp}: fell from {old_count} to {new_count} matches"
            )


def write_json(out_path: str, matches: Sequence[ChampionshipMatch]) -> None:
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "matches": [match.to_dict() for match in matches],
    }

    temp_path = f"{out_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp_path, out_path)


def resolve_out_path(outdir: str, out: Optional[str]) -> str:
    if out:
        return out
    env_path = os.environ.get("LGH_CHAMPIONSHIP_OUT")
    if env_path:
        return env_path
    return os.path.join(outdir, f"hurling_{SEASON}.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="data", help="Directory for hurling_2026.json")
    parser.add_argument("--out", default=None, help="Full output path; overrides --outdir")
    parser.add_argument(
        "--baseline",
        default=os.path.join("data", f"hurling_{SEASON}.json"),
        help="Existing JSON used for drop protection (default: data/hurling_2026.json)",
    )
    parser.add_argument(
        "--no-guard",
        action="store_true",
        help="Disable comparison with the existing JSON; structural validation still runs",
    )
    args = parser.parse_args()

    out_path = resolve_out_path(args.outdir, args.out)
    all_fixtures: List[ChampionshipMatch] = []
    all_results: List[ChampionshipMatch] = []

    for page_name, url, slug in PAGES:
        mode = "results" if page_name.endswith("results") else "fixtures"
        html = get_page_html(url, slug)
        lines = normalize_lines(html)
        print(f"[championship] {page_name}: {len(lines)} text lines", flush=True)
        parsed = parse_page(lines, mode, page_name)
        if mode == "fixtures":
            all_fixtures.extend(parsed)
        else:
            all_results.extend(parsed)

    # De-duplicate inside each source class before merging results over fixtures.
    fixtures = merge_matches(all_fixtures, [])
    results = merge_matches([], all_results)
    merged = merge_matches(fixtures, results)

    # One-off override: Garryspillane v Patrickswell, Round 3
    merged = [
        replace(
            match,
            status="Result",
            home_goals=2,
            home_points=18,
            away_goals=4,
            away_points=23,
        )
        if (
            match.competition == "Senior Hurling Championship"
            and match.date == "2026-08-28"
            and match.home == "Garryspillane"
            and match.away == "Patrickswell"
        )
        else match
        for match in merged
    ]

    print(f"[championship] fixture rows: {len(fixtures)}", flush=True)
    print(f"[championship] result rows: {len(results)}", flush=True)
    print(f"[championship] merged rows: {len(merged)}", flush=True)
    for competition, count in sorted(competition_counts(merged).items()):
        print(f"[championship]   {competition}: {count}", flush=True)

    try:
        validate_scrape(
            fixtures=fixtures,
            merged=merged,
            baseline_path=args.baseline,
            guard_enabled=not args.no_guard,
        )
    except RuntimeError as exc:
        print(f"[championship] ABORTED: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2) from exc

    write_json(out_path, merged)
    print(f"[championship] wrote {len(merged)} matches -> {out_path}", flush=True)


if __name__ == "__main__":
    main()

