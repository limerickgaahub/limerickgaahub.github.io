(function(){
  if(typeof DATA === 'undefined'){ console.warn('LGH: DATA missing'); return; }
  const pad2=n=>String(n).padStart(2,'0'), day3=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const fmtDateShort=iso=>{ if(!iso) return ''; const d=new Date(iso+'T00:00:00'); return `${day3[d.getDay()]} ${pad2(d.getDate())}/${pad2(d.getMonth()+1)}`; };
  const fmtTimeShort=t=>{ if(!t) return ''; const m=t.match(/^(\d{1,2}):(\d{2})/); return m?`${pad2(m[1])}${m[2]}`:t; };
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const score=(g,p)=> (g==null||p==null)?'':`${g}-${p}`;
  const NDATA2 = DATA.map(d=>({...d, home_score:score(d.home_goals,d.home_points), away_score:score(d.away_goals,d.away_points)}));
  const sportOf=r=>/football/i.test(r.group||'')?'Football':'Hurling';
  const toMillis=r=> new Date((r.date||'')+'T'+(r.time||'00:00')).getTime();

  // By Team
  (function(){
    const sel=document.getElementById('team2'), tbl=document.getElementById('team-table');
    if(!sel||!tbl) return;
    const teams=[...new Set(NDATA2.flatMap(r=>[r.home_team,r.away_team]).filter(Boolean))].sort();
    sel.innerHTML='<option value="">Select team…</option>'+teams.map(t=>`<option>${t}</option>`).join('');
    function render(){
      const team=sel.value||''; const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches;
      const thead=tbl.querySelector('thead');
      if(isMobile){
        thead.innerHTML=isTiny?'<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>':'<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>';
      } else {
        thead.innerHTML='<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Home</th><th class="right">H</th><th>Away</th><th class="right">A</th><th>Venue</th><th>Referee</th><th>Status</th></tr>';
      }
      const rows=NDATA2.filter(r=>!team||r.home_team===team||r.away_team===team).sort((a,b)=>toMillis(a)-toMillis(b));
      tbl.querySelector('tbody').innerHTML=rows.map(r=>{
        const st=r.status||'', rShort=(r.round||'').replace(/^Round\s*/i,'R')||'—', dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||''), venue=esc(r.venue||''), scoreMid=(r.home_score&&r.away_score)?esc(r.home_score+' — '+r.away_score):'—', stShort=st.startsWith('R')?'R':'F';
        if(isMobile){
          if(isTiny){
            const dt=`${dShort} ${tShort}`.trim();
            return `<tr><td class="rcol">${esc(rShort)}</td><td class="dcol">${esc(dt)}</td><td class="match"><div class="match-block"><span class="match-team">${esc(r.home_team||'')}</span><span class="match-score">${scoreMid}</span><span class="match-team">${esc(r.away_team||'')}</span></div></td><td class="vcol"><span class="venue-ellipsis" title="${venue}">${venue}</span></td><td class="stcol">${stShort}</td></tr>`;
          } else {
            return `<tr><td class="rcol">${esc(rShort)}</td><td class="dcol">${esc(dShort)}</td><td class="tcol">${esc(tShort)}</td><td class="match"><div class="match-block"><span class="match-team">${esc(r.home_team||'')}</span><span class="match-score">${scoreMid}</span><span class="match-team">${esc(r.away_team||'')}</span></div></td><td class="vcol"><span class="venue-ellipsis" title="${venue}">${venue}</span></td><td class="stcol">${stShort}</td></tr>`;
          }
        } else {
          return `<tr><td>${esc(r.round||'')}</td><td class="dcol">${esc(r.date||'')}</td><td class="tcol">${esc(r.time||'')}</td><td>${esc(r.home_team||'')}</td><td class="right">${esc(r.home_score||'')}</td><td>${esc(r.away_team||'')}</td><td class="right">${esc(r.away_score||'')}</td><td>${venue}</td><td>${esc(r.referee||'')}</td><td><span class="status-badge status-${st}">${esc(st)}</span></td></tr>`;
        }
      }).join('');
    }
    sel.addEventListener('input', render); addEventListener('resize', render); render();
  })();

  // By Date
  (function(){
    const sel=document.getElementById('date-sport'), tbl=document.getElementById('date-table');
    if(!sel||!tbl) return;
    function render(){
      const sport=sel.value||'Hurling'; const isMobile=matchMedia('(max-width:880px)').matches; const isTiny=matchMedia('(max-width:400px)').matches;
      const thead=tbl.querySelector('thead');
      if(isMobile){
        thead.innerHTML=isTiny?'<tr><th class="rcol">R</th><th class="dcol">Date/Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>':'<tr><th class="rcol">R</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Match</th><th class="vcol">Venue</th><th class="stcol">S</th></tr>';
      } else {
        thead.innerHTML='<tr><th>Round</th><th class="dcol">Date</th><th class="tcol">Time</th><th>Home</th><th class="right">H</th><th>Away</th><th class="right">A</th><th>Venue</th><th>Referee</th><th>Status</th></tr>';
      }
      const rows=NDATA2.filter(r=>sportOf(r)===sport).sort((a,b)=>toMillis(a)-toMillis(b));
      tbl.querySelector('tbody').innerHTML=rows.map(r=>{
        const st=r.status||'', rShort=(r.round||'').replace(/^Round\s*/i,'R')||'—', dShort=fmtDateShort(r.date), tShort=fmtTimeShort(r.time||''), venue=esc(r.venue||''), scoreMid=(r.home_score&&r.away_score)?esc(r.home_score+' — '+r.away_score):'—', stShort=st.startsWith('R')?'R':'F';
        if(isMobile){
          if(isTiny){
            const dt=`${dShort} ${tShort}`.trim();
            return `<tr><td class="rcol">${esc(rShort)}</td><td class="dcol">${esc(dt)}</td><td class="match"><div class="match-block"><span class="match-team">${esc(r.home_team||'')}</span><span class="match-score">${scoreMid}</span><span class="match-team">${esc(r.away_team||'')}</span></div></td><td class="vcol"><span class="venue-ellipsis" title="${venue}">${venue}</span></td><td class="stcol">${stShort}</td></tr>`;
          } else {
            return `<tr><td class="rcol">${esc(rShort)}</td><td class="dcol">${esc(dShort)}</td><td class="tcol">${esc(tShort)}</td><td class="match"><div class="match-block"><span class="match-team">${esc(r.home_team||'')}</span><span class="match-score">${scoreMid}</span><span class="match-team">${esc(r.away_team||'')}</span></div></td><td class="vcol"><span class="venue-ellipsis" title="${venue}">${venue}</span></td><td class="stcol">${stShort}</td></tr>`;
          }
        } else {
          return `<tr><td>${esc(r.round||'')}</td><td class="dcol">${esc(r.date||'')}</td><td class="tcol">${esc(r.time||'')}</td><td>${esc(r.home_team||'')}</td><td class="right">${esc(r.home_score||'')}</td><td>${esc(r.away_team||'')}</td><td class="right">${esc(r.away_score||'')}</td><td>${venue}</td><td>${esc(r.referee||'')}</td><td><span class="status-badge status-${st}">${esc(st)}</span></td></tr>`;
        }
      }).join('');
    }
    sel.addEventListener('input', render); addEventListener('resize', render); render();
  })();
  window.LGH_EXTRA_READY = true;
})();