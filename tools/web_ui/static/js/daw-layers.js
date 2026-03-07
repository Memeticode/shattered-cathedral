/* ================================================================
   DAW Layers  –  layer card stack with embedded piano rolls
   ================================================================ */

const DAWLayers = (() => {
  const pianoRolls = new Map(); // layerId -> createPianoRoll instance
  let stackEl;
  let audioEl;
  let playheadAnimId = null;

  function init() {
    stackEl = document.getElementById('daw-layer-stack');
    audioEl = document.getElementById('daw-audio');

    document.getElementById('daw-add-layer')?.addEventListener('click', () => {
      const layer = DAW.addLayer('synth');
      if (layer) DAW.selectLayer(layer.id);
    });

    // full rebuild only on structural changes
    DAW.on('layers', renderLayerStack);

    // lightweight re-render for note/selection changes
    DAW.on('notes', renderAllPianoRolls);
    DAW.on('selection', renderAllPianoRolls);

    setupAudioEvents();
    renderLayerStack();
  }

  function renderAllPianoRolls() {
    for (const [, pr] of pianoRolls) {
      pr.render();
    }
  }

  function renderLayerStack() {
    if (!stackEl) return;

    // destroy old piano roll instances
    for (const [, pr] of pianoRolls) {
      pr.destroy();
    }
    pianoRolls.clear();

    stackEl.innerHTML = '';

    for (const layer of DAW.layers) {
      const meta = LAYER_TYPES[layer.type];
      if (!meta) continue;

      const card = document.createElement('div');
      card.className = 'layer-card' +
        (layer.id === DAW.selectedLayerId ? ' selected' : '') +
        (layer.mute ? ' muted' : '') +
        (layer.collapsed ? ' collapsed' : '');
      card.dataset.layerId = layer.id;

      const sec = layer.sections || { instrument: false, keyboard: false, effects: true, visualization: true };
      const sectionArrow = (collapsed) => collapsed ? '\u25B6' : '\u25BC';

      card.innerHTML = `
        <div class="layer-card-header">
          <button class="layer-collapse-btn" data-action="collapse" title="Collapse/Expand">${layer.collapsed ? '\u25B6' : '\u25BC'}</button>
          <span class="layer-icon">${meta.icon}</span>
          <input type="text" class="layer-name-input" value="${esc(layer.name)}" data-action="rename"/>
          <div class="layer-card-controls">
            <button class="layer-sm-btn ${layer.solo ? 'active-solo' : ''}" data-action="solo" title="Solo">S</button>
            <button class="layer-sm-btn ${layer.mute ? 'active-mute' : ''}" data-action="mute" title="Mute">M</button>
            <div class="layer-vol-wrap">
              <input type="range" min="0" max="1" step="0.01" value="${layer.vol}" data-action="volume"/>
              <span class="layer-vol-val">${(layer.vol * 100).toFixed(0)}%</span>
            </div>
            <button class="layer-remove-btn" data-action="remove" title="Remove layer">&times;</button>
          </div>
        </div>

        <div class="layer-section${sec.instrument ? ' collapsed' : ''}" data-section="instrument">
          <div class="layer-section-header" data-action="toggle-section" data-section="instrument">
            <span class="section-arrow">${sectionArrow(sec.instrument)}</span> Instrument
          </div>
          <div class="layer-section-body">
            ${renderLayerParams(layer, meta)}
          </div>
        </div>

        <div class="layer-section${sec.keyboard ? ' collapsed' : ''}" data-section="keyboard">
          <div class="layer-section-header" data-action="toggle-section" data-section="keyboard">
            <span class="section-arrow">${sectionArrow(sec.keyboard)}</span> Keyboard
          </div>
          <div class="layer-section-body">
            <div class="layer-card-piano-wrap">
              <canvas class="layer-piano-roll-canvas"></canvas>
            </div>
          </div>
        </div>

        <div class="layer-section${sec.effects ? ' collapsed' : ''}" data-section="effects">
          <div class="layer-section-header" data-action="toggle-section" data-section="effects">
            <span class="section-arrow">${sectionArrow(sec.effects)}</span> Effects
          </div>
          <div class="layer-section-body">
            <div class="layer-effects-list">
              ${renderLayerEffects(layer)}
            </div>
            <button class="layer-effect-add-btn" data-action="add-effect">+ Add Effect</button>
          </div>
        </div>

        <div class="layer-section${sec.visualization ? ' collapsed' : ''}" data-section="visualization">
          <div class="layer-section-header" data-action="toggle-section" data-section="visualization">
            <span class="section-arrow">${sectionArrow(sec.visualization)}</span> Visualization
          </div>
          <div class="layer-section-body">
            <span class="section-placeholder">Coming soon</span>
          </div>
        </div>
      `;

      bindCardEvents(card, layer);
      stackEl.appendChild(card);

      // create piano roll for this layer (skip if layer or keyboard section collapsed)
      const kbOpen = !layer.collapsed && !(layer.sections || {}).keyboard;
      if (kbOpen) {
        const canvas = card.querySelector('.layer-piano-roll-canvas');
        if (canvas) {
          const pr = createPianoRoll(canvas, layer.id);
          pianoRolls.set(layer.id, pr);
        }
      }
    }
  }

  function bindCardEvents(card, layer) {
    card.addEventListener('click', (e) => {
      const actionEl = e.target.closest('[data-action]');
      const action = actionEl?.dataset?.action;
      if (action === 'collapse') {
        layer.collapsed = !layer.collapsed;
        DAW.notify('layers');
        return;
      }
      if (action === 'remove') {
        DAW.removeLayer(layer.id);
        return;
      }
      if (action === 'solo') {
        layer.solo = !layer.solo;
        if (layer.solo) {
          for (const l of DAW.layers) {
            if (l.id !== layer.id) l.solo = false;
          }
        }
        DAW.notify('layers');
        return;
      }
      if (action === 'mute') {
        layer.mute = !layer.mute;
        DAW.notify('layers');
        return;
      }
      if (action === 'add-effect') {
        if (!layer.effects) layer.effects = [];
        const fxMeta = EFFECT_TYPES.reverb;
        const fx = { type: 'reverb' };
        for (const p of fxMeta.params) fx[p.key] = p.default;
        layer.effects.push(fx);
        DAW.notify('layers');
        return;
      }
      if (action === 'toggle-section') {
        const sectionEl = actionEl.closest('[data-section]');
        const sectionName = sectionEl?.dataset.section;
        if (sectionName && layer.sections) {
          layer.sections[sectionName] = !layer.sections[sectionName];
          DAW.notify('layers');
        }
        return;
      }
      if (action === 'remove-effect') {
        const fxIdx = parseInt(actionEl.dataset.fxIdx);
        if (layer.effects && !isNaN(fxIdx)) {
          layer.effects.splice(fxIdx, 1);
          DAW.notify('layers');
        }
        return;
      }
    });

    // name editing
    const nameInput = card.querySelector('[data-action="rename"]');
    nameInput?.addEventListener('change', () => {
      layer.name = nameInput.value || layer.name;
    });
    // prevent card click when typing in name
    nameInput?.addEventListener('click', (e) => e.stopPropagation());

    // volume slider
    const volSlider = card.querySelector('[data-action="volume"]');
    volSlider?.addEventListener('input', (e) => {
      layer.vol = parseFloat(e.target.value);
      DAW._dirty = true;
      const valSpan = card.querySelector('.layer-vol-val');
      if (valSpan) valSpan.textContent = (layer.vol * 100).toFixed(0) + '%';
    });

    // param inputs
    card.querySelectorAll('[data-param]').forEach(inp => {
      inp.addEventListener('change', () => {
        const key = inp.dataset.param;
        if (inp.type === 'checkbox') {
          layer[key] = inp.checked;
        } else {
          layer[key] = parseFloat(inp.value);
        }
        DAW._dirty = true;
      });
    });

    // effect param inputs
    card.querySelectorAll('[data-fx-param]').forEach(inp => {
      inp.addEventListener('change', () => {
        const fxIdx = parseInt(inp.dataset.fxIdx);
        const key = inp.dataset.fxParam;
        if (layer.effects && layer.effects[fxIdx]) {
          layer.effects[fxIdx][key] = parseFloat(inp.value);
          DAW._dirty = true;
        }
      });
    });
  }

  function renderLayerParams(layer, meta) {
    let html = '';
    for (const p of meta.params) {
      html += '<div class="layer-param-row">';
      html += `<label>${p.label}</label>`;
      if (p.type === 'select') {
        html += `<select data-param="${p.key}">`;
        for (const opt of p.options) {
          html += `<option value="${opt}" ${layer[p.key] === opt ? 'selected' : ''}>${opt}</option>`;
        }
        html += '</select>';
      } else if (p.type === 'checkbox') {
        html += `<input type="checkbox" data-param="${p.key}" ${layer[p.key] ? 'checked' : ''}/>`;
      } else {
        html += `<input type="number" data-param="${p.key}" value="${layer[p.key] ?? ''}" ` +
                `min="${p.min ?? ''}" max="${p.max ?? ''}" step="${p.step ?? 'any'}"/>`;
      }
      html += '</div>';
    }
    return html;
  }

  function renderLayerEffects(layer) {
    if (!layer.effects || !layer.effects.length) return '<span class="fx-empty">No effects</span>';
    let html = '';
    for (let i = 0; i < layer.effects.length; i++) {
      const fx = layer.effects[i];
      const meta = EFFECT_TYPES[fx.type];
      if (!meta) continue;
      html += `<div class="fx-row" data-fx-idx="${i}">
        <span class="fx-label">${meta.label}</span>
        <div class="fx-params">`;
      for (const p of meta.params) {
        const val = fx[p.key] ?? p.default;
        html += `<label class="fx-param">${p.label}
          <input type="number" value="${val}" min="${p.min}" max="${p.max}" step="${p.step}"
                 data-fx-param="${p.key}" data-fx-idx="${i}"/>
        </label>`;
      }
      html += `</div>
        <button class="fx-remove" data-action="remove-effect" data-fx-idx="${i}">&times;</button>
      </div>`;
    }
    return html;
  }

  /* --- playback --- */

  function stopPlayback() {
    if (audioEl) {
      audioEl.pause();
      audioEl.currentTime = 0;
    }
    stopPlayheadLoop();
    for (const [, pr] of pianoRolls) {
      pr.playheadBeat = 0;
      pr.render();
    }
    if (typeof DAWTransport !== 'undefined') DAWTransport.stopMetronome();
  }

  /* --- playhead animation --- */

  function startPlayheadLoop() {
    stopPlayheadLoop();
    if (DAW.metronome && typeof DAWTransport !== 'undefined') DAWTransport.startMetronome();

    function tick() {
      if (!audioEl || audioEl.paused) {
        stopPlayheadLoop();
        if (typeof DAWTransport !== 'undefined') DAWTransport.stopMetronome();
        return;
      }
      const t = audioEl.currentTime;
      const dur = DAW.durationSeconds;
      const beat = dur > 0 ? (t / dur) * DAW.totalBeats : 0;
      for (const [, pr] of pianoRolls) {
        pr.playheadBeat = beat;
        pr.render();
      }
      playheadAnimId = requestAnimationFrame(tick);
    }
    playheadAnimId = requestAnimationFrame(tick);
  }

  function stopPlayheadLoop() {
    if (playheadAnimId) {
      cancelAnimationFrame(playheadAnimId);
      playheadAnimId = null;
    }
  }

  function setupAudioEvents() {
    if (!audioEl) return;
    audioEl.addEventListener('ended', () => {
      stopPlayheadLoop();
      if (typeof DAWTransport !== 'undefined') {
        DAWTransport.stopMetronome();
        DAWTransport.onPlaybackEnded();
      }
      for (const [, pr] of pianoRolls) {
        pr.playheadBeat = 0;
        pr.render();
      }
    });
  }

  return { init, getPianoRolls: () => pianoRolls, stopPlayback, startPlayheadLoop };
})();
