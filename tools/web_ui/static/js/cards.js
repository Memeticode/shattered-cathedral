/* === Card builder functions for the live dashboard === */

function addIterDivider(iter, total) {
  var el = document.createElement('div');
  el.className = 'card card-iter';
  el.innerHTML = '<span class="iter-badge">Iteration ' + iter + ' / ' + total + '</span><span class="iter-line"></span>';
  getCardTarget(iter).appendChild(el);
}

function addStatusCard(iter, text) {
  var el = document.createElement('div');
  el.className = 'card card-status';
  el.id = 'status-' + iter;
  el.innerHTML = '<span class="spinner"></span>' + esc(text);
  getCardTarget(iter).appendChild(el);
  scrollToBottom();
  return el;
}

function removeStatusCard(iter) {
  var el = document.getElementById('status-' + iter);
  if (el) el.remove();
}

function addConfigCard(iter, config, diff) {
  var el = document.createElement('div');
  el.className = 'card card-config';
  var bodyId = 'cfg-body-' + iter;
  var arrowId = 'cfg-arrow-' + iter;

  var summary = 'Baseline';
  if (diff && diff.length > 0) {
    var changed = diff.filter(function(c) { return c.action === 'changed'; }).length;
    var added = diff.filter(function(c) { return c.action === 'added'; }).length;
    var removed = diff.filter(function(c) { return c.action === 'removed'; }).length;
    var parts = [];
    if (changed) parts.push(changed + ' changed');
    if (added) parts.push(added + ' added');
    if (removed) parts.push(removed + ' removed');
    summary = parts.join(', ');
  }

  var diffHtml = '';
  if (diff && diff.length > 0) {
    diffHtml = diff.map(function(ch) {
      var oldStr = ch.old !== null && ch.old !== undefined ? JSON.stringify(ch.old) : '(none)';
      var newStr = ch['new'] !== null && ch['new'] !== undefined ? JSON.stringify(ch['new']) : '(removed)';
      return '<div class="diff-row">' +
        '<span class="path">' + esc(ch.path) + '</span>' +
        '<span class="old-val">' + esc(oldStr) + '</span>' +
        '<span class="arrow">&rarr;</span>' +
        '<span class="new-val">' + esc(newStr) + '</span></div>';
    }).join('');
  } else {
    diffHtml = '<div class="diff-baseline">Baseline config &mdash; no previous iteration to compare</div>';
  }

  var configPreId = 'cfg-pre-' + iter;
  var configBtnId = 'cfg-btn-' + iter;
  var exportBtnId = 'cfg-export-' + iter;
  el.innerHTML =
    '<div class="config-header" id="cfg-hdr-' + iter + '">' +
      '<span class="config-arrow" id="' + arrowId + '">&#9656;</span>' +
      '<span class="card-label">Config</span>' +
      '<span class="config-summary">' + esc(summary) + '</span>' +
    '</div>' +
    '<div class="config-body" id="' + bodyId + '">' +
      diffHtml +
      '<div style="display:flex;gap:8px;margin:6px 0">' +
        '<button class="config-expand" id="' + configBtnId + '">Show full config</button>' +
        '<button class="config-expand" id="' + exportBtnId + '">Export config</button>' +
      '</div>' +
      '<pre class="config-pre" id="' + configPreId + '">' + esc(JSON.stringify(config, null, 2)) + '</pre>' +
    '</div>';

  getCardTarget(iter).appendChild(el);

  document.getElementById('cfg-hdr-' + iter).addEventListener('click', function() {
    var body = document.getElementById(bodyId);
    var arrow = document.getElementById(arrowId);
    body.classList.toggle('open');
    arrow.classList.toggle('open');
  });
  document.getElementById(configBtnId).addEventListener('click', function() {
    var pre = document.getElementById(configPreId);
    pre.classList.toggle('open');
    this.textContent = pre.classList.contains('open') ? 'Hide config' : 'Show full config';
  });
  document.getElementById(exportBtnId).addEventListener('click', function() {
    var blob = new Blob([JSON.stringify(config, null, 2)], {type: 'application/json'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'config_iter_' + iter + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  });

  var pianoHtml = renderPianoRoll(config);
  if (pianoHtml) {
    var rollDiv = document.createElement('div');
    rollDiv.innerHTML = pianoHtml;
    document.getElementById(bodyId).appendChild(rollDiv.firstChild);
  }
  scrollToBottom();
  return el;
}

function addAudioCard(iter, wavUrl) {
  var el = document.createElement('div');
  el.className = 'card card-audio';
  el.id = 'audio-card-' + iter;
  el.innerHTML = '<div class="card-label">Audio &mdash; Iteration ' + iter + '</div>' +
    '<div class="audio-row">' +
      '<div class="audio-left">' +
        '<audio controls preload="auto" src="' + wavUrl + '"></audio>' +
        '<div class="metrics-row" id="metrics-row-' + iter + '"></div>' +
      '</div>' +
      '<div class="viz-slot" id="viz-slot-' + iter + '"></div>' +
    '</div>';

  var audioPlayer = document.getElementById('audio-player');
  var cardAudio = el.querySelector('audio');
  cardAudio.addEventListener('play', function() {
    if (audioPlayer) {
      audioPlayer.src = wavUrl;
      audioPlayer.currentTime = cardAudio.currentTime;
      audioPlayer.play().catch(function(){});
    }
  });

  getCardTarget(iter).appendChild(el);
  scrollToBottom();
  return el;
}

function updateAudioMetrics(iter, m) {
  var row = document.getElementById('metrics-row-' + iter);
  if (!row) return;
  row.innerHTML =
    '<span class="m-item">RMS <span class="m-val">' + (m.rms != null ? m.rms.toFixed(4) : '?') + '</span></span>' +
    '<span class="m-item">dBFS <span class="m-val">' + (m.dbfs != null ? m.dbfs.toFixed(1) : '?') + '</span></span>' +
    '<span class="m-item">LUFS <span class="m-val">' + (m.lufs != null ? m.lufs.toFixed(1) : '?') + '</span></span>' +
    '<span class="m-item">Centroid <span class="m-val">' + (m.spectral_centroid != null ? Math.round(m.spectral_centroid) + ' Hz' : '?') + '</span></span>' +
    '<span class="m-item">Spread <span class="m-val">' + (m.spectral_spread != null ? Math.round(m.spectral_spread) + ' Hz' : '?') + '</span></span>';
}

function addVizToAudioCard(iter, pngUrl) {
  var slot = document.getElementById('viz-slot-' + iter);
  if (!slot) return;
  slot.innerHTML = '<img class="viz-img" src="' + pngUrl + '?t=' + Date.now() + '" alt="waveform/spectrogram"/>';
  scrollToBottom();
}

function addThoughtCard(iter, commentary, critique, rationale, plan) {
  var el = document.createElement('div');
  el.className = 'card card-thought';
  var html = '<div class="card-label">Critique</div>';
  if (commentary) html += '<div class="commentary">' + esc(commentary) + '</div>';
  if (critique) html += '<div class="critique-label">Issues</div><div class="critique">' + esc(critique) + '</div>';
  if (rationale) html += '<div class="rationale">' + esc(rationale) + '</div>';
  if (plan) html += '<div class="plan-label">Direction</div><div class="plan">' + esc(plan) + '</div>';
  el.innerHTML = html;
  getCardTarget(iter).appendChild(el);
  scrollToBottom();
  return el;
}

function addErrorCard(iter, error) {
  var el = document.createElement('div');
  el.className = 'card card-error';
  el.innerHTML = '<div class="card-label">Error</div><div>' + esc(error) + '</div>';
  getCardTarget(iter).appendChild(el);
  scrollToBottom();
}
