// Top-level nav router (.navtab) — targets .navpanel (no clash with .panel)
(function(){
  const tabs = document.querySelectorAll('.navtab');
  const panels = {
    'nav-hurling': document.getElementById('nav-hurling'),
    'nav-football': document.getElementById('nav-football'),
    'nav-team': document.getElementById('nav-team'),
    'nav-date': document.getElementById('nav-date'),
  };
  function show(id){
    Object.values(panels).forEach(p => p && p.classList.remove('active'));
    const el = panels[id];
    if(el){ el.classList.add('active'); }
    tabs.forEach(t => t.classList.remove('active'));
    const btn = document.querySelector(`.navtab[data-nav="${id}"]`);
    if(btn) btn.classList.add('active');
  }
  tabs.forEach(t => t.addEventListener('click', ()=> show(t.getAttribute('data-nav'))));
  // Initial display state
  show('nav-hurling');
})();