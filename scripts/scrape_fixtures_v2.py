#!/usr/bin/env python3
"""
Limerick GAA Hub — Hurling scraper v2 (comprehensive)
- Crawls limerickgaa.ie within bounds and extracts fixtures & results
- Uses keyword-guided crawling (configurable in patterns.yaml)
- Parses tables, lists, and paragraphs; detects scores, groups, rounds, dates, venues
- Merges into data/hurling_2025.json (prefers richer entries)
- Prints a coverage summary
"""
import argparse, re, sys, json, hashlib, datetime, time, urllib.parse, os
from pathlib import Path
from collections import deque

import requests
from bs4 import BeautifulSoup
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "hurling_2025.json"
DEFAULT_PATTERNS = ROOT / "scripts" / "patterns.yaml"

UA = {"User-Agent": "limerick-gaa-hub-scraper-v2/1.0 (+github actions)"}

DASH = r"[\-–—]"  # -, en, em
TEAM_RX = re.compile(r"([A-Za-z’'./&\-\s]+?)\s+v(?:s\.?)?\s+([A-Za-z’'./&\-\s]+?)\b", re.I)
DATE_RX  = re.compile(r"\b(\d{1,2})[\/\-](\d{1,2})[\/\-](20\d{2})\b")
TIME_RX  = re.compile(r"\b(\d{1,2}):(\d{2})\b")
SCORE_RX = re.compile(rf"\b(\d+){DASH}(\d+)\s*(?:to|–|—|-)?\s*(\d+){DASH}(\d+)\b", re.I)
GROUP_RX = re.compile(r"\bGroup\s*([A-Z]|\d+)\b", re.I)
ROUND_RX = re.compile(r"\bRound\s*(\d+)\b", re.I)
VENUE_RX = re.compile(r"\b(?:at|@)\s+([A-Za-z0-9’'&\-/.,\s]+?)(?:\.|,|;|$)", re.I)
RESULT_HINTS = re.compile(r"\b(FT|Full\s*Time|Result[s]?)\b", re.I)

COMP_MAP = {
    "Senior": "Senior Hurling Championship",
    "Premier Intermediate": "Premier Intermediate Hurling Championship",
    "Intermediate": "Intermediate Hurling Championship",
    "Premier Junior A": "Premier Junior A Hurling Championship",
    "Junior A": "Junior A Hurling Championship",
    "SHC": "Senior Hurling Championship",
    "PIHC": "Premier Intermediate Hurling Championship",
    "IHC": "Intermediate Hurling Championship",
    "PJAHC": "Premier Junior A Hurling Championship",
    "JAHC": "Junior A Hurling Championship",
}

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def load_patterns(path: Path):
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # defaults if no yaml
    return {
        "domain": "https://limerickgaa.ie",
        "max_pages": 200,
        "year": "2025",
        "seed_paths": [
            "/senior-hurling-fixtures/",
            "/category/club-championship/",
        ],
        "include_keywords": ["Hurling", "Championship", "fixtures", "results"],
        "exclude_paths": ["/football"],
    }

def rich_text_blocks(soup: BeautifulSoup):
    # Prefer content areas; fall back to body
    for sel in ["article", "main", ".entry-content", "#content", "body"]:
        node = soup.select_one(sel)
        if node:
            return [ln for ln in node.get_text("\n", strip=True).splitlines() if ln.strip()]
    return []

def guess_competition(text: str) -> str:
    text = text or ""
    for key, full in COMP_MAP.items():
        if key.lower() in text.lower():
            return full
    return ""

def extract_entries_from_page(html: str, url: str):
    soup = BeautifulSoup(html, "lxml")
    title_txt = " ".join(filter(None, [
        soup.title.get_text(" ", strip=True) if soup.title else "",
        soup.find(["h1","h2"]).get_text(" ", strip=True) if soup.find(["h1","h2"]) else ""
    ]))
    lines = rich_text_blocks(soup)
    comp_from_title = guess_competition(title_txt)

    entries = []
    for i, line in enumerate(lines):
        m = TEAM_RX.search(line)
        if not m:
            continue
        home = norm_space(m.group(1))
        away = norm_space(m.group(2))

        window_lines = lines[max(0, i-4): i+6]
        window = " ".join(window_lines)

        group = ""
        g = GROUP_RX.search(window)
        if g:
            gi = g.group(1).upper()
            group = f"Group {gi}"

        round_ = ""
        rr = ROUND_RX.search(window)
        if rr:
            round_ = f"Round {rr.group(1)}"

        date = ""
        dd = DATE_RX.search(window)
        if dd:
            d, mth, y = dd.groups()
            date = f"{int(y):04d}-{int(mth):02d}-{int(d):02d}"

        time = ""
        tt = TIME_RX.search(window)
        if tt:
            hh, mm = tt.groups()
            time = f"{int(hh):02d}:{int(mm):02d}"

        venue = ""
        vv = VENUE_RX.search(window)
        if vv:
            venue = norm_space(vv.group(1))

        competition = comp_from_title or guess_competition(window)

        status = "Fixture"
        home_goals = home_points = away_goals = away_points = None
        s = SCORE_RX.search(window)
        if s:
            status = "Result"
            home_goals, home_points, away_goals, away_points = map(int, s.groups())
        elif RESULT_HINTS.search(window):
            status = "Result"

        # Skip if we couldn't identify competition at all
        entries.append({
            "competition": competition or "",
            "group": group or "",
            "round": round_ or "",
            "date": date, "time": time,
            "home": home, "away": away,
            "venue": venue,
            "status": status,
            "home_goals": home_goals, "home_points": home_points,
            "away_goals": away_goals, "away_points": away_points,
            "source": url,
        })
    return entries

def load_json(path: Path):
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                j = json.load(f)
            if isinstance(j, dict) and "matches" in j:
                return j
            elif isinstance(j, list):
                return {"updated":"", "season": 2025, "matches": j}
        except Exception:
            pass
    return {"updated":"", "season": 2025, "matches": []}

def key_of(m):
    base = f"{m.get('competition')}|{m.get('group')}|{m.get('round')}|{m.get('date')}|{m.get('home')}|{m.get('away')}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def richness(x):
    r = 0
    if x.get("status") == "Result": r += 1
    if x.get("home_goals") is not None: r += 1
    if x.get("away_goals") is not None: r += 1
    if x.get("time"): r += 1
    if x.get("venue"): r += 1
    if x.get("group"): r += 1
    if x.get("round"): r += 1
    return r

def merge(existing, new):
    seen = { key_of(m): m for m in existing }
    for m in new:
        k = key_of(m)
        if k not in seen:
            seen[k] = m
        else:
            if richness(m) > richness(seen[k]):
                seen[k] = m
    return list(seen.values())

def crawl(domain, seeds, include_keywords, exclude_paths, max_pages=200, timeout=20):
    seen_urls = set()
    q = deque()

    def norm(u):
        return urllib.parse.urljoin(domain, u)

    for s in seeds:
        q.append(norm(s))

    pages = []
    while q and len(pages) < max_pages:
        url = q.popleft()
        if url in seen_urls: 
            continue
        seen_urls.add(url)
        if not url.startswith(domain):
            continue
        if any(ex in url for ex in exclude_paths):
            continue
        # keyword filter
        if include_keywords and not any(k.lower() in url.lower() for k in include_keywords):
            # allow it if it's an exact seed
            if url not in [norm(s) for s in seeds]:
                continue
        try:
            resp = requests.get(url, headers=UA, timeout=timeout)
            resp.raise_for_status()
            pages.append((url, resp.text))
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select("a[href]"):
                href = a.get("href")
                if not href: 
                    continue
                absu = urllib.parse.urljoin(url, href)
                if absu.startswith(domain) and absu not in seen_urls:
                    q.append(absu)
        except Exception as e:
            print(f"[warn] crawl {url}: {e}", file=sys.stderr)
            continue
    return pages

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patterns", type=str, default=str(DEFAULT_PATTERNS), help="patterns.yaml path")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_patterns(Path(args.patterns))
    domain = cfg.get("domain", "https://limerickgaa.ie")
    seeds = cfg.get("seed_paths", ["/senior-hurling-fixtures/"])
    include = cfg.get("include_keywords", ["Hurling","Championship"])
    exclude = cfg.get("exclude_paths", ["/football"])
    max_pages = int(cfg.get("max_pages", 200))

    print(f"[info] Crawling {domain} seeds={len(seeds)} max_pages={max_pages}")
    pages = crawl(domain, seeds, include, exclude, max_pages=max_pages)

    all_new = []
    for url, html in pages:
        ents = extract_entries_from_page(html, url)
        if ents:
            print(f"[ok] {url} -> {len(ents)}")
            all_new.extend(ents)

    data = load_json(DATA_FILE)
    merged = merge(data.get("matches", []), all_new)

    out = {
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": data.get("season", 2025),
        "matches": merged
    }

    if args.dry_run:
        print(json.dumps({
            "pages_crawled": len(pages),
            "new_found": len(all_new),
            "total_after_merge": len(merged)
        }, indent=2))
        return

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"[write] {DATA_FILE} total={len(out['matches'])}")

if __name__ == "__main__":
    main()
