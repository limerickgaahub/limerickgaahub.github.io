#!/usr/bin/env python3
"""
Validate data/hurling_2025.json for coverage and schema sanity.
- Prints counts per competition & group
- Warns if a competition has no groups or no entries
- Checks that all Result entries have scores
"""
import json, sys
from pathlib import Path
from collections import defaultdict

DATA = Path(__file__).resolve().parents[1] / "data" / "hurling_2025.json"

def main():
    if not DATA.exists():
        print("Missing data/hurling_2025.json", file=sys.stderr)
        sys.exit(1)
    with open(DATA, "r", encoding="utf-8") as f:
        j = json.load(f)
    matches = j.get("matches", j if isinstance(j, list) else [])
    by_comp = defaultdict(list)
    for m in matches:
        by_comp[m.get("competition","")].append(m)
    print("=== Coverage by competition ===")
    for comp, rows in sorted(by_comp.items()):
        groups = sorted({r.get("group","") or "Unassigned" for r in rows})
        res = sum(1 for r in rows if r.get("status") == "Result")
        fx = sum(1 for r in rows if r.get("status") == "Fixture")
        print(f"- {comp or '(missing)'}: {len(rows)} (Results {res} / Fixtures {fx}), groups: {', '.join(groups)}")
        if "(missing)" in comp or not comp:
            print("  ! warning: missing competition name")
        if groups == ["Unassigned"]:
            print("  ! warning: all groups unassigned")
    # Score sanity
    bad_scores = [r for r in matches if r.get("status")=="Result" and (r.get("home_goals") is None or r.get("home_points") is None or r.get("away_goals") is None or r.get("away_points") is None)]
    if bad_scores:
        print(f"! {len(bad_scores)} result rows missing scores")
    else:
        print("✓ All result rows have scores (or no Results found)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
