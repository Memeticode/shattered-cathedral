/* ================================================================
   DAW Transport  –  global config sync, play/render, metronome
   ================================================================ */

const DAWTransport = (() => {
  let bpmIn, measuresIn, statusEl;
  let audioEl, playerEl, renderTimeEl;
  let projectNameIn, descriptionIn, metronomeIn;
  let playBtn;
  let metronomeCtx = null;
  let metronomeInterval = null;
  let _isPlaying = false;

  function init() {
    bpmIn = document.getElementById('daw-bpm');
    measuresIn = document.getElementById('daw-measures');
    statusEl = document.getElementById('daw-status');
    audioEl = document.getElementById('daw-audio');
    playerEl = document.getElementById('daw-player');
    renderTimeEl = document.getElementById('daw-render-time');
    projectNameIn = document.getElementById('daw-project-name');
    descriptionIn = document.getElementById('daw-description');
    metronomeIn = document.getElementById('daw-metronome');
    playBtn = document.getElementById('daw-play-all');

    bpmIn?.addEventListener('change', syncFromInputs);
    measuresIn?.addEventListener('change', syncFromInputs);
    projectNameIn?.addEventListener('change', () => {
      DAW.global.projectName = projectNameIn.value || 'Untitled';
    });
    descriptionIn?.addEventListener('change', () => {
      DAW.global.description = descriptionIn.value || '';
    });
    metronomeIn?.addEventListener('change', () => {
      DAW.metronome = metronomeIn.checked;
    });

    playBtn?.addEventListener('click', () => {
      if (_isPlaying) stopAll();
      else playAll();
    });

    document.getElementById('daw-export')?.addEventListener('click', exportConfig);
    document.getElementById('daw-json-toggle')?.addEventListener('click', toggleJson);
    document.getElementById('daw-json-apply')?.addEventListener('click', applyJson);
    document.getElementById('daw-json-close')?.addEventListener('click', () => {
      document.getElementById('daw-json-overlay').style.display = 'none';
    });

    DAW.on('layers', syncToInputs);
    DAW.on('render', syncToInputs);
    syncToInputs();
  }

  function syncFromInputs() {
    DAW.global.bpm = parseInt(bpmIn?.value) || 72;
    DAW.global.measures = parseInt(measuresIn?.value) || 8;
    DAW.notify('notes');
  }

  function syncToInputs() {
    if (bpmIn) bpmIn.value = DAW.global.bpm;
    if (measuresIn) measuresIn.value = DAW.global.measures;
    if (projectNameIn) projectNameIn.value = DAW.global.projectName || 'Untitled';
    if (descriptionIn) descriptionIn.value = DAW.global.description || '';
    if (metronomeIn) metronomeIn.checked = DAW.metronome;
  }

  function setStatus(text, rendering) {
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.className = 'transport-status' + (rendering ? ' rendering' : '');
    }
  }

  function updatePlayButton() {
    if (!playBtn) return;
    playBtn.innerHTML = _isPlaying ? '&#9632; Stop' : '&#9654; Play';
    playBtn.classList.toggle('transport-playing', _isPlaying);
  }

  /* ----- play/stop ----- */

  async function playAll() {
    if (_isPlaying) return;

    const config = DAW.toConfig();
    if (!config.layers.length) {
      setStatus('No layers');
      return;
    }

    // If clean and cached, play directly
    if (!DAW._dirty && DAW._cachedMixUrl) {
      console.log('[DAW] Playing cached audio:', DAW._cachedMixUrl);
      audioEl.src = DAW._cachedMixUrl;
      audioEl.load();
      audioEl.play().catch(err => {
        console.error('[DAW] Audio play failed:', err);
        setStatus('Playback error');
        const errEl = document.getElementById('daw-error');
        if (errEl) errEl.textContent = 'Playback failed: ' + err.message;
      });
      if (playerEl) playerEl.style.display = '';
      _isPlaying = true;
      updatePlayButton();
      DAWLayers.startPlayheadLoop();
      return;
    }

    // Otherwise render first
    await renderAll();
  }

  function stopAll() {
    _isPlaying = false;
    updatePlayButton();
    DAWLayers.stopPlayback();
  }

  function onPlaybackEnded() {
    _isPlaying = false;
    updatePlayButton();
  }

  /* ----- render ----- */

  async function renderAll() {
    const config = DAW.toConfig();
    if (!config.layers.length) {
      setStatus('No layers to render');
      return;
    }

    const errEl = document.getElementById('daw-error');
    if (errEl) errEl.textContent = '';

    setStatus('Rendering...', true);
    _isPlaying = false;
    updatePlayButton();
    const t0 = performance.now();

    try {
      console.log('[DAW] Rendering config:', JSON.stringify(config).substring(0, 200));
      const resp = await fetch('/api/playground/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config })
      });
      const data = await resp.json();
      const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
      console.log('[DAW] Render response:', data);

      if (!resp.ok || data.status !== 'ok') {
        setStatus('Error');
        const msg = data.error || `Render failed (HTTP ${resp.status})`;
        console.error('[DAW] Render error:', msg);
        if (errEl) errEl.textContent = msg;
        return;
      }

      setStatus('Ready');
      DAW.markClean(data.wav_url);
      if (audioEl) {
        audioEl.src = data.wav_url;
        audioEl.load();
        audioEl.play().catch(err => {
          console.error('[DAW] Audio play failed:', err);
          if (errEl) errEl.textContent = 'Playback failed: ' + err.message;
        });
      }
      if (playerEl) playerEl.style.display = '';
      if (renderTimeEl) {
        let info = `Rendered in ${elapsed}s`;
        if (data.peak_db != null) {
          info += ` | Peak: ${data.peak_db}dB`;
          if (data.peak_db < -60) info += ' (silent!)';
        }
        renderTimeEl.textContent = info;
      }

      _isPlaying = true;
      updatePlayButton();
      DAW.notify('render');
      DAWLayers.startPlayheadLoop();
    } catch (e) {
      setStatus('Error');
      console.error('[DAW] Render exception:', e);
      if (errEl) errEl.textContent = e.message;
    }
  }

  function exportConfig() {
    const config = DAW.toConfig();
    const json = JSON.stringify(config, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `config_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function toggleJson() {
    const overlay = document.getElementById('daw-json-overlay');
    const textarea = document.getElementById('daw-json-textarea');
    if (!overlay) return;

    if (overlay.style.display === 'none') {
      const config = DAW.toConfig();
      textarea.value = JSON.stringify(config, null, 2);
      overlay.style.display = '';
    } else {
      overlay.style.display = 'none';
    }
  }

  function applyJson() {
    const textarea = document.getElementById('daw-json-textarea');
    const errEl = document.getElementById('daw-error');
    try {
      const config = JSON.parse(textarea.value);
      DAW.fromConfig(config);
      document.getElementById('daw-json-overlay').style.display = 'none';
      if (errEl) errEl.textContent = '';
    } catch (e) {
      if (errEl) errEl.textContent = 'Invalid JSON: ' + e.message;
    }
  }

  /* ----- metronome ----- */

  function startMetronome() {
    stopMetronome();
    if (!DAW.metronome) return;
    if (!metronomeCtx) metronomeCtx = new AudioContext();

    const bpm = DAW.global.bpm;
    const beatMs = (60 / bpm) * 1000;

    function click() {
      if (!metronomeCtx) return;
      const osc = metronomeCtx.createOscillator();
      const gain = metronomeCtx.createGain();
      osc.connect(gain);
      gain.connect(metronomeCtx.destination);
      osc.frequency.value = 1000;
      gain.gain.setValueAtTime(0.3, metronomeCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, metronomeCtx.currentTime + 0.05);
      osc.start(metronomeCtx.currentTime);
      osc.stop(metronomeCtx.currentTime + 0.05);
    }

    click();
    metronomeInterval = setInterval(click, beatMs);
  }

  function stopMetronome() {
    if (metronomeInterval) {
      clearInterval(metronomeInterval);
      metronomeInterval = null;
    }
  }

  return { init, setStatus, renderAll, startMetronome, stopMetronome, stopAll, onPlaybackEnded };
})();
