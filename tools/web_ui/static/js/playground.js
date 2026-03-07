/* ================================================================
   Playground  –  DAW orchestrator (init, preset loading)
   ================================================================ */

document.addEventListener('DOMContentLoaded', function() {
  // Only initialize if playground page exists
  if (!document.getElementById('page-playground')) return;

  // Populate preset dropdown
  const sel = document.getElementById('daw-preset-select');
  if (sel && typeof presetsData !== 'undefined') {
    Object.keys(presetsData).forEach(function(key) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = presetsData[key].title || key;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', function() {
      if (sel.value) dawLoadPreset(sel.value);
    });
  }

  // Initialize DAW components (piano rolls are created per-layer inside DAWLayers)
  DAWLayers.init();
  DAWNoteProps.init();
  DAWTransport.init();
  DAWWaveform.init();

  // Load first preset by default, or add a single synth layer
  const firstKey = typeof presetsData !== 'undefined' ? Object.keys(presetsData)[0] : null;
  if (firstKey) {
    dawLoadPreset(firstKey);
    if (sel) sel.value = firstKey;
  } else {
    DAW.addLayer('synth');
  }
});

function dawLoadPreset(key) {
  if (!key || typeof presetsData === 'undefined') return;
  const preset = presetsData[key];
  if (preset && preset.config) {
    DAW.fromConfig(JSON.parse(JSON.stringify(preset.config)));
  }
}
