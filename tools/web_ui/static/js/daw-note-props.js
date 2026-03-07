/* ================================================================
   DAW Note Properties  –  selected note editor panel
   ================================================================ */

const DAWNoteProps = (() => {
  let panelEl, innerEl;

  function init() {
    panelEl = document.getElementById('daw-note-props');
    innerEl = document.getElementById('note-props-inner');

    DAW.on('selection', render);
    DAW.on('notes', render);
    render();
  }

  function render() {
    if (!panelEl || !innerEl) return;
    const layer = DAW.selectedLayer;
    const indices = DAW.selectedNoteIndices;

    if (!layer || !indices.length || !LAYER_TYPES[layer.type]?.hasNotes) {
      panelEl.style.display = 'none';
      return;
    }

    panelEl.style.display = '';

    if (indices.length === 1) {
      renderSingleNote(layer, indices[0]);
    } else {
      renderMultiNote(layer, indices);
    }
  }

  function renderSingleNote(layer, idx) {
    const n = layer.notes[idx];
    if (!n) { panelEl.style.display = 'none'; return; }

    const name = midiToName(n.pitch);

    let html = `
      <div class="note-prop-group">
        <label>Pitch</label>
        <input type="number" id="np-pitch" value="${n.pitch}" min="0" max="127"/>
        <span class="note-name-display">${name}</span>
      </div>
      <div class="note-prop-group">
        <label>Beat</label>
        <input type="number" id="np-start" value="${n.startBeat}" min="0" step="0.25"/>
      </div>
      <div class="note-prop-group">
        <label>Duration</label>
        <input type="number" id="np-beats" value="${n.beats}" min="0.25" step="0.25"/>
      </div>
      <div class="note-prop-group">
        <label>Velocity</label>
        <input type="range" id="np-velocity" value="${n.velocity}" min="0" max="1" step="0.01" style="width:80px"/>
        <span style="color:#888;font-size:11px">${(n.velocity * 100).toFixed(0)}%</span>
      </div>
      <div class="note-prop-group">
        <label>Brightness</label>
        <input type="range" id="np-brightness" value="${n.brightness ?? 0.5}" min="0" max="1" step="0.01" style="width:60px"/>
      </div>
      <div class="note-prop-group">
        <label>Vibrato</label>
        <input type="range" id="np-vibrato" value="${n.vibrato ?? 0}" min="0" max="1" step="0.01" style="width:60px"/>
      </div>
      <div class="note-ext-chips" id="np-extensions">
        ${renderExtensions(n)}
      </div>
    `;

    innerEl.innerHTML = html;
    bindInputs(layer, idx);
  }

  function renderMultiNote(layer, indices) {
    const notes = indices.map(i => layer.notes[i]).filter(Boolean);
    if (!notes.length) { panelEl.style.display = 'none'; return; }

    innerEl.innerHTML = `
      <div class="note-prop-group">
        <span style="color:#888">${notes.length} notes selected</span>
      </div>
      <div class="note-prop-group">
        <label>Velocity</label>
        <input type="range" id="np-velocity-multi" value="${notes[0].velocity}" min="0" max="1" step="0.01" style="width:80px"/>
      </div>
      <div class="note-prop-group">
        <label>Brightness</label>
        <input type="range" id="np-brightness-multi" value="${notes[0].brightness ?? 0.5}" min="0" max="1" step="0.01" style="width:60px"/>
      </div>
      <div class="note-prop-group">
        <button class="note-ext-add-btn" id="np-delete-multi">Delete All</button>
      </div>
    `;

    const velSlider = document.getElementById('np-velocity-multi');
    velSlider?.addEventListener('input', () => {
      const v = parseFloat(velSlider.value);
      for (const i of indices) DAW.updateNote(layer.id, i, { velocity: v });
    });

    const brSlider = document.getElementById('np-brightness-multi');
    brSlider?.addEventListener('input', () => {
      const v = parseFloat(brSlider.value);
      for (const i of indices) DAW.updateNote(layer.id, i, { brightness: v });
    });

    document.getElementById('np-delete-multi')?.addEventListener('click', () => {
      const sorted = [...indices].sort((a, b) => b - a);
      for (const i of sorted) layer.notes.splice(i, 1);
      DAW.selectedNoteIndices = [];
      DAW.notify('notes');
      DAW.notify('selection');
    });
  }

  function renderExtensions(note) {
    let html = '';
    for (let i = 0; i < (note.extensions || []).length; i++) {
      const ext = note.extensions[i];
      if (ext.type === 'slide') {
        html += `<span class="note-ext-chip">
          Slide → ${midiToName(ext.targetPitch)} (${ext.beats}b)
          <span class="chip-remove" data-ext-idx="${i}">&times;</span>
        </span>`;
      } else if (ext.type === 'hold') {
        html += `<span class="note-ext-chip">
          Hold +${ext.beats}b
          <span class="chip-remove" data-ext-idx="${i}">&times;</span>
        </span>`;
      }
    }
    html += `<button class="note-ext-add-btn" id="np-add-ext">+ Extension</button>`;
    return html;
  }

  function bindInputs(layer, idx) {
    const update = (changes) => DAW.updateNote(layer.id, idx, changes);

    const pitchIn = document.getElementById('np-pitch');
    pitchIn?.addEventListener('change', () => update({ pitch: parseInt(pitchIn.value) || 60 }));

    const startIn = document.getElementById('np-start');
    startIn?.addEventListener('change', () => update({ startBeat: parseFloat(startIn.value) || 0 }));

    const beatsIn = document.getElementById('np-beats');
    beatsIn?.addEventListener('change', () => update({ beats: Math.max(0.25, parseFloat(beatsIn.value) || 1) }));

    const velIn = document.getElementById('np-velocity');
    velIn?.addEventListener('input', () => update({ velocity: parseFloat(velIn.value) }));

    const brIn = document.getElementById('np-brightness');
    brIn?.addEventListener('input', () => update({ brightness: parseFloat(brIn.value) }));

    const vibIn = document.getElementById('np-vibrato');
    vibIn?.addEventListener('input', () => update({ vibrato: parseFloat(vibIn.value) }));

    // extension removal
    innerEl.querySelectorAll('.chip-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        const extIdx = parseInt(btn.dataset.extIdx);
        const n = layer.notes[idx];
        if (n && n.extensions) {
          n.extensions.splice(extIdx, 1);
          DAW.notify('notes');
        }
      });
    });

    // add extension
    document.getElementById('np-add-ext')?.addEventListener('click', () => {
      const n = layer.notes[idx];
      if (!n) return;

      const choice = prompt('Extension type: slide / hold', 'slide');
      if (choice === 'slide') {
        const target = parseInt(prompt('Target pitch (MIDI)', n.pitch - 2)) || (n.pitch - 2);
        const beats = parseFloat(prompt('Slide duration (beats)', '0.5')) || 0.5;
        if (!n.extensions) n.extensions = [];
        n.extensions.push({ type: 'slide', targetPitch: target, beats });
        DAW.notify('notes');
      } else if (choice === 'hold') {
        const beats = parseFloat(prompt('Hold duration (beats)', '1')) || 1;
        if (!n.extensions) n.extensions = [];
        n.extensions.push({ type: 'hold', beats });
        DAW.notify('notes');
      }
    });
  }

  return { init };
})();
