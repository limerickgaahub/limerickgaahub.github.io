// Top-level nav and Hurling sub-tabs
(function(){
  // Top-level
  const tabs = document.querySelectorAll('.navtab');
  const panels = {
    'nav-hurling': document.getElementById('nav-hurling'),
    'nav-football': document.getElementById('nav-football'),
    'nav-about': document.getElementById('nav-about'),
  };
  function showTop(id){
    Object.values(panels).forEach(p => p && p.classList.remove('active'));
    const el = panels[id];
    if(el){ el.classList.add('active'); }
    tabs.forEach(t => t.classList.remove('active'));
    const btn = document.querySelector(`.navtab[data-nav="${id}"]`);
    if(btn) btn.classList.add('active');
  }
  tabs.forEach(t => t.addEventListener('click', ()=> showTop(t.getAttribute('data-nav'))));
  showTop('nav-hurling');

  // Hurling sub-tabs
  const hTabs = document.querySelectorAll('#h-tabs .htab');
  const hPanels = {
    'h-grades': document.getElementById('h-grades'),
    'h-team': document.getElementById('h-team'),
    'h-date': document.getElementById('h-date'),
  };
  function showH(id){
    Object.values(hPanels).forEach(p => p && p.classList.remove('active'));
    const el = hPanels[id];
    if(el){ el.classList.add('active'); }
    hTabs.forEach(t => t.classList.remove('active'));
    const btn = document.querySelector(`#h-tabs .htab[data-hpanel="${id}"]`);
    if(btn) btn.classList.add('active');
  }
  hTabs.forEach(t => t.addEventListener('click', ()=> showH(t.getAttribute('data-hpanel'))));
  showH('h-grades');

  window.LGH_ROUTER_READY = true;
})();