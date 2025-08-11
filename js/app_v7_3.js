(function(){
  // Signal early
  window.LGH_V7_3_READY = true;

  const DATA_URL = 'data/hurling_2025.json';

  // Known competition short codes
  const COMP_CODES = {
    "Senior Hurling Championship": "SHC",
    "Premier Intermediate Hurling Championship": "PIHC",
    "Intermediate Hurling Championship": "IHC",
    "Premier Junior A Hurling Championship": "PJAHC",
    "Junior A Hurling Championship": "JAHC",
  };

  // --- utils ---
  const el = id => document.getElementById(id);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));
  const pad2=n=>String(n).padStart(2,'0');
  const day3=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const fmtDateShort=iso=>{ if(!iso) return ''; const d=new Date(iso+'T00:00:00'); return `${day3[d.getDay()]} ${pad2(d.getDate())}/${pad2(d.getMonth()+1)}`; };
  const fmtTimeShort=t=>{ if(!t) return ''; const m=t.match(/^(\d{1,2}):(\d{2})/); return m?`${pad2(m[1])}${m[2]}`:t; };
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const groupShort=g=> (g||'').replace(/^Group\s*/i,'G').trim();
  const compCode=name=> COMP_CODES[name] || (name? name.split(/\s+/).map(w=>w[0]).join('').toUpperCase() : '?');
  const toInt = v => v==null || v==='' ? null : (Number(v)||0);

  // Score parsing: supports {home_goals,home_points,...} or "1-18" strings
  function attachScores(m){
    if(m.home_score && m.away_score && !('home_goals' in m)) {
      const a = parseScoreString(m.home_score), b = parseScoreString(m.away_score);
      if(a){ m.home_goals=a.g; m.home_points=a.p; }
      if(b){ m.away_goals=b.g; m.away_points=b.p; }
    }
    m.home_goals = toInt(m.home_goals); m.home_points = toInt(m.home_points);
    m.away_goals = toInt(m.away_goals); m.away_points = toInt(m.away_points);
    m._homeMid = (m.home_goals!=null && m.home_points!=null) ? `${m.home_goals}-${m.home_points}` : '';
    m._awayMid = (m.away_goals!=null && m.away_points!=null) ? `${m.away_goals}-${m.away_points}` : '';
    return m;
  }
  function parseScoreString(s){
    if(!s) return null;
    const m = String(s).match(/^\s*(\d+)\s*[-–—]\s*(\d+)\s*$/);
    return m ? {g:Number(m[1]), p:Number(m[2])} : null;
  }
  function totalPoints(g,p){ return (g==null||p==null) ? null : (Number(g)||0)*3 + (Number(p)||0); }

  // --- state ---
  let RAW=null, MATCHES=[];
  const state = { comp:null, group:null };

  // --- fetch & normalize ---
  async function fetchJSON(){
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`, {cache:'no-cache'});
    if(!res.ok) throw new Error(`Failed to fetch ${DATA_URL} (${res.status})`);
    const j = await res.json();
    return j;
  }
  function normalize(j){
    const matches = (j.matches || j || []); // support either {matches:[...]} or bare array
    const list = matches.map(r=>{
      const out = {
        competition: r.competition || r.comp || '',
        group: r.group || r.grp || '',
        round: r.round || r.rnd || '',
        date: r.date || r.match_date || '',
        time: r.time || r.match_time || '',
        home: r.home || r.home_team || '',
        away: r.away || r.away_team || '',
        venue: r.venue || '',
        status: r.status || r.result_status || '', // "Fixture" or "Result"
        home_goals: r.home_goals, home_points: r.home_points,
        away_goals: r.away_goals, away_points: r.away_points,
      };
      attachScores(out);
      out.code = compCode(out.competition);
      return out;
    });
    RAW = j;
    MATCHES = list;
    el('last-updated').textContent = j.updated ? `Updated: ${j.updated}` : '';
  }

  // --- menus ---
  function wireMenu(triggerId, menuId){
    const trig = el(triggerId), menu = el(menuId);
    function open(){ menu.classList.add('open'); trig.setAttribute('aria-expanded','true'); }
    function close(){ menu.classList.remove('open'); trig.setAttribute('aria-expanded','false'); }
    trig.addEventListener('click', (e)=>{ e.stopPropagation(); menu.classList.contains('open')?close():open(); });
    document.addEventListener('click', (e)=>{ if(!menu.contains(e.target) && !trig.contains(e.target)) close(); });
    document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') close(); });
    return {open, close, menu, trig};
  }
  const mComp = wireMenu('comp-trigger','comp-menu');
  const mGroup = wireMenu('group-trigger','group-menu');
  const mMore = wireMenu('more-trigger','more-menu');

  function buildMenus(){
    const comps = [...new Set(MATCHES.map(m=>m.competition).filter(Boolean))].sort();
    el('comp-menu').innerHTML = comps.map((c,i)=>`<div class="item ${i===0?'active':''}" data-comp="${esc(c)}">${esc(c)}</div>`).join('');
    function groupsFor(c){ return [...new Set(MATCHES.filter(m=>m.competition===c).map(m=>m.group||'Unassigned'))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true})); }
    function setComp(name){
      state.comp = name;
      el('comp-current').textContent = compCode(name);
      $$('#comp-menu .item').forEach(i=>i.classList.toggle('active', i.dataset.comp===name));
      const gs = groupsFor(name);
      el('group-menu').innerHTML = gs.map((g,i)=>`<div class="item ${i===0?'active':''}" data-group="${esc(g)}">${esc(g)}</div>`).join('');
      setGroup(gs[0]);
    }
    function setGroup(g){
      state.group = g;
      el('group-current').textContent = g;
      $$('#group-menu .item').forEach(i=>i.classList.toggle('active', i.dataset.group===g));
      renderPanelTitle(); renderGroupTable();
    }
    el('comp-menu').onclick = e=>{ const it=e.target.closest('.item'); if(!it) return; setComp(it.dataset.comp); mComp.close(); };
    el('group-menu').onclick = e=>{ const it=e.target.closest('.item'); if(!it) return; setGroup(it.dataset.group); mGroup.close(); };
    setComp(comps[0]); // init
  }

  function renderPanelTitle(){
    el('panel-title').textContent = `${compCode(state.comp)} — ${state.group}`;
  }

  // --- rendering helpers ---
  function buildThead(thead, isMobile, isTiny){
    if(isMobile){
      thead.innerHTML = isTiny
        ? `<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`
        : `<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`;
    } else {
      thead.innerHTML = `<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th class="ccol">Comp</th><th>Match</th><th>Venue</th><th>Status</th></tr>`;
    }
  }
  function rowHTML(r, isMobile, isTiny){
    const rShort=(r.round||'').replace(/^Round\s*/i,'R')||'—', dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||'');
    const stShort = (r.status||'').startsWith('R')?'R':'F';
    const scoreMid=(r._homeMid&&r._awayMid)?esc(r._homeMid+' — '+r._awayMid):'—';
    const compBadge = `<span class="comp-badge"><span class="comp-code">${esc(r.code)}</span><span class="group-code">${esc(groupShort(r.group))}</span></span>`;
    const matchCell = `<div class="match-block"><span class="match-team">${esc(r.home||'')}</span><span class="match-score">${scoreMid}</span><span class="match-team">${esc(r.away||'')}</span><div class="match-meta">${esc(r.code)} · ${esc(groupShort(r.group||''))}</div></div>`;
    if(isMobile){
      if(isTiny){
        const dt=`${dShort} ${tShort}`.trim();
        return `<tr><td class="rcol" style="text-align:center">${esc(rShort)}</td><td class="dcol">${esc(dt)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td><td class="stcol">${stShort}</td></tr>`;
      } else {
        return `<tr><td class="rcol" style="text-align:center">${esc(rShort)}</td><td class="dcol">${esc(dShort)}</td><td class="tcol">${esc(tShort)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td><td class="stcol">${stShort}</td></tr>`;
      }
    } else {
      return `<tr><td>${esc(r.round||'')}</td><td class="dcol">${esc(r.date||'')}</td><td class="tcol">${esc(r.time||'')}</td><td class="ccol">${compBadge}</td><td class="match">${matchCell}</td><td>${esc(r.venue||'')}</td><td><span class="status-badge status-${esc(r.status||'')}">${esc(r.status||'')}</span></td></tr>`;
    }
  }

  // --- group view ---
  function renderGroupTable(){
    const tbl = el('g-table'); const thead = tbl.tHead || tbl.createTHead(); const tbody = tbl.tBodies[0] || tbl.createTBody();
    const isMobile = matchMedia('(max-width:880px)').matches;
    const isTiny = matchMedia('(max-width:400px)').matches;
    buildThead(thead, isMobile, isTiny);
    const status = el('status').value;
    const rows = MATCHES.filter(r=>r.competition===state.comp && r.group===state.group && (!status || r.status===status))
      .sort((a,b)=> (a.date||'').localeCompare(b.date) || (a.time||'').localeCompare(b.time) );
    tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny)).join('');
  }

  // --- standings ---
  function renderStandings(){
    const rows = MATCHES.filter(r=>r.competition===state.comp && r.group===state.group && r.status==='Result');
    const teams = new Map();
    for(const m of rows){
      const hs=totalPoints(m.home_goals,m.home_points), as=totalPoints(m.away_goals,m.away_points);
      if(hs==null||as==null) continue;
      if(!teams.has(m.home)) teams.set(m.home,{team:m.home,p:0,w:0,d:0,l:0,pf:0,pa:0,diff:0,pts:0});
      if(!teams.has(m.away)) teams.set(m.away,{team:m.away,p:0,w:0,d:0,l:0,pf:0,pa:0,diff:0,pts:0});
      const H=teams.get(m.home), A=teams.get(m.away);
      H.p++; A.p++; H.pf+=hs; H.pa+=as; A.pf+=as; A.pa+=hs;
      if(hs>as){ H.w++; H.pts+=2; A.l++; } else if(hs<as){ A.w++; A.pts+=2; H.l++; } else { H.d++; A.d++; H.pts++; A.pts++; }
    }
    for(const t of teams.values()) t.diff=t.pf-t.pa;
    const sorted=[...teams.values()].sort((a,b)=> b.pts-a.pts || b.diff-a.diff || b.pf-a.pf || a.team.localeCompare(b.team));
    const tbody = document.querySelector('#g-standings-table tbody');
    tbody.innerHTML = sorted.map(r=>`<tr><td>${esc(r.team)}</td><td class="right">${r.p}</td><td class="right">${r.w}</td><td class="right">${r.d}</td><td class="right">${r.l}</td><td class="right">${r.pf}</td><td class="right">${r.pa}</td><td class="right">${r.diff}</td><td class="right"><strong>${r.pts}</strong></td></tr>`).join('');
  }

  // --- status filter ---
  el('status').addEventListener('input', renderGroupTable);

  // --- section tabs ---
  $$('.section-tabs .seg').forEach(seg=>{
    seg.addEventListener('click', ()=>{
      const row = seg.parentElement;
      row.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
      seg.classList.add('active');
      const showTable = seg.getAttribute('data-view')==='table';
      el('g-standings').style.display = showTable ? '' : 'none';
      document.querySelector('.matches-wrap').style.display = showTable ? 'none' : '';
      if(showTable) renderStandings();
    });
  });

  // --- more menu navigation ---
  el('more-menu').addEventListener('click', (e)=>{
    const it = e.target.closest('.item'); if(!it) return;
    $$('#panel-hurling .panel').forEach(p=> p.style.display='none');
    el(it.dataset.target).style.display='';
    mMore.close();
    if(it.dataset.target==='by-team'){ renderByTeam(); }
    if(it.dataset.target==='by-date'){ renderByDate(); }
  });

  // --- by team ---
  function renderByTeam(){
    const sel = el('team');
    const teams = [...new Set(MATCHES.flatMap(r=>[r.home, r.away]).filter(Boolean))].sort();
    sel.innerHTML = '<option value="">Select team…</option>' + teams.map(t=>`<option>${esc(t)}</option>`).join('');
    sel.oninput = draw;
    addEventListener('resize', draw);
    draw();
    function buildHead(thead, isMobile, isTiny){
      if(isMobile){
        thead.innerHTML = isTiny
          ? `<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`
          : `<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`;
      } else {
        thead.innerHTML = `<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th class="ccol">Comp</th><th>Match</th><th>Venue</th><th>Status</th></tr>`;
      }
    }
    function draw(){
      const team = sel.value||'';
      const tbl = el('team-table'); const thead = tbl.tHead || tbl.createTHead(); const tbody = tbl.tBodies[0] || tbl.createTBody();
      const isMobile = matchMedia('(max-width:880px)').matches;
      const isTiny = matchMedia('(max-width:400px)').matches;
      buildHead(thead, isMobile, isTiny);
      const rows = MATCHES.filter(r=>!team || r.home===team || r.away===team)
        .sort((a,b)=> (a.date||'').localeCompare(b.date) || (a.time||'').localeCompare(b.time) );
      tbody.innerHTML = rows.map(r=> rowHTML(r,isMobile,isTiny).replace('<td class="ccol">', `<td class="ccol">`)).join('');
    }
  }

  // --- by date ---
  function renderByDate(){
    const tbl = el('date-table'); const thead = tbl.tHead || tbl.createTHead(); const tbody = tbl.tBodies[0] || tbl.createTBody();
    const isMobile = matchMedia('(max-width:880px)').matches;
    const isTiny = matchMedia('(max-width:400px)').matches;
    buildThead(thead, isMobile, isTiny);
    const rows = [...MATCHES].sort((a,b)=> (a.date||'').localeCompare(b.date) || (a.time||'').localeCompare(b.time) );
    tbody.innerHTML = rows.map(r=> rowHTML(r,isMobile,isTiny)).join('');
  }

  // --- top tabs ---
  $$('.navtab').forEach(tab=>{
    tab.addEventListener('click', ()=>{
      $$('.navtab').forEach(t=>t.classList.remove('active'));
      tab.classList.add('active');
      const name = tab.dataset.nav;
      el('panel-hurling').style.display = name==='hurling'? '': 'none';
      el('panel-football').style.display = name==='football'? '': 'none';
      el('panel-about').style.display = name==='about'? '': 'none';
    });
  });

  // --- refresh ---
  el('refresh').addEventListener('click', async ()=>{
    try {
      await load();
      // Rebuild menus & current view
      buildMenus();
    } catch (e) {
      showError(e);
    }
  });

  function showError(e){
    const box = el('lgh-error');
    box.textContent = String(e);
    box.style.display = 'block';
  }

  // --- init ---
  async function load(){
    try {
      const raw = await fetchJSON();
      normalize(raw);
    } catch (e) {
      showError(e);
      throw e;
    }
  }
  (async function init(){
    await load();
    buildMenus();
  })();
})();