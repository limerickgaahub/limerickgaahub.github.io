#!/usr/bin/env python3
"""
Scrape fixtures/results from limerickgaa.ie and update /data/hurling_2025.json.
Heuristic parser; safe to run in GitHub Actions (has internet).

- Gathers posts/pages listed in URLS
- Extracts lines matching "Team A v Team B" with nearby date/time if present
- Merges into existing JSON (dedupe by competition+group+date+teams+round)
- Writes pretty JSON

You will want to extend URLS and refine selectors over time.
"""
import re, json, sys, hashlib, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "hurling_2025.json"

URLS = [
    # TODO: add the specific limerickgaa.ie fixture pages & posts for 2025 here.
    # Example stubs:
    "https://limerickgaa.ie/senior-hurling-fixtures/",
    "https://limerickgaa.ie/category/club-championship/",
]

COMP_MAP = {
    "Senior": "Senior Hurling Championship",
    "Premier Intermediate": "Premier Intermediate Hurling Championship",
    "Intermediate": "Intermediate Hurling Championship",
    "Premier Junior A": "Premier Junior A Hurling Championship",
    "Junior A": "Junior A Hurling Championship",
}

TEAM_RX = re.compile(r"([A-Za-z’'./\s]+)\s+v(?:s\.?)?\s+([A-Za-z’'./\s]+)", re.I)
DATE_RX = re.compile(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](20\d{2})")  # dd/mm/yyyy or d-m-yyyy
TIME_RX = re.compile(r"(\d{1,2}):(\d{2})")

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def guess_competition(text: str) -> str:
    for key, comp in COMP_MAP.items():
        if key.lower() in text.lower():
            return comp
    return ""

def extract_entries(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    entries = []
    for line in text.splitlines():
        m = TEAM_RX.search(line)
        if not m: continue
        home, away = norm_space(m.group(1)), norm_space(m.group(2))
        around = line
        date = time = ""
        mdate = DATE_RX.search(around)
        if mdate:
            d, mth, y = mdate.groups()
            date = f"{int(y):04d}-{int(mth):02d}-{int(d):02d}"
        mtime = TIME_RX.search(around)
        if mtime:
            hh, mm = mtime.groups()
            time = f"{int(hh):02d}:{int(mm):02d}"
        comp = guess_competition(around)
        entries.append({
            "competition": comp or "",
            "group": "",  # unknown here; can be enriched later
            "round": "",  # unknown here; can be enriched later
            "date": date, "time": time,
            "home": home, "away": away,
            "venue": "", "status": "Fixture",
        })
    return entries

def load_json(path: Path):
    if path.exists():
        return json.loads(path.read_text())
    return {"updated": "", "season": 2025, "matches": []}

def key_of(m):
    base = f"{m.get('competition')}|{m.get('group')}|{m.get('round')}|{m.get('date')}|{m.get('home')}|{m.get('away')}"
    return hashlib.sha1(base.encode()).hexdigest()

def merge(existing, new):
    seen = { key_of(m): m for m in existing }
    for m in new:
        k = key_of(m)
        if k not in seen:
            seen[k] = m
        else:
            # prefer entries with scores/venue/time
            def richness(x):
                r = 0
                if x.get("venue"): r+=1
                if x.get("time"): r+=1
                if x.get("home_goals") is not None: r+=1
                if x.get("away_goals") is not None: r+=1
                if x.get("status")=="Result": r+=1
                return r
            if richness(m) > richness(seen[k]):
                seen[k] = m
    return list(seen.values())

def main():
    data = load_json(DATA_FILE)
    all_new = []
    for url in URLS:
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            all_new.extend(extract_entries(resp.text, url))
        except Exception as e:
            print(f"warn: failed {url}: {e}", file=sys.stderr)
    merged = merge(data.get("matches", []), all_new)
    out = {"updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "season": data.get("season", 2025), "matches": merged}
    DATA_FILE.write_text(json.dumps(out, indent=2))
    print(f"Wrote {DATA_FILE} with {len(merged)} matches.")

if __name__ == "__main__":
    main()
