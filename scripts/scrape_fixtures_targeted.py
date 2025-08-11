#!/usr/bin/env python3
import argparse, re, sys, json, hashlib, datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "hurling_2025.json"
HEADERS = {"User-Agent": "lgh-targeted-scraper/1.0 (+github actions)"}

TEAM_RX = re.compile(r"([A-Za-z’'./&\-\s]+?)\s+v(?:s\.?)?\s+([A-Za-z’'./&\-\s]+?)\b", re.I)
DATE_RX  = re.compile(r"\b(\d{1,2})[\/\-](\d{1,2})[\/\-](20\d{2})\b")
TIME_RX  = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DASH = r"[\-–—]"
SCORE_RX = re.compile(rf"\b(\d+){DASH}(\d+)\s*(?:to|–|—|-)?\s*(\d+){DASH}(\d+)\b", re.I)
GROUP_RX = re.compile(r"\bGroup\s*([A-Z]|\d+)\b", re.I)
ROUND_RX = re.compile(r"\bRound\s*(\d+)\b", re.I)
VENUE_RX = re.compile(r"\b(?:at|@)\s+([A-Za-z0-9’'&\-/.,\s]+?)(?:\.|,|;|$)", re.I)

COMP_MAP = {
    "senior": "Senior Hurling Championship",
    "intermediate": "Intermediate Hurling Championship",
    "junior": "Junior A Hurling Championship",
}

def norm_space(s): 
    import re
    return re.sub(r"\s+", " ", (s or "")).strip()

def comp_from_url(url: str) -> str:
    u = url.lower()
    for key, full in COMP_MAP.items():
        if f"/{key}-hurling-" in u:
            return full
    return ""

def status_from_url(url: str) -> str:
    return "Result" if "/results" in url.lower() else "Fixture"

def read_urls(path: Path):
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]

def parse_table(table, url):
    def cols(tr): return [norm_space(td.get_text(" ", strip=True)) for td in tr.find_all(["td","th"])]
    rows, trs = [], table.find_all("tr")
    if not trs: return rows
    header, body = cols(trs[0]), trs[1:]
    idx = { "date": -1, "time": -1, "home": -1, "away": -1, "venue": -1, "group": -1, "round": -1, "score": -1 }
    for i, h in enumerate(header):
        hl = h.lower()
        if "date" in hl: idx["date"]=i
        elif "time" in hl: idx["time"]=i
        elif "home" in hl or "team 1" in hl or "team a" in hl: idx["home"]=i
        elif "away" in hl or "team 2" in hl or "team b" in hl: idx["away"]=i
        elif "venue" in hl or "ground" in hl: idx["venue"]=i
        elif "group" in hl: idx["group"]=i
        elif "round" in hl: idx["round"]=i
        elif "score" in hl or "result" in hl: idx["score"]=i
    for tr in body:
        c = cols(tr)
        if not any(c): continue
        home = c[idx["home"]] if idx["home"]>=0 and idx["home"]<len(c) else ""
        away = c[idx["away"]] if idx["away"]>=0 and idx["away"]<len(c) else ""
        combined = " ".join(c)
        if not home or not away:
            m = TEAM_RX.search(combined)
            if m: home, away = norm_space(m.group(1)), norm_space(m.group(2))
        date = c[idx["date"]] if idx["date"]>=0 and idx["date"]<len(c) else ""
        time = c[idx["time"]] if idx["time"]>=0 and idx["time"]<len(c) else ""
        venue = c[idx["venue"]] if idx["venue"]>=0 and idx["venue"]<len(c) else ""
        group = c[idx["group"]] if idx["group"]>=0 and idx["group"]<len(c) else ""
        round_ = c[idx["round"]] if idx["round"]>=0 and idx["round"]<len(c) else ""
        score = c[idx["score"]] if idx["score"]>=0 and idx["score"]<len(c) else ""
        import re as _re
        md = DATE_RX.search(date or combined); date_iso = ""
        if md: d, m, y = md.groups(); date_iso = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        mt = TIME_RX.search(time or combined); time_24 = ""
        if mt: hh, mm = mt.groups(); time_24 = f"{int(hh):02d}:{int(mm):02d}"
        mg = GROUP_RX.search(group or combined); group_out = ""
        if mg: group_out = f"Group {mg.group(1).upper()}"
        mr = ROUND_RX.search(round_ or combined); round_out = ""
        if mr: round_out = f"Round {mr.group(1)}"
        home_goals = home_points = away_goals = away_points = None
        status = status_from_url(url)
        ms = SCORE_RX.search(score or combined)
        if ms:
            status = "Result"
            home_goals, home_points, away_goals, away_points = map(int, ms.groups())
        if not (home and away): continue
        rows.append({
            "date": date_iso, "time": time_24,
            "home": home, "away": away,
            "venue": venue, "group": group_out, "round": round_out,
            "status": status,
            "home_goals": home_goals, "home_points": home_points,
            "away_goals": away_goals, "away_points": away_points,
        })
    return rows

def parse_paragraphs(soup, url):
    items = []
    blocks = soup.select("article, .entry-content, main, #content, body")
    text = ""
    for b in blocks:
        text = b.get_text("\n", strip=True)
        if text: break
    lines = [ln for ln in text.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        m = TEAM_RX.search(line)
        if not m: continue
        home, away = norm_space(m.group(1)), norm_space(m.group(2))
        window = " ".join(lines[max(0, i-3):i+4])
        md = DATE_RX.search(window); date_iso = ""
        if md: d, mo, y = md.groups(); date_iso = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        mt = TIME_RX.search(window); time_24 = ""
        if mt: hh, mm = mt.groups(); time_24 = f"{int(hh):02d}:{int(mm):02d}"
        mv = VENUE_RX.search(window); venue = norm_space(mv.group(1)) if mv else ""
        mg = GROUP_RX.search(window); group = f"Group {mg.group(1).upper()}" if mg else ""
        mr = ROUND_RX.search(window); round_ = f"Round {mr.group(1)}" if mr else ""
        status = status_from_url(url)
        ms = SCORE_RX.search(window)
        home_goals = home_points = away_goals = away_points = None
        if ms:
            status = "Result"
            home_goals, home_points, away_goals, away_points = map(int, ms.groups())
        items.append({
            "date": date_iso, "time": time_24, "home": home, "away": away,
            "venue": venue, "group": group, "round": round_,
            "status": status,
            "home_goals": home_goals, "home_points": home_points,
            "away_goals": away_goals, "away_points": away_points,
        })
    return items

def fetch(url, timeout=25):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text

def enrich_with_comp(et, url):
    comp = comp_from_url(url)
    for e in et:
        e["competition"] = comp
        e["source"] = url
    return et

def load_json(path: Path):
    if path.exists():
        try:
            j = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(j, dict) and "matches" in j: return j
            if isinstance(j, list): return {"updated":"", "season":2025, "matches": j}
        except Exception: pass
    return {"updated":"", "season":2025, "matches":[]}

def key_of(m):
    base = f"{m.get('competition')}|{m.get('group')}|{m.get('round')}|{m.get('date')}|{m.get('home')}|{m.get('away')}"
    import hashlib
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def richness(x):
    r=0
    if x.get("status")=="Result": r+=1
    if x.get("home_goals") is not None: r+=1
    if x.get("away_goals") is not None: r+=1
    if x.get("time"): r+=1
    if x.get("venue"): r+=1
    if x.get("group"): r+=1
    if x.get("round"): r+=1
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", type=str, required=True)
    args = ap.parse_args()
    url_file = Path(args.urls)
    urls = [ln.strip() for ln in url_file.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]

    data = load_json(DATA_FILE)
    all_new = []
    for u in urls:
        try:
            html = fetch(u)
            soup = BeautifulSoup(html, "lxml")
            found = []
            for table in soup.find_all("table"):
                found.extend(parse_table(table, u))
            if len(found) < 2:
                found.extend(parse_paragraphs(soup, u))
            found = enrich_with_comp(found, u)
            print(f"[ok] {u} -> {len(found)} rows")
            all_new.extend(found)
        except Exception as e:
            print(f"[warn] {u}: {e}", file=sys.stderr)

    merged = merge(data.get("matches", []), all_new)
    out = {
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": data.get("season", 2025),
        "matches": merged
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[write] {DATA_FILE} total={len(merged)}")

if __name__ == "__main__":
    main()
