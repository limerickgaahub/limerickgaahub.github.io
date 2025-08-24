// app_v7_3_3.js — Fixtures, Results, Tables, deep links, share, expand modal
(function(){
  // Ready flag (for the warning banner)
  window.LGH_V7_3_READY = true;

  // ---- Config / helpers
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

  // Polyfill: CSS.escape for older browsers
  const cssEscape = (window.CSS && typeof CSS.escape === 'function')
    ? CSS.escape
    : function (str) { return String(str).replace(/[^a-zA-Z0-9_\-]/g, '\\$&'); };

  const RESULT_RE = /^(res|final)/i;
  const isResult = s => RESULT_RE.test(String(s||''));
  const isFixture = s => !isResult(s);

  // URL/state
  const params = new Proxy(new URLSearchParams(location.search), { get:(sp,prop)=> sp.get(prop) });
  const state={ section:'hurling', view:'matches', comp:null, group:null, team:null, date:null };

  let MATCHES=[];
  let VIEW_MODE='competition';

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
  const sortDateComp=(a,b)=> {
    const da=a.date||'', db=b.date||'';
    if(da!==db) return da.localeCompare(db);
    const ca=(a.competition||''), cb=(b.competition||'');
    if(ca!==cb) return ca.localeCompare(cb);
    return (a.time||'').localeCompare(b.time||'');
  };

  function buildHead(thead,isMobile,isTiny){
    if(isMobile){
      thead.innerHTML = isTiny
        ? `<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th class="match">Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`
        : `<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th class="match">Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>`;
    } else {
      thead.innerHTML = `<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th class="ccol">Comp</th><th class="match">Match</th><th>Venue</th><th>Status</th></tr>`;
    }
  }

  function rowHTML(r,isMobile,isTiny){
    const rShort=(r.round||'').replace(/^Round\s*/i,'R').replace(/\s+/g,'')||'—';
    const dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||'');
    const stShort=isResult(r.status)?'R':'F';
    const scoreMid=(r._homeMid&&r._awayMid)?esc(r._homeMid+' - '+r._awayMid):'—';

    const showMeta=(VIEW_MODE!=='competition');
    const meta = showMeta ? `<div class="match-meta">${esc(r.code)} · ${esc(groupShort(r.group||''))}</div>` : '';
    const matchCell = `<div class="match-block"><span class="match-team">${esc(r.home||'')}</span><span class="match-score">${scoreMid}</span><span class="match-team">${esc(r.away||'')}</span>${meta}</div>`;
    const compBadge = `<span class="comp-badge"><span class="comp-code">${esc(r.code)}</span><span class="group-code">${esc(groupShort(r.group||''))}</span></span>`;
    const trAttr=`data-date="${esc(r.date||'')}"`;

    if(isMobile){
      if(isTiny){
        const dt=`${dShort} ${tShort}`.trim();
        return `<tr ${trAttr}><td class="rcol">${esc(rShort)}</td><td class="dcol">${esc(dt)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td><td class="stcol">${stShort}</td></tr>`;
      } else {
        return `<tr ${trAttr}><td class="rcol">${esc(rShort)}</td><td class="dcol">${esc(dShort)}</td><td class="tcol">${esc(tShort)}</td><td class="match">${matchCell}</td><td class="vcol">${esc(r.venue||'')}</td><td class="stcol">${stShort}</td></tr>`;
      }
    } else {
      return `<tr ${trAttr}><td>${esc(r.round||'')}</td><td class="dcol">${esc(r.date||'')}</td><td class="tcol">${esc(r.time||'')}</td><td class="ccol">${compBadge}</td><td class="match">${matchCell}</td><td>${esc(r.venue||'')}</td><td><span class="status-badge status-${esc(r.status||'')}">${esc(r.status||'')}</span></td></tr>`;
    }
  }

  // ---- Competition dropdown only (group picked automatically)
  function buildMenus(){
    // Unique competitions
    const comps = [...new Set(MATCHES.map(m=>m.competition).filter(Boolean))];

    // Preferred default: Senior Hurling Championship
    let desiredComp = comps.find(c => /Senior Hurling Championship/i.test(c)) || comps[0] || '';

    // If URL has comp and it exists, use it
    if (params.comp && comps.includes(params.comp)) desiredComp = params.comp;

    // Build menu
    const menu = el('comp-menu');
    menu.innerHTML = comps.map(c =>
      `<div class="item${c===desiredComp?' active':''}" data-comp="${esc(c)}">${esc(c)}</div>`
    ).join('');

    // Click handling
    menu.onclick = (e)=>{
      const it = e.target.closest('.item'); if(!it) return;
      const comp = it.getAttribute('data-comp');
      $$('#comp-menu .item').forEach(i=>i.classList.remove('active'));
      it.classList.add('active');
      setCompetition(comp);
      combo.close();
    };

    // Trigger open/close (whole pill clickable)
    const combo = (function(){
      const trig = el('comp-trigger');
      function close(){ menu.classList.remove('open'); }
      trig.addEventListener('click', e=>{ e.stopPropagation(); menu.classList.toggle('open'); });
      document.addEventListener('click', e=>{ if(!menu.contains(e.target) && !trig.contains(e.target)) close(); });
      return { close };
    })();

    // Initial apply
    setCompetition(desiredComp);
  }

  // Choose competition, auto-select group (Group 1 if available), update label and render
  function setCompetition(compName){
    state.comp = compName || null;

    // Determine default group within this competition
    const groups = [...new Set(MATCHES.filter(m=>m.competition===compName).map(m=>m.group || 'Unassigned'))]
      .sort((a,b)=> a.localeCompare(b, undefined, {numeric:true}));
    let chosenGroup = groups.find(g => /^Group\s*1$/i.test(g)) || groups[0] || null;
    state.group = chosenGroup;

    // Update pill and subheader label
    el('comp-current').textContent = compName || '—';
    const label = el('comp-selected');
    if (label) label.textContent = compName || '';

    // Re-render current subview
    const tableSegActive = document.querySelector('#group-panel .section-tabs .seg[data-view="table"].active');
    if (tableSegActive) { renderStandings(); } else { renderGroupTable(); }

    // Deep link
    syncURL();
  }

  // ---- Renders
  function renderGroupTable(){
    VIEW_MODE='competition';
    const tbl=el('g-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
    const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches; buildHead(thead,isMobile,isTiny);
    const status=el('status').value;
    const rows = MATCHES.filter(r=>{
      if(state.comp && r.competition!==state.comp) return false;
      if(state.group && r.group!==state.group) return false;
      if(status==='Result')  return isResult(r.status);
      if(status==='Fixture') return isFixture(r.status);
      return true;
    }).sort(sortRoundDate);
    tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny)).join('');
  }

  function pointsFromGoalsPoints(g,p){ return (g==null||p==null)?null:(Number(g)||0)*3+(Number(p)||0); }

  function renderStandings(){
    const rows = MATCHES.filter(r=>r.competition===state.comp && r.group===state.group && isResult(r.status));
    const teams=new Map();
    for(const m of rows){
      const hs=pointsFromGoalsPoints(m.home_goals,m.home_points), as=pointsFromGoalsPoints(m.away_goals,m.away_points);
      if(hs==null||as==null) continue;
      if(!teams.has(m.home)) teams.set(m.home,{team:m.home,p:0,w:0,d:0,l:0,pf:0,pa:0,diff:0,pts:0});
      if(!teams.has(m.away)) teams.set(m.away,{team:m.away,p:0,w:0,d:0,pf:0,pa:0,diff:0,pts:0});
      const H=teams.get(m.home), A=teams.get(m.away);
      H.p++; A.p++; H.pf+=hs; H.pa+=as; A.pf+=as; A.pa+=hs;
      if(hs>as){ H.w++; H.pts+=2; A.l++; } else if(hs<as){ A.w++; A.pts+=2; H.l++; } else { H.d++; A.d++; H.pts++; A.pts++; }
    }
    for(const t of teams.values()) t.diff=t.pf-t.pa;

    // Sort: Pts desc → Diff desc → PF desc → Team asc
    const sorted=[...teams.values()].sort((a,b)=>
      b.pts-a.pts || b.diff-a.diff || b.pf-a.pf || a.team.localeCompare(b.team)
      // TODO: Head-to-Head tiebreaker could be inserted here
    );

    // Default compact table (no PF/PA/Diff)
    const tbody=document.querySelector('#g-standings-table tbody');
    tbody.innerHTML = sorted.map(r =>
      `<tr>
        <td>${esc(r.team)}</td>
        <td class="right">${r.p}</td>
        <td class="right">${r.w}</td>
        <td class="right">${r.d}</td>
        <td class="right">${r.l}</td>
        <td class="right"><strong>${r.pts}</strong></td>
      </tr>`
    ).join('');

    // Expanded modal table (full columns)
    const mt=el('modal-standings');
    if(mt){
      if(!mt.tHead || !mt.tHead.rows.length){
        mt.createTHead().innerHTML = `<tr><th>Team</th><th class="right">P</th><th class="right">W</th><th class="right">D</th><th class="right">L</th><th class="right">PF</th><th class="right">PA</th><th class="right">Diff</th><th class="right">Pts</th></tr>`;
      }
      const mb = mt.tBodies[0]||mt.createTBody();
      mb.innerHTML = sorted.map(r =>
        `<tr>
          <td>${esc(r.team)}</td>
          <td class="right">${r.p}</td>
          <td class="right">${r.w}</td>
          <td class="right">${r.d}</td>
          <td class="right">${r.l}</td>
          <td class="right">${r.pf}</td>
          <td class="right">${r.pa}</td>
          <td class="right">${r.diff}</td>
          <td class="right"><strong>${r.pts}</strong></td>
        </tr>`
      ).join('');
    }
  }

  // ---- Share / deep links
  function syncURL(push=false){
    const sp=new URLSearchParams();
    sp.set('s', state.section);
    sp.set('v', state.view);
    if(state.comp) sp.set('comp', state.comp);
    if(state.group) sp.set('group', state.group);
    if(state.team) sp.set('team', state.team);
    if(state.date) sp.set('date', state.date);
    const url = `${location.pathname}?${sp.toString()}`;
    (push?history.pushState:history.replaceState).call(history, null, '', url);
  }
  function currentShareURL(){ syncURL(false); return location.href; }
  function toast(msg){ const div=document.createElement('div'); div.textContent=msg; div.style.cssText='position:fixed;left:50%;transform:translateX(-50%);bottom:20px;background:#111;color:#fff;padding:8px 12px;border-radius:8px;z-index:200;opacity:.95'; document.body.appendChild(div); setTimeout(()=>div.remove(),1500); }

  document.addEventListener('click', (e)=>{
    if(e.target.closest('#btn-share')){ const url=currentShareURL(); const title='Limerick GAA Hub'; const text='Fixtures, results & tables'; if(navigator.share){ navigator.share({title,text,url}); } else { navigator.clipboard?.writeText(url); toast('Link copied'); } }
    if(e.target.closest('#btn-copy')){ navigator.clipboard?.writeText(currentShareURL()); toast('Link copied'); }
  });

  // ---- Event wiring

  // Matches/Table (Competition panel ONLY)
  $$('#group-panel .section-tabs .seg').forEach(seg=>{
    seg.addEventListener('click', ()=>{
      const wrap = seg.parentElement;
      wrap.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
      seg.classList.add('active');
      const showTable = seg.getAttribute('data-view')==='table';
      state.view = showTable ? 'table' : 'matches';

      el('g-standings').style.display = showTable ? '' : 'none';
      document.querySelector('.matches-wrap').style.display = showTable ? 'none' : '';

      // Hide status in Table view
      const controls = document.querySelector('#group-panel .controls');
      if (controls) controls.style.display = showTable ? 'none' : '';

      if(showTable) renderStandings(); else renderGroupTable();
      syncURL(true);
    });
  });

  // Top-level tabs
  $$('.navtab').forEach(tab=>{
    tab.addEventListener('click', ()=>{
      $$('.navtab').forEach(t=>t.classList.remove('active'));
      tab.classList.add('active');
      const name=tab.dataset.nav;
      state.section = name;
      el('panel-hurling').style.display = name==='hurling'?'':'none';
      el('panel-football').style.display = name==='football'?'':'none';
      el('panel-about').style.display = name==='about'?'':'none';
      syncURL(true);
    });
  });

  // Competition / Team / Date switcher
  $$('.view-tabs .vt').forEach(seg=>{
    seg.addEventListener('click', ()=>{
      seg.parentElement.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
      seg.classList.add('active');
      const target = seg.getAttribute('data-target');

      $$('#panel-hurling .panel').forEach(p=> p.style.display='none');
      el(target).style.display='';

      // comp controls visibility
      const cc = document.querySelector('.comp-controls');
      if(cc) cc.style.display = (target==='group-panel') ? '' : 'none';

      if(target==='group-panel'){ state.view='matches'; renderGroupTable(); }
      if(target==='by-team'){ renderByTeam(); }
      if(target==='by-date'){ renderByDate(); }
      syncURL(true);
    });
  });

  // Team view
  function renderByTeam(){
    VIEW_MODE='team'; state.view='team';
    const sel=el('team');
    const teams=[...new Set(MATCHES.flatMap(r=>[r.home,r.away]).filter(Boolean))].sort();
    sel.innerHTML='<option value="">Select team…</option>'+teams.map(t=>`<option>${esc(t)}</option>`).join('');
    const draw=()=>{
      const team=sel.value||''; state.team = team || null; syncURL();
      const tbl=el('team-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
      const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches; buildHead(thead,isMobile,isTiny);
      if(!team){ tbody.innerHTML=''; return; }
      const rows = MATCHES.filter(r=> r.home===team || r.away===team).sort(sortRoundDate);
      tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny)).join('');
    };
    sel.oninput=draw; addEventListener('resize', draw);
    const tbl=el('team-table'); const thead=tbl.tHead||tbl.createTHead(); buildHead(thead, matchMedia('(max-width:880px)').matches, matchMedia('(max-width:400px)').matches);
    tbl.tBodies[0] ? (tbl.tBodies[0].innerHTML='') : tbl.createTBody();

    if(params.team){ sel.value=params.team; sel.dispatchEvent(new Event('input')); }
  }

  // Date view
  function renderByDate(){
    VIEW_MODE='date'; state.view='date';
    const tbl=el('date-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
    const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches; buildHead(thead,isMobile,isTiny);

    const rows=[...MATCHES].sort(sortDateComp);
    tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny)).join('');

    const candidates = Array.from(tbody.querySelectorAll('tr[data-date]'));
    const jump=el('date-jump');
    if(jump){
      const allDates = rows.map(r=>r.date).filter(Boolean).sort();
      const minD = allDates[0] || ''; const maxD = allDates[allDates.length-1] || '';
      if(minD) jump.min=minD; if(maxD) jump.max=maxD;

      jump.onchange=()=>{
        const ymd = jump.value; state.date = ymd || null; syncURL();
        if(!ymd || candidates.length===0) return;
        let target = tbody.querySelector(`tr[data-date="${cssEscape(ymd)}"]`);
        if(!target){
          let chosen=null;
          for(const tr of candidates){ const d = tr.getAttribute('data-date')||''; if(d<=ymd) chosen = tr; else break; }
          target = chosen || candidates[candidates.length-1] || candidates[0] || null;
          if(target){ const td = target.getAttribute('data-date') || ''; if(td){ const firstOfDate = tbody.querySelector(`tr[data-date="${cssEscape(td)}"]`); if(firstOfDate) target = firstOfDate; } }
        }
        if(target){ target.scrollIntoView({behavior:'smooth', block:'start'}); target.style.outline='2px solid var(--accent)'; setTimeout(()=>{ target.style.outline=''; }, 1500); }
      };

      if(params.date){ jump.value=params.date; jump.dispatchEvent(new Event('change')); }
    }
  }

  // Expand modal
  (function(){
    const btn=el('btn-expand'), modal=el('standings-modal'), close=el('modal-close');
    if(btn && modal && close){
      btn.addEventListener('click', ()=>{ modal.classList.add('open'); modal.setAttribute('aria-hidden','false'); document.body.style.overflow='hidden'; });
      close.addEventListener('click', ()=>{ modal.classList.remove('open'); modal.setAttribute('aria-hidden','true'); document.body.style.overflow=''; });
      modal.addEventListener('click', (e)=>{ if(e.target===modal) close.click(); });
    }
  })();

  // Status filter
  el('status').addEventListener('input', ()=>{ renderGroupTable(); syncURL(); });

  // ---- Init: load data, menus, then apply URL state
  (async function(){
    await load();
    buildMenus();

    // Section
    const s = params.s || 'hurling';
    (function(n){ if(n) n.click(); })(document.querySelector(`.navtab[data-nav="${s}"]`));

    // View
    const v = params.v || 'matches';
    if(v==='table'){
      (function(n){ if(n) n.click(); })(document.querySelector('#group-panel .section-tabs .seg[data-view="table"]'));
    } else if(v==='matches'){
      (function(n){ if(n) n.click(); })(document.querySelector('#group-panel .section-tabs .seg[data-view="matches"]'));
    } else if(v==='team'){
      (function(n){ if(n) n.click(); })(document.querySelector('.view-tabs .vt[data-target="by-team"]'));
    } else if(v==='date'){
      (function(n){ if(n) n.click(); })(document.querySelector('.view-tabs .vt[data-target="by-date"]'));
    } else {
      renderGroupTable();
    }
  })();
})();
