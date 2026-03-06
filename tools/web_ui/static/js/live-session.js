/* === Live session: SSE, modal, session start/continue/stop === */

/* State */
var lastCompletedIter = 0;
var iterOffset = 0;
var evtSource = null;
var sessionActive = false;
var iterationData = {};
var continueMode = false;

/* --- Modal: seed list & preview --- */

function buildSeedList() {
  var list = document.getElementById('seed-list');
  if (!list) return;
  list.innerHTML = '';
  presetKeys.forEach(function(key) {
    var item = document.createElement('div');
    item.className = 'seed-item' + (key === selectedSeed ? ' selected' : '');
    if (continueMode) item.classList.add('disabled');
    item.textContent = presetsData[key].title || key;
    item.dataset.key = key;
    if (!continueMode) {
      item.addEventListener('click', function() {
        selectedSeed = key;
        document.querySelectorAll('.seed-item').forEach(function(el) {
          el.classList.toggle('selected', el.dataset.key === key);
        });
        updatePresetPreview(key);
      });
    }
    list.appendChild(item);
  });
  updatePresetPreview(selectedSeed);
}

function updatePresetPreview(key) {
  var p = presetsData[key];
  if (!p) { p = {title: key, description: '', tags: []}; }
  var titleEl = document.getElementById('preview-title');
  var descEl = document.getElementById('preview-desc');
  var tagsEl = document.getElementById('preview-tags');
  if (titleEl) titleEl.textContent = p.title || key;
  if (descEl) descEl.textContent = p.description || '';
  if (tagsEl) {
    tagsEl.innerHTML = (p.tags || []).map(function(t) {
      return '<span class="preview-tag">' + esc(t) + '</span>';
    }).join('');
  }
}

/* --- BPM / Measures / Duration linkage --- */
var beatsPerMeasure = 4;
var _linkLock = false;

function updateDurationFromMeasures() {
  if (_linkLock) return;
  _linkLock = true;
  var bpmInput = document.getElementById('cfg-bpm');
  var measuresInput = document.getElementById('cfg-measures');
  var durationInput = document.getElementById('duration');
  if (bpmInput && measuresInput && durationInput) {
    var bpm = parseFloat(bpmInput.value) || 72;
    var measures = parseFloat(measuresInput.value) || 8;
    durationInput.value = (measures * beatsPerMeasure * 60 / bpm).toFixed(2);
  }
  _linkLock = false;
}

function updateMeasuresFromDuration() {
  if (_linkLock) return;
  _linkLock = true;
  var bpmInput = document.getElementById('cfg-bpm');
  var measuresInput = document.getElementById('cfg-measures');
  var durationInput = document.getElementById('duration');
  if (bpmInput && measuresInput && durationInput) {
    var bpm = parseFloat(bpmInput.value) || 72;
    var secs = parseFloat(durationInput.value) || 15;
    measuresInput.value = Math.max(1, Math.round(secs * bpm / (beatsPerMeasure * 60)));
  }
  _linkLock = false;
}

/* --- Modal open/close --- */

function openModal(isContinue) {
  continueMode = !!isContinue;
  var modalTitle = document.getElementById('modal-title');
  var btnStart = document.getElementById('btn-start');
  var modal = document.getElementById('start-modal');
  if (modalTitle) modalTitle.textContent = continueMode ? 'Continue Session' : 'Configure Session';
  if (btnStart) btnStart.textContent = continueMode ? 'Continue' : 'Start Session';
  buildSeedList();
  if (modal) modal.style.display = 'flex';
}

function closeModal() {
  var modal = document.getElementById('start-modal');
  if (modal) modal.style.display = 'none';
}

/* --- SSE --- */

function startSSE() {
  if (evtSource) evtSource.close();
  evtSource = new EventSource('/api/events');
  sessionActive = true;
  setLayoutToggleEnabled(false);

  var timeline = document.getElementById('timeline');
  var pageNav = document.getElementById('page-nav');
  var progressFill = document.getElementById('progress-fill');

  evtSource.addEventListener('iteration_start', function(e) {
    var d = JSON.parse(e.data);
    var gi = d.iteration + iterOffset;
    var totalGi = d.total + iterOffset;
    currentBuildIter = gi;
    totalPages = totalGi;

    var pct = ((d.iteration - 1) / d.total * 100).toFixed(0);
    if (progressFill) progressFill.style.width = pct + '%';
    setStatus('Iteration ' + gi + '/' + totalGi, true);
    iterationData[gi] = {};

    if (layoutMode === 'page') {
      var slot = document.createElement('div');
      slot.className = 'page-slot';
      slot.id = 'page-slot-' + gi;
      if (timeline) timeline.appendChild(slot);
      pageSlots[gi] = slot;
      if (pageNav) pageNav.classList.add('visible');

      var hdr = document.createElement('div');
      hdr.className = 'card card-iter';
      hdr.innerHTML = '<span class="iter-badge">Iteration ' + gi + ' / ' + totalGi + '</span><span class="iter-line"></span>';
      slot.appendChild(hdr);

      addStatusCard(gi, 'Rendering...');
      showPage(gi);
    } else {
      addIterDivider(gi, totalGi);
      addStatusCard(gi, 'Rendering...');
    }
  });

  evtSource.addEventListener('config_ready', function(e) {
    var d = JSON.parse(e.data);
    var gi = d.iteration + iterOffset;
    iterationData[gi] = iterationData[gi] || {};
    iterationData[gi].config = d.config;
    iterationData[gi].diff = d.diff;
    addConfigCard(gi, d.config, d.diff);
  });

  evtSource.addEventListener('render_complete', function(e) {
    var d = JSON.parse(e.data);
    var gi = d.iteration + iterOffset;
    iterationData[gi] = iterationData[gi] || {};
    iterationData[gi].wav_url = d.wav_url;
    removeStatusCard(gi);
    addAudioCard(gi, d.wav_url);
    setStatus('Iteration ' + gi + ' \u2014 Analyzing...', true);
  });

  evtSource.addEventListener('metrics_ready', function(e) {
    var d = JSON.parse(e.data);
    var gi = d.iteration + iterOffset;
    iterationData[gi] = iterationData[gi] || {};
    iterationData[gi].metrics = d.metrics;
    updateAudioMetrics(gi, d.metrics);
  });

  evtSource.addEventListener('evaluation_ready', function(e) {
    var d = JSON.parse(e.data);
    var gi = d.iteration + iterOffset;
    iterationData[gi] = iterationData[gi] || {};
    iterationData[gi].commentary = d.commentary;
    iterationData[gi].critique = d.critique;
    iterationData[gi].rationale = d.rationale;
    iterationData[gi].plan = d.plan;
    addThoughtCard(gi, d.commentary, d.critique, d.rationale, d.plan);
    setStatus('Iteration ' + gi + ' \u2014 Complete', false);
    completedPages.add(gi);
    if (layoutMode === 'page') updateNavControls();
  });

  evtSource.addEventListener('visualization_ready', function(e) {
    var d = JSON.parse(e.data);
    var gi = d.iteration + iterOffset;
    iterationData[gi] = iterationData[gi] || {};
    iterationData[gi].png_url = d.png_url;
    addVizToAudioCard(gi, d.png_url);
  });

  evtSource.addEventListener('error_event', function(e) {
    var d = JSON.parse(e.data);
    var gi = d.iteration + iterOffset;
    removeStatusCard(gi);
    addErrorCard(gi, d.error || 'Unknown error');
    setStatus('Error in iteration ' + gi, false);
  });

  evtSource.addEventListener('session_complete', function(e) {
    var d = JSON.parse(e.data);
    lastCompletedIter = d.iteration + iterOffset;
    if (progressFill) progressFill.style.width = '100%';
    setStatus('Session complete (' + lastCompletedIter + ' iterations)', false);
    sessionActive = false;
    var btnStop = document.getElementById('btn-stop');
    var btnContinue = document.getElementById('btn-continue');
    if (btnStop) btnStop.style.display = 'none';
    if (btnContinue) btnContinue.style.display = '';
    setLayoutToggleEnabled(true);
    evtSource.close();
    evtSource = null;
    if (layoutMode === 'page') updateNavControls();
  });

  evtSource.onerror = function() {
    if (sessionActive) setStatus('Connection lost \u2014 reconnecting...', true);
  };
}

/* --- Wire up all event listeners on DOMContentLoaded --- */
document.addEventListener('DOMContentLoaded', function() {
  var btnOpenModal = document.getElementById('btn-open-modal');
  var modal = document.getElementById('start-modal');
  var modalCloseBtn = document.getElementById('modal-close');
  var btnStart = document.getElementById('btn-start');
  var btnStop = document.getElementById('btn-stop');
  var btnContinue = document.getElementById('btn-continue');
  var bpmInput = document.getElementById('cfg-bpm');
  var measuresInput = document.getElementById('cfg-measures');
  var durationInput = document.getElementById('duration');
  var configFileInput = document.getElementById('input-config-file');

  if (btnOpenModal) btnOpenModal.addEventListener('click', function() { openModal(false); });
  if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
  if (modal) modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });

  if (bpmInput) bpmInput.addEventListener('input', updateDurationFromMeasures);
  if (measuresInput) measuresInput.addEventListener('input', updateDurationFromMeasures);
  if (durationInput) durationInput.addEventListener('input', updateMeasuresFromDuration);

  if (configFileInput) {
    configFileInput.addEventListener('change', function(e) {
      var file = e.target.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function(ev) {
        var ta = document.getElementById('input-config');
        if (ta) ta.value = ev.target.result;
      };
      reader.readAsText(file);
    });
  }

  if (btnStop) {
    btnStop.addEventListener('click', function() {
      btnStop.disabled = true;
      setStatus('Stopping...', false);
    });
  }

  if (btnContinue) {
    btnContinue.addEventListener('click', function() { openModal(true); });
  }

  if (btnStart) {
    btnStart.addEventListener('click', function() {
      var provider = (document.getElementById('ai-provider') || {}).value || 'anthropic';
      var iterations = parseInt((document.getElementById('iter-count') || {}).value) || 5;
      var duration = parseFloat((document.getElementById('duration') || {}).value) || 15;
      var bpm = parseInt((document.getElementById('cfg-bpm') || {}).value) || 72;
      var measures = parseInt((document.getElementById('cfg-measures') || {}).value) || 8;
      var visualize = (document.getElementById('cb-visualize') || {}).checked !== false;
      var normalize = !!(document.getElementById('cb-normalize') || {}).checked;
      var userPrompt = ((document.getElementById('user-prompt') || {}).value || '').trim() || null;
      var inputConfigStr = ((document.getElementById('input-config') || {}).value || '').trim();
      var inputConfig = null;
      if (inputConfigStr) {
        try { inputConfig = JSON.parse(inputConfigStr); }
        catch(e) { setStatus('Invalid JSON in input config: ' + e.message, false); return; }
      }

      closeModal();
      var sessionBar = document.getElementById('session-bar');
      var progressFill = document.getElementById('progress-fill');
      if (sessionBar) sessionBar.style.display = 'flex';
      if (btnStop) { btnStop.style.display = ''; btnStop.disabled = false; }
      if (btnContinue) btnContinue.style.display = 'none';
      if (progressFill) progressFill.style.width = '0%';

      if (continueMode) {
        iterOffset = lastCompletedIter;
        fetch('/api/continue', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({provider: provider, iterations: iterations, duration: duration,
                                bpm: bpm, measures: measures,
                                visualize: visualize, normalize: normalize,
                                user_prompt: userPrompt})
        }).then(function(r) { return r.json(); }).then(function(d) {
          if (d.status === 'started') {
            setStatus('Continuing...', true);
            startSSE();
          } else {
            setStatus('Error: ' + (d.error || 'failed to continue'), false);
            if (btnContinue) btnContinue.style.display = '';
            if (btnStop) btnStop.style.display = 'none';
          }
        }).catch(function(err) {
          setStatus('Error: ' + err.message, false);
          if (btnContinue) btnContinue.style.display = '';
          if (btnStop) btnStop.style.display = 'none';
        });
      } else {
        iterationData = {};
        iterOffset = 0;
        lastCompletedIter = 0;
        pageSlots = {};
        completedPages = new Set();
        currentPage = 0;
        totalPages = 0;
        currentBuildIter = 0;

        var welcome = document.getElementById('welcome');
        var timeline = document.getElementById('timeline');
        var pageNav = document.getElementById('page-nav');
        if (welcome) welcome.remove();
        if (timeline) timeline.innerHTML = '';
        var navDots = document.getElementById('nav-dots');
        if (navDots) navDots.innerHTML = '';
        if (pageNav) pageNav.classList.toggle('visible', false);

        fetch('/api/start', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({seed: selectedSeed, provider: provider,
                                iterations: iterations, duration: duration,
                                bpm: bpm, measures: measures,
                                visualize: visualize, normalize: normalize,
                                user_prompt: userPrompt,
                                input_config: inputConfig})
        }).then(function(r) { return r.json(); }).then(function(d) {
          if (d.status === 'started') {
            setStatus('Starting...', true);
            startSSE();
          } else {
            setStatus('Error: ' + (d.error || 'failed to start'), false);
            if (btnStop) btnStop.style.display = 'none';
          }
        }).catch(function(err) {
          setStatus('Error: ' + err.message, false);
          if (btnStop) btnStop.style.display = 'none';
        });
      }
    });
  }
});
