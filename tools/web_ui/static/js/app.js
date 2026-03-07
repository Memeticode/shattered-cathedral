/* === Sidebar navigation & shared utilities === */

function navigate(page) {
  var pages = ['home', 'playground', 'live'];
  if (pages.indexOf(page) === -1) page = 'home';
  pages.forEach(function(p) {
    var el = document.getElementById('page-' + p);
    if (el) el.style.display = (p === page) ? (p === 'playground' ? 'flex' : 'block') : 'none';
  });
  document.querySelectorAll('.nav-item').forEach(function(a) {
    a.classList.toggle('active', a.dataset.page === page);
  });
  history.replaceState(null, '', '#' + page);
}

function esc(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function setStatus(text, pulsing) {
  var el = document.getElementById('status');
  if (el) {
    el.textContent = text;
    el.classList.toggle('pulsing', !!pulsing);
  }
}

function scrollToBottom() {
  if (typeof layoutMode !== 'undefined' && layoutMode === 'page') return;
  setTimeout(function() { window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'}); }, 50);
}

function getCardTarget(gi) {
  if (typeof layoutMode !== 'undefined' && layoutMode === 'page' && typeof pageSlots !== 'undefined' && pageSlots[gi]) {
    return pageSlots[gi];
  }
  return document.getElementById('timeline');
}

/* Sidebar toggle */
document.addEventListener('DOMContentLoaded', function() {
  var toggle = document.getElementById('sidebar-toggle');
  if (toggle) {
    toggle.addEventListener('click', function() {
      document.getElementById('sidebar').classList.toggle('collapsed');
    });
  }

  /* Hash routing */
  window.addEventListener('hashchange', function() {
    navigate(location.hash.slice(1) || 'home');
  });

  /* Initial route */
  var hash = location.hash.slice(1);
  if (hash) navigate(hash);
});
