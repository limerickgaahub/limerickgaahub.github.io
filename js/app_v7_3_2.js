// app_v7_3_2.js — hide comp controls in Team/Date, better mobile width, date jump bounds
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

  function sortRoundDate(a,b){
    return (a._rnum-b._rnum) || (a.date||'').localeCompare(b.date||'') || (a.time||'').localeCompare(b.time||'');
  }

  function buildHead(thead,isMobile,isTiny){
    if(isMobile){
      thead.innerHTML = isTiny
        ? `<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`
        : `<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`;
    } else {
      thead.innerHTML = `<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th class="ccol">Comp</th><th>Match</th><th>Venue</th><th>Status</th></tr>`;
    }
  }

  function rowHTML(r,isMobile,isTiny){
    const rShort=(r.round||'').replace(/^Round\s*/i,'R').replace(/\s+/g,'')||'—';
    const dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||'');
    const stShort=(r.status||'').toLowerCase().startsWith('res')?'R':'F';
    const scoreMid=(r._homeMid&&r._awayMid)?esc(r._homeMid+' - '+r._awayMid):'—'; // short dash

    // meta only in Team/Date
    const showMeta=(VIEW_MODE!=='competition');
    const meta = showMeta ? `<div class="match-meta">${esc(r.code)} · ${esc(groupShort(r.group||''))}</div>` : '';
    const matchCell = `<div class="match-block"><span class="match-team">${esc(r.home||'')}</span><span class="match-score">${scoreMid}</span><span class="match-team">${esc(r.away||'')}</span>${meta}</div>`;
    const compBadge = `<span class="comp-badge"><span class="comp-code">${esc(r.code)}</span><span class="group-code">${esc(groupShort(r.group||''))}</span></span>`;
    const trAttr=`data-date="${esc(r.date||'')}"`;

    if(isMobile){
      if(isTiny){
        const dt=`${dShort} ${tShort}`.trim();
        return `<tr ${trAttr}><td class="rcol" style="text-align:center">${esc(rShort)}</td><td class="dcol">${esc(dt)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td><td class="stcol">${stShort}</td></tr>`;
      } else {
        return `<tr ${trAttr}><td class="rcol" style="text-align:center">${esc(rShort)}</td><td class="dcol">${esc(dShort)}</td><td class="tcol">${esc(tShort)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td><td class="stcol">${stShort}</td></tr>`;
      }
    } else {
      return `<tr ${trAttr}><td>${esc(r.round||'')}</td><td class="dcol">${esc(r.date||'')}</td><td class="tcol">${esc(r.time||'')}</td><td class="ccol">${compBadge}</td><td class="match">${matchCell}</td><td>${esc(r.venue||'')}</td><td><span class="status-badge status-${esc(r.status||'')}">${esc(r.status||'')}</span></td></tr>`;
    }
  }

  // Menus
  function buildMenus(){
    const all = [...new Set(MATCHES.map(m=>m.competition).filter(Boolean))];
    const preferred = ["Senior Hurling Championship","Premier Intermediate Hurling Championship","Intermediate Hurling Championship"];
    const rest = all.filter(c=>!preferred.includes(c)).sort();
    const comps = preferred.filter(c=>all.includes(c)).concat(rest);

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
      renderGroupTable();
    }
    el('comp-menu').onclick=e=>{ const it=e.target.closest('.item'); if(!it) return; setComp(it.dataset.comp); mComp.close(); };
    el('group-menu').onclick=e=>{ const it=e.target.closest('.item'); if(!it) return; setGroup(it.dataset.group); mGroup.close(); };
    setComp(comps[0]);
  }

  const mComp = (function(){ const trig=el('comp-trigger'), menu=el('comp-menu'); function close(){menu.classList.remove('open');} trig.addEventListener('click',e=>{e.stopPropagation(); menu.classList.toggle('open');}); document.addEventListener('click',e=>{ if(!menu.contains(e.target) && !trig.contains(e.target)) close(); }); return {close}; })();
  const mGroup = (function(){ const trig=el('group-trigger'), menu=el('group-menu'); function close(){menu.classList.remove('open');} trig.addEventListener('click',e=>{e.stopPropagation(); menu.classList.toggle('open');}); document.addEventListener('click',e=>{ if(!menu.contains(e.target) && !trig.contains(e.target)) close(); }); return {close}; })();

  const state={comp:null, group:null};

  function renderGroupTable(){
    VIEW_MODE='competition';
    const tbl=el('g-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
    const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches; buildHead(thead,isMobile,isTiny);
    const status=el('status').value;
    const rows = MATCHES.filter(r=>{
      if(state.comp && r.competition!==state.comp) return false;
      if(state.group && r.group!==state.group) return false;
      if(status==='Result')  return r.status==='Result';
      if(status==='Fixture') return r.status!=='Result';
      return true;
    }).sort(sortRoundDate);
    tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny)).join('');
  }

  // Standings
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

  // Matches/Table toggle (Competition)
  $$('.section-tabs .seg').forEach(seg=>{
    seg.addEventListener('click', ()=>{
      const wrap = seg.parentElement;
      wrap.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
      seg.classList.add('active');
      const showTable = seg.getAttribute('data-view')==='table';
      el('g-standings').style.display = showTable ? '' : 'none';
      document.querySelector('.matches-wrap').style.display = showTable ? 'none' : '';
      if(showTable) renderStandings();
    });
  });

  // Top-level tabs (Hurling/Football/About)
  $$('.navtab').forEach(tab=>{
    tab.addEventListener('click', ()=>{
      $$('.navtab').forEach(t=>t.classList.remove('active'));
      tab.addEventListener
      tab.classList.add('active');
      const name=tab.dataset.nav;
      el('panel-hurling').style.display = name==='hurling'?'':'none';
      el('panel-football').style.display = name==='football'?'':'none';
      el('panel-about').style.display = name==='about'?'':'none';
    });
  });

  // Team view (hide comp controls; empty until selection)
  function renderByTeam(){
    VIEW_MODE='team';
    el('comp-controls')?.style?.setProperty('display','none');
    const sel=el('team');
    const teams=[...new Set(MATCHES.flatMap(r=>[r.home,r.away]).filter(Boolean))].sort();
    sel.innerHTML='<option value="">Select team…</option>'+teams.map(t=>`<option>${esc(t)}</option>`).join('');
    sel.oninput=draw; addEventListener('resize', draw);
    function draw(){
      const team=sel.value||'';
      const tbl=el('team-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
      const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches; buildHead(thead,isMobile,isTiny);
      if(!team){ tbody.innerHTML=''; return; }
      const rows = MATCHES.filter(r=> r.home===team || r.away===team).sort(sortRoundDate);
      tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny)).join('');
    }
    const tbl=el('team-table'); const thead=tbl.tHead||tbl.createTHead(); buildHead(thead, matchMedia('(max-width:880px)').matches, matchMedia('(max-width:400px)').matches);
    tbl.tBodies[0] ? (tbl.tBodies[0].innerHTML='') : tbl.createTBody();
  }

  // Date view (hide comp controls) + Go-to-date with bounds (to first/last if out of range)
  function renderByDate(){
    VIEW_MODE='date';
    el('comp-controls')?.style?.setProperty('display','none');
    const tbl=el('date-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
    const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches; buildHead(thead,isMobile,isTiny);
    const rows=[...MATCHES].sort(sortRoundDate);
    tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny)).join('');

    const allDates = rows.map(r=>r.date).filter(Boolean).sort();
    const minD = allDates[0] || null;
    const maxD = allDates[allDates.length-1] || null;

    const jump=el('date-jump');
    if(jump){
      if(minD) jump.min=minD;
      if(maxD) jump.max=maxD;
      jump.onchange=()=>{
        const ymd = jump.value; if(!ymd) return;
        let targetRow = tbody.querySelector(`tr[data-date="${CSS.escape(ymd)}"]`);
        if(!targetRow){
          // find first match with date >= selected; if none, go last; if selected < min, go first
          const candidates = Array.from(tbody.querySelectorAll('tr[data-date]'));
          targetRow = candidates.find(tr => (tr.getAttribute('data-date')||'') >= ymd)
                    || candidates[candidates.length-1]
                    || null;
        }
        if(targetRow){
          targetRow.scrollIntoView({behavior:'smooth', block:'start'});
          targetRow.style.outline='2px solid var(--accent)';
          setTimeout(()=>{ targetRow.style.outline=''; }, 1500);
        }
      };
    }
  }

  // Switch between Competition / Team / Date views
  $$('.view-tabs .vt').forEach(seg=>{
    seg.addEventListener('click', ()=>{
      seg.parentElement.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
      seg.classList.add('active');
      const target = seg.getAttribute('data-target');
      $$('#panel-hurling .panel').forEach(p=> p.style.display='none');
      el(target).style.display='';
      // show/hide comp controls
      const cc = document.querySelector('.comp-controls');
      if(cc) cc.style.display = (target==='group-panel') ? '' : 'none';
      if(target==='group-panel') renderGroupTable();
      if(target==='by-team') renderByTeam();
      if(target==='by-date') renderByDate();
    });
  });

  (async function(){ await load(); buildMenus(); })();
})();
