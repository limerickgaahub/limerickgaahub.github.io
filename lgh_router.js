// Top-level nav router (.navtab) — no conflict with existing .tab logic
(function(){
  const tabs = document.querySelectorAll('.navtab');
  const panels = {
    'nav-hurling': document.getElementById('nav-hurling'),
    'nav-football': document.getElementById('nav-football'),
    'nav-team': document.getElementById('nav-team'),
    'nav-date': document.getElementById('nav-date'),
  };
  function show(id){
    Object.values(panels).forEach(p => p && (p.classList.remove('active'), p.style.display='none'));
    const el = panels[id];
    if(el){ el.classList.add('active'); el.style.display='block'; }
    tabs.forEach(t => t.classList.remove('active'));
    const btn = document.querySelector(`.navtab[data-nav="${id}"]`);
    if(btn) btn.classList.add('active');
  }
  tabs.forEach(t => t.addEventListener('click', ()=> show(t.getAttribute('data-nav'))));
  // Initial display state
  show('nav-hurling');
})();