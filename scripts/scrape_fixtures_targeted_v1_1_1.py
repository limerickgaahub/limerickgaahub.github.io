#!/usr/bin/env python3
import argparse, re, sys, json, hashlib, datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "hurling_2025.json"
HEADERS = {"User-Agent": "lgh-targeted-scraper/1.1.1 (+github actions)"}

# Regex + helpers
DASH = r"[\-–—]"
TEAM_INLINE_RX = re.compile(r"([A-Za-z’'./&\-\s]+?)\s+v(?:s\.?)?\s+([A-Za-z’'./&\-\s]+?)\b", re.I)
SCORE_RX = re.compile(rf"\b(\d+){DASH}(\d+)\b")
GROUP_RX = re.compile(r"\bGroup\s*([A-Z]|\d+)\b", re.I)
ROUND_RX = re.compile(r"\bRound\s*(\d+)\b", re.I)
VENUE_LINE_RX = re.compile(r"^\s*Venue:\s*(.+)$", re.I)
# time like "2pm" or "2 pm" or "2.00pm" or "14:30"
TIME_RX = re.compile(r"\b(\d{1,2})(?::|\.|)?(\d{2})?\s*(am|pm)?\b", re.I)
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
    return re.sub(r"\s+", " ", (s or "")).strip()

def to_24h(hh, mm, ampm):
    hh = int(hh); mm = int(mm) if mm else 0
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
    if "senior-hurling" in u and "league" not in u: return "Senior Hurling Championship"
    if "intermediate-hurling" in u and "league" not in u: return "Intermediate Hurling Championship"
    if "junior-hurling" in u and "league" not in u: return "Junior A Hurling Championship"
    return ""

def clean_venue_and_time(text, time_current):
    # If a "Venue:" line includes a time, split it out
    venue = text
    time = time_current
    mt = TIME_RX.search(text)
    if mt:
        time = to_24h(mt.group(1), mt.group(2), mt.group(3))
        venue = TIME_RX.sub("", text).strip(" ,;")
    return venue, time

# simple team canonicalizer for common quirks
def canonical_team(name, window_text=""):
    s = norm_space(name)
    s = s.replace("’","'")
    s = re.sub(r"\bSt\.?\b", "St", s)  # "St." -> "St"
    # If it's literally just "St", try to expand with local context
    if s.lower() == "st":
        if re.search(r"\bKierans\b", window_text, re.I):
            return "St Kierans"
    # Add other known canonicalizations here if needed
    return s

def sectionize(node):
    """Split content into sections by H2/H3 headings; return [(heading_text, text_lines)]."""
    sections = []
    current_head = ""
    current_lines = []
    for el in node.find_all(["h2","h3","p","li","div","span","table","strong"], recursive=True):
        tag = el.name.lower()
        if tag in ("h2","h3","strong"):
            # flush previous
            if current_lines:
                sections.append((current_head, current_lines))
            current_head = norm_space(el.get_text(" ", strip=True))
            current_lines = []
        elif tag == "table":
            # keep table marker as line to trigger table parsing separately
            current_lines.append(("__TABLE__", el))
        else:
            t = norm_space(el.get_text(" ", strip=True))
            if t:
                current_lines.append(t)
    if current_lines:
        sections.append((current_head, current_lines))
    return sections

def parse_tables_from_section(sec_lines, url):
    rows = []
    for item in sec_lines:
        if isinstance(item, tuple) and item[0] == "__TABLE__":
            table = item[1]
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
                if not any(cells): continue
                combined = " ".join(cells)
                home = cells[idx["home"]] if idx["home"]>=0 and idx["home"]<len(cells) else ""
                away = cells[idx["away"]] if idx["away"]>=0 and idx["away"]<len(cells) else ""
                if not (home and away):
                    m = TEAM_INLINE_RX.search(combined)
                    if m: home, away = norm_space(m.group(1)), norm_space(m.group(2))
                date = ""
                if idx["date"]>=0 and idx["date"]<len(cells):
                    date = parse_date(cells[idx["date"]]) or parse_date(combined)
                else:
                    date = parse_date(combined)
                time = ""
                if idx["time"]>=0 and idx["time"]<len(cells):
                    mt = TIME_RX.search(cells[idx["time"]]); 
                    if mt: time = to_24h(mt.group(1), mt.group(2), mt.group(3))
                if not time:
                    mt = TIME_RX.search(combined)
                    if mt: time = to_24h(mt.group(1), mt.group(2), mt.group(3))
                venue = cells[idx["venue"]] if idx["venue"]>=0 and idx["venue"]<len(cells) else ""
                if venue:
                    venue, time = clean_venue_and_time(venue, time)
                g = cells[idx["group"]] if idx["group"]>=0 and idx["group"]<len(cells) else ""
                r = cells[idx["round"]] if idx["round"]>=0 and idx["round"]<len(cells) else ""
                mg = GROUP_RX.search(g or combined); group = f"Group {mg.group(1).upper()}" if mg else ""
                mr = ROUND_RX.search(r or combined); round_ = f"Round {mr.group(1)}" if mr else ""
                status = "Fixture"
                home_goals = home_points = away_goals = away_points = None
                ms = SCORE_RX.findall(cells[idx["score"]]) if idx["score"]>=0 and idx["score"]<len(cells) else []
                if not ms: ms = SCORE_RX.findall(combined)
                if ms:
                    status = "Result"
                    if len(ms) >= 2:
                        (hg,hp),(ag,ap) = ms[0], ms[1]
                        home_goals, home_points, away_goals, away_points = map(int, (hg,hp,ag,ap))
                if not (home and away): continue
                rows.append({
                    "date": date, "time": time,
                    "home": home, "away": away,
                    "venue": venue, "group": group, "round": round_,
                    "status": status,
                    "home_goals": home_goals, "home_points": home_points,
                    "away_goals": away_goals, "away_points": away_points,
                })
    return rows

def parse_blocks_from_section(sec_lines, url, comp_ctx):
    rows = []
    group_ctx = ""
    round_ctx = ""
    time_ctx = ""
    date_ctx = ""
    venue_ctx = ""

    def is_v_line(s): return s.strip().lower() in {"v","vs","vs."}

    for i, item in enumerate(sec_lines):
        if isinstance(item, tuple):  # table marker
            continue
        line = item.strip()
        if not line: 
            continue
        if FOOTBALL_RX.search(line):  # skip football references on these pages
            continue

        # context
        mg = GROUP_RX.search(line)
        if mg: group_ctx = f"Group {mg.group(1).upper()}"
        mr = ROUND_RX.search(line)
        if mr: round_ctx = f"Round {mr.group(1)}"
        pd = parse_date(line)
        if pd: date_ctx = pd
        mt = TIME_RX.search(line)
        if mt: time_ctx = to_24h(mt.group(1), mt.group(2), mt.group(3))
        mv = VENUE_LINE_RX.search(line)
        if mv:
            venue_ctx, time_ctx = clean_venue_and_time(mv.group(1), time_ctx)

        # multi-line block: "A [score]" / 'V' / "B [score]"
        if is_v_line(line) and i>=1 and i+1<len(sec_lines):
            hline = sec_lines[i-1].strip()
            aline = sec_lines[i+1].strip()
            # score lines may be adjacent above/below
            window = " ".join(sec_lines[max(0,i-3):min(len(sec_lines),i+4)])
            # names
            home = canonical_team(re.sub(SCORE_RX, "", hline).strip(), window)
            away = canonical_team(re.sub(SCORE_RX, "", aline).strip(), window)
            # scores
            hs = SCORE_RX.search(hline) or SCORE_RX.search(sec_lines[i-2]) if i-2>=0 else None
            as_ = SCORE_RX.search(aline) or (SCORE_RX.search(sec_lines[i+2]) if i+2<len(sec_lines) else None)
            status = "Fixture"
            hg=hp=ag=ap=None
            if hs and as_:
                status = "Result"
                hg,hp = map(int, hs.groups())
                ag,ap = map(int, as_.groups())
            rows.append({
                "date": date_ctx, "time": time_ctx,
                "home": home, "away": away,
                "venue": venue_ctx, "group": group_ctx, "round": round_ctx,
                "status": status,
                "home_goals": hg, "home_points": hp,
                "away_goals": ag, "away_points": ap,
            })
        else:
            m = TEAM_INLINE_RX.search(line)
            if m:
                window = " ".join(sec_lines[max(0,i-2):min(len(sec_lines),i+3)])
                home = canonical_team(m.group(1), window)
                away = canonical_team(m.group(2), window)
                # scores possibly in-line or nearby
                allsc = [*SCORE_RX.findall(line), *SCORE_RX.findall(window)]
                status = "Result" if len(allsc) >= 2 else "Fixture"
                hg=hp=ag=ap=None
                if len(allsc) >= 2:
                    (hg,hp),(ag,ap) = allsc[0], allsc[1]
                    hg,hp,ag,ap = map(int, (hg,hp,ag,ap))
                rows.append({
                    "date": date_ctx, "time": time_ctx,
                    "home": home, "away": away,
                    "venue": venue_ctx, "group": group_ctx, "round": round_ctx,
                    "status": status,
                    "home_goals": hg, "home_points": hp,
                    "away_goals": ag, "away_points": ap,
                })
    # competition override rules
    if comp_ctx == "Premier Intermediate Hurling Championship":
        for r in rows: r["group"] = ""  # PIHC has no groups
    if comp_ctx.endswith("League"):
        rows = []  # drop leagues
    return rows

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

    url_file = Path(args.urls)
    urls = read_urls(url_file)

    data = load_json(DATA_FILE)
    all_new = []

    for u in urls:
        try:
            r = requests.get(u, headers=HEADERS, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            # Work inside the main content area
            node = soup.select_one("article, .entry-content, main, #content, body") or soup
            sections = sectionize(node)
            page_comp_hint = comp_from_url(u)

            for head, lines in sections:
                # derive competition from heading text or URL hint
                comp_ctx = ""
                for cname, rx in COMP_HINTS:
                    if rx.search(head):
                        comp_ctx = cname; break
                if not comp_ctx:
                    comp_ctx = page_comp_hint

                # skip leagues globally
                if comp_ctx.endswith("League"):
                    continue

                # tables in this section
                tab_rows = parse_tables_from_section(lines, u)
                for r2 in tab_rows:
                    r2["competition"] = comp_ctx
                    r2["source"] = u

                # text blocks in this section
                blk_rows = parse_blocks_from_section(lines, u, comp_ctx)
                for r3 in blk_rows:
                    r3["competition"] = comp_ctx or r3.get("competition") or page_comp_hint
                    r3["source"] = u

                all_new.extend(tab_rows+blk_rows)

            print(f"[ok] {u} -> {len(tab_rows)+len(blk_rows)} rows (sections={len(sections)})")
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
