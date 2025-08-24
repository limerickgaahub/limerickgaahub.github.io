// app_v7_3_2.js — Fixtures, Results, Tables
(function(){
  window.LGH_V7_3_READY = true;
  const DATA_URL = 'data/hurling_2025.json';
  const COMP_CODES = {
    "Senior Hurling Championship": "SHC",
    "Premier Intermediate Hurling Championship": "PIHC",
    "Intermediate Hurling Championship": "IHC",
    "Premier Junior A Hurling Championship": "PJAHC",
    "Junior A Hurling Championship": "JAHC",
  };
  const el=id=>document.getElementById(id), $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
  const pad2=n=>String(n).padStart(2,'0'); const day3=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const fmtDateShort=iso=>{ if(!iso) return ''; const d=new Date(iso+'T00:00:00'); return `${day3[d.getDay()]} ${pad2(d.getDate())}/${pad2(d.getMonth()+1)}`; };
  const fmtTimeShort=t=>{ if(!t) return ''; const m=t.match(/^(\d{1,2}):(\d{2})/); return m?`${pad2(m[1])}${m[2]}`:t; };
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const groupShort=g=> (g||'').replace(/^Group\s*/i,'G').trim();
  const compCode=name=> COMP_CODES[name] || (name? name.split(/\s+/).map(w=>w[0]).join('').toUpperCase() : '?');
  const toInt=v=>v==null||v===''?null:(Number(v)||0);
  const parseRoundNum=r=>{ const m=String(r||'').match(/(\d+)/); return m?Number(m[1]):999; };

  const RESULT_RE = /^(res|final)/i;
  const isResult = s => RESULT_RE.test(String(s||''));
  const isFixture = s => !isResult(s);

  let VIEW_MODE='competition';
  let MATCHES=[];

  const attachScores=m=>{
    m.home_goals = toInt(m.home_goals); m.home_points = toInt(m.home_points);
    m.away_goals = toInt(m.away_goals); m.away_points = toInt(m.away_points);
    m._homeMid = (m.home_goals!=null && m.home_points!=null) ? `${m.home_goals}-${m.home_points}` : '';
    m._awayMid = (m.away_goals!=null && m.away_points!=null) ? `${m.away_goals}-${m.away_points}` : '';
    m._rnum = parseRoundNum(m.round);
    return m;
  };

  async function load(){
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`, {cache:'no-cache'});
    const j = await res.json();
    MATCHES = (j.matches||j||[]).map(r=>{
      const out = {
        competition: r.competition || '', group: r.group || '', round: r.round || '',
        date: r.date || '', time: r.time || '', home: r.home || '', away: r.away || '',
        venue: r.venue || '', status: r.status || '',
        home_goals: r.home_goals, home_points: r.home_points, away_goals: r.away_goals, away_points: r.away_points,
      };
      out.code = compCode(out.competition);
      return attachScores(out);
    });
  }

  const sortRoundDate=(a,b)=> (a._rnum-b._rnum) || (a.date||'').localeCompare(b.date||'') || (a.time||'').localeCompare(b.time||'');
  const sortDateComp=(a,b)=> (a.date||'').localeCompare(b.date||'') || (a.time||'').localeCompare(b.time||'');

  function buildHead(thead,isMobile){ thead.innerHTML=isMobile
    ? `<tr><th>R</th><th>Date/Time</th><th>Match</th><th>Venue</th><th>S</th></tr>`
    : `<tr><th>Round</th><th>Date</th><th>Time</th><th>Comp</th><th>Match</th><th>Venue</th><th>Status</th></tr>`; }

  function rowHTML(r,isMobile){
    const scoreMid=(r._homeMid&&r._awayMid)?esc(r._homeMid+' - '+r._awayMid):'—';
    const meta = (VIEW_MODE!=='competition') ? `<div class="match-meta">${esc(r.code)} · ${esc(groupShort(r.group||''))}</div>` : '';
    const matchCell = `<div class="match-block"><span>${esc(r.home||'')}</span><span class="match-score">${scoreMid}</span><span>${esc(r.away||'')}</span>${meta}</div>`;
    const compBadge = `<span class="comp-code">${esc(r.code)}</span>`;
    return isMobile
      ? `<tr><td>${esc(r.round||'')}</td><td>${esc(r.date||'')}</td><td>${matchCell}</td><td>${esc(r.venue||'')}</td><td>${isResult(r.status)?'R':'F'}</td></tr>`
      : `<tr><td>${esc(r.round||'')}</td><td>${esc(r.date||'')}</td><td>${esc(r.time||'')}</td><td>${compBadge}</td><td>${matchCell}</td><td>${esc(r.venue||'')}</td><td>${esc(r.status||'')}</td></tr>`;
  }

  function renderGroupTable(){
    VIEW_MODE='competition';
    const tbl=el('g-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
    const isMobile=matchMedia('(max-width:880px)').matches; buildHead(thead,isMobile);
    const status=el('status').value;
    const rows = MATCHES.filter(r=>{
      if(state.comp && r.competition!==state.comp) return false;
      if(state.group && r.group!==state.group) return false;
      if(status==='Result')  return isResult(r.status);
      if(status==='Fixture') return isFixture(r.status);
      return true;
    }).sort(sortRoundDate);
    tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile)).join('');
  }

  function renderStandings(){
    const rows = MATCHES.filter(r=>r.competition===state.comp && r.group===state.group && isResult(r.status));
    const teams=new Map();
    for(const m of rows){
      const hs=(m.home_goals||0)*3+(m.home_points||0), as=(m.away_goals||0)*3+(m.away_points||0);
      if(!teams.has(m.home)) teams.set(m.home,{team:m.home,p:0,w:0,d:0,l:0,pf:0,pa:0,diff:0,pts:0});
      if(!teams.has(m.away)) teams.set(m.away,{team:m.away,p:0,w:0,d:0,l:0,pf:0,pa:0,diff:0,pts:0});
      const H=teams.get(m.home), A=teams.get(m.away);
      H.p++; A.p++; H.pf+=hs; H.pa+=as; A.pf+=as; A.pa+=hs;
      if(hs>as){ H.w++; H.pts+=2; A.l++; } else if(hs<as){ A.w++; A.pts+=2; H.l++; } else { H.d++; A.d++; H.pts++; A.pts++; }
    }
    for(const t of teams.values()) t.diff=t.pf-t.pa;
    const sorted=[...teams.values()].sort((a,b)=>
      b.pts-a.pts || b.diff-a.diff || b.pf-a.pf || a.team.localeCompare(b.team)
      // TODO: add Head-to-Head tiebreaker here if needed
    );
    const tbody=document.querySelector('#g-standings-table tbody');
    tbody.innerHTML = sorted.map(r=>`<tr><td>${esc(r.team)}</td><td class="right">${r.p}</td><td class="right">${r.w}</td><td class="right">${r.d}</td><td class="right">${r.l}</td><td class="right">${r.pf}</td><td class="right">${r.pa}</td><td class="right">${r.diff}</td><td class="right"><strong>${r.pts}</strong></td></tr>`).join('');
    el('modal-standings').innerHTML=tbody.innerHTML;
  }

  el('status').addEventListener('input', renderGroupTable);

  $$('.section-tabs .seg').forEach(seg=>seg.addEventListener('click', ()=>{
    seg.parentElement.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
    seg.classList.add('active');
    const showTable=seg.dataset.view==='table';
    el('g-standings').style.display=showTable?'':'none';
    document.querySelector('.matches-wrap').style.display=showTable?'none':'';
    if(showTable) renderStandings(); else renderGroupTable();
  }));

  $$('.navtab').forEach(tab=>tab.addEventListener('click', ()=>{
    $$('.navtab').forEach(t=>t.classList.remove('active'));
    tab.classList.add('active');
    const name=tab.dataset.nav;
    el('panel-hurling').style.display = name==='hurling'?'':'none';
    el('panel-football').style.display = name==='football'?'':'none';
    el('panel-about').style.display = name==='about'?'':'none';
  }));

  (async function(){ await load(); renderGroupTable(); })();
})();
