/* ================================================================
   DAW Piano Roll  –  factory function for per-layer canvas editors
   ================================================================ */

/* --- NotePreview: timbre-aware note preview (Web Audio) --- */
const NotePreview = (() => {
  let ctx = null;
  let nodes = null; // { oscs, gain, filter, stopTimeout }

  function _midiToFreq(m) { return 440 * Math.pow(2, (m - 69) / 12); }

  function _ensureCtx() {
    if (!ctx) ctx = new AudioContext();
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  function _buildOsc(ctx, timbre, freq) {
    const oscs = [];
    if (timbre === 'fm') {
      // FM synthesis: modulator → carrier
      const mod = ctx.createOscillator();
      const modGain = ctx.createGain();
      mod.type = 'sine';
      mod.frequency.value = freq;  // ratio 1:1
      modGain.gain.value = freq * 5; // index=5
      mod.connect(modGain);
      const carrier = ctx.createOscillator();
      carrier.type = 'sine';
      carrier.frequency.value = freq;
      modGain.connect(carrier.frequency);
      mod.start();
      oscs.push(mod, carrier);
      return { oscs, output: carrier, freqParam: carrier.frequency, modFreq: mod.frequency, modGain };
    }

    const osc = ctx.createOscillator();
    if (timbre === 'saw') osc.type = 'sawtooth';
    else if (timbre === 'glass') osc.type = 'triangle';
    else osc.type = 'sine';
    osc.frequency.value = freq;
    oscs.push(osc);
    return { oscs, output: osc, freqParam: osc.frequency };
  }

  function play(midiPitch, opts = {}) {
    stop(); // stop any active preview
    const ac = _ensureCtx();

    const timbre = opts.timbre || 'sine';
    const brightness = opts.brightness != null ? opts.brightness : 0.5;
    const velocity = opts.velocity != null ? opts.velocity : 0.7;
    const durationBeats = opts.durationBeats || 0.5;
    const beatSec = 60 / (DAW.global.bpm || 72);
    const dur = Math.min(3, durationBeats * beatSec); // cap at 3s

    const freq = _midiToFreq(midiPitch);
    const built = _buildOsc(ac, timbre, freq);

    // Brightness filter: 0→400Hz, 1→8000Hz
    const filter = ac.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 400 + brightness * 7600;
    filter.Q.value = 1;

    // Gain envelope
    const gain = ac.createGain();
    const now = ac.currentTime;
    const peakGain = 0.15 * velocity;
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(peakGain, now + 0.01); // quick attack
    gain.gain.setValueAtTime(peakGain, now + Math.max(0.01, dur - 0.05));
    gain.gain.exponentialRampToValueAtTime(0.001, now + dur);

    built.output.connect(filter);
    filter.connect(gain);
    gain.connect(ac.destination);

    for (const o of built.oscs) o.start(now);
    for (const o of built.oscs) o.stop(now + dur + 0.01);

    const stopTimeout = setTimeout(() => { nodes = null; }, (dur + 0.05) * 1000);

    nodes = { oscs: built.oscs, gain, filter, freqParam: built.freqParam,
              modFreq: built.modFreq, modGain: built.modGain, stopTimeout };
  }

  function updatePitch(midiPitch) {
    if (!nodes || !ctx) return;
    const freq = _midiToFreq(midiPitch);
    const now = ctx.currentTime;
    nodes.freqParam.exponentialRampToValueAtTime(Math.max(1, freq), now + 0.03);
    if (nodes.modFreq) {
      nodes.modFreq.exponentialRampToValueAtTime(Math.max(1, freq), now + 0.03);
      nodes.modGain.gain.exponentialRampToValueAtTime(Math.max(1, freq * 5), now + 0.03);
    }
  }

  function stop() {
    if (!nodes || !ctx) return;
    const now = ctx.currentTime;
    try {
      nodes.gain.gain.cancelScheduledValues(now);
      nodes.gain.gain.setValueAtTime(nodes.gain.gain.value, now);
      nodes.gain.gain.exponentialRampToValueAtTime(0.001, now + 0.03);
      for (const o of nodes.oscs) {
        try { o.stop(now + 0.05); } catch (_) {}
      }
    } catch (_) {}
    clearTimeout(nodes.stopTimeout);
    nodes = null;
  }

  return { play, updatePitch, stop };
})();

/* --- Curve interpolation for slide extensions --- */
const CURVE_TYPES = ['linear', 'ease-in', 'ease-out', 'ease-in-out'];

function curveInterpolate(t, curve) {
  t = Math.max(0, Math.min(1, t));
  switch (curve) {
    case 'linear':      return t;
    case 'ease-in':     return t * t * t;
    case 'ease-out':    return 1 - Math.pow(1 - t, 3);
    case 'ease-in-out': return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    default:            return t;
  }
}

function createPianoRoll(canvasEl, layerId) {
  /* --- constants --- */
  const KEY_W = 48;
  const HEADER_H = 22;
  const MIN_PITCH = 36;
  const MAX_PITCH = 96;
  const SNAP = 0.25;
  const RESIZE_ZONE = 6;

  let canvas = canvasEl;
  let ctx = canvas.getContext('2d');
  let beatWidth = 32;
  let cellH = 14;
  let scrollX = 0, scrollY = 0;
  let _playheadBeat = 0;

  /* --- interaction state --- */
  let dragMode = null;
  let dragNote = null;
  let dragStart = null;
  let hoveredNote = null;
  let hoveredKeyPitch = null;
  let keyboardDragging = false;
  let lastPlayedKeyPitch = null;

  /* --- derived --- */
  const pitchCount = () => MAX_PITCH - MIN_PITCH;
  const gridLeft = () => KEY_W;
  const gridWidth = () => DAW.totalBeats * beatWidth;
  const gridHeight = () => pitchCount() * cellH;
  const totalH = () => HEADER_H + gridHeight();

  function isBlackKey(pitch) {
    return [1,3,6,8,10].includes(pitch % 12);
  }

  /* --- coordinate helpers --- */
  function beatToX(beat) { return gridLeft() + beat * beatWidth - scrollX; }
  function pitchToY(pitch) { return HEADER_H + (MAX_PITCH - pitch - 1) * cellH - scrollY; }
  function xToBeat(x) { return (x - gridLeft() + scrollX) / beatWidth; }
  function yToPitch(y) { return MAX_PITCH - 1 - Math.floor((y - HEADER_H + scrollY) / cellH); }
  function snapBeat(b) { return Math.round(b / SNAP) * SNAP; }

  function getLayer() { return DAW.getLayer(layerId); }

  /* --- extension geometry computation --- */
  function computeExtensionSegments(note) {
    const segs = [];
    let curX = beatToX(note.startBeat) + note.beats * beatWidth;
    let curPitch = note.pitch;

    for (let ei = 0; ei < (note.extensions || []).length; ei++) {
      const ext = note.extensions[ei];
      const segW = ext.beats * beatWidth;

      if (ext.type === 'slide') {
        segs.push({
          extIndex: ei, type: 'slide', x: curX, width: segW,
          fromPitch: curPitch, toPitch: ext.targetPitch,
          fromY: pitchToY(curPitch), toY: pitchToY(ext.targetPitch),
          curve: ext.curve || 'ease-in-out'
        });
        curPitch = ext.targetPitch;
      } else if (ext.type === 'hold') {
        segs.push({
          extIndex: ei, type: 'hold', x: curX, width: segW,
          pitch: curPitch, y: pitchToY(curPitch)
        });
      }
      curX += segW;
    }
    segs._endX = curX;
    segs._endPitch = curPitch;
    return segs;
  }

  /* --- init --- */
  function init() {
    resizeCanvas();
    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('mouseleave', onMouseUp);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('dblclick', onDblClick);
    canvas.addEventListener('contextmenu', showContextMenu);
    _resizeHandler = () => resizeCanvas();
    window.addEventListener('resize', _resizeHandler);
    render();
  }

  let _resizeHandler = null;

  function destroy() {
    canvas.removeEventListener('mousedown', onMouseDown);
    canvas.removeEventListener('mousemove', onMouseMove);
    canvas.removeEventListener('mouseup', onMouseUp);
    canvas.removeEventListener('mouseleave', onMouseUp);
    canvas.removeEventListener('wheel', onWheel);
    canvas.removeEventListener('dblclick', onDblClick);
    canvas.removeEventListener('contextmenu', showContextMenu);
    hideContextMenu();
    if (_resizeHandler) window.removeEventListener('resize', _resizeHandler);
  }

  function resizeCanvas() {
    const wrap = canvas.parentElement;
    if (!wrap) return;
    const rect = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    // Always fit wrapper width — horizontal panning via scrollX only
    const w = rect.width;
    const h = Math.max(rect.height, totalH());
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /* ================================
     Rendering
     ================================ */
  function render() {
    if (!ctx) return;
    const w = canvas.width / (window.devicePixelRatio || 1);
    const h = canvas.height / (window.devicePixelRatio || 1);
    ctx.clearRect(0, 0, w, h);

    drawGrid(w, h);
    drawNotes(w, h);
    drawPlayhead(h);
    drawKeyboard(h);
    drawHeader(w);
  }

  function drawGrid(w, h) {
    const beats = DAW.totalBeats;
    const tsNum = DAW.global.timeSig[0];

    // Clip to grid area (right of keyboard)
    ctx.save();
    ctx.beginPath();
    ctx.rect(KEY_W, HEADER_H, w - KEY_W, h - HEADER_H);
    ctx.clip();

    for (let p = MIN_PITCH; p < MAX_PITCH; p++) {
      const y = pitchToY(p);
      if (y < HEADER_H || y > h) continue;
      ctx.fillStyle = '#10121a';
      ctx.fillRect(gridLeft(), y, w, cellH);
      if (p % 12 === 0) {
        ctx.strokeStyle = '#1a1c28';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(gridLeft(), y + cellH);
        ctx.lineTo(w, y + cellH);
        ctx.stroke();
      }
    }

    for (let b = 0; b <= beats; b++) {
      const x = beatToX(b);
      if (x < gridLeft() || x > w) continue;
      const isMeasure = b % tsNum === 0;
      ctx.strokeStyle = isMeasure ? '#252838' : '#181a24';
      ctx.lineWidth = isMeasure ? 1.5 : 0.5;
      ctx.beginPath();
      ctx.moveTo(x, HEADER_H);
      ctx.lineTo(x, HEADER_H + gridHeight());
      ctx.stroke();
    }

    ctx.restore();
  }

  function drawHeader(w) {
    ctx.fillStyle = '#12141c';
    ctx.fillRect(0, 0, w, HEADER_H);
    ctx.fillStyle = '#0e1018';
    ctx.fillRect(0, 0, gridLeft(), HEADER_H);

    const beats = DAW.totalBeats;
    const tsNum = DAW.global.timeSig[0];
    ctx.font = '10px system-ui';
    ctx.textAlign = 'center';

    for (let b = 0; b <= beats; b++) {
      const x = beatToX(b);
      if (x < gridLeft() || x > w) continue;
      if (b % tsNum === 0) {
        const measure = Math.floor(b / tsNum) + 1;
        ctx.fillStyle = '#888';
        ctx.fillText(measure.toString(), x, 14);
      } else {
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(x, HEADER_H - 4);
        ctx.lineTo(x, HEADER_H);
        ctx.stroke();
      }
    }
  }

  function drawKeyboard(h) {
    ctx.fillStyle = '#0e1018';
    ctx.fillRect(0, HEADER_H, KEY_W, h - HEADER_H);

    for (let p = MIN_PITCH; p < MAX_PITCH; p++) {
      const y = pitchToY(p);
      if (y + cellH < HEADER_H || y > h) continue;

      const isHoveredKey = hoveredKeyPitch === p;
      ctx.fillStyle = isHoveredKey ? '#2a2c48' : '#1a1e2e';
      ctx.fillRect(0, y, KEY_W, cellH);

      // Row separator — thicker at octave boundaries
      if (p % 12 === 0) {
        ctx.strokeStyle = '#2a2c38';
        ctx.lineWidth = 1;
      } else {
        ctx.strokeStyle = '#181a24';
        ctx.lineWidth = 0.5;
      }
      ctx.beginPath();
      ctx.moveTo(0, y + cellH);
      ctx.lineTo(KEY_W, y + cellH);
      ctx.stroke();

      // Label every key
      if (cellH >= 10) {
        ctx.fillStyle = p % 12 === 0 ? '#aaa' : '#666';
        ctx.font = '9px system-ui';
        ctx.textAlign = 'right';
        ctx.fillText(midiToName(p), KEY_W - 4, y + cellH - 3);
      }
    }

    ctx.strokeStyle = '#1e2030';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(KEY_W, HEADER_H);
    ctx.lineTo(KEY_W, h);
    ctx.stroke();
  }

  function drawNotes(w, h) {
    const layer = getLayer();
    if (!layer || !LAYER_TYPES[layer.type]?.hasNotes) return;

    const color = LAYER_TYPES[layer.type]?.color || '#4af';
    const isSelected = DAW.selectedLayerId === layerId;

    // Clip to grid area so notes don't paint over keyboard
    ctx.save();
    ctx.beginPath();
    ctx.rect(KEY_W, HEADER_H, w - KEY_W, h - HEADER_H);
    ctx.clip();

    for (let i = 0; i < layer.notes.length; i++) {
      const n = layer.notes[i];
      const x = beatToX(n.startBeat);
      const y = pitchToY(n.pitch);
      const nw = n.beats * beatWidth;
      const noteSelected = isSelected && DAW.selectedNoteIndices.includes(i);
      const isHovered = hoveredNote && hoveredNote.noteIndex === i;

      ctx.globalAlpha = 0.35 + n.velocity * 0.55;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.roundRect(x + 1, y + 1, nw - 2, cellH - 2, 2);
      ctx.fill();
      ctx.globalAlpha = 1;

      if (noteSelected) {
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.roundRect(x + 1, y + 1, nw - 2, cellH - 2, 2);
        ctx.stroke();
      } else if (isHovered) {
        ctx.strokeStyle = 'rgba(255,255,255,0.3)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(x + 1, y + 1, nw - 2, cellH - 2, 2);
        ctx.stroke();
      }

      if (n.vibrato > 0.05) {
        ctx.strokeStyle = '#ff0';
        ctx.globalAlpha = 0.4;
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(x + 2, y + 2);
        ctx.lineTo(x + nw - 2, y + 2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
      }

      // Draw extensions as filled ribbons
      const segs = computeExtensionSegments(n);
      for (const seg of segs) {
        if (seg.type === 'slide') {
          const steps = Math.max(8, Math.ceil(seg.width / 2));
          const fromTop = seg.fromY + 1;
          const fromBot = seg.fromY + cellH - 1;
          const toTop = seg.toY + 1;
          const toBot = seg.toY + cellH - 1;

          ctx.globalAlpha = 0.3 + n.velocity * 0.4;
          ctx.fillStyle = color;
          ctx.beginPath();
          // Top edge left-to-right
          for (let s = 0; s <= steps; s++) {
            const t = s / steps;
            const ct = curveInterpolate(t, seg.curve);
            const px = seg.x + t * seg.width;
            const py = fromTop + ct * (toTop - fromTop);
            if (s === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          // Bottom edge right-to-left
          for (let s = steps; s >= 0; s--) {
            const t = s / steps;
            const ct = curveInterpolate(t, seg.curve);
            const px = seg.x + t * seg.width;
            const py = fromBot + ct * (toBot - fromBot);
            ctx.lineTo(px, py);
          }
          ctx.closePath();
          ctx.fill();
          ctx.globalAlpha = 1;
        }

        if (seg.type === 'hold') {
          ctx.globalAlpha = 0.25 + n.velocity * 0.3;
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.roundRect(seg.x + 1, seg.y + 1, seg.width - 2, cellH - 2, 2);
          ctx.fill();
          ctx.globalAlpha = 1;
          // Dashed center line to distinguish from note body
          ctx.strokeStyle = 'rgba(255,255,255,0.15)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(seg.x + 2, seg.y + cellH / 2);
          ctx.lineTo(seg.x + seg.width - 2, seg.y + cellH / 2);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      // Hover icon: "+" at extension chain endpoint
      if (isHovered || noteSelected) {
        const iconX = segs._endX;
        const iconY = pitchToY(segs._endPitch) + cellH / 2;
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.beginPath();
        ctx.arc(iconX, iconY, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#000';
        ctx.font = 'bold 8px system-ui';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('+', iconX, iconY);
        ctx.textBaseline = 'alphabetic';
      }

      if (nw > 24) {
        ctx.fillStyle = '#000';
        ctx.globalAlpha = 0.7;
        ctx.font = '9px system-ui';
        ctx.textAlign = 'left';
        ctx.fillText(midiToName(n.pitch), x + 4, y + cellH - 3);
        ctx.globalAlpha = 1;
      }
    }

    ctx.restore();
  }

  function drawPlayhead(h) {
    if (_playheadBeat <= 0) return;
    const x = beatToX(_playheadBeat);
    if (x < gridLeft()) return;

    ctx.strokeStyle = '#f44';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, HEADER_H);
    ctx.lineTo(x, h);
    ctx.stroke();

    ctx.fillStyle = '#f44';
    ctx.beginPath();
    ctx.moveTo(x - 5, 0);
    ctx.lineTo(x + 5, 0);
    ctx.lineTo(x, 8);
    ctx.closePath();
    ctx.fill();
  }

  /* ================================
     Interaction
     ================================ */
  function hitTest(mx, my) {
    const layer = getLayer();
    if (!layer || !LAYER_TYPES[layer.type]?.hasNotes) return null;

    for (let i = layer.notes.length - 1; i >= 0; i--) {
      const n = layer.notes[i];
      const x = beatToX(n.startBeat);
      const y = pitchToY(n.pitch);
      const w = n.beats * beatWidth;

      // Check note body
      if (mx >= x && mx <= x + w && my >= y && my <= y + cellH) {
        const nearRightEdge = mx >= x + w - RESIZE_ZONE;
        return { noteIndex: i, resize: nearRightEdge, zone: 'body' };
      }

      // Check extension segments
      const segs = computeExtensionSegments(n);
      for (const seg of segs) {
        if (seg.type === 'hold') {
          if (mx >= seg.x && mx <= seg.x + seg.width &&
              my >= seg.y && my <= seg.y + cellH) {
            return { noteIndex: i, resize: false, zone: 'extension',
                     extIndex: seg.extIndex, extType: 'hold' };
          }
        }
        if (seg.type === 'slide') {
          if (mx >= seg.x && mx <= seg.x + seg.width) {
            const t = (mx - seg.x) / seg.width;
            const ct = curveInterpolate(t, seg.curve);
            const topY = (seg.fromY + 1) + ct * (seg.toY + 1 - seg.fromY - 1);
            const botY = topY + cellH - 2;
            if (my >= topY && my <= botY) {
              return { noteIndex: i, resize: false, zone: 'extension',
                       extIndex: seg.extIndex, extType: 'slide' };
            }
          }
        }
      }

      // Check "+" icon at chain endpoint
      const iconX = segs._endX;
      const iconY = pitchToY(segs._endPitch) + cellH / 2;
      const dist = Math.sqrt((mx - iconX) ** 2 + (my - iconY) ** 2);
      if (dist <= 7) {
        return { noteIndex: i, resize: false, zone: 'add-extension' };
      }
    }
    return null;
  }

  function onMouseDown(e) {
    // Only handle left button for note interaction
    if (e.button !== 0) return;

    // auto-select this layer
    if (DAW.selectedLayerId !== layerId) {
      DAW.selectLayer(layerId);
    }

    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Keyboard click — play preview tone + start glissando drag
    if (mx < gridLeft() && my > HEADER_H) {
      const pitch = yToPitch(my);
      if (pitch >= MIN_PITCH && pitch < MAX_PITCH) {
        const layer = getLayer();
        NotePreview.play(pitch, {
          timbre: layer?.timbre || 'sine',
          brightness: layer?.defaultBrightness || 0.5,
          velocity: 0.7,
          durationBeats: 2
        });
        keyboardDragging = true;
        lastPlayedKeyPitch = pitch;
      }
      return;
    }
    if (my <= HEADER_H) return;

    const hit = hitTest(mx, my);
    const layer = getLayer();

    if (hit && hit.zone === 'add-extension') {
      showExtensionAddMenu(e, layer.notes[hit.noteIndex], hit.noteIndex);
      return;
    }

    if (hit) {
      const n = layer.notes[hit.noteIndex];
      if (e.shiftKey) {
        const idx = DAW.selectedNoteIndices.indexOf(hit.noteIndex);
        if (idx >= 0) DAW.selectedNoteIndices.splice(idx, 1);
        else DAW.selectedNoteIndices.push(hit.noteIndex);
      } else {
        DAW.selectedNoteIndices = [hit.noteIndex];
      }
      DAW.notify('selection');

      dragMode = hit.resize ? 'resize' : 'move';
      dragNote = {
        noteIndex: hit.noteIndex,
        startBeat0: n.startBeat,
        pitch0: n.pitch,
        beats0: n.beats
      };
      dragStart = { x: mx, y: my };
      // Play preview of the clicked note
      NotePreview.play(n.pitch, {
        timbre: layer?.timbre || 'sine',
        brightness: n.brightness || layer?.defaultBrightness || 0.5,
        velocity: n.velocity || 0.7,
        durationBeats: n.beats || 1
      });
    } else {
      const beat = snapBeat(xToBeat(mx));
      const pitch = yToPitch(my);
      if (layer && LAYER_TYPES[layer.type]?.hasNotes && pitch >= MIN_PITCH && pitch < MAX_PITCH && beat >= 0) {
        DAW.addNote(layer.id, {
          pitch,
          startBeat: beat,
          beats: SNAP,
          velocity: 0.7,
          brightness: layer.defaultBrightness || 0.5,
          vibrato: 0,
          extensions: []
        });
        NotePreview.play(pitch, {
          timbre: layer?.timbre || 'sine',
          brightness: layer?.defaultBrightness || 0.5,
          velocity: 0.7,
          durationBeats: SNAP
        });
        const idx = layer.notes.findIndex(n => n.startBeat === beat && n.pitch === pitch);
        if (idx >= 0) {
          DAW.selectedNoteIndices = [idx];
          DAW.notify('selection');
          // Start drag-to-draw: resize the new note as user drags
          dragMode = 'draw';
          dragNote = {
            noteIndex: idx,
            startBeat0: beat,
            pitch0: pitch,
            beats0: SNAP
          };
          dragStart = { x: mx, y: my };
        }
      } else {
        DAW.selectedNoteIndices = [];
        DAW.notify('selection');
      }
    }
  }

  function onMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Keyboard glissando drag
    if (keyboardDragging) {
      if (mx < gridLeft() && my > HEADER_H) {
        const pitch = yToPitch(my);
        if (pitch >= MIN_PITCH && pitch < MAX_PITCH && pitch !== lastPlayedKeyPitch) {
          NotePreview.updatePitch(pitch);
          lastPlayedKeyPitch = pitch;
        }
      }
      // Update hover regardless
      const prevKey = hoveredKeyPitch;
      hoveredKeyPitch = (mx < gridLeft() && my > HEADER_H) ? yToPitch(my) : null;
      if (hoveredKeyPitch !== prevKey) render();
      return;
    }

    if (dragMode && dragNote) {
      const layer = getLayer();
      if (!layer) return;
      const n = layer.notes[dragNote.noteIndex];
      if (!n) return;

      if (dragMode === 'move') {
        const dBeat = snapBeat(xToBeat(mx) - xToBeat(dragStart.x));
        const dPitch = yToPitch(my) - yToPitch(dragStart.y);
        n.startBeat = Math.max(0, dragNote.startBeat0 + dBeat);
        const newPitch = Math.max(MIN_PITCH, Math.min(MAX_PITCH - 1, dragNote.pitch0 + dPitch));
        if (newPitch !== n.pitch) {
          n.pitch = newPitch;
          NotePreview.updatePitch(newPitch);
        } else {
          n.pitch = newPitch;
        }
      } else if (dragMode === 'resize' || dragMode === 'draw') {
        const newEnd = snapBeat(xToBeat(mx));
        const newBeats = Math.max(SNAP, newEnd - dragNote.startBeat0);
        n.beats = newBeats;
      }
      render();
      DAW.notify('notes');
      return;
    }

    // Keyboard hover
    const prevKey = hoveredKeyPitch;
    if (mx < gridLeft() && my > HEADER_H) {
      const pitch = yToPitch(my);
      hoveredKeyPitch = (pitch >= MIN_PITCH && pitch < MAX_PITCH) ? pitch : null;
      canvas.style.cursor = hoveredKeyPitch != null ? 'pointer' : 'default';
    } else {
      hoveredKeyPitch = null;
    }

    const hit = hitTest(mx, my);
    const prevHovered = hoveredNote;
    hoveredNote = hit;
    if (mx >= gridLeft()) {
      if (hit && (hit.zone === 'add-extension' || hit.zone === 'extension')) {
        canvas.style.cursor = 'pointer';
      } else if (hit) {
        canvas.style.cursor = hit.resize ? 'ew-resize' : 'grab';
      } else {
        canvas.style.cursor = 'crosshair';
      }
    }
    if (hoveredNote !== prevHovered || hoveredKeyPitch !== prevKey) render();
  }

  function onMouseUp() {
    if (keyboardDragging) {
      keyboardDragging = false;
      lastPlayedKeyPitch = null;
      NotePreview.stop();
      return;
    }
    if (dragMode) {
      NotePreview.stop();
      dragMode = null;
      dragNote = null;
      dragStart = null;
      const layer = getLayer();
      if (layer) {
        layer.notes.sort((a, b) => a.startBeat - b.startBeat || a.pitch - b.pitch);
        DAW.notify('notes');
      }
    }
  }

  function onWheel(e) {
    e.preventDefault();
    if (e.ctrlKey && e.shiftKey) {
      // Vertical zoom — change row height
      const oldCH = cellH;
      cellH = Math.max(6, Math.min(32, cellH + (e.deltaY > 0 ? -1 : 1)));
      if (cellH !== oldCH) {
        resizeCanvas();
        render();
      }
    } else if (e.ctrlKey) {
      // Horizontal zoom — change beat width
      const oldBW = beatWidth;
      beatWidth = Math.max(8, Math.min(128, beatWidth + (e.deltaY > 0 ? -4 : 4)));
      if (beatWidth !== oldBW) {
        render();
      }
    } else if (e.shiftKey) {
      scrollX = Math.max(0, scrollX + e.deltaY);
      render();
    } else {
      scrollY = Math.max(0, Math.min(gridHeight() - 200, scrollY + e.deltaY));
      render();
    }
  }

  function onDblClick(e) {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const hit = hitTest(mx, my);
    if (hit) {
      DAW.removeNote(layerId, hit.noteIndex);
    }
  }

  /* --- right-click context menu --- */
  let ctxMenu = null;

  function showContextMenu(e) {
    e.preventDefault();
    hideContextMenu();

    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hit = hitTest(mx, my);

    // Build menu items
    const items = [];
    if (hit && hit.zone === 'extension') {
      const layer = getLayer();
      const n = layer?.notes[hit.noteIndex];
      if (n && hit.extType === 'slide') {
        const ext = n.extensions[hit.extIndex];
        for (const curveType of CURVE_TYPES) {
          items.push({
            label: `Curve: ${curveType}` + (ext.curve === curveType ? ' \u2713' : ''),
            action: () => {
              ext.curve = curveType;
              DAW.notify('notes');
            }
          });
        }
        items.push({ separator: true });
      }
      items.push({
        label: 'Remove extension',
        action: () => {
          n.extensions.splice(hit.extIndex, 1);
          DAW.notify('notes');
        }
      });
    } else if (hit) {
      const layer = getLayer();
      const n = layer?.notes[hit.noteIndex];
      // Auto-select the right-clicked note
      if (!DAW.selectedNoteIndices.includes(hit.noteIndex)) {
        DAW.selectedNoteIndices = [hit.noteIndex];
        DAW.notify('selection');
      }
      const selCount = DAW.selectedNoteIndices.length;
      items.push({
        label: selCount > 1 ? `Delete ${selCount} notes` : `Delete note`,
        action: () => {
          const indices = [...DAW.selectedNoteIndices].sort((a, b) => b - a);
          for (const i of indices) layer.notes.splice(i, 1);
          DAW.selectedNoteIndices = [];
          DAW.notify('notes');
          DAW.notify('selection');
        }
      });
      if (selCount === 1 && n) {
        items.push({
          label: 'Duplicate',
          action: () => {
            DAW.addNote(layerId, {
              pitch: n.pitch,
              startBeat: n.startBeat + n.beats,
              beats: n.beats,
              velocity: n.velocity,
              brightness: n.brightness,
              vibrato: n.vibrato,
              extensions: [...(n.extensions || []).map(x => ({...x}))]
            });
            DAW.notify('notes');
          }
        });
      }
      if (selCount > 0) {
        items.push({ separator: true });
        items.push({
          label: 'Select all',
          action: () => {
            DAW.selectedNoteIndices = layer.notes.map((_, i) => i);
            DAW.notify('selection');
          }
        });
      }
    } else {
      const layer = getLayer();
      if (layer && layer.notes.length > 0) {
        items.push({
          label: 'Select all notes',
          action: () => {
            DAW.selectedNoteIndices = layer.notes.map((_, i) => i);
            DAW.notify('selection');
          }
        });
      }
      const beat = snapBeat(xToBeat(mx));
      const pitch = yToPitch(my);
      if (layer && LAYER_TYPES[layer.type]?.hasNotes && pitch >= MIN_PITCH && pitch < MAX_PITCH && beat >= 0) {
        items.push({
          label: `Add note (${midiToName(pitch)})`,
          action: () => {
            DAW.addNote(layer.id, {
              pitch,
              startBeat: beat,
              beats: 1,
              velocity: 0.7,
              brightness: layer.defaultBrightness || 0.5,
              vibrato: 0,
              extensions: []
            });
          }
        });
      }
    }

    if (!items.length) return;

    // Create menu DOM
    ctxMenu = document.createElement('div');
    ctxMenu.className = 'piano-ctx-menu';
    ctxMenu.style.cssText = `
      position: fixed; left: ${e.clientX}px; top: ${e.clientY}px;
      background: #1e2030; border: 1px solid #333; border-radius: 6px;
      padding: 4px 0; min-width: 140px; z-index: 9999;
      box-shadow: 0 4px 16px rgba(0,0,0,0.5); font: 12px system-ui; color: #ccc;
    `;

    for (const item of items) {
      if (item.separator) {
        const sep = document.createElement('div');
        sep.style.cssText = 'height: 1px; background: #333; margin: 4px 8px;';
        ctxMenu.appendChild(sep);
        continue;
      }
      const row = document.createElement('div');
      row.textContent = item.label;
      row.style.cssText = 'padding: 6px 14px; cursor: pointer;';
      row.addEventListener('mouseenter', () => row.style.background = '#2a2c48');
      row.addEventListener('mouseleave', () => row.style.background = 'transparent');
      row.addEventListener('click', () => {
        item.action();
        hideContextMenu();
      });
      ctxMenu.appendChild(row);
    }

    document.body.appendChild(ctxMenu);

    // Close on next click anywhere
    setTimeout(() => {
      document.addEventListener('mousedown', _ctxOutsideClick, { once: true });
    }, 0);
  }

  function _ctxOutsideClick(e) {
    if (ctxMenu && !ctxMenu.contains(e.target)) {
      hideContextMenu();
    }
  }

  function showExtensionAddMenu(e, note, noteIndex) {
    hideContextMenu();
    const segs = computeExtensionSegments(note);
    const endPitch = segs._endPitch;

    const items = [
      {
        label: 'Add Slide (down)',
        action: () => {
          if (!note.extensions) note.extensions = [];
          note.extensions.push({
            type: 'slide', targetPitch: Math.max(MIN_PITCH, endPitch - 2),
            beats: 0.5, curve: 'ease-in-out'
          });
          DAW.notify('notes');
        }
      },
      {
        label: 'Add Slide (up)',
        action: () => {
          if (!note.extensions) note.extensions = [];
          note.extensions.push({
            type: 'slide', targetPitch: Math.min(MAX_PITCH - 1, endPitch + 2),
            beats: 0.5, curve: 'ease-in-out'
          });
          DAW.notify('notes');
        }
      },
      {
        label: 'Add Hold',
        action: () => {
          if (!note.extensions) note.extensions = [];
          note.extensions.push({ type: 'hold', beats: 1 });
          DAW.notify('notes');
        }
      }
    ];

    ctxMenu = document.createElement('div');
    ctxMenu.style.cssText = `
      position: fixed; left: ${e.clientX}px; top: ${e.clientY}px;
      background: #1e2030; border: 1px solid #333; border-radius: 6px;
      padding: 4px 0; min-width: 140px; z-index: 9999;
      box-shadow: 0 4px 16px rgba(0,0,0,0.5); font: 12px system-ui; color: #ccc;
    `;
    for (const item of items) {
      const row = document.createElement('div');
      row.textContent = item.label;
      row.style.cssText = 'padding: 6px 14px; cursor: pointer;';
      row.addEventListener('mouseenter', () => row.style.background = '#2a2c48');
      row.addEventListener('mouseleave', () => row.style.background = 'transparent');
      row.addEventListener('click', () => { item.action(); hideContextMenu(); });
      ctxMenu.appendChild(row);
    }
    document.body.appendChild(ctxMenu);
    setTimeout(() => {
      document.addEventListener('mousedown', _ctxOutsideClick, { once: true });
    }, 0);
  }

  function hideContextMenu() {
    if (ctxMenu) {
      ctxMenu.remove();
      ctxMenu = null;
    }
    document.removeEventListener('mousedown', _ctxOutsideClick);
  }

  init();

  return {
    render, resizeCanvas,
    destroy,
    layerId,
    get playheadBeat() { return _playheadBeat; },
    set playheadBeat(v) { _playheadBeat = v; }
  };
}

/* --- Global keyboard handler (operates on DAW.selectedLayer) --- */
document.addEventListener('keydown', function(e) {
  const pgPage = document.getElementById('page-playground');
  if (!pgPage || pgPage.style.display === 'none') return;

  if (e.key === 'Delete' || e.key === 'Backspace') {
    const layer = DAW.selectedLayer;
    if (!layer) return;
    const indices = [...DAW.selectedNoteIndices].sort((a, b) => b - a);
    for (const i of indices) {
      layer.notes.splice(i, 1);
    }
    DAW.selectedNoteIndices = [];
    DAW.notify('notes');
    DAW.notify('selection');
    e.preventDefault();
  }

  if (e.ctrlKey && e.key === 'c') {
    const layer = DAW.selectedLayer;
    if (layer) DAW.copyNotes(layer.id);
  }
  if (e.ctrlKey && e.key === 'v') {
    const layer = DAW.selectedLayer;
    if (layer) DAW.pasteNotes(layer.id);
  }
});
