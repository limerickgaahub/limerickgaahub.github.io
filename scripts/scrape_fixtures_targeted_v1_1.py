#!/usr/bin/env python3
import argparse, re, sys, json, hashlib, datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "hurling_2025.json"
HEADERS = {"User-Agent": "lgh-targeted-scraper/1.1 (+github actions)"}

# ---- regex helpers ----
DASH = r"[\-–—]"  # -, en, em
TEAM_INLINE_RX = re.compile(r"([A-Za-z’'./&\-\s]+?)\s+v(?:s\.?)?\s+([A-Za-z’'./&\-\s]+?)\b", re.I)
SCORE_RX = re.compile(rf"\b(\d+){DASH}(\d+)\b")
GROUP_RX = re.compile(r"\bGroup\s*([A-Z]|\d+)\b", re.I)
ROUND_RX = re.compile(r"\bRound\s*(\d+)\b", re.I)
VENUE_LINE_RX = re.compile(r"^\s*Venue:\s*(.+)$", re.I)
TIME_RX = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", re.I)
DATE_TXT_RX = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),\s*(20\d{2})\b")
DATE_NUM_RX = re.compile(r"\b(\d{1,2})[\/\-](\d{1,2})[\/\-](20\d{2})\b")

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], 1
)}

COMP_HINTS = [
    ("Senior Hurling Championship", re.compile(r"Senior Hurling Championship", re.I)),
    ("Premier Intermediate Hurling Championship", re.compile(r"Premier Intermediate Hurling Championship", re.I)),
    ("Intermediate Hurling Championship", re.compile(r"(?<!Premier )Intermediate Hurling Championship", re.I)),
    ("Junior A Hurling Championship", re.compile(r"Junior (?:A )?Hurling Championship", re.I)),
    ("Senior Hurling League", re.compile(r"Senior Hurling League", re.I)),
]
FOOTBALL_RX = re.compile(r"\bFootball\b", re.I)

def norm_space(s:str) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", (s or "")).strip()

def to_24h(hh, mm, ampm):
    hh = int(hh); mm = int(mm)
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hh != 12: hh += 12
        if ampm == "am" and hh == 12: hh = 0
    return f"{hh:02d}:{mm:02d}"

def parse_date(text):
    m = DATE_TXT_RX.search(text)
    if m:
        d, mon, y = m.groups()
        mon_i = MONTHS.get(mon.lower(), 0)
        if mon_i:
            return f"{int(y):04d}-{mon_i:02d}-{int(d):02d}"
    m = DATE_NUM_RX.search(text)
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return ""

def comp_from_url(url: str) -> str:
    u = url.lower()
    if "senior-hurling" in u: return "Senior Hurling Championship"
    if "intermediate-hurling" in u: return "Intermediate Hurling Championship"  # page also lists PIHC; headings will refine
    if "junior-hurling" in u: return "Junior A Hurling Championship"
    return ""

def parse_tables(soup, url):
    rows = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if not trs: 
            continue
        header = [norm_space(th.get_text(" ", strip=True)) for th in trs[0].find_all(["th","td"])]
        idx = {"date":-1,"time":-1,"home":-1,"away":-1,"venue":-1,"group":-1,"round":-1,"score":-1}
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
        for tr in trs[1:]:
            cells = [norm_space(td.get_text(" ", strip=True)) for td in tr.find_all(["td","th"])]
            if not any(cells): 
                continue
            combined = " ".join(cells)
            # derive fields
            home = cells[idx["home"]] if idx["home"]>=0 and idx["home"]<len(cells) else ""
            away = cells[idx["away"]] if idx["away"]>=0 and idx["away"]<len(cells) else ""
            if not (home and away):
                m = TEAM_INLINE_RX.search(combined)
                if m: home, away = norm_space(m.group(1)), norm_space(m.group(2))
            # date & time
            date = ""
            if idx["date"]>=0 and idx["date"]<len(cells):
                date = parse_date(cells[idx["date"]])
            if not date:
                date = parse_date(combined)
            time = ""
            if idx["time"]>=0 and idx["time"]<len(cells):
                mt = TIME_RX.search(cells[idx["time"]]); 
                if mt: time = to_24h(mt.group(1), mt.group(2), mt.group(3))
            if not time:
                mt = TIME_RX.search(combined)
                if mt: time = to_24h(mt.group(1), mt.group(2), mt.group(3))
            # venue
            venue = cells[idx["venue"]] if idx["venue"]>=0 and idx["venue"]<len(cells) else ""
            # group/round
            g = cells[idx["group"]] if idx["group"]>=0 and idx["group"]<len(cells) else ""
            r = cells[idx["round"]] if idx["round"]>=0 and idx["round"]<len(cells) else ""
            mg = GROUP_RX.search(g or combined); group = f"Group {mg.group(1).upper()}" if mg else ""
            mr = ROUND_RX.search(r or combined); round_ = f"Round {mr.group(1)}" if mr else ""
            # score / status
            status = "Fixture"
            home_goals = home_points = away_goals = away_points = None
            ms = SCORE_RX.findall(cells[idx["score"]]) if idx["score"]>=0 and idx["score"]<len(cells) else []
            if not ms:
                ms = SCORE_RX.findall(combined)
            if ms:
                status = "Result"
                if len(ms) >= 2:
                    (hg,hp),(ag,ap) = ms[0], ms[1]
                    home_goals, home_points, away_goals, away_points = map(int, (hg,hp,ag,ap))
            if not (home and away):
                continue
            rows.append({
                "date": date, "time": time, "home": home, "away": away,
                "venue": venue, "group": group, "round": round_,
                "status": status,
                "home_goals": home_goals, "home_points": home_points,
                "away_goals": away_goals, "away_points": away_points,
            })
    return rows

def parse_blocks(lines, url):
    """Parse free text where matches are in multi-line blocks with a 'V' separator."""
    rows = []
    comp_ctx = comp_from_url(url)
    group_ctx = ""
    round_ctx = ""
    i = 0
    N = len(lines)

    def is_v_line(s): return s.strip().lower() in {"v","vs","vs."}
    def grab_scores(s):
        ss = SCORE_RX.findall(s)
        if len(ss) >= 1:
            return tuple(map(int, ss[0]))
        return None

    while i < N:
        line = lines[i].strip()
        if not line:
            i += 1; continue

        # Update context from headings
        if FOOTBALL_RX.search(line):
            # Skip football blocks entirely on these pages
            i += 1; continue
        for comp_name, rx in COMP_HINTS:
            if rx.search(line):
                comp_ctx = comp_name
        mg = GROUP_RX.search(line)
        if mg: group_ctx = f"Group {mg.group(1).upper()}"
        mr = ROUND_RX.search(line)
        if mr: round_ctx = f"Round {mr.group(1)}"

        # Date/time/venue lines update ephemeral context for the next match block
        date_line = parse_date(line)
        time_line = ""
        mt = TIME_RX.search(line)
        if mt: time_line = to_24h(mt.group(1), mt.group(2), mt.group(3))
        venue_line = ""
        mv = VENUE_LINE_RX.search(line)
        if mv: venue_line = norm_space(mv.group(1))

        # Multi-line block: [home(+opt score)] / (opt score) / 'V' / [away(+opt score)]
        if is_v_line(line) and i >= 1 and i+1 < N:
            # backtrack to find the nearest non-empty above (home)
            hline = lines[i-1].strip()
            aline = lines[i+1].strip()
            # Sometimes scores are on the same line as team; sometimes on the next lines — grab from both
            home_name = norm_space(re.sub(SCORE_RX, "", hline)).strip()
            away_name = norm_space(re.sub(SCORE_RX, "", aline)).strip()
            # Scores
            hs = grab_scores(hline) or (grab_scores(lines[i-2]) if i-2>=0 else None)
            as_ = grab_scores(aline) or (grab_scores(lines[i+2]) if i+2<N else None)

            status = "Fixture"
            hg=hp=ag=ap=None
            if hs and as_:
                status = "Result"
                hg,hp = hs
                ag,ap = as_

            rows.append({
                "date": date_line, "time": time_line,
                "home": home_name, "away": away_name,
                "venue": venue_line, "group": group_ctx, "round": round_ctx,
                "status": status,
                "home_goals": hg, "home_points": hp,
                "away_goals": ag, "away_points": ap,
                "competition": comp_ctx,
            })
        else:
            # Single-line inline "A v B"
            m = TEAM_INLINE_RX.search(line)
            if m:
                home, away = norm_space(m.group(1)), norm_space(m.group(2))
                hs = SCORE_RX.search(line)
                status = "Result" if hs else status_from_url(url)
                hg=hp=ag=ap=None
                if hs:
                    # Need a pair; try to locate second score near
                    # often the line contains both scores like '1-18 to 1-17' (rare on these pages)
                    # we search in a small window
                    window = " ".join(lines[max(0,i-2):min(N,i+3)])
                    ss = SCORE_RX.findall(window)
                    if len(ss) >= 2:
                        (hg,hp),(ag,ap) = ss[0], ss[1]
                        hg,hp,ag,ap = map(int,(hg,hp,ag,ap))
                rows.append({
                    "date": date_line, "time": time_line,
                    "home": home, "away": away,
                    "venue": venue_line, "group": group_ctx, "round": round_ctx,
                    "status": status,
                    "home_goals": hg, "home_points": hp,
                    "away_goals": ag, "away_points": ap,
                    "competition": comp_ctx,
                })
        i += 1
    return rows

def status_from_url(url: str) -> str:
    return "Result" if "/results" in url.lower() else "Fixture"

def fetch(url: str, timeout=25):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text

def read_urls(path: Path):
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]

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
    import hashlib; return hashlib.sha1(base.encode("utf-8")).hexdigest()

def richness(x):
    r = 0
    if x.get("status")=="Result": r+=1
    if x.get("home_goals") is not None: r+=1
    if x.get("away_goals") is not None: r+=1
    if x.get("time"): r+=1
    if x.get("venue"): r+=1
    if x.get("group"): r+=1
    if x.get("round"): r+=1
    return r

def merge(existing, new):
    seen = { key_of(m): m for m in existing if m.get("home") and m.get("away") }
    for m in new:
        if not (m.get("home") and m.get("away")): 
            continue
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

    urls = read_urls(Path(args.urls))
    data = load_json(DATA_FILE)
    all_new = []

    for u in urls:
        try:
            html = fetch(u)
            soup = BeautifulSoup(html, "lxml")

            # 1) Parse tables
            tab_rows = parse_tables(soup, u)

            # 2) Parse multi-line blocks with context
            # Prefer content containers; else use body
            node = soup.select_one("article, .entry-content, main, #content, body")
            text = node.get_text("\n", strip=True) if node else soup.get_text("\n", strip=True)
            lines = [ln for ln in text.splitlines() if ln.strip()]
            blk_rows = parse_blocks(lines, u)

            found = tab_rows + blk_rows

            # Filter out any accidental football items
            found = [r for r in found if "Football" not in (r.get("competition") or "")]

            # Enrich competition for any rows missing it
            comp_u = comp_from_url(u)
            for r in found:
                if not r.get("competition"):
                    r["competition"] = comp_u
                r["source"] = u

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
