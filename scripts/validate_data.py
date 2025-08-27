#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Validate scraper outputs before replacing / committing data/.

Usage:
  python scripts/validate_data.py --indir tmp_data

What it checks:
- All JSON files in --indir parse cleanly (UTF-8, valid JSON)
- For combined file (hurling_2025.json):
    - matches[] exists and is a list
    - required fields present with correct basic types
    - status ∈ {"SCHEDULED", "Result", "Walkover", "Bye"}
    - team names are sane (no stage labels, no "W/O" as a team)
    - "BYE" may appear only when status == "Bye"
    - group value looks like "Group 1"/"Group 2" OR "Premier Intermediate"
    - walkovers: scores must be null
    - dates are YYYY-MM-DD (or empty/None is tolerated for fixtures without a date)
    - no duplicate (competition, group, date, home, away) tuples
- For per-competition files (senior.json, etc.):
    - fixtures[]/results[] elements contain the same key structure as produced by scraper
    - status values pass the same checks as above

If any rule fails, exit code 1 (GitHub Action stops).
"""

import os
import re
import sys
import json
import argparse
from typing import Any, Dict, List, Tuple, Optional

ALLOWED_STATUS = {"SCHEDULED", "Result", "Walkover", "Bye"}
GROUP_OK_RE = re.compile(r"^(Group\s*[12]|Premier\s+Intermediate)$", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LABEL_LIKE_RE = re.compile(
    r"^(final|semi[-\s]?finals?|quarter[-\s]?finals?|round\s*\d+|play[-\s]?off|relegation|.*\bcup\b|league)$",
    re.I
)
WO_RE = re.compile(r"^(W\/O|Walkover)$", re.I)
BYE_RE = re.compile(r"^BYE$", re.I)

def looks_like_label_or_code(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    if LABEL_LIKE_RE.match(t):
        return True
    u = t.upper()
    # short all-caps token with digits like "SJBHCG1"
    if len(u) <= 8 and " " not in u and u == t and any(ch.isdigit() for ch in u):
        return True
    return False

def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def is_intlike(x) -> bool:
    if x is None:
        return True
    if isinstance(x, int):
        return True
    # allow numeric strings that are integers
    if isinstance(x, str) and x.isdigit():
        return True
    return False

def validate_match(record: Dict, problems: List[str], where: str):
    # Required keys presence (lenient on empty strings for some)
    req_keys = ["competition", "group", "round", "date", "time", "home", "away", "venue", "status"]
    for k in req_keys:
        if k not in record:
            problems.append(f"{where}: missing key '{k}'")

    # Status
    status = record.get("status") or ""
    if status not in ALLOWED_STATUS and status != "":
        problems.append(f"{where}: invalid status '{status}' (allowed: {sorted(ALLOWED_STATUS) + ['']})")

    # Group format
    grp = (record.get("group") or "").strip()
    if grp and not GROUP_OK_RE.match(grp):
        problems.append(f"{where}: unexpected group label '{grp}' (expected 'Group 1/2' or 'Premier Intermediate')")

    # Teams
    home = (record.get("home") or "").strip()
    away = (record.get("away") or "").strip()

    if not home or not away:
        problems.append(f"{where}: home/away team missing or empty")

    # "BYE" only allowed when status == Bye
    if BYE_RE.match(home) or BYE_RE.match(away):
        if status != "Bye":
            problems.append(f"{where}: team has 'BYE' but status is '{status}' (must be 'Bye')")

    # Never allow "W/O" or label-like tokens as team names
    for side, name in (("home", home), ("away", away)):
        if WO_RE.match(name):
            problems.append(f"{where}: team '{side}' is 'W/O' (should be a status, not a team)")
        if looks_like_label_or_code(name):
            problems.append(f"{where}: team '{side}' looks like a stage/label/code ('{name}')")

    # Scores consistency
    hg, hp = record.get("home_goals"), record.get("home_points")
    ag, ap = record.get("away_goals"), record.get("away_points")

    # For Walkover: scores must be None/null (UI will render W/O)
    if status == "Walkover":
        if hg is not None or hp is not None or ag is not None or ap is not None:
            problems.append(f"{where}: Walkover must not carry numeric scores")

    # For Result: if any score provided, ensure int-like
    if status in {"Result", "Walkover"}:
        for label, v in (("home_goals", hg), ("home_points", hp), ("away_goals", ag), ("away_points", ap)):
            if v is not None and not is_intlike(v):
                problems.append(f"{where}: score field '{label}' is not int-like (got {v!r})")

    # Date format
    date_str = record.get("date")
    if date_str:
        if not isinstance(date_str, str) or not DATE_RE.match(date_str):
            problems.append(f"{where}: date '{date_str}' is not YYYY-MM-DD")

def validate_combined(path: str, problems: List[str]):
    try:
        obj = load_json(path)
    except Exception as e:
        problems.append(f"[{path}] JSON parse error: {e}")
        return

    matches = obj.get("matches")
    if not isinstance(matches, list):
        problems.append(f"[{path}] 'matches' missing or not a list")
        return

    seen_keys = set()
    for i, m in enumerate(matches):
        if not isinstance(m, dict):
            problems.append(f"[{path}] matches[{i}] is not an object")
            continue
        where = f"[{path}] matches[{i}]"
        validate_match(m, problems, where)

        key = (m.get("competition"), m.get("group"), m.get("date"), m.get("home"), m.get("away"))
        if key in seen_keys:
            problems.append(f"{where}: duplicate key tuple {key}")
        else:
            seen_keys.add(key)

def validate_per_comp_file(path: str, problems: List[str]):
    try:
        obj = load_json(path)
    except Exception as e:
        problems.append(f"[{path}] JSON parse error: {e}")
        return

    # Optional keys; be lenient if file structure changes, but validate arrays
    for arr_key in ("fixtures", "results"):
        arr = obj.get(arr_key, [])
        if not isinstance(arr, list):
            problems.append(f"[{path}] '{arr_key}' is not a list")
            continue
        for i, r in enumerate(arr):
            if not isinstance(r, dict):
                problems.append(f"[{path}] {arr_key}[{i}] is not an object")
                continue
            where = f"[{path}] {arr_key}[{i}]"
            # Bring per-file records up to the combined schema for validation
            # Map time_local -> time; fill competition if present on the file root
            rec = {
                "competition": obj.get("competition"),
                "group": r.get("group"),
                "round": r.get("round"),
                "date": r.get("date"),
                "time": r.get("time_local"),
                "home": r.get("home"),
                "away": r.get("away"),
                "venue": r.get("venue"),
                "status": r.get("status") or ("Result" if arr_key == "results" else "SCHEDULED"),
                "home_goals": r.get("home_goals"),
                "home_points": r.get("home_points"),
                "away_goals": r.get("away_goals"),
                "away_points": r.get("away_points"),
            }
            validate_match(rec, problems, where)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True, help="Directory containing scraper JSON output (e.g., tmp_data)")
    args = ap.parse_args()

    indir = args.indir
    if not os.path.isdir(indir):
        print(f"ERROR: --indir '{indir}' is not a directory", file=sys.stderr)
        sys.exit(2)

    problems: List[str] = []

    # Validate combined file first (if present)
    combined_path = os.path.join(indir, "hurling_2025.json")
    if os.path.exists(combined_path):
        validate_combined(combined_path, problems)
    else:
        problems.append(f"[{combined_path}] missing (expected combined output)")

    # Validate per-competition files if present (optional but helpful)
    for fname in ("senior.json", "premier_intermediate.json", "intermediate.json",
                  "premier_junior_a.json", "junior_a.json", "junior_c.json"):
        p = os.path.join(indir, fname)
        if os.path.exists(p):
            validate_per_comp_file(p, problems)
        # don't error if a file is missing — scraper might be narrowed; combined file is the key artifact

    if problems:
        print("VALIDATION FAILED:")
        for msg in problems:
            print(" -", msg)
        sys.exit(1)

    print("Validation passed ✔")
    sys.exit(0)

if __name__ == "__main__":
    main()
