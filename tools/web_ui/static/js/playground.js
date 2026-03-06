/* === Playground: visual controls, raw JSON, preset loading, render === */

var playgroundConfig = null;
var pgCurrentTab = 'visual';

/* Populate preset dropdown */
document.addEventListener('DOMContentLoaded', function() {
  var sel = document.getElementById('pg-preset-select');
  if (!sel) return;
  Object.keys(presetsData).forEach(function(key) {
    var opt = document.createElement('option');
    opt.value = key;
    opt.textContent = presetsData[key].title || key;
    sel.appendChild(opt);
  });
  var firstKey = Object.keys(presetsData)[0];
  if (firstKey) {
    sel.value = firstKey;
    pgLoadPreset(firstKey);
  }
});

function pgLoadPreset(key) {
  if (!key) return;
  var preset = presetsData[key];
  if (preset && preset.config) {
    playgroundConfig = JSON.parse(JSON.stringify(preset.config));
    var ta = document.getElementById('pg-json-textarea');
    if (ta) ta.value = JSON.stringify(playgroundConfig, null, 2);
    pgRenderVisualControls(playgroundConfig);
  }
}

function pgSwitchTab(tab) {
  pgCurrentTab = tab;
  document.querySelectorAll('.pg-tab').forEach(function(b) {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  var tabVisual = document.getElementById('pg-tab-visual');
  var tabJson = document.getElementById('pg-tab-json');
  if (tabVisual) tabVisual.classList.toggle('active', tab === 'visual');
  if (tabJson) tabJson.classList.toggle('active', tab === 'json');
  if (tab === 'visual') {
    try {
      var ta = document.getElementById('pg-json-textarea');
      if (ta) {
        var cfg = JSON.parse(ta.value);
        playgroundConfig = cfg;
        pgRenderVisualControls(cfg);
      }
    } catch(e) {
      var err = document.getElementById('pg-error');
      if (err) err.textContent = 'JSON parse error: ' + e.message;
    }
  } else {
    if (playgroundConfig) {
      var ta = document.getElementById('pg-json-textarea');
      if (ta) ta.value = JSON.stringify(playgroundConfig, null, 2);
    }
  }
}

function pgSyncToJson() {
  if (playgroundConfig) {
    var ta = document.getElementById('pg-json-textarea');
    if (ta) ta.value = JSON.stringify(playgroundConfig, null, 2);
  }
  var err = document.getElementById('pg-error');
  if (err) err.textContent = '';
}

/* --- Render --- */
function pgRender() {
  var btn = document.getElementById('pg-render-btn');
  var statusEl = document.getElementById('pg-status');
  var errorEl = document.getElementById('pg-error');
  if (errorEl) errorEl.textContent = '';
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = 'Rendering...';

  var cfg;
  try {
    var ta = document.getElementById('pg-json-textarea');
    cfg = JSON.parse(ta.value);
  } catch(e) {
    if (errorEl) errorEl.textContent = 'Invalid JSON: ' + e.message;
    if (btn) btn.disabled = false;
    if (statusEl) statusEl.textContent = '';
    return;
  }

  var t0 = Date.now();
  fetch('/api/playground/render', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({config: cfg})
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (btn) btn.disabled = false;
    if (d.status === 'ok') {
      var audio = document.getElementById('pg-audio');
      if (audio) audio.src = d.wav_url + '?t=' + Date.now();
      var player = document.getElementById('pg-player');
      if (player) player.style.display = 'flex';
      var elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      if (statusEl) statusEl.textContent = 'Done (' + elapsed + 's)';
      var renderTime = document.getElementById('pg-render-time');
      if (renderTime) renderTime.textContent = elapsed + 's';
    } else {
      if (errorEl) errorEl.textContent = 'Render error: ' + (d.error || 'unknown');
      if (statusEl) statusEl.textContent = 'Failed';
    }
  }).catch(function(e) {
    if (btn) btn.disabled = false;
    if (errorEl) errorEl.textContent = 'Network error: ' + e.message;
    if (statusEl) statusEl.textContent = 'Failed';
  });
}

/* --- Visual Controls Builder --- */

function pgMakeField(labelText, inputHtml) {
  return '<div class="pg-field"><label>' + labelText + '</label>' + inputHtml + '</div>';
}

function pgNumInput(id, val, min, max, step) {
  step = step || 1;
  return '<input type="number" id="' + id + '" value="' + (val != null ? val : '') +
         '" min="' + min + '" max="' + max + '" step="' + step +
         '" onchange="pgOnVisualChange()">';
}

function pgSlider(id, val, min, max, step) {
  step = step || 0.01;
  val = val != null ? val : min;
  return '<input type="range" id="' + id + '" value="' + val +
         '" min="' + min + '" max="' + max + '" step="' + step +
         '" oninput="document.getElementById(\'' + id + '-val\').textContent=this.value;pgOnVisualChange()">' +
         '<span class="range-val" id="' + id + '-val">' + val + '</span>';
}

function pgRenderVisualControls(cfg) {
  if (!cfg) return;
  var container = document.getElementById('pg-tab-visual');
  if (!container) return;
  var g = cfg.global || {};
  var m = cfg.master || {};
  var layers = cfg.layers || [];

  var html = '';

  // Global section
  html += '<div class="pg-section"><div class="pg-section-header" onclick="pgToggleSection(this)">' +
          '<span class="pg-section-arrow open">&#9656;</span><span class="pg-section-title">Global</span></div>' +
          '<div class="pg-section-body open">' +
          pgMakeField('BPM', pgNumInput('pg-v-bpm', g.bpm || 72, 30, 240, 1)) +
          pgMakeField('Measures', pgNumInput('pg-v-measures', g.measures || 8, 1, 64, 1)) +
          pgMakeField('Time Sig', pgNumInput('pg-v-ts-num', (g.time_sig||[4,4])[0], 1, 16, 1) +
                      ' / ' + pgNumInput('pg-v-ts-den', (g.time_sig||[4,4])[1], 1, 16, 1)) +
          '</div></div>';

  // Master section
  html += '<div class="pg-section"><div class="pg-section-header" onclick="pgToggleSection(this)">' +
          '<span class="pg-section-arrow open">&#9656;</span><span class="pg-section-title">Master</span></div>' +
          '<div class="pg-section-body open">' +
          pgMakeField('Reverb Size', pgSlider('pg-v-rev-size', m.reverb_size, 0, 1, 0.01)) +
          pgMakeField('Reverb Mix', pgSlider('pg-v-rev-mix', m.reverb_mix, 0, 1, 0.01)) +
          pgMakeField('Delay L', pgNumInput('pg-v-delay-l', (m.delay_time||[0.4,0.5])[0], 0, 5, 0.01)) +
          pgMakeField('Delay R', pgNumInput('pg-v-delay-r', (m.delay_time||[0.4,0.5])[1], 0, 5, 0.01)) +
          pgMakeField('Delay FB', pgSlider('pg-v-delay-fb', m.delay_fb, 0, 1, 0.01)) +
          '</div></div>';

  // Layers section
  html += '<div class="pg-section"><div class="pg-section-header" onclick="pgToggleSection(this)">' +
          '<span class="pg-section-arrow open">&#9656;</span><span class="pg-section-title">Layers (' + layers.length + ')</span></div>' +
          '<div class="pg-section-body open" id="pg-layers-body">';
  layers.forEach(function(layer, idx) {
    html += pgRenderLayerCard(layer, idx);
  });
  html += '<button class="pg-add-layer" onclick="pgAddLayer()">+ Add Layer</button>';
  html += '</div></div>';

  container.innerHTML = html;
}

function pgToggleSection(headerEl) {
  var body = headerEl.nextElementSibling;
  var arrow = headerEl.querySelector('.pg-section-arrow, .pg-layer-arrow');
  body.classList.toggle('open');
  if (arrow) arrow.classList.toggle('open');
}

function pgRenderLayerCard(layer, idx) {
  var type = layer.type || 'void_bass';
  var html = '<div class="pg-layer-card" id="pg-layer-' + idx + '">' +
             '<div class="pg-layer-header" onclick="pgToggleSection(this)">' +
             '<span class="pg-layer-arrow open">&#9656;</span>' +
             '<span class="pg-layer-type">' + type + '</span>' +
             '<span style="font-size:11px;color:#666;margin-left:8px">vol: ' + (layer.vol != null ? layer.vol : '?') + '</span>' +
             '<button class="pg-layer-remove" onclick="event.stopPropagation();pgRemoveLayer(' + idx + ')">&#x2715;</button>' +
             '</div><div class="pg-layer-body open">';

  html += pgMakeField('Volume', pgSlider('pg-l' + idx + '-vol', layer.vol, 0, 1, 0.01));
  html += pgMakeField('Fade In', pgNumInput('pg-l' + idx + '-fi', layer.fade_in, 0, 60, 0.5));
  html += pgMakeField('Fade Out', pgNumInput('pg-l' + idx + '-fo', layer.fade_out, 0, 60, 0.5));

  if (type === 'void_bass') {
    html += pgMakeField('Freq (Hz)', pgNumInput('pg-l' + idx + '-freq', layer.freq, 20, 200, 0.1));
    html += pgMakeField('Drive', pgSlider('pg-l' + idx + '-drive', layer.drive, 0, 1, 0.01));
  } else if (type === 'cathedral_pad') {
    html += pgMakeField('Chord (Hz)', '<input type="text" id="pg-l' + idx + '-chord" value="' +
            (layer.chord || []).join(', ') + '" onchange="pgOnVisualChange()">');
    html += pgMakeField('Rot Speed', pgSlider('pg-l' + idx + '-rotspd', layer.rot_speed, 0.001, 0.1, 0.001));
    html += pgMakeField('Rot Depth', pgSlider('pg-l' + idx + '-rotdep', layer.rot_depth, 0.01, 0.5, 0.01));
    html += pgMakeField('Filter Peak', pgNumInput('pg-l' + idx + '-fpeak', layer.filter_peak, 100, 10000, 10));
    html += pgMakeField('Resonance', pgSlider('pg-l' + idx + '-reso', layer.resonance, 0, 1, 0.01));
  } else if (type === 'phantom_choir') {
    html += pgMakeField('Pitch (Hz)', pgNumInput('pg-l' + idx + '-pitch', layer.pitch, 100, 5000, 1));
    html += pgMakeField('Mod Depth', pgNumInput('pg-l' + idx + '-moddep', layer.mod_depth, 1, 200, 1));
    html += pgMakeField('FM Ratio', '<input type="text" id="pg-l' + idx + '-fmratio" value="' +
            (layer.fm_ratio || [1, 1]).join(', ') + '" onchange="pgOnVisualChange()">');
    html += pgMakeField('FM Index', pgNumInput('pg-l' + idx + '-fmidx', layer.fm_index, 1, 30, 0.1));
    html += pgMakeField('Glitch Dens', pgNumInput('pg-l' + idx + '-gdens', layer.glitch_density, 0.1, 20, 0.1));
    html += pgMakeField('Glitch Dur', pgNumInput('pg-l' + idx + '-gdur', layer.glitch_duration, 0.01, 3, 0.01));
  } else if (type === 'expressive_melody') {
    html += pgMakeField('Timbre', '<select id="pg-l' + idx + '-timbre" onchange="pgOnVisualChange()">' +
            ['glass','sine','saw','fm'].map(function(t) {
              return '<option' + (layer.timbre === t ? ' selected' : '') + '>' + t + '</option>';
            }).join('') + '</select>');
    html += pgMakeField('Def Decay', pgNumInput('pg-l' + idx + '-ddecay', layer.default_decay, 0.1, 5, 0.1));
    html += pgMakeField('Def Bright', pgSlider('pg-l' + idx + '-dbright', layer.default_brightness, 0, 1, 0.01));
    html += pgMakeField('Loop', '<input type="checkbox" id="pg-l' + idx + '-loop"' +
            (layer.loop ? ' checked' : '') + ' onchange="pgOnVisualChange()">');
    html += pgRenderNoteEditor(layer.notes || [], idx);
  } else if (type === 'tape_decay') {
    html += pgMakeField('Crackle Dens', pgNumInput('pg-l' + idx + '-crackle', layer.crackle_density, 0.1, 20, 0.1));
  }

  html += '</div></div>';
  return html;
}

function pgRenderNoteEditor(notes, layerIdx) {
  var html = '<div style="margin-top:8px"><strong style="font-size:11px;color:#888">Notes (' + notes.length + ')</strong>';
  html += '<table class="pg-note-table"><thead><tr>' +
          '<th>Pitch</th><th>Beats</th><th>Vel</th><th>Bright</th><th>Vib</th><th>Slide</th><th>SBeats</th><th></th>' +
          '</tr></thead><tbody>';
  notes.forEach(function(n, ni) {
    var pre = 'pg-n' + layerIdx + '-' + ni;
    html += '<tr>' +
      '<td><input id="' + pre + '-p" type="number" value="' + (n.pitch||60) + '" min="0" max="127" onchange="pgOnVisualChange()"></td>' +
      '<td><input id="' + pre + '-b" type="number" value="' + (n.beats||1) + '" min="0.25" max="16" step="0.25" onchange="pgOnVisualChange()"></td>' +
      '<td><input id="' + pre + '-v" type="number" value="' + (n.velocity!=null?n.velocity:0.7) + '" min="0" max="1" step="0.05" onchange="pgOnVisualChange()"></td>' +
      '<td><input id="' + pre + '-br" type="number" value="' + (n.brightness!=null?n.brightness:'') + '" min="0" max="1" step="0.05" onchange="pgOnVisualChange()"></td>' +
      '<td><input id="' + pre + '-vib" type="number" value="' + (n.vibrato||'') + '" min="0" max="1" step="0.01" onchange="pgOnVisualChange()"></td>' +
      '<td><input id="' + pre + '-st" type="number" value="' + (n.slide_to!=null?n.slide_to:'') + '" min="0" max="127" onchange="pgOnVisualChange()"></td>' +
      '<td><input id="' + pre + '-sb" type="number" value="' + (n.slide_beats||'') + '" min="0" max="8" step="0.25" onchange="pgOnVisualChange()"></td>' +
      '<td><button class="pg-note-remove" onclick="pgRemoveNote(' + layerIdx + ',' + ni + ')">&#x2715;</button></td>' +
      '</tr>';
  });
  html += '</tbody></table>';
  html += '<button class="pg-add-note" onclick="pgAddNote(' + layerIdx + ')">+ Add Note</button></div>';
  return html;
}

/* --- Visual -> Config sync --- */
function pgOnVisualChange() {
  pgBuildConfigFromForm();
  pgSyncToJson();
}

function pgBuildConfigFromForm() {
  if (!playgroundConfig) playgroundConfig = {};
  var cfg = playgroundConfig;

  cfg.global = cfg.global || {};
  var bpm = document.getElementById('pg-v-bpm');
  if (bpm) cfg.global.bpm = parseFloat(bpm.value) || 72;
  var meas = document.getElementById('pg-v-measures');
  if (meas) cfg.global.measures = parseInt(meas.value) || 8;
  var tsn = document.getElementById('pg-v-ts-num');
  var tsd = document.getElementById('pg-v-ts-den');
  if (tsn && tsd) cfg.global.time_sig = [parseInt(tsn.value)||4, parseInt(tsd.value)||4];

  cfg.master = cfg.master || {};
  var rs = document.getElementById('pg-v-rev-size');
  if (rs) cfg.master.reverb_size = parseFloat(rs.value);
  var rm = document.getElementById('pg-v-rev-mix');
  if (rm) cfg.master.reverb_mix = parseFloat(rm.value);
  var dl = document.getElementById('pg-v-delay-l');
  var dr = document.getElementById('pg-v-delay-r');
  if (dl && dr) cfg.master.delay_time = [parseFloat(dl.value)||0.4, parseFloat(dr.value)||0.5];
  var dfb = document.getElementById('pg-v-delay-fb');
  if (dfb) cfg.master.delay_fb = parseFloat(dfb.value);

  var layers = cfg.layers || [];
  layers.forEach(function(layer, idx) {
    var vol = document.getElementById('pg-l' + idx + '-vol');
    if (vol) layer.vol = parseFloat(vol.value);
    var fi = document.getElementById('pg-l' + idx + '-fi');
    if (fi) layer.fade_in = parseFloat(fi.value);
    var fo = document.getElementById('pg-l' + idx + '-fo');
    if (fo) layer.fade_out = parseFloat(fo.value);

    if (layer.type === 'void_bass') {
      var freq = document.getElementById('pg-l' + idx + '-freq');
      if (freq) layer.freq = parseFloat(freq.value);
      var drive = document.getElementById('pg-l' + idx + '-drive');
      if (drive) layer.drive = parseFloat(drive.value);
    } else if (layer.type === 'cathedral_pad') {
      var chord = document.getElementById('pg-l' + idx + '-chord');
      if (chord) layer.chord = chord.value.split(',').map(function(s){ return parseFloat(s.trim()); }).filter(function(n){ return !isNaN(n); });
      var rotspd = document.getElementById('pg-l' + idx + '-rotspd');
      if (rotspd) layer.rot_speed = parseFloat(rotspd.value);
      var rotdep = document.getElementById('pg-l' + idx + '-rotdep');
      if (rotdep) layer.rot_depth = parseFloat(rotdep.value);
      var fpeak = document.getElementById('pg-l' + idx + '-fpeak');
      if (fpeak) layer.filter_peak = parseFloat(fpeak.value);
      var reso = document.getElementById('pg-l' + idx + '-reso');
      if (reso) layer.resonance = parseFloat(reso.value);
    } else if (layer.type === 'phantom_choir') {
      var pitch = document.getElementById('pg-l' + idx + '-pitch');
      if (pitch) layer.pitch = parseFloat(pitch.value);
      var moddep = document.getElementById('pg-l' + idx + '-moddep');
      if (moddep) layer.mod_depth = parseFloat(moddep.value);
      var fmratio = document.getElementById('pg-l' + idx + '-fmratio');
      if (fmratio) layer.fm_ratio = fmratio.value.split(',').map(function(s){ return parseFloat(s.trim()); });
      var fmidx = document.getElementById('pg-l' + idx + '-fmidx');
      if (fmidx) layer.fm_index = parseFloat(fmidx.value);
      var gdens = document.getElementById('pg-l' + idx + '-gdens');
      if (gdens) layer.glitch_density = parseFloat(gdens.value);
      var gdur = document.getElementById('pg-l' + idx + '-gdur');
      if (gdur) layer.glitch_duration = parseFloat(gdur.value);
    } else if (layer.type === 'expressive_melody') {
      var timbre = document.getElementById('pg-l' + idx + '-timbre');
      if (timbre) layer.timbre = timbre.value;
      var ddecay = document.getElementById('pg-l' + idx + '-ddecay');
      if (ddecay) layer.default_decay = parseFloat(ddecay.value);
      var dbright = document.getElementById('pg-l' + idx + '-dbright');
      if (dbright) layer.default_brightness = parseFloat(dbright.value);
      var loop = document.getElementById('pg-l' + idx + '-loop');
      if (loop) layer.loop = loop.checked;

      layer.notes = layer.notes || [];
      layer.notes.forEach(function(n, ni) {
        var pre = 'pg-n' + idx + '-' + ni;
        var pp = document.getElementById(pre + '-p');
        if (pp) n.pitch = parseInt(pp.value) || 60;
        var pb = document.getElementById(pre + '-b');
        if (pb) n.beats = parseFloat(pb.value) || 1;
        var pv = document.getElementById(pre + '-v');
        if (pv) n.velocity = parseFloat(pv.value);
        var pbr = document.getElementById(pre + '-br');
        if (pbr && pbr.value !== '') n.brightness = parseFloat(pbr.value);
        else delete n.brightness;
        var pvib = document.getElementById(pre + '-vib');
        if (pvib && pvib.value !== '' && parseFloat(pvib.value) > 0) n.vibrato = parseFloat(pvib.value);
        else delete n.vibrato;
        var pst = document.getElementById(pre + '-st');
        if (pst && pst.value !== '') n.slide_to = parseInt(pst.value);
        else delete n.slide_to;
        var psb = document.getElementById(pre + '-sb');
        if (psb && psb.value !== '') n.slide_beats = parseFloat(psb.value);
        else delete n.slide_beats;
      });
    } else if (layer.type === 'tape_decay') {
      var crackle = document.getElementById('pg-l' + idx + '-crackle');
      if (crackle) layer.crackle_density = parseFloat(crackle.value);
    }
  });
  cfg.layers = layers;
  playgroundConfig = cfg;
}

/* --- Layer add/remove --- */
function pgAddLayer() {
  if (!playgroundConfig) return;
  var types = ['void_bass','cathedral_pad','phantom_choir','expressive_melody','tape_decay'];
  var type = prompt('Layer type?\n' + types.join(', '));
  if (!type || types.indexOf(type) === -1) return;
  var newLayer = {type: type, vol: 0.3, fade_in: 3, fade_out: 5};
  if (type === 'void_bass') { newLayer.freq = 55; newLayer.drive = 0.2; }
  else if (type === 'cathedral_pad') { newLayer.chord = [261.63, 329.63, 392.0]; newLayer.rot_speed = 0.01; newLayer.filter_peak = 2000; newLayer.resonance = 0.3; }
  else if (type === 'phantom_choir') { newLayer.pitch = 440; newLayer.mod_depth = 30; newLayer.fm_ratio = [1, 1.5]; newLayer.fm_index = 5; newLayer.glitch_density = 3; newLayer.glitch_duration = 0.1; }
  else if (type === 'expressive_melody') { newLayer.timbre = 'glass'; newLayer.default_decay = 1.0; newLayer.default_brightness = 0.5; newLayer.loop = true; newLayer.notes = [{pitch:60,beats:2,velocity:0.7}]; }
  else if (type === 'tape_decay') { newLayer.crackle_density = 5; }
  playgroundConfig.layers = playgroundConfig.layers || [];
  playgroundConfig.layers.push(newLayer);
  pgRenderVisualControls(playgroundConfig);
  pgSyncToJson();
}

function pgRemoveLayer(idx) {
  if (!playgroundConfig || !playgroundConfig.layers) return;
  playgroundConfig.layers.splice(idx, 1);
  pgRenderVisualControls(playgroundConfig);
  pgSyncToJson();
}

function pgAddNote(layerIdx) {
  if (!playgroundConfig || !playgroundConfig.layers) return;
  var layer = playgroundConfig.layers[layerIdx];
  if (!layer || layer.type !== 'expressive_melody') return;
  pgBuildConfigFromForm();
  layer.notes = layer.notes || [];
  var lastPitch = layer.notes.length > 0 ? layer.notes[layer.notes.length-1].pitch : 60;
  layer.notes.push({pitch: lastPitch + 2, beats: 1, velocity: 0.7});
  pgRenderVisualControls(playgroundConfig);
  pgSyncToJson();
}

function pgRemoveNote(layerIdx, noteIdx) {
  if (!playgroundConfig || !playgroundConfig.layers) return;
  var layer = playgroundConfig.layers[layerIdx];
  if (!layer || !layer.notes) return;
  pgBuildConfigFromForm();
  layer.notes.splice(noteIdx, 1);
  pgRenderVisualControls(playgroundConfig);
  pgSyncToJson();
}
