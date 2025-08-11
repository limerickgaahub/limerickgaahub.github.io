(function(){
  const tabs = document.querySelectorAll('.navtab');
  const panels = {
    'nav-hurling': document.getElementById('nav-hurling'),
    'nav-football': document.getElementById('nav-football'),
    'nav-about': document.getElementById('nav-about'),
  };
  function showTop(id){
    Object.values(panels).forEach(p => p && p.classList.remove('active'));
    const el = panels[id]; if(el) el.classList.add('active');
    tabs.forEach(t => t.classList.remove('active'));
    const btn = document.querySelector(`.navtab[data-nav="${id}"]`);
    if(btn) btn.classList.add('active');
  }
  tabs.forEach(t => t.addEventListener('click', ()=> showTop(t.getAttribute('data-nav'))));
  showTop('nav-hurling');
  window.LGH_ROUTER_READY = true;
})();