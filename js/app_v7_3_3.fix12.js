const __PROD__ = !/^(localhost|127\.0\.0\.1)$/.test(location.hostname);
const log  = (...a) => { if (!__PROD__) console.log(...a); };
const warn = (...a) => { if (!__PROD__) console.warn(...a); };
const err  = (...a) => console.error(...a);



log("[LGH] app js evaluating");
window.LGH_V7_3_READY = true;
window.LGH_V7_3_3_READY = true;
log("[LGH] flags now:",
  "LGH_V7_3_READY =", window.LGH_V7_3_READY,
  "LGH_V7_3_3_READY =", window.LGH_V7_3_3_READY
);


function showWarn(msg){
  let n = document.querySelector('#js-warning');
  if (!n) {
    n = document.createElement('p');
    n.id = 'js-warning';
    n.className = 'notice';
    document.querySelector('main')?.prepend(n);
  }
  n.textContent = msg;
  n.style.display = 'block';
}

// app_v7_3_3.js — stable markup, naming, views
(function(){
  window.LGH_V7_3_READY = true;
  window.LGH_V7_3_3_READY = true;

  const DATA_URL = 'data/hurling_2025.json';

  const KO_URL = 'datastatic/knockout_2025.json';

  function isKO(m){
    return (m.stage === 'knockout') || ((m.group || '').toLowerCase() === 'knockout');
  }
  
  // simple dedupe by id or by composite key
  function _key(m){
    return m.id || [m.competition,m.round,m.date,m.time,m.venue,m.home,m.away].join('|');
  }
  function mergeById(base, extra){
    const map = new Map(base.map(m => [_key(m), m]));
    for (const m of extra) map.set(_key(m), { ...map.get(_key(m)), ...m });
    return [...map.values()];
  }


// Codes used internally (must match combined JSON "competition" strings)
const COMP_CODES = {
  "Senior Hurling Championship": "SHC",
  "Premier Intermediate Hurling Championship": "PIHC",
  "Intermediate Hurling Championship": "IHC",
  "Premier Junior A Hurling Championship": "PJAHC",
  "Junior A Hurling Championship": "JAHC",
  "Junior B Hurling Championship": "JBHC",
  "Junior C Hurling Championship": "JCHC",
};

const INV_COMP_CODES = {
  SHC:  'Senior Hurling Championship',
  PIHC: 'Premier Intermediate Hurling Championship',
  IHC:  'Intermediate Hurling Championship',
  PJAHC:'Premier Junior A Hurling Championship',
  JAHC: 'Junior A Hurling Championship',
  JBHC: 'Junior B Hurling Championship',
  JCHC: 'Junior C Hurling Championship'
};


// Optional, if you have an explicit display/order list:
const COMPETITION_ORDER = [
  "Senior",
  "Premier Intermediate",
  "Intermediate",
  "Premier Junior A",
  "Junior A",
  "Junior B",
  "Junior C",
];

// Display labels used for dropdown pills and expanded headers
const DISPLAY_NAMES = {
  "Senior Hurling Championship": {
    label: "Senior",
    long:  "WhiteBox County Senior Hurling Championship",
    groups: ["Group 1","Group 2"]          // used for Matches dropdown
  },
  "Premier Intermediate Hurling Championship": {
    label: "Premier Intermediate",
    long:  "Lyons of Limerick County Premier Intermediate Hurling Championship",
    pihc:  true                             // special case: Matches shows "PIHC" only
  },
  "Intermediate Hurling Championship": {
    label: "Intermediate",
    long:  "County Intermediate Hurling Championship",
    groups:["Group 1","Group 2"]
  },
  "Premier Junior A Hurling Championship": {
    label: "Premier Junior A",
    long:  "Woodlands House Hotel County Premier Junior A Hurling Championship",
    groups:["Group 1","Group 2"]
  },
  "Junior A Hurling Championship": {
    label: "Junior A",
    long:  "Woodlands House Hotel County Junior A Hurling Championship",
    groups:["Group 1","Group 2"]
  },
  "Junior B Hurling Championship": {
    label: "Junior B",
    long:  "Woodlands House Hotel Junior B Hurling Championship",
  },
  "Junior C Hurling Championship": {
    label: "Junior C",
    long:  "Woodlands House Hotel County Junior C Hurling Championship",
    groups:["Group 1","Group 2"]
  }
};

// ---- Sort helpers (date-first + stable comp order) ----
const COMP_RANK = (() => {
  // Order we want in "By Date" when dates are equal
  const ORDER = [
    "Senior", "Premier Intermediate", "Intermediate",
    "Premier Junior A", "Junior A", "Junior B", "Junior C"
  ];
  const rank = {};
  // Map full competition name -> rank using DISPLAY_NAMES.label
  for (const [full, meta] of Object.entries(DISPLAY_NAMES)) {
    const lbl = meta?.label || full;
    const idx = ORDER.indexOf(lbl);
    rank[full] = idx >= 0 ? idx + 1 : 99;
  }
  return rank;
})();

// date + time only (strict chronological)
const sortDateOnly = (a, b) =>
  (a.date || '').localeCompare(b.date || '') ||
  (a.time || '').localeCompare(b.time || '');


  const el=id=>document.getElementById(id), $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
  const pad2=n=>String(n).padStart(2,'0'); const day3=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const fmtDateShort=iso=>{ if(!iso) return ''; const d=new Date(iso+'T00:00:00'); return `${day3[d.getDay()]} ${pad2(d.getDate())}/${pad2(d.getMonth()+1)}`; };
  const fmtTimeShort=t=>{ if(!t) return ''; const m=t.match(/^(\d{1,2}):(\d{2})/); return m?`${pad2(m[1])}:${m[2]}`:t; }; // <-- add colon
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const groupShort=g=>(g||'').replace(/^Group\s*/i,'G').trim();
  const compCode=name=> COMP_CODES[name] || (name? name.split(/\s+/).map(w=>w[0]).join('').toUpperCase() : '?');
  const toInt=v=>v==null||v===''?null:(Number(v)||0);
  const parseRoundNum=r=>{ const m=String(r||'').match(/(\d+)/); return m?Number(m[1]):999; };

  // Treat "Walkover" as a result for all filters/partitions.
  const RESULT_RE=/^(res|final|walkover)/i;
  const isResult=s=>RESULT_RE.test(String(s||''));
  const isFixture=s=>!isResult(s);
  
  // Helper to sort Results first, then Fixtures (used in Team/Date views)
  const resultRank = m => isResult(m?.status) ? 0 : 1;


  const params=new Proxy(new URLSearchParams(location.search),{get:(sp,prop)=>sp.get(prop)});
  const state={ section:'hurling', view:'matches', comp:null, group:null, team:null, date:null };
  const FIRST_LOAD_NO_QUERY = !location.search;   // true if user landed without query params

  let MATCHES=[];
  let VIEW_MODE='competition';

  const attachScores=m=>{
    m.home_goals=toInt(m.home_goals); m.home_points=toInt(m.home_points);
    m.away_goals=toInt(m.away_goals); m.away_points=toInt(m.away_points);
    m._homeMid=(m.home_goals!=null&&m.home_points!=null)?`${m.home_goals}-${m.home_points}`:'';
    m._awayMid=(m.away_goals!=null&&m.away_points!=null)?`${m.away_goals}-${m.away_points}`:'';
    m._rnum=parseRoundNum(m.round);
    return m;
  };

// ---------- GA4 helpers (SPA virtual pages + events) ----------
const LGH_ANALYTICS = (function(){
  let lastPath = null;

  const slug = s => (s||'').toString()
    .trim().toLowerCase()
    .replace(/&/g,'and')
    .replace(/[^a-z0-9]+/g,'-')
    .replace(/^-+|-+$/g,'');

  const page = (path, title) => {
    if (!path) return;
    if (path === lastPath) return;      // avoid duplicates
    lastPath = path;
    const full = location.origin + path;
    if (typeof gtag === 'function') {
      gtag('event', 'page_view', {
        page_title: title || document.title,
        page_location: full,
        page_path: path
      });
    }
  };

  const viewAbout = () => page('/about', 'About – Limerick GAA Hub');
  const viewPrivacy = () => page('/privacy', 'Privacy – Limerick GAA Hub');

  const viewCompetition = (competition, group, viewMode /* 'matches' | 'table' */) => {
    const p = `/competition/${slug(competition||'all')}/${slug(group||'all')}/${slug(viewMode||'matches')}`;
    page(p, `${competition||'All'} – ${group||'All'} – ${viewMode||'Matches'}`);
    if (typeof gtag === 'function') {
      gtag('event','view_competition',{ competition: competition||'(none)', group: group||'(none)', view: viewMode||'matches' });
    }
  };

    const viewTeam = (teamName) => {
      const p = `/club/${slug(teamName||'none')}`;
      page(p, `Club – ${teamName||'(none)'}`);
      if (typeof gtag === 'function') gtag('event','view_club',{ club: teamName||'(none)' });
    };

  const viewDate = (isoDate) => {
    const p = `/date/${isoDate||'none'}`;
    page(p, `Date – ${isoDate||'(none)'}`);
    if (typeof gtag === 'function') gtag('event','view_date',{ date: isoDate||'(none)' });
  };

  const clickSocial = (platform) => { if (typeof gtag === 'function') gtag('event','click_social',{ platform }); };
  const clickOutbound = (host) => { if (typeof gtag === 'function') gtag('event','click_outbound',{ destination: host }); };
  const clickShare = (method) => { if (typeof gtag === 'function') gtag('event','share_action',{ method }); };

  const autoBind = () => {
    // Socials (About panel)
    document.querySelectorAll('.social-list .social-link').forEach(a=>{
      const href = a.getAttribute('href')||'';
      const platform =
        href.includes('instagram.com') ? 'instagram' :
        href.includes('x.com') ? 'x' :
        href.startsWith('mailto:') ? 'email' : 'other';
      a.addEventListener('click', ()=> clickSocial(platform));
    });
    // Outbound official link
    document.querySelectorAll('a[href*="limerickgaa.ie"]').forEach(a=>{
      a.addEventListener('click', ()=> clickOutbound('limerickgaa.ie'));
    });
    // Share/copy buttons
    document.querySelectorAll('[data-role="copy"]').forEach(btn=>{
      btn.addEventListener('click', ()=> clickShare('copy'));
    });
    document.querySelectorAll('[data-role="share"]').forEach(btn=>{
      btn.addEventListener('click', ()=> clickShare('share'));
    });
  };

  return { page, viewAbout, viewPrivacy, viewCompetition, viewTeam, viewDate, clickSocial, clickOutbound, clickShare, autoBind };
})();

document.addEventListener('DOMContentLoaded', ()=> LGH_ANALYTICS.autoBind());

/* === Date input: default to today + re-render on change === */
document.addEventListener('DOMContentLoaded', () => {
  const di = document.getElementById('date-input');
  if (!di) return;

  // Default to today if empty
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth()+1).padStart(2,'0');
  const dd = String(today.getDate()).padStart(2,'0');
  if (!di.value) di.value = `${yyyy}-${mm}-${dd}`;

  // Re-render Date view when changed
  di.addEventListener('change', () => {
    if (window.state) state.date = di.value;
    if (typeof renderByDate === 'function') renderByDate();
    if (window.LGH_ANALYTICS) LGH_ANALYTICS.viewDate(di.value);
  });
});

// === Make the big chevron button open the native date picker ===
document.addEventListener('DOMContentLoaded', () => {
  const di = document.getElementById('date-input');
  const btn = document.querySelector('.pretty-input .date-open');
  if (!di || !btn) return;

  const openPicker = () => {
    if (typeof di.showPicker === 'function') {
      di.showPicker();   // Modern Chrome/Android, some Safari
    } else {
      di.focus();        // Fallback (opens native picker on mobile)
      di.click?.();      // iOS Safari needs click
    }
  };

  btn.addEventListener('click', openPicker);
});

  
async function load(){
  try {
    let j = null;
    let stale = false;
      const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache:'no-store' });
      if (res.ok) {
        j = await res.json();
      } else {
        stale = true;
        warn('[LGH] Data fetch not OK:', res.status, res.statusText);
      }

        if (stale) {
      showWarn('Live data is slow — showing last verified snapshot.');
      j = window.__LGH_BOOTSTRAP__ || {};
    }
    
    // 1) Base dataset
    MATCHES = (j.matches || j || []).map(r => {
      const out = {
        competition: r.competition || '',
        group:       r.group || '',
        round:       r.round || '',
        date:        r.date || '',
        time:        r.time || '',
        home:        r.home || '',
        away:        r.away || '',
        venue:       r.venue || '',
        status:      r.status || '',
        home_goals:  r.home_goals,
        home_points: r.home_points,
        away_goals:  r.away_goals,
        away_points: r.away_points,
      };

      // ↓ normalize short codes (e.g. "PIHC") to full names once, in memory
      out.competition = INV_COMP_CODES[out.competition] || out.competition;
      
      out.code = compCode(out.competition);

// Walkover detection
const WO_STATUS = /walkover/i;
// accept "W/O", "W / O", etc. if ever present in the team name
const WO_TAG = /\bW\s*\/\s*O\b/i;

// Trigger on either: status says Walkover OR the team name has "W/O"
const isWO = WO_STATUS.test(out.status) || WO_TAG.test(out.home) || WO_TAG.test(out.away);

if (isWO) {
  out.is_walkover = true;

  out.home = out.home.replace(/\s*\bW\s*\/\s*O\b/i, '').trim();
  out.away = out.away.replace(/\s*\bW\s*\/\s*O\b/i, '').trim();

  // 1) Prefer the explicit tag beside the team name: that side RECEIVED the W/O
  if (WO_TAG.test(String(out.home))) {
    out.walkover_winner = 'home';
  } else if (WO_TAG.test(String(out.away))) {
    out.walkover_winner = 'away';
  } else {
    // 2) Fallback: parse status like "Walkover – Murroe Boher" (giver named in status)
    const s = String(out.status).toLowerCase();
    const homeName = String(out.home).toLowerCase();
    const awayName = String(out.away).toLowerCase();

    // If status mentions the HOME club, they conceded → AWAY wins.
    if (s.includes(homeName))      out.walkover_winner = 'away';
    else if (s.includes(awayName)) out.walkover_winner = 'home';
    else                           out.walkover_winner = null; // unknown
  }
}


      // Normalise group names
      if (out.group) {
        const g = String(out.group).trim();
        const m = g.match(/(Group\s*[A-Z0-9]+)\s*$/i);
        if (m) out.group = m[1].replace(/\s+/g, ' ').trim();
        else {
          const c = String(out.competition).trim();
          out.group = g.replace(c, '').trim() || g;
        }
      }

      return attachScores(out);
    });

    const baseCount = MATCHES.length;

    // 2) Manual Knockout overlay (OUTSIDE the map)
    try {
      const r2 = await fetch(`${KO_URL}?t=${Date.now()}`, { cache:'no-store' });
      if (r2.ok) {
        const ko = await r2.json();
        const normalized = (ko.matches || ko || []).map(r => {
          const out = {
            competition: r.competition || '',
            group:       'Knockout',
            stage:       'knockout',
            round:       r.round || '',
            date:        r.date || '',
            time:        r.time || '',
            home:        r.home || '',
            away:        r.away || '',
            venue:       r.venue || '',
            status:      r.status || 'Provisional',
            home_goals:  r.home_goals,
            home_points: r.home_points,
            away_goals:  r.away_goals,
            away_points: r.away_points
          };

          // ↓ normalize here too, to keep everything consistent
          out.competition = INV_COMP_CODES[out.competition] || out.competition;
          
          out.code = compCode(out.competition);
          return attachScores(out);
        });
        MATCHES = mergeById(MATCHES, normalized);
        log('[LGH] load(): base=%d, knockout=%d, total=%d', baseCount, normalized.length, MATCHES.length);
      } else {
        warn('[LGH] KO overlay fetch not OK:', r2.status, r2.statusText);
      }
    } catch(e){
      warn('[LGH] KO overlay skipped:', e);
    }

} catch (e) {
err('[LGH] Data load threw error:', e);
// Optional but recommended fail-soft if the outer try trips:
showWarn('Live data is slow — showing last verified snapshot.');
const j = window.__LGH_BOOTSTRAP__ || {};
MATCHES = (j.matches || j || []).map(r => attachScores({
competition: r.competition, group: r.group, round: r.round,
date: r.date, time: r.time, home: r.home, away: r.away,
venue: r.venue, status: r.status,
home_goals: r.home_goals, home_points: r.home_points,
away_goals: r.away_goals, away_points: r.away_points
}));    
  }
}

  const sortRoundDate=(a,b)=> (a._rnum-b._rnum) || (a.date||'').localeCompare(b.date||'') || (a.time||'').localeCompare(b.time||'');
  const sortDateComp = (a, b) => {
  const da = a.date || '', db = b.date || '';
  if (da !== db) return da.localeCompare(db);         // date asc
  const ra = COMP_RANK[a.competition] ?? 99;
  const rb = COMP_RANK[b.competition] ?? 99;
  if (ra !== rb) return ra - rb;                       // Senior → … → Junior C
  return (a.time || '').localeCompare(b.time || '');   // time asc
};


  function buildHead(thead,isMobile,isTiny){
  if(isMobile){
    // Single Date/Time column for ALL mobile sizes (tiny & normal)
    thead.innerHTML =
      `<tr>
        <th class="rcol">R</th>
        <th class="dcol">Date/Time</th>
        <th class="match">Match</th>
        <th class="vcol">Venue</th>
      </tr>`;
  } else {
    thead.innerHTML =
      `<tr>
        <th>Round</th>
        <th class="dcol">Date</th>
        <th class="tcol">Time</th>
        <th class="match">Match</th>
        <th>Venue</th>
        <th>Status</th>
      </tr>`;
  }
}


  function rowHTML(r,isMobile,isTiny){
    const rShort=(r.round||'').replace(/^Round\s*/i,'R').replace(/\s+/g,'')||'—';
    const dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||'');
    const stShort=isResult(r.status)?'R':'F';
    const scoreMid = (/^walkover$/i.test(r.status))
  ? 'W/O'
  : ((r._homeMid && r._awayMid) ? `${r._homeMid} - ${r._awayMid}` : '—');

    const showMeta=(VIEW_MODE!=='competition');
    const meta = showMeta ? `<div class="match-meta">${esc(r.code)} · ${esc(groupShort(r.group||''))}</div>` : '';

    const homeHTML=`<span class="match-team">${esc(r.home||'')}</span>`;
    const scoreHTML=`<span class="match-score">${esc(scoreMid)}</span>`;
    const awayHTML=`<span class="match-team">${esc(r.away||'')}</span>`;
    const matchCell=`<div class="match-block">${homeHTML}${scoreHTML}${awayHTML}${meta}</div>`;

    const trAttr=`data-date="${esc(r.date||'')}"`;

    if(isMobile){
  // Three-line Date/Time: day, date, time — centred via CSS
  const parts = (dShort||'').split(' ');
  const dayLine = parts[0] || '';
  const dateLine = parts.slice(1).join(' ') || '';
  const dtHTML = `<div class="dt3">
                    <div class="dt-day">${esc(dayLine)}</div>
                    <div class="dt-date">${esc(dateLine)}</div>
                    <div class="dt-time">${esc(tShort)}</div>
                  </div>`;
  return `<tr ${trAttr}>
            <td class="rcol">${esc(rShort)}</td>
            <td class="dcol">${dtHTML}</td>
            <td class="match">${matchCell}</td>
            <td class="vcol">${esc(r.venue||'')}</td>
          </tr>`;
} else {
  return `<tr ${trAttr}>
            <td>${esc(r.round||'')}</td>
            <td class="dcol">${esc(r.date||'')}</td>
            <td class="tcol">${esc(r.time||'')}</td>
            <td class="match">${matchCell}</td>
            <td>${esc(r.venue||'')}</td>
            <td><span class="status-badge status-${esc(r.status||'')}">${esc(r.status||'')}</span></td>
          </tr>`;
}
  } // /* LGH PATCH: close rowHTML cleanly */

function buildCompetitionMenu(){
  // Limit to the seven comps (order preserved)
  const ALL = [
    "Senior Hurling Championship",
    "Premier Intermediate Hurling Championship",
    "Intermediate Hurling Championship",
    "Premier Junior A Hurling Championship",
    "Junior A Hurling Championship",
    "Junior B Hurling Championship",
    "Junior C Hurling Championship"
  ];


  // Build menu items (no groups here)
    // Build menu items
  const menu = el('comp-menu');
  menu.innerHTML = ALL.map(c => {
    const dn = DISPLAY_NAMES[c];
    // Use short label (dn.label) for dropdown; fallback to c
    const label = (dn && dn.label) ? dn.label : c;
    return `<div class="item" data-comp="${esc(c)}">${esc(label)}</div>`;
  }).join('');


  // Desired default: Senior -> Group 1
  function setCompetition(comp, push=false, suppressUrl=false){
    state.comp = comp || ALL[0];

    // Default group: Group 1 for all except PIHC (no groups)
      const meta = DISPLAY_NAMES[state.comp] || {};
      if (meta.pihc) {
        state.group = null;                       // PIHC: no groups
      } else if (meta.divisions?.length) {
        state.group = meta.divisions[0];          // JBHC: default to "City"
      } else if (meta.groups?.length) {
        state.group = meta.groups[0];             // all others with groups: default "Group 1"
      } else {
        state.group = null;
      }


    // Selected header
    const dn = DISPLAY_NAMES[state.comp];
    el('comp-selected').textContent = (dn && dn.long) ? dn.long : state.comp;

    // Rebuild matches menu/label for this comp
    rebuildMatchesMenu();
    updateTableTabVisibility();

    
    // Render matches (ensure Matches view visible)
    el('g-standings').style.display = 'none';
    document.querySelector('.matches-wrap').style.display = '';

    // Show Matches-only controls in Matches view
    const mc = document.getElementById('controls-matches');
    if (mc) mc.style.display = '';

    const onTable = document.querySelector('#group-panel .section-tabs .seg[data-view="table"].active');
    if (onTable) renderStandings(); else renderGroupTable();

    if (!suppressUrl) syncURL(push);
    LGH_ANALYTICS.viewCompetition(state.comp, state.group, onTable ? 'table' : 'matches');
  }

  // Click binding
  const compTab = el('comp-tab');
  const openMenu = ()=>{
    const rect = compTab.getBoundingClientRect();
    menu.style.top = `${rect.bottom + window.scrollY + 6}px`;
    menu.style.left = `${rect.left + window.scrollX}px`;
    menu.classList.add('open');
    menu.setAttribute('aria-hidden','false');
  };
  const closeMenu = ()=>{
    menu.classList.remove('open');
    menu.setAttribute('aria-hidden','true');
  };

  compTab.addEventListener('click', ()=>{ 
    if(menu.classList.contains('open')) closeMenu(); else openMenu();
  });

  menu.addEventListener('click', (e)=>{
    const it = e.target.closest('.item');
    if(!it) return;
    $$('#comp-menu .item').forEach(i=>i.classList.remove('active'));
    it.classList.add('active');
    const comp = it.getAttribute('data-comp');
    setCompetition(comp, true);
    closeMenu();
  });

  document.addEventListener('click', (e)=>{
    if(menu.classList.contains('open') && !menu.contains(e.target) && !compTab.contains(e.target)){
      closeMenu();
    }
  });
  window.addEventListener('resize', closeMenu, {passive:true});
  window.addEventListener('scroll', closeMenu, {passive:true});

  // Initial selection (URL overrides if present)
  let initialComp = params.comp && ALL.includes(params.comp) ? params.comp : ALL[0];
  setCompetition(initialComp, false, FIRST_LOAD_NO_QUERY);
}

function getGroupsForComp(comp){
  const meta = DISPLAY_NAMES[comp] || {};

  // PIHC: no league groups — let rebuildMatchesMenu add "PIHC" + optional "Knockout"
  if (meta.pihc) return [];

  // Build the base list first
  let groups = [];
  if (meta.divisions?.length) {
    groups = [...meta.divisions];          // e.g. City/East/West
  } else if (meta.groups?.length) {
    groups = [...meta.groups];             // e.g. Group 1/Group 2
  } else {
    // Fallback: infer from data (exclude KO rows)
    const groupsRaw = MATCHES
      .filter(m => m.competition === comp && !isKO(m))
      .map(m => m.group || '')
      .filter(Boolean);
    groups = [...new Set(groupsRaw)]
      .sort((a,b)=>a.localeCompare(b, undefined, {numeric:true}));
  }

  // Append "Knockout" if KO games exist for this competition
  if (MATCHES.some(m => m.competition === comp && isKO(m))) {
    if (!groups.includes('Knockout')) groups.push('Knockout');
  }

  return groups;
}




function setMatchesLabel(){
  const matchesLabel = el('matches-label');
  if (!matchesLabel) return;
  const meta = DISPLAY_NAMES[state.comp] || {};

  if (state.group === 'Knockout') {
    matchesLabel.textContent = 'Knockout';
  } else if (meta.pihc) {
    matchesLabel.textContent = 'PIHC';
  } else if (meta.divisions?.length) {
    matchesLabel.textContent = state.group || meta.divisions[0];
  } else {
    matchesLabel.textContent = state.group || 'Group 1';
  }
}

function updateTableTabVisibility(){
  const tableSeg   = document.querySelector('#group-panel .section-tabs .seg[data-view="table"]');
  const matchesSeg = document.querySelector('#group-panel .section-tabs .seg[data-view="matches"]');
  if (!tableSeg) return;

  const hide = (state.group === 'Knockout');
  tableSeg.style.display = hide ? 'none' : '';

  // If Table was active and we’re hiding it, switch back to Matches
  if (hide && tableSeg.classList.contains('active') && matchesSeg) {
    matchesSeg.click();
  }
}


function closeMatchesMenu(){
  const mm = el('matches-menu');
  if (!mm) return;
  mm.classList.remove('open');
  mm.setAttribute('aria-hidden','true');
}

function openMatchesMenu(){
  const trig = el('matches-seg');
  const mm = el('matches-menu');
  if (!trig || !mm) return;
  const rect = trig.getBoundingClientRect();
  mm.style.top  = `${rect.bottom + window.scrollY + 6}px`;
  mm.style.left = `${rect.left   + window.scrollX}px`;
  mm.classList.add('open');
  mm.setAttribute('aria-hidden','false');
}

// --- KO footnote helper (append under the Matches table) ---
function toggleKOFootnote(show){
  const gp = document.getElementById('group-panel');
  if (!gp) return;

  // Place the footnote immediately after the matches table wrapper
  const matchesWrap = gp.querySelector('.matches-wrap');
  if (!matchesWrap) return;

  let note = document.getElementById('ko-footnote');
  if (!note) {
    note = document.createElement('div');
    note.id = 'ko-footnote';
    note.className = 'footnote';
    note.textContent = '';
    matchesWrap.insertAdjacentElement('afterend', note);
  }
  note.style.display = show ? '' : 'none';
}


function rebuildMatchesMenu(){
  const mm = el('matches-menu');
  if (!mm) return;

  const groups = getGroupsForComp(state.comp);
  mm.innerHTML = '';

  if (!groups.length){
    // PIHC base item
    const b = document.createElement('div');
    b.className = 'item';
    b.textContent = 'PIHC';
    b.addEventListener('click', ()=>{
      state.group = null;
      setMatchesLabel();
      closeMatchesMenu();
      updateTableTabVisibility();
      renderGroupTable();
      syncURL();
    });
    mm.appendChild(b);

    // Optional Knockout for PIHC
    if (MATCHES.some(m => m.competition === state.comp && isKO(m))) {
      const k = document.createElement('div');
      k.className = 'item';
      k.textContent = 'Knockout';
      k.addEventListener('click', ()=>{
        state.group = 'Knockout';
        setMatchesLabel();
        closeMatchesMenu();
        updateTableTabVisibility(); 
        renderGroupTable();
        syncURL();
      });
      mm.appendChild(k);
    }

    state.group = state.group === 'Knockout' ? 'Knockout' : null;

  } else {
    // Normal grouped/divisional competitions
    groups.forEach(g=>{
      const b = document.createElement('div');
      b.className = 'item';
      b.textContent = g;
      b.addEventListener('click', ()=>{
        state.group = g;
        setMatchesLabel();
        closeMatchesMenu();
        updateTableTabVisibility();
        renderGroupTable();
        syncURL();
        LGH_ANALYTICS.viewCompetition(state.comp, state.group, 'matches');
      });
      mm.appendChild(b);
    });

    if (!state.group || !groups.includes(state.group)) state.group = groups[0];
  }

  setMatchesLabel();
}


// Toggle/open the Matches dropdown only when Matches view is active
(function(){
  const seg = el('matches-seg');
  if (!seg) return;
  seg.addEventListener('click', ()=>{
    const onTable = document.querySelector('#group-panel .section-tabs .seg[data-view="table"].active');
    if (onTable) return; // don't open when Table is active
    const mm = el('matches-menu');
    if (mm?.classList.contains('open')) closeMatchesMenu(); else openMatchesMenu();
  });

  // Close when clicking elsewhere, or switching tabs/views
  document.addEventListener('click', (e)=>{
    const mm = el('matches-menu');
    if (mm?.classList.contains('open') && !mm.contains(e.target) && !seg.contains(e.target)) closeMatchesMenu();
  });
})();


  
  function renderGroupTable(){
  VIEW_MODE='competition';
  const tbl=el('g-table'); const thead=tbl.tHead||tbl.createTHead(); const tbody=tbl.tBodies[0]||tbl.createTBody();
  const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches; 
  buildHead(thead,isMobile,isTiny);
  const statusEl = el('status');
  const status = statusEl ? statusEl.value : 'All';
  updateTableTabVisibility();

  // ensure visibility
  el('g-standings').style.display='none';
  document.querySelector('.matches-wrap').style.display='';

  // KO-aware filtering
  const meta = DISPLAY_NAMES[state.comp] || {};
  let rows = MATCHES.filter(r=>{
    if (state.comp && r.competition !== state.comp) return false;

    if (state.group === 'Knockout') {
      // Show ONLY knockout games when Knockout is selected
      if (!isKO(r)) return false;
    } else {
      // Hide knockout games from the league phase
      if (isKO(r)) return false;

      // For grouped comps, keep current group only
      if (!meta.pihc && state.group && (r.group || '') !== (state.group || '')) return false;
      // For PIHC (no groups): include all non-KO fixtures
    }

    if (status === 'Result')  return isResult(r.status);
    if (status === 'Fixture') return isFixture(r.status);
    return true;
  });

  // Sorting:
  // - Knockout: strict by date/time
  // - League phase: round → date → time (existing rule)
  rows = (state.group === 'Knockout')
    ? rows.sort(sortDateOnly)
    : rows.sort(sortRoundDate);

  tbody.innerHTML = rows.map(r=>rowHTML(r,isMobile,isTiny)).join('');

  // Show KO footnote only for Knockout selection (in Matches view)
  toggleKOFootnote(state.group === 'Knockout');
}

  function pointsFromGoalsPoints(g,p){ return (g==null||p==null)?null:(Number(g)||0)*3+(Number(p)||0); }

// Read a team’s numeric total (pointsFor) and goals from a match row
function _readScoreFromRow(m, side /* 'home' | 'away' */){
  const g = (side==='home') ? m.home_goals : m.away_goals;
  const p = (side==='home') ? m.home_points : m.away_points;
  const total = pointsFromGoalsPoints(g, p);
  return { total: Number(total||0), goals: Number(g||0) };
}

// --- Walkover helpers ---
const isWalkover = (m) =>
m?.is_walkover === true || /walkover/i.test(String(m?.status || ''));
function walkoverWinner(m){
  // winner side was inferred earlier into m.walkover_winner ('home'|'away'|null)
  if (!isWalkover(m)) return null;
  if (m.walkover_winner === 'home') return m.home;
  if (m.walkover_winner === 'away') return m.away;
  return null;
}
function walkoverGiver(m){
  if (!isWalkover(m)) return null;
  if (m.walkover_winner === 'home') return m.away;  // away conceded
  if (m.walkover_winner === 'away') return m.home;  // home conceded
  return null;
}

// --- TEMP: manual walkover credits for Junior C (2025 only) ---
// Structure: Group -> [ "Team1", "Team2", ... ]
const MANUAL_JC_POINTS = {
  "Group 1": [
    "Na Piarsaigh",
    "Ballybrown",
    "Monagea",
    "Garryspillane",
    "Garryspillane",
    "Patrickswell",
    "Kilteely Dromkeen",
    "Garryspillane"
  ],
  "Group 2": [
    "Crecora Manistir",
    "Dromcollogher Broadford",
    "Dromcollogher Broadford",
    "Askeaton Ballysteen Kilcornan",
    "St Kieran's",
    "St Kieran's"
  ]
};

  
// Return the winner’s team name for a scored match (null for draw/unknown)
function _winnerOf(m){
  // handle walkover earlier in renderStandings; here assume scored
  const hs = _readScoreFromRow(m,'home');
  const as = _readScoreFromRow(m,'away');
  if (hs.total > as.total) return m.home;
  if (as.total > hs.total) return m.away;
  return null;
}

// Head-to-head compare ONLY when exactly two teams are tied on points
function _h2hCompare(a, b, allResults){
  // league phase only (exclude KO), any round; pick the most recent meeting
  const games = allResults
    .filter(m =>
      ((m.home === a.team && m.away === b.team) || (m.home === b.team && m.away === a.team))
    )
    .sort((x,y) => (x.date||'').localeCompare(y.date||'') || (x.time||'').localeCompare(y.time||''));
  if (!games.length) return 0;

  const last = games[games.length - 1];

  // Walkover counts as a win for the receiver per competition rules
  if (isWalkover(last)) {
    const w = walkoverWinner(last);
    if (w === a.team) return -1;
    if (w === b.team) return  1;
    return 0;
  }

  // Scored meeting
  const w = _winnerOf(last);
  if (w === a.team) return -1;
  if (w === b.team) return  1;
  return 0;
}


// Stable compare used AFTER deciding points buckets
function _compareByPD_PF_GF(a, b){
  const pdA = (a.pf||0) - (a.pa||0);
  const pdB = (b.pf||0) - (b.pa||0);
  if (pdA !== pdB) return pdB - pdA;      // PD
  if ((a.pf||0) !== (b.pf||0)) return (b.pf||0) - (a.pf||0);  // Points For
  if ((a.gf||0) !== (b.gf||0)) return (b.gf||0) - (a.gf||0);  // Goals For
  return a.team.localeCompare(b.team);
}

  
function renderStandings(){
  // For PIHC (no groups) include all fixtures in the competition.
  // For all others, filter by the currently selected group/division.
  const meta = DISPLAY_NAMES[state.comp] || {};
  const fixtures = MATCHES.filter(r =>
    r.competition === state.comp &&
    !isKO(r) &&
    ( meta.pihc ? true : (r.group || '') === (state.group || '') )
  );

  // Hide Matches-only controls when Table view is active
  const mc = document.getElementById('controls-matches');
  if (mc) mc.style.display = 'none';

  // Seed teams
  const teams=new Map();
  for(const f of fixtures){
    if(!teams.has(f.home)) teams.set(f.home,{team:f.home,p:0,w:0,d:0,l:0,pf:0,pa:0,gf:0,ga:0,pts:0,wo_given:0});
    if(!teams.has(f.away)) teams.set(f.away,{team:f.away,p:0,w:0,d:0,l:0,pf:0,pa:0,gf:0,ga:0,pts:0,wo_given:0});
  }

  // Results only
  const results = fixtures.filter(r => isResult(r.status) || isWalkover(r));

      function miniLeagueStats(tiedTeams, results){
      const set = new Set(tiedTeams.map(t => t.team));
      // Only games between tied teams; exclude walkovers for PF/PA/GF purposes
      const games = results.filter(m => set.has(m.home) && set.has(m.away));
    
      const acc = new Map();
      for (const t of set) acc.set(t, { pf:0, pa:0, gf:0 });
      for (const m of games) {
        if (isWalkover(m)) continue; // do not inflate PF/PA/GF with W/O
        const hs = _readScoreFromRow(m,'home');
        const as = _readScoreFromRow(m,'away');
        if (hs.total == null || as.total == null) continue;
    
        const H = acc.get(m.home), A = acc.get(m.away);
        H.pf += hs.total; H.pa += as.total; H.gf += hs.goals;
        A.pf += as.total; A.pa += hs.total; A.gf += as.goals;
      }
      return (teamName) => acc.get(teamName) || { pf:0, pa:0, gf:0 };
    }
  

  for (const m of results) {
    const H = teams.get(m.home);
    const A = teams.get(m.away);

// --- Walkover: both played; award 2 pts to the pre-decided side; no PF/PA/GF/GA ---
if (isWalkover(m)) {
  H.p++; 
  A.p++;

  const winnerSide = m.walkover_winner; // must be set at load()

  if (winnerSide === 'home') {
    H.w++; H.pts += 2; A.l++;
  } else if (winnerSide === 'away') {
    A.w++; A.pts += 2; H.l++;
  } else {
    // Visible in prod so we can catch missing decisions
    err('[LGH] Walkover with unknown winnerSide (no points awarded):', m);
  }

  // Optional tiebreak stat: walkovers GIVEN by conceder
  if (winnerSide) {
    const giverName = (winnerSide === 'home') ? m.away : m.home;
    const G = teams.get(giverName);
    if (G) G.wo_given = (G.wo_given || 0) + 1;
  }
  continue;
}



    // --- Scored result path ---
    const hs = _readScoreFromRow(m,'home'); // {total, goals}
    const as = _readScoreFromRow(m,'away');

    // If no numeric scores, skip tally to avoid NaN
    if (hs.total == null || as.total == null) continue;

    H.p++; A.p++;
    H.pf += hs.total; H.pa += as.total; H.gf += hs.goals; H.ga += as.goals;
    A.pf += as.total; A.pa += hs.total; A.gf += as.goals; A.ga += hs.goals;

    if (hs.total > as.total) { H.w++; H.pts += 2; A.l++; }
    else if (as.total > hs.total) { A.w++; A.pts += 2; H.l++; }
    else { H.d++; A.d++; H.pts++; A.pts++; }
  }

    // ---- TEMP PATCH: add manual walkovers for Junior C ----
  if (state.comp === "Junior C Hurling Championship") {
    const groupFix = MANUAL_JC_POINTS[state.group] || [];
    for (const teamName of groupFix) {
      const row = teams.get(teamName);
      if (row) {
        row.pts += 2;  // each entry = +2 points
        row.w   += 1;  // and +1 win
      }
    }
  }

  
  // ---- Sort with Head-to-Head rule (two-team ties only) ----
  const all = [...teams.values()];
  // 1) Group by league points
  const byPts = new Map();
  for (const t of all){
    if (!byPts.has(t.pts)) byPts.set(t.pts, []);
    byPts.get(t.pts).push(t);
  }

  // ---- Sorting ----
const sorted = []
  .concat(...[...byPts.keys()].sort((a,b)=>b-a).map(pts=>{
    const bucket = byPts.get(pts);

    // If any of these teams has been *affected* by a walkover in league games,
    // we switch to the walkover pathway. "Affected" := any W/O involving them (given or received).
    const names = new Set(bucket.map(t => t.team));
    const woAffected = results.some(m => isWalkover(m) && (names.has(m.home) || names.has(m.away)));

    if (woAffected) {
      const mini = miniLeagueStats(bucket, results);
      bucket.sort((x,y)=>{
        // 1) Least walkovers given
        const wg = (x.wo_given||0) - (y.wo_given||0);
        if (wg !== 0) return wg;

        // 2) Mini-league PD (desc)
        const mx = mini(x.team), my = mini(y.team);
        const pdx = (mx.pf - mx.pa), pdy = (my.pf - my.pa);
        if (pdx !== pdy) return pdy - pdx;

        // 3) Mini-league PF (desc)
        if (mx.pf !== my.pf) return my.pf - mx.pf;

        // 4) Mini-league GF (desc)
        if (mx.gf !== my.gf) return my.gf - mx.gf;

        // 5) Still tied → leave alphabetical (play-off required)
        return x.team.localeCompare(y.team);
      });
      return bucket;
    }

    // --- Standard pathway ---
    if (bucket.length === 2){
      bucket.sort((a,b)=>{
        const h2h = _h2hCompare(a, b, results);
        if (h2h !== 0) return h2h;
        return _compareByPD_PF_GF(a,b);    // PD → PF → GF → name
      });
      return bucket;
    }

    // 3+ teams → PD → PF → GF → name
    bucket.sort(_compareByPD_PF_GF);
    return bucket;
  }));


  // ensure visibility
  el('g-standings').style.display='';
  document.querySelector('.matches-wrap').style.display='none';

  // Ensure the in-page standings header shows PD (the modal already has it)
  const gt = el('g-standings-table');
  if (gt) {
    const th = gt.tHead || gt.createTHead();
    // Always (re)write the header so it matches the body
    th.innerHTML = `<tr>
      <th>Team</th><th class="right">P</th><th class="right">W</th>
      <th class="right">D</th><th class="right">L</th>
      <th class="right">PD</th><th class="right">Pts</th>
    </tr>`;
  }

  const tbody=document.querySelector('#g-standings-table tbody');
  tbody.innerHTML=sorted.map(r=>`
    <tr>
      <td>${esc(r.team)}</td>
      <td class="right">${r.p||0}</td>
      <td class="right">${r.w||0}</td>
      <td class="right">${r.d||0}</td>
      <td class="right">${r.l||0}</td>
      <td class="right">${(r.pf||0)-(r.pa||0)}</td>
      <td class="right"><strong>${r.pts||0}</strong></td>
    </tr>`).join('');

  // Modal (already includes PF/PA/PD; keep your existing head)
  const mt=el('modal-standings');
  if(mt){
    if(!mt.tHead||!mt.tHead.rows.length){
      mt.createTHead().innerHTML=`<tr><th>Team</th><th class="right">P</th><th class="right">W</th><th class="right">D</th><th class="right">L</th><th class="right">PF</th><th class="right">PA</th><th class="right">PD</th><th class="right">Pts</th></tr>`;
    }
    const mb=mt.tBodies[0]||mt.createTBody();
    mb.innerHTML=sorted.map(r=>`
      <tr>
        <td>${esc(r.team)}</td>
        <td class="right">${r.p||0}</td>
        <td class="right">${r.w||0}</td>
        <td class="right">${r.d||0}</td>
        <td class="right">${r.l||0}</td>
        <td class="right">${r.pf||0}</td>
        <td class="right">${r.pa||0}</td>
        <td class="right">${(r.pf||0)-(r.pa||0)}</td>
        <td class="right"><strong>${r.pts||0}</strong></td>
      </tr>`).join('');
  }
}

 
  function syncURL(push=false){
    const sp = new URLSearchParams();
  
    // only include non-defaults so the root stays clean
    if (state.section && state.section !== 'hurling') sp.set('s', state.section);
    if (state.view    && state.view    !== 'matches') sp.set('v', state.view);
    if (state.comp)   sp.set('comp',  state.comp);
    if (state.group)  sp.set('group', state.group);
    if (state.team)   sp.set('team',  state.team);
    if (state.date)   sp.set('date',  state.date);
      // Preserve the share gate if it was enabled when the page loaded
    if (window.__LGH_SHARE_ENABLED === true) sp.set('share', '1');

  
    const q   = sp.toString();
    const url = q ? `${location.pathname}?${q}` : location.pathname;
    (push ? history.pushState : history.replaceState).call(history, null, '', url);
  }


  function currentShareURL(){ syncURL(false); return location.href; }
  function toast(msg){ const div=document.createElement('div'); div.textContent=msg; div.style.cssText='position:fixed;left:50%;transform:translateX(-50%);bottom:20px;background:#111;color:#fff;padding:8px 12px;border-radius:8px;z-index:200;opacity:.95'; document.body.appendChild(div); setTimeout(()=>div.remove(),1500); }

  document.addEventListener('click',(e)=>{
    if (e.target.closest('#btn-share')) {
      const url = currentShareURL();
      const title = 'Limerick GAA Hub';
      const text  = 'Fixtures, results & tables';
      if (navigator.share) {
        navigator.share({ title, text, url });
      } else {
        navigator.clipboard?.writeText(url);
        toast('Link copied');
      }
      LGH_ANALYTICS.clickShare('share');   // ← inside the if
    }
  
    if (e.target.closest('#btn-copy')) {
      navigator.clipboard?.writeText(currentShareURL());
      toast('Link copied');
      LGH_ANALYTICS.clickShare('copy');    // ← inside the if
    }
  });

  // Section tabs (Matches/Table)
  $$('#group-panel .section-tabs .seg').forEach(seg=>{
    seg.addEventListener('click',()=>{
      const wrap=seg.parentElement;
      wrap.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
      seg.classList.add('active');

      const showTable=seg.getAttribute('data-view')==='table';
            // 2c: keep Matches dropdown state correct when switching views

      const tblFoot = document.getElementById('table-footnote');
        if (tblFoot) tblFoot.style.display = showTable ? '' : 'none';

      
      if (showTable) {
        // Close the Matches dropdown if it’s open
        const mm = document.getElementById('matches-menu');
        if (mm) { mm.classList.remove('open'); mm.setAttribute('aria-hidden','true'); }
      } else {
        // Ensure Matches pill label is correct when returning to Matches view
        if (typeof setMatchesLabel === 'function') setMatchesLabel();
      }
      state.view=showTable?'table':'matches';


      el('g-standings').style.display=showTable?'':'none';
      document.querySelector('.matches-wrap').style.display=showTable?'none':'';

      // Keep KO footnote only when Matches is visible and Knockout selected
      toggleKOFootnote(!showTable && state.group === 'Knockout');

      
      if(showTable) renderStandings(); else renderGroupTable();
      // Only push a new URL if we’re NOT on the default (matches) view,
      // or if there were already query params in the URL.
      if (state.view !== 'matches' || location.search) {
        syncURL(true);
      } else {
        // Clean any leftover query string (if present) without adding to history
        syncURL(false);
      }

      LGH_ANALYTICS.viewCompetition(state.comp, state.group, showTable ? 'table' : 'matches');

    });
  });

  // Top nav tabs
  $$('.navtab').forEach(tab=>{
    tab.addEventListener('click',()=>{
      $$('.navtab').forEach(t=>t.classList.remove('active'));
      tab.classList.add('active');
      const name=tab.dataset.nav;
      state.section=name;
      el('panel-hurling').style.display=(name==='hurling')?'':'none';
      el('panel-football').style.display=(name==='football')?'':'none';
      el('panel-about').style.display=(name==='about')?'':'none';
      syncURL(true);
      if (name === 'about') LGH_ANALYTICS.viewAbout();
      else if (name === 'hurling') LGH_ANALYTICS.page('/hurling','Hurling – Limerick GAA Hub');
      else if (name === 'football') LGH_ANALYTICS.page('/football','Football – Limerick GAA Hub');
    });
  });

// View tabs (Competition/Team/Date)
$$('.view-tabs .vt').forEach(seg=>{
  seg.addEventListener('click',()=>{
    seg.parentElement.querySelectorAll('.seg').forEach(s=>s.classList.remove('active'));
    seg.classList.add('active');
    const target = seg.getAttribute('data-target');

    // Switch visible panel
    $$('#panel-hurling .panel').forEach(p=>p.style.display='none');
    el(target).style.display='';

    // Render target view
    if (target==='group-panel'){ 
      state.view='matches'; VIEW_MODE='competition'; 
      renderGroupTable(); 
      LGH_ANALYTICS.viewCompetition(state.comp, state.group, 'matches'); 
    }
    if (target==='by-team'){ 
      VIEW_MODE='team'; 
      renderByTeam(); 
      LGH_ANALYTICS.viewTeam(state.team||'(none)'); 
    }
    if (target==='by-date'){ 
      VIEW_MODE='date'; 
      renderByDate(); 
      LGH_ANALYTICS.viewDate(state.date||'(none)'); 
    }

    // KO footnote only on Competition view (and only when Knockout + Matches)
    toggleKOFootnote(target==='group-panel' && state.group==='Knockout');

    // 🔼 Back-to-top button: show only on Date panel
    const btnTop = el('scroll-top-btn');
    if (btnTop) btnTop.style.display = (target === 'by-date') ? 'inline-flex' : 'none';

    syncURL(true);
  });
});


// Pseudo-team placeholders to exclude from the Club dropdown
const TEAM_EXCLUDE_RE = /^(?:QF\s*Winner|SF\d*\s*Winner)$/i;
// Explicit club exclusions (exact matches only)
const CLUB_EXCLUDE = new Set([
"Adare / Ballybrown",
"Cappamore / Na Piarsaigh",
"Crecora Manister / Caherline",
"Cup SF1 Winner",
"Cup SF2 Winner",
"Feohanagh/Hospital Herbertstown",
"Knockaderry / Monaleen",
"Monaleen / Kilmallock",
"Old Christians / Garryspillane",
"Templeglantine / Killeedy"
]);


function renderByTeam(){
  VIEW_MODE='team'; state.view='team';
  const sel = el('team');

  const cleanName = s => String(s || '')
    .replace(/\(\s*W\/\s*O\s*\)/gi, '')
    .replace(/\bW\/\s*O\b/gi, '')
    .replace(/\s{2,}/g,' ')
    .trim();

  const looksLikeClub = s => {
    const x = (s || '').trim();
    if (!x) return false;
    if (/\bgroup\b/i.test(x)) return false;                                
    if (/^(winner|winners|runner|runners-?up|loser|losers)\b/i.test(x)) return false;
    if (TEAM_EXCLUDE_RE.test(x)) return false;   // NEW: hide QF/SF placeholders
    if (/^(tbc|bye)$/i.test(x)) return false;
    if (CLUB_EXCLUDE.has(x)) return false;
    return true;
  };

  const teams = [...new Set(
    MATCHES.flatMap(r => [cleanName(r.home), cleanName(r.away)]).filter(looksLikeClub)
  )].sort();

  sel.innerHTML = '<option value="">Select club…</option>' +
                  teams.map(t => `<option>${esc(t)}</option>`).join('');

  const draw = () => {
    const team = sel.value || '';
    state.team = team || null;
    syncURL();

    const tbl   = el('team-table');
    const thead = tbl.tHead || tbl.createTHead();
    const tbody = tbl.tBodies[0] || tbl.createTBody();
    const isMobile = matchMedia('(max-width:880px)').matches;
    const isTiny   = matchMedia('(max-width:400px)').matches;
    buildHead(thead, isMobile, isTiny);

    if (!team) { tbody.innerHTML=''; return; }

    const rows = MATCHES
      .filter(r => cleanName(r.home) === team || cleanName(r.away) === team)
      .sort((a,b) => resultRank(a) - resultRank(b) || sortRoundDate(a,b));

    tbody.innerHTML = rows.map(r => rowHTML(r, isMobile, isTiny)).join('');
    LGH_ANALYTICS.viewTeam(team);
  };

  sel.oninput = draw;
  addEventListener('resize', draw);

  const tbl = el('team-table');
  const thead = tbl.tHead || tbl.createTHead();
  buildHead(thead, matchMedia('(max-width:880px)').matches, matchMedia('(max-width:400px)').matches);
  tbl.tBodies[0] ? (tbl.tBodies[0].innerHTML='') : tbl.createTBody();

  if (params.team) { sel.value = params.team; sel.dispatchEvent(new Event('input')); }
}


function renderByDate(){
  VIEW_MODE='date'; state.view='date';

  const tbl   = el('date-table');
  const thead = tbl.tHead || tbl.createTHead();
  const tbody = tbl.tBodies[0] || tbl.createTBody();

  const isMobile = matchMedia('(max-width:880px)').matches;
  const isTiny   = matchMedia('(max-width:400px)').matches;
  buildHead(thead, isMobile, isTiny);

  // Strict sort: date → competition rank → time
  const rows = [...MATCHES].sort(sortDateComp);
  tbody.innerHTML = rows.map(r => rowHTML(r, isMobile, isTiny)).join('');

// Hook up the <input type="date" id="date-input">
const di = el('date-input');
if (di) {
  const scrollToDate = (ymd) => {
    state.date = ymd || null;
    syncURL();

    if (!ymd) return;
    const candidates = Array.from(tbody.querySelectorAll('tr[data-date]'));
    if (!candidates.length) return;

    let target = tbody.querySelector(`tr[data-date="${ymd}"]`);
    if (!target) {
      let chosen = null;
      for (const tr of candidates) {
        const d = tr.getAttribute('data-date') || '';
        if (d <= ymd) chosen = tr; else break;
      }
      target = chosen || candidates[candidates.length-1] || candidates[0] || null;
      if (target) {
        const td = target.getAttribute('data-date') || '';
        if (td) {
          const firstOfDate = tbody.querySelector(`tr[data-date="${td}"]`);
          if (firstOfDate) target = firstOfDate;
        }
      }
    }

    if (target) {
      target.scrollIntoView({ behavior:'smooth', block:'start' });
      target.style.outline = '2px solid var(--accent)';
      setTimeout(() => { target.style.outline = ''; }, 1500);
    }

    LGH_ANALYTICS.viewDate(ymd);
  };

  di.addEventListener('change', () => scrollToDate(di.value));

  // Deep-link: ?date=YYYY-MM-DD
  if (params.date) {
    di.value = params.date;
    di.dispatchEvent(new Event('change'));
  } else {
    // Ensure the picker has a value (fallback to today) before pre-scroll
    if (!di.value) {
      const now = new Date();
      di.value = `${now.getFullYear()}-${pad2(now.getMonth()+1)}-${pad2(now.getDate())}`;
    }
    // Prescroll to the currently selected date (usually today)
    scrollToDate(di.value);
  }
  }
}
  
  (function(){
  const btn   = el('btn-expand');
  const modal = el('standings-modal');
  const close = el('modal-close');
  const sheet = modal?.querySelector('.sheet');
  if (!btn || !modal || !close || !sheet) return;

  let lastFocused = null;
  const onKeyDown = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); }
    // Simple focus trap: keep tab focus inside the modal
    if (e.key === 'Tab') {
      const focusables = sheet.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      const list = Array.from(focusables).filter(x => !x.hasAttribute('disabled') && x.tabIndex !== -1);
      if (!list.length) return;
      const first = list[0], last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  };

  function openModal(){
    lastFocused = document.activeElement;
    modal.removeAttribute('inert');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    // Move focus inside dialog
    (close.focus?.() || sheet.focus?.());
    document.addEventListener('keydown', onKeyDown);
  }

  function closeModal(){
    // Blur anything focused in the dialog before hiding
    document.activeElement?.blur?.();
    modal.setAttribute('aria-hidden', 'true');
    modal.setAttribute('inert', '');
    document.body.style.overflow = '';
    document.removeEventListener('keydown', onKeyDown);
    // Return focus to the trigger for a11y
    lastFocused?.focus?.();
  }

  btn.addEventListener('click', openModal);
  close.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
})();


 const statusEl = el('status');
  if (statusEl) statusEl.addEventListener('input', ()=>{ renderGroupTable(); syncURL(); });

// Back to top (Date view) — wire click + set initial visibility
(function () {
  const btn = el('scroll-top-btn');
  if (!btn) return;

  // Smooth scroll
  btn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // Android/narrow UI: blur selects on change so pickers close
  (function () {
    ['team', 'status', 'date', 'date-input'].forEach(id => {
      const s = el(id);
      if (s) s.addEventListener('change', () => s.blur());
    });
  })();

  // Initial visibility based on current panel
  const datePanel = el('by-date');
  const visible = datePanel && getComputedStyle(datePanel).display !== 'none';
  btn.style.display = visible ? 'inline-flex' : 'none';
})();

   (async function(){
    await load();

     
    buildCompetitionMenu();
    if (typeof rebuildMatchesMenu === 'function') rebuildMatchesMenu();

    // Select top-level section
    const s = params.s || 'hurling';
    (function(n){ if(n) n.click(); })(document.querySelector(`.navtab[data-nav="${s}"]`));

    // Only click into non-default views when explicitly requested via params.
    if (params.v === 'table') {
      (function(n){ if(n) n.click(); })(document.querySelector('#group-panel .section-tabs .seg[data-view="table"]'));
    } else if (params.v === 'team') {
      (function(n){ if(n) n.click(); })(document.querySelector('.view-tabs .vt[data-target="by-team"]'));
    } else if (params.v === 'date') {
      (function(n){ if(n) n.click(); })(document.querySelector('.view-tabs .vt[data-target="by-date"]'));
    } else {
      // Default (matches) — render directly so the URL stays as /
      renderGroupTable();
    }
  })();

  // --- LGH Share Card: tiny public, read-only API ---
  window.LGH = window.LGH || {};
  Object.defineProperties(window.LGH, {
    state:         { get: () => state },
    matches:       { get: () => MATCHES },
    DISPLAY_NAMES: { get: () => DISPLAY_NAMES }
  });
  window.LGH.isResult = (s) => /^(res|final|walkover)/i.test(String(s||''));
  window.LGH.isKO = (m) => String(m.group||'').toLowerCase()==='knockout' || String(m.stage||'').toLowerCase()==='knockout';

// --- Keep "All / Fixtures / Results" visible only on Matches, and restore when returning ---
function updateMatchFilterVisibility() {
  const mc = document.getElementById('controls-matches');
  if (!mc) return;

  const groupPanel = document.getElementById('group-panel');
  const standingsPanel = document.getElementById('g-standings'); // table container

  const isHidden = (el) => !el || el.hidden || getComputedStyle(el).display === 'none';

  // Show control when Matches list is visible (group panel shown & standings hidden)
  const show = groupPanel && !isHidden(groupPanel) && isHidden(standingsPanel);

  mc.hidden = !show;
  mc.style.display = show ? '' : 'none';
}

// Re-evaluate whenever a view/tab button with data-target or data-view is clicked
document.addEventListener('click', (e) => {
  if (e.target.closest('[data-target]') || e.target.closest('[data-view]')) {
    setTimeout(updateMatchFilterVisibility, 0);
  }
});

// Also recompute on hash changes (deep links) and once at load end
window.addEventListener('hashchange', updateMatchFilterVisibility);
updateMatchFilterVisibility();
})();
