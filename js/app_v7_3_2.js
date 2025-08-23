// app_v7_3_2.js — mobile R column restored, wider match cell, centered cells,
// Competition view hides comp/group meta; Team/Date keeps it (PIHC meta simplified)
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
  const attachScores=m=>{
    if(m.home_score && m.away_score && !('home_goals' in m)) {
      const a = (m.home_score||'').match(/(\d+)[-–—](\d+)/), b=(m.away_score||'').match(/(\d+)[-–—](\d+)/);
      if(a){ m.home_goals=Number(a[1]); m.home_points=Number(a[2]); }
      if(b){ m.away_goals=Number(b[1]); m.away_points=Number(b[2]); }
    }
    m.home_goals = toInt(m.home_goals); m.home_points = toInt(m.home_points);
    m.away_goals = toInt(m.away_goals); m.away_points = toInt(m.away_points);
    m._homeMid = (m.home_goals!=null && m.home_points!=null) ? `${m.home_goals}-${m.home_points}` : '';
    m._awayMid = (m.away_goals!=null && m.away_points!=null) ? `${m.away_goals}-${m.away_points}` : '';
    m._rnum = parseRoundNum(m.round);
    return m;
  };

  let MATCHES=[];
  async function load(){
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`, {cache:'no-cache'});
    const j = await res.json();
    MATCHES = (j.matches||j||[]).map(r=>{
      const statusNorm = (r.status && String(r.status).toLowerCase().startsWith('res')) ? 'Result' : 'Fixture';
      const out = {
        competition: r.competition || '',
        group: r.group || '',
        round: r.round || '',
        date: r.date || '',
        time: r.time || '',
        home: r.home || '',
        away: r.away || '',
        venue: r.venue || '',
        status: statusNorm,
        home_goals: r.home_goals, home_points: r.home_points,
        away_goals: r.away_goals, away_points: r.away_points,
      };
      attachScores(out); out.code = compCode(out.competition); return out;
    });
  }

  function sortRoundDate(a,b){
    return (a._rnum-b._rnum) || (a.date||'').localeCompare(b.date||'') || (a.time||'').localeCompare(b.time||'');
  }

  // ------- table builders
  function buildHead(thead,isMobile,isTiny,showRound=true,showStatus=false){
    if(isMobile){
      // Mobile: R | Date | Time | Match | Venue
      const colsTiny = showRound
        ? `<th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th>`
        : `<th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th>`;
      const cols = showRound
        ? `<th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th>`
        : `<th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th>`;
      thead.innerHTML = `<tr>${isTiny?colsTiny:cols}${showStatus?`<th class="stcol">S</th>`:''}</tr>`;
    } else {
      thead.innerHTML = `<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th>Venue</th><th>Status</th></tr>`;
    }
  }

  function metaTextFor(r){
    const g = groupShort(r.group||'');
    // In Team/Date views: keep comp code; drop "Premier Intermediate" tail for PIHC
    if (r.code === 'PIHC') return 'PIHC';
    return g ? `${r.code} · ${g}` : `${r.code}`;
  }

  function rowHTML(r,isMobile,isTiny,{showMeta=true, showRound=true, showStatus=false}={}){
    const rShort = String(r.round||'').replace(/round\s*/i,'R').replace(/\s+/g,'') || '—';
    const dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||'');
    const scoreMid=(r._homeMid&&r._awayMid)?esc(r._homeMid+' – '+r._awayMid):'—';
    const meta = showMeta ? `<div class="match-meta">${esc(metaTextFor(r))}</div>` : '';
    const matchCell = `<div class="match-block"><span class="match-team">${esc(r.home||'')}</span><span class="match-score">${scoreMid}</span><span class="match-team">${esc(r.away||'')}</span>${meta}</div>`;

    if(isMobile){
      if(isTiny){
        const dt=`${dShort} ${tShort}`.trim();
        return `<tr>${
          showRound?`<td class="rcol" style="text-align:center">${esc(rShort)}</td>`:''
        }<td class="dcol">${esc(dt)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td>${showStatus?`<td class="stcol">${r.status==='Result'?'R':'F'}</td>`:''}</tr>`;
      } else {
        return `<tr>${
          showRound?`<td class="rcol" style="text-align:center">${esc(rShort)}</td>`:''
        }<td class="dcol">${esc(dShort)}</td><td class="tcol">${esc(tShort)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td>${showStatus?`<td class="stcol">${r.status==='Result'?'R':'F'}</td>`:''}</tr>`;
      }
    } else {
      return `<tr><td>${esc(rShort)}</td><td class="dcol">${esc(r.date||'')}</td><td class="tcol">${esc(r.time||'')}</td><td class="match">${matchCell}</td><td>${esc(r.venue||'')}</td><td><span class="status-badge status-${esc(r.status||'')}">${esc(r.status||'')}</span></td></tr>`;
    }
  }

  // ------- menus
  function buildMenus(){
    const PRIORITY = [
      "Senior Hurling Championship",
      "Premier Intermediate Hurling Championship",
      "Intermediate Hurling Championship"
    ];
    const comps = [...new Set(MATCHES.map(m=>m.competition).filter(Boolean))]
      .sort((a,b)=>{
        const ia = PRIORITY.indexOf(a), ib = PRIORITY.indexOf(b);
        return (ia===-1)-(ib===-1) || (ia-ib) || a.localeCompare(b);
      });

    const compMenu=el('comp-menu');
    compMenu.innerHTML = comps.map((c,i)=>`<div class="item ${i===0?'active':''}" data-comp="${esc(c)}">${esc(c)}</div>`).join('');
    function groupsFor(c){ return [...new Set(MATCHES.filter(m=>m.competition===c).map(m=>m.group||'Unassigned'))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true})); }
    function setComp(name){
      state.comp=name; el('comp-current').textContent=compCode(name);
      $$('#comp-menu .item').forEach(i=>i.classList.toggle('active', i.dataset.comp===name));
      const gs=groupsFor(name); const gMenu=el('group-menu');
      gMenu.innerHTML = gs.map((g,i)=>`<div class="item ${i===0?'active':''}" data-group="${esc(g)}">${esc(g)}</div>`).join('');
      setGroup(gs[0]);
    }
    function setGroup(g){
      state.group=g; el('group-current').textContent=g;
      $$('#group-menu .item').forEach(i=>i.classList.toggle('active', i.dataset.group===g));
      renderPanelTitle(); renderGroupTable();
    }
    el('comp-menu').onclick=e=>{ const it=e.target.closest('.item'); if(!it) return; setComp(it.dataset.comp); mComp.close(); };
    el('group-menu').onclick=e=>{ const it=e.target.closest('.item'); if(!it) return; setGroup(it.dataset.group); mGroup.close(); };
    setComp(comps[0]);
  }

  const mComp = (function(){ const trig=el('comp-trigger'), menu=el('comp-menu'); function close(){menu.classList.remove('open');} trig.addEventListener('click',e=>{e.stopPropagation(); menu.classList.toggle('open');}); document.addEventListener('click',e=>{ if(!menu.contains(e.target) && !trig.contains(e.target)) close(); }); return {close}; })();
  const mGroup = (function(){ const trig=el('group-trigger'), menu=el('group-menu'); function close(){menu.classList.remove('open');} trig.addEventListener('click',e=>{e.stopPropagation(); menu.classList.toggle('open');}); document.addEventListener('click',e=>{ if(!menu.contains(e.target) && !trig.contains(e.target)) close(); }); return {close}; })();

  const state={comp:null, group:null};
  function renderPanelTitle(){ el('panel-title').textContent = `${compCode(state.comp)} — ${state.group}`; }

  function renderGroupTable(){
    const tbl=el('g-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
    const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches;
    buildHead(thead,isMobile,isTiny,true,false); // showRound on mobile, hide status col
    const status=el('status').value;
    const rows = MATCHES
      .filter(r=>r.competition===state.comp && r.group===state.group)
      .filter(r=> !status || r.status===status)
      .sort(sortRoundDate);
    tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny,{showMeta:false, showRound:true, showStatus:false})).join('');
  }

  // standings (unchanged)
  function totalPoints(g,p){ return (g==null||p==null)?null:(Number(g)||0)*3+(Number(p)||0); }
  function renderStandings(){
    const rows = MATCHES.filter(r=>r.competition===state.comp && r.group===state.group && r.status==='Result');
    const teams=new Map();
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
    const tbody=document.querySelector('#g-standings-table tbody');
    tbody.innerHTML = sorted.map(r=>`<tr><td>${esc(r.team)}</td><td class="right">${r.p}</td><td class="right">${r.w}</td><td class="right">${r.d}</td><td class="right">${r.l}</td><td class="right">${r.pf}</td><td class="right">${r.pa}</td><td class="right">${r.diff}</td><td class="right"><strong>${r.pts}</strong></td></tr>`).join('');
  }

  el('status').addEventListener('input', renderGroupTable);

  // Matches/Table toggle (keep this near top of panel)
  $$('.section-tabs .seg').forEach(seg=>{
    seg.addEventListener('click', ()=>{
      seg.parentElement.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
      seg.classList.add('active');
      const showTable = seg.getAttribute('data-view')==='table';
      el('g-standings').style.display = showTable ? '' : 'none';
      document.querySelector('.matches-wrap').style.display = showTable ? 'none' : '';
      if(showTable) renderStandings();
    });
  });

  // More views
  function rowSorter(a,b){ return sortRoundDate(a,b); }

  function renderByTeam(){
    const sel=el('team');
    const teams=[...new Set(MATCHES.flatMap(r=>[r.home,r.away]).filter(Boolean))].sort();
    sel.innerHTML='<option value="">Select team…</option>'+teams.map(t=>`<option>${esc(t)}</option>`).join('');
    sel.oninput=draw; addEventListener('resize', draw);
    function draw(){
      const team=sel.value||''; const tbl=el('team-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
      const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches;
      buildHead(thead,isMobile,isTiny,true,false);
      const rows = MATCHES.filter(r=>!team || r.home===team || r.away===team).sort(rowSorter);
      tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny,{showMeta:true, showRound:true, showStatus:false})).join('');
    }
    draw();
  }

  function renderByDate(){
    const tbl=el('date-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
    const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches;
    buildHead(thead,isMobile,isTiny,true,false);
    const rows=[...MATCHES].sort(rowSorter);
    tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny,{showMeta:true, showRound:true, showStatus:false})).join('');
  }

  // Top nav
  $$('.navtab').forEach(tab=>{
    tab.addEventListener('click', ()=>{
      $$('.navtab').forEach(t=>t.classList.remove('active'));
      tab.classList.add('active');
      const name=tab.dataset.nav;
      el('panel-hurling').style.display = name==='hurling'?'':'none';
      el('panel-football').style.display = name==='football'?'':'none';
      el('panel-about').style.display = name==='about'?'':'none';
    });
  });

  (async function(){ await load(); buildMenus(); })();
})();
