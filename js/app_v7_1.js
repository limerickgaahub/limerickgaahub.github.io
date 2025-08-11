(function(){
  const DATA_URL = 'data/hurling_2025.json';
  const COMP = {
    "Senior Hurling Championship": { code:"SHC" },
    "Premier Intermediate Hurling Championship": { code:"PIHC" },
    "Intermediate Hurling Championship": { code:"IHC" },
    "Premier Junior A Hurling Championship": { code:"PJAHC" },
    "Junior A Hurling Championship": { code:"JAHC" },
  };
  const pad2=n=>String(n).padStart(2,'0');
  const day3=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const fmtDateShort=iso=>{ if(!iso) return ''; const d=new Date(iso+'T00:00:00'); return `${day3[d.getDay()]} ${pad2(d.getDate())}/${pad2(d.getMonth()+1)}`; };
  const fmtTimeShort=t=>{ if(!t) return ''; const m=t.match(/^(\d{1,2}):(\d{2})/); return m?`${pad2(m[1])}${m[2]}`:t; };
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const score=(g,p)=> (g==null||p==null)?'':`${g}-${p}`;
  const totalPoints=(g,p)=> (g==null||p==null)?null:(Number(g)||0)*3 + (Number(p)||0);
  const groupShort=g=> (g||'').replace(/^Group\s*/i,'G');
  const mobileMeta=r=> `<div class="match-meta">${esc(r.code)} · ${esc(groupShort(r.group||''))}</div>`;

  let RAW = null; // loaded JSON
  let MATCHES = []; // normalized with codes
  const el = id => document.getElementById(id);

  async function fetchJSON(bust=true){
    const url = bust ? `${DATA_URL}?t=${Date.now()}` : DATA_URL;
    const res = await fetch(url, { cache:'no-cache' });
    if(!res.ok) throw new Error('Failed to fetch data');
    const j = await res.json();
    RAW = j;
    MATCHES = (j.matches||[]).map(r=>{
      const code = (COMP[r.competition]||{}).code || '?';
      return {...r, code, home_score:score(r.home_goals,r.home_points), away_score:score(r.away_goals,r.away_points)};
    });
    el('last-updated').textContent = `Updated: ${j.updated || '—'}`;
  }

  function buildMenus(){
    const comps = [...new Set(MATCHES.map(m=>m.competition))].filter(Boolean).sort();
    const compMenu = el('comp-menu');
    compMenu.innerHTML = comps.map((c,i)=>`<div class="item ${i===0?'active':''}" data-comp="${esc(c)}">${esc(c)}</div>`).join('');
    const groupsFor = comp => [...new Set(MATCHES.filter(m=>m.competition===comp).map(m=>m.group||'Unassigned'))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
    const groupMenu = el('group-menu');

    function setComp(name){
      state.comp = name;
      el('comp-current').textContent = (COMP[name]||{}).code || name;
      compMenu.querySelectorAll('.item').forEach(i=>i.classList.toggle('active', i.dataset.comp===name));
      const gs = groupsFor(name);
      groupMenu.innerHTML = gs.map((g,i)=>`<div class="item ${i===0?'active':''}" data-group="${esc(g)}">${esc(g)}</div>`).join('');
      const first = gs[0]; setGroup(first);
    }
    function setGroup(g){
      state.group = g;
      el('group-current').textContent = g;
      groupMenu.querySelectorAll('.item').forEach(i=>i.classList.toggle('active', i.dataset.group===g));
      renderPanelTitle(); renderGroupTable();
    }

    compMenu.onclick = e=>{ const it=e.target.closest('.item'); if(!it) return; setComp(it.dataset.comp); closeAllMenus(); };
    groupMenu.onclick = e=>{ const it=e.target.closest('.item'); if(!it) return; setGroup(it.dataset.group); closeAllMenus(); };

    // init to first comp
    setComp(comps[0]);
  }

  function openMenu(triggerId, menuId){
    const trig = el(triggerId), menu = el(menuId);
    function open(){ menu.classList.add('open'); trig.setAttribute('aria-expanded','true'); }
    function close(){ menu.classList.remove('open'); trig.setAttribute('aria-expanded','false'); }
    trig.addEventListener('click', (e)=>{ e.stopPropagation(); menu.classList.contains('open')?close():open(); });
    document.addEventListener('click', (e)=>{ if(!menu.contains(e.target) && !trig.contains(e.target)) close(); });
    document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') close(); });
    return { open, close, trig, menu };
  }
  const mComp = openMenu('comp-trigger','comp-menu');
  const mGroup = openMenu('group-trigger','group-menu');
  const mMore = openMenu('more-trigger','more-menu');
  function closeAllMenus(){ mComp.close(); mGroup.close(); mMore.close(); }

  const state = { comp:null, group:null };

  function renderPanelTitle(){
    const code = (COMP[state.comp]||{}).code || state.comp;
    el('panel-title').textContent = `${code} — ${state.group}`;
  }

  function renderGroupTable(){
    const tbl = el('g-table'); const thead=tbl.tHead || tbl.createTHead(); const tbody = tbl.tBodies[0] || tbl.createTBody();
    const isMobile = matchMedia('(max-width:880px)').matches;
    const isTiny = matchMedia('(max-width:400px)').matches;
    if(isMobile){
      thead.innerHTML = isTiny
        ? `<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`
        : `<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`;
    } else {
      thead.innerHTML = `<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th class="ccol">Comp</th><th>Match</th><th>Venue</th><th>Status</th></tr>`;
    }
    const status = el('status').value;
    const rows = MATCHES.filter(r=>r.competition===state.comp && r.group===state.group && (!status || r.status===status))
      .sort((a,b)=> (a.date||'').localeCompare(b.date) || (a.time||'').localeCompare(b.time) );
    tbody.innerHTML = rows.map(r=>{
      const rShort=(r.round||'').replace(/^Round\s*/i,'R')||'—', dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||'');
      const stShort = (r.status||'').startsWith('R')?'R':'F';
      const scoreMid=(r.home_score&&r.away_score)?esc(r.home_score+' — '+r.away_score):'—';
      const compBadge = `<span class="comp-badge"><span class="comp-code">${esc(r.code)}</span><span class="group-code">${esc(groupShort(r.group))}</span></span>`;
      const matchCell = `<div class="match-block"><span>${esc(r.home||'')}</span><span class="match-score">${scoreMid}</span><span>${esc(r.away||'')}</span>${mobileMeta(r)}</div>`;
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
    }).join('');
  }

  function renderStandings(){
    const rows = MATCHES.filter(r=>r.competition===state.comp && r.group===state.group && r.status==='Result');
    const teams = new Map();
    const tp=(g,p)=> (g==null||p==null)?null:(Number(g)||0)*3 + (Number(p)||0);
    for(const m of rows){
      const hs=tp(m.home_goals,m.home_points), as=tp(m.away_goals,m.away_points);
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

  // Pills toggle
  document.querySelectorAll('.section-tabs .seg').forEach(seg=>{
    seg.addEventListener('click', ()=>{
      const row = seg.parentElement;
      row.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
      seg.classList.add('active');
      const showTable = seg.getAttribute('data-view')==='table';
      document.getElementById('g-standings').style.display = showTable ? '' : 'none';
      document.querySelector('.matches-wrap').style.display = showTable ? 'none' : '';
      if(showTable) renderStandings();
    });
  });

  // More menu navigation
  el('more-menu').addEventListener('click', (e)=>{
    const it = e.target.closest('.item'); if(!it) return;
    document.querySelectorAll('.grid .panel').forEach(p=>p.style.display='none');
    el(it.dataset.target).style.display='';
    closeAllMenus();
    if(it.dataset.target==='by-team'){ renderByTeam(); }
    if(it.dataset.target==='by-date'){ renderByDate(); }
  });

  // Status filter
  el('status').addEventListener('input', renderGroupTable);

  // Refresh button re-fetches JSON and re-renders current view
  el('refresh').addEventListener('click', async ()=>{
    el('refresh').disabled = true;
    await fetchJSON(true);
    buildMenus(); // rebuild menus in case new comps/groups were added
    el('refresh').disabled = false;
  });

  function renderByTeam(){
    const sel = el('team');
    const teams = [...new Set(MATCHES.flatMap(r=>[r.home, r.away]).filter(Boolean))].sort();
    sel.innerHTML = '<option value="">Select team…</option>' + teams.map(t=>`<option>${esc(t)}</option>`).join('');
    sel.oninput = () => draw();
    addEventListener('resize', draw);
    draw();
    function draw(){
      const team=sel.value||'';
      const tbl = el('team-table'); const thead=tbl.tHead || tbl.createTHead(); const tbody = tbl.tBodies[0] || tbl.createTBody();
      const isMobile = matchMedia('(max-width:880px)').matches;
      const isTiny = matchMedia('(max-width:400px)').matches;
      if(isMobile){
        thead.innerHTML = isTiny
          ? `<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`
          : `<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`;
      } else {
        thead.innerHTML = `<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th class="ccol">Comp</th><th>Match</th><th>Venue</th><th>Status</th></tr>`;
      }
      const rows = MATCHES.filter(r=>!team || r.home===team || r.away===team)
        .sort((a,b)=> (a.date||'').localeCompare(b.date) || (a.time||'').localeCompare(b.time) );
      tbody.innerHTML = rows.map(r=>{
        const rShort=(r.round||'').replace(/^Round\s*/i,'R')||'—', dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||'');
        const stShort = (r.status||'').startsWith('R')?'R':'F';
        const scoreMid=(r.home_score&&r.away_score)?esc(r.home_score+' — '+r.away_score):'—';
        const compBadge = `<span class="comp-badge"><span class="comp-code">${esc(r.code)}</span><span class="group-code">${esc(groupShort(r.group))}</span></span>`;
        const matchCell = `<div class="match-block"><span>${esc(r.home||'')}</span><span class="match-score">${scoreMid}</span><span>${esc(r.away||'')}</span>${mobileMeta(r)}</div>`;
        if(isMobile){
          if(isTiny){
            const dt = `${dShort} ${tShort}`.trim();
            return `<tr><td class="rcol" style="text-align:center">${esc(rShort)}</td><td class="dcol">${esc(dt)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td><td class="stcol">${stShort}</td></tr>`;
          } else {
            return `<tr><td class="rcol" style="text-align:center">${esc(rShort)}</td><td class="dcol">${esc(dShort)}</td><td class="tcol">${esc(tShort)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td><td class="stcol">${stShort}</td></tr>`;
          }
        } else {
          return `<tr><td>${esc(r.round||'')}</td><td class="dcol">${esc(r.date||'')}</td><td class="tcol">${esc(r.time||'')}</td><td class="ccol">${compBadge}</td><td class="match">${matchCell}</td><td>${esc(r.venue||'')}</td><td><span class="status-badge status-${esc(r.status||'')}">${esc(r.status||'')}</span></td></tr>`;
        }
      }).join('');
    }
  }

  function renderByDate(){
    const tbl = el('date-table'); const thead=tbl.tHead || tbl.createTHead(); const tbody = tbl.tBodies[0] || tbl.createTBody();
    const isMobile = matchMedia('(max-width:880px)').matches;
    const isTiny = matchMedia('(max-width:400px)').matches;
    if(isMobile){
      thead.innerHTML = isTiny
        ? `<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`
        : `<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`;
    } else {
      thead.innerHTML = `<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th class="ccol">Comp</th><th>Match</th><th>Venue</th><th>Status</th></tr>`;
    }
    const rows = [...MATCHES].sort((a,b)=> (a.date||'').localeCompare(b.date) || (a.time||'').localeCompare(b.time) );
    tbody.innerHTML = rows.map(r=>{
      const rShort=(r.round||'').replace(/^Round\s*/i,'R')||'—', dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||'');
      const stShort = (r.status||'').startsWith('R')?'R':'F';
      const scoreMid=(r.home_score&&r.away_score)?esc(r.home_score+' — '+r.away_score):'—';
      const compBadge = `<span class="comp-badge"><span class="comp-code">${esc(r.code)}</span><span class="group-code">${esc(groupShort(r.group))}</span></span>`;
      const matchCell = `<div class="match-block"><span>${esc(r.home||'')}</span><span class="match-score">${scoreMid}</span><span>${esc(r.away||'')}</span>${mobileMeta(r)}</div>`;
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
    }).join('');
  }

  // Initial load
  (async function init(){
    try {
      await fetchJSON(false);
      buildMenus();
      window.LGH_V7_1_READY = true;
    } catch (e) {
      console.error(e);
    }
  })();

})();