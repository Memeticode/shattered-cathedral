/* === Layout mode (scroll/page) and page navigation === */

/* State (shared with live-session.js) */
var layoutMode = localStorage.getItem('sc_layout_mode') || 'scroll';
var pageSlots = {};
var completedPages = new Set();
var currentPage = 0;
var totalPages = 0;
var currentBuildIter = 0;

function setLayoutMode(mode) {
  layoutMode = mode;
  localStorage.setItem('sc_layout_mode', mode);
  var btnScroll = document.getElementById('btn-layout-scroll');
  var btnPage = document.getElementById('btn-layout-page');
  var timeline = document.getElementById('timeline');
  var pageNav = document.getElementById('page-nav');
  if (btnScroll) btnScroll.classList.toggle('active', mode === 'scroll');
  if (btnPage) btnPage.classList.toggle('active', mode === 'page');
  if (timeline) timeline.classList.toggle('page-mode', mode === 'page');
  if (pageNav) pageNav.classList.toggle('visible', mode === 'page' && totalPages > 0);
  if (mode === 'page' && currentPage > 0) showPage(currentPage);
}

function setLayoutToggleEnabled(enabled) {
  var btnScroll = document.getElementById('btn-layout-scroll');
  var btnPage = document.getElementById('btn-layout-page');
  if (btnScroll) btnScroll.disabled = !enabled;
  if (btnPage) btnPage.disabled = !enabled;
}

function showPage(gi) {
  currentPage = gi;
  Object.entries(pageSlots).forEach(function(entry) {
    entry[1].classList.toggle('active', parseInt(entry[0]) === gi);
  });
  updateNavControls();
}

function updateNavControls() {
  var counter = document.getElementById('nav-counter');
  var prev = document.getElementById('nav-prev');
  var next = document.getElementById('nav-next');
  if (counter) counter.textContent = 'Step ' + currentPage + ' / ' + totalPages;
  if (prev) prev.disabled = (currentPage <= 1);
  var nextExists = pageSlots[currentPage + 1] !== undefined;
  if (next) next.disabled = !nextExists;
  updateNavDots();
}

function updateNavDots() {
  var dots = document.getElementById('nav-dots');
  if (!dots) return;
  dots.innerHTML = '';
  var keys = Object.keys(pageSlots).map(Number).sort(function(a,b){return a-b;});
  keys.forEach(function(gi) {
    var dot = document.createElement('button');
    dot.className = 'page-dot';
    if (completedPages.has(gi)) dot.classList.add('done');
    if (gi === currentPage) dot.classList.add('current');
    if (gi === currentBuildIter && !completedPages.has(gi)) dot.classList.add('live');
    dot.addEventListener('click', function() { showPage(gi); });
    dots.appendChild(dot);
  });
}

/* Wire up layout buttons and page nav on DOMContentLoaded */
document.addEventListener('DOMContentLoaded', function() {
  var btnScroll = document.getElementById('btn-layout-scroll');
  var btnPage = document.getElementById('btn-layout-page');
  if (btnScroll) {
    btnScroll.addEventListener('click', function() {
      if (!this.disabled) setLayoutMode('scroll');
    });
  }
  if (btnPage) {
    btnPage.addEventListener('click', function() {
      if (!this.disabled) setLayoutMode('page');
    });
  }

  var navPrev = document.getElementById('nav-prev');
  var navNext = document.getElementById('nav-next');
  if (navPrev) {
    navPrev.addEventListener('click', function() {
      if (currentPage > 1) showPage(currentPage - 1);
    });
  }
  if (navNext) {
    navNext.addEventListener('click', function() {
      if (pageSlots[currentPage + 1]) showPage(currentPage + 1);
    });
  }

  /* Apply initial layout mode */
  setLayoutMode(layoutMode);
});
