/* ================================================================
   DAW State  –  central state management for the playground DAW
   ================================================================ */

const NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

function midiToName(m) {
  return NOTE_NAMES[m % 12] + (Math.floor(m / 12) - 1);
}

function midiToFreq(m) {
  return 440 * Math.pow(2, (m - 69) / 12);
}

function freqToMidi(f) {
  return Math.round(69 + 12 * Math.log2(f / 440));
}

/* ---------- layer type metadata ---------- */

const LAYER_TYPES = {
  synth: {
    label: 'Synth',
    icon: '\u{1F3B9}',
    color: '#4af',
    hasNotes: true,
    defaults: {
      timbre: 'glass', defaultDecay: 1.5, defaultBrightness: 0.5, loop: true,
      vol: 0.35, fadeIn: 4, fadeOut: 8
    },
    params: [
      { key: 'timbre', label: 'Timbre', type: 'select', options: ['glass','sine','saw','fm'] },
      { key: 'defaultDecay', label: 'Decay', type: 'number', min: 0.1, max: 10, step: 0.1 },
      { key: 'defaultBrightness', label: 'Brightness', type: 'number', min: 0, max: 1, step: 0.05 },
      { key: 'loop', label: 'Loop', type: 'checkbox' }
    ]
  }
};

/* ---------- effect type metadata ---------- */

const EFFECT_TYPES = {
  reverb: {
    label: 'Reverb',
    params: [
      { key: 'size', label: 'Size', type: 'number', min: 0, max: 1, step: 0.01, default: 0.8 },
      { key: 'mix', label: 'Mix', type: 'number', min: 0, max: 1, step: 0.01, default: 0.3 }
    ]
  }
};

/* ---------- DAW singleton ---------- */

let _layerIdCounter = 0;

const DAW = {
  /* ----- global state ----- */
  global: { bpm: 72, measures: 8, timeSig: [4, 4], projectName: 'Untitled', description: '' },
  master: { reverb_size: 0.85, reverb_mix: 0.5 },
  metronome: false,
  layers: [],

  /* ----- render cache ----- */
  _dirty: true,
  _cachedMixUrl: null,
  markClean(mixUrl) {
    this._dirty = false;
    this._cachedMixUrl = mixUrl;
  },

  /* ----- selection ----- */
  selectedLayerId: null,
  selectedNoteIndices: [],   // array for multi-select
  clipboard: null,           // { notes: [...] } for copy/paste

  /* ----- computed ----- */
  get totalBeats() {
    return this.global.measures * this.global.timeSig[0];
  },
  get durationSeconds() {
    return (this.totalBeats * 60) / this.global.bpm;
  },

  /* ----- layer helpers ----- */
  newLayerId() {
    return 'layer-' + (++_layerIdCounter);
  },

  addLayer(type) {
    const meta = LAYER_TYPES[type];
    if (!meta) return null;
    const id = this.newLayerId();
    const layer = {
      id,
      name: meta.label + ' ' + _layerIdCounter,
      type,
      solo: false,
      mute: false,
      collapsed: false,
      sections: { instrument: false, keyboard: false, effects: true, visualization: true },
      notes: [],
      effects: [],
      wavUrl: null,
      rendering: false,
      ...JSON.parse(JSON.stringify(meta.defaults))
    };
    this.layers.push(layer);
    if (!this.selectedLayerId) this.selectedLayerId = id;
    this.notify('layers');
    return layer;
  },

  removeLayer(id) {
    this.layers = this.layers.filter(l => l.id !== id);
    if (this.selectedLayerId === id) {
      this.selectedLayerId = this.layers.length ? this.layers[0].id : null;
      this.selectedNoteIndices = [];
    }
    this.notify('layers');
  },

  getLayer(id) {
    return this.layers.find(l => l.id === id) || null;
  },

  get selectedLayer() {
    return this.getLayer(this.selectedLayerId);
  },

  selectLayer(id) {
    this.selectedLayerId = id;
    this.selectedNoteIndices = [];
    this.notify('selection');
  },

  /* ----- note helpers ----- */
  addNote(layerId, note) {
    const layer = this.getLayer(layerId);
    if (!layer) return;
    layer.notes.push({
      pitch: 60, startBeat: 0, beats: 1, velocity: 0.7,
      brightness: 0.5, vibrato: 0, extensions: [], delay: null,
      ...note
    });
    layer.notes.sort((a, b) => a.startBeat - b.startBeat || a.pitch - b.pitch);
    this.notify('notes');
  },

  removeNote(layerId, index) {
    const layer = this.getLayer(layerId);
    if (!layer) return;
    layer.notes.splice(index, 1);
    this.selectedNoteIndices = [];
    this.notify('notes');
  },

  updateNote(layerId, index, changes) {
    const layer = this.getLayer(layerId);
    if (!layer || !layer.notes[index]) return;
    Object.assign(layer.notes[index], changes);
    this.notify('notes');
  },

  /* ----- copy/paste ----- */
  copyNotes(layerId) {
    const layer = this.getLayer(layerId);
    if (!layer) return;
    const indices = this.selectedNoteIndices.length > 0
      ? this.selectedNoteIndices
      : layer.notes.map((_, i) => i);
    this.clipboard = {
      notes: indices.map(i => JSON.parse(JSON.stringify(layer.notes[i]))).filter(Boolean)
    };
  },

  pasteNotes(layerId) {
    if (!this.clipboard || !this.clipboard.notes.length) return;
    const layer = this.getLayer(layerId);
    if (!layer) return;
    const meta = LAYER_TYPES[layer.type];
    if (!meta || !meta.hasNotes) return;
    for (const n of this.clipboard.notes) {
      layer.notes.push(JSON.parse(JSON.stringify(n)));
    }
    layer.notes.sort((a, b) => a.startBeat - b.startBeat || a.pitch - b.pitch);
    this.notify('notes');
  },

  /* ----- config conversion ----- */
  toConfig() {
    const cfg = {
      global: {
        bpm: this.global.bpm,
        measures: this.global.measures,
        time_sig: [...this.global.timeSig]
      },
      master: { ...this.master },
      layers: []
    };
    for (const layer of this.layers) {
      if (layer.mute) continue;
      cfg.layers.push(this._layerToConfig(layer));
    }
    return cfg;
  },

  toLayerConfig(layerId) {
    const layer = this.getLayer(layerId);
    if (!layer) return null;
    return {
      global: {
        bpm: this.global.bpm,
        measures: this.global.measures,
        time_sig: [...this.global.timeSig]
      },
      master: { ...this.master },
      layers: [this._layerToConfig(layer)]
    };
  },

  _layerToConfig(layer) {
    // map synth → expressive_melody for engine compatibility
    const engineType = layer.type === 'synth' ? 'expressive_melody' : layer.type;
    const lc = { type: engineType, vol: layer.vol, fade_in: layer.fadeIn, fade_out: layer.fadeOut };

    lc.timbre = layer.timbre;
    lc.default_decay = layer.defaultDecay;
    lc.default_brightness = layer.defaultBrightness;
    lc.loop = layer.loop;
    const sorted = [...layer.notes].sort((a, b) => a.startBeat - b.startBeat);
    lc.notes = sorted.map(n => {
      const en = {
        pitch: n.pitch,
        start_beat: n.startBeat,
        beats: n.beats,
        velocity: n.velocity
      };
      if (n.brightness != null && n.brightness !== layer.defaultBrightness) en.brightness = n.brightness;
      if (n.vibrato) en.vibrato = n.vibrato;
      const exts = n.extensions || [];
      if (exts.length > 0) {
        en.extensions = exts.map(ext => {
          if (ext.type === 'slide') {
            return { type: 'slide', target_pitch: ext.targetPitch, beats: ext.beats, curve: ext.curve || 'ease-in-out' };
          }
          if (ext.type === 'hold') {
            return { type: 'hold', beats: ext.beats };
          }
          return ext;
        });
        // Backward compat: also emit slide_to/slide_beats for first slide
        const firstSlide = exts.find(e => e.type === 'slide');
        if (firstSlide) {
          en.slide_to = firstSlide.targetPitch;
          en.slide_beats = firstSlide.beats;
        }
      }
      if (n.delay) {
        en.delay = { time: n.delay.time, feedback: n.delay.feedback, mix: n.delay.mix };
      }
      return en;
    });

    if (layer.effects && layer.effects.length) {
      lc.effects = layer.effects.map(fx => ({ ...fx }));
    }

    return lc;
  },

  fromConfig(config) {
    const g = config.global || {};
    this.global.bpm = g.bpm || 72;
    this.global.measures = g.measures || 8;
    this.global.timeSig = g.time_sig || [4, 4];

    const m = config.master || {};
    this.master.reverb_size = m.reverb_size ?? 0.85;
    this.master.reverb_mix = m.reverb_mix ?? 0.5;

    this.layers = [];
    _layerIdCounter = 0;
    for (const lc of (config.layers || [])) {
      // map expressive_melody → synth for backward compat
      const dawType = lc.type === 'expressive_melody' ? 'synth' : lc.type;
      const meta = LAYER_TYPES[dawType];
      if (!meta) continue;
      const id = this.newLayerId();
      const layer = {
        id,
        name: meta.label + ' ' + _layerIdCounter,
        type: dawType,
        solo: false, mute: false, collapsed: false,
        sections: { instrument: false, keyboard: false, effects: true, visualization: true },
        notes: [],
        effects: [],
        wavUrl: null, rendering: false,
        vol: lc.vol ?? meta.defaults.vol ?? 0.5,
        fadeIn: lc.fade_in ?? meta.defaults.fadeIn ?? 4,
        fadeOut: lc.fade_out ?? meta.defaults.fadeOut ?? 8,
        ...JSON.parse(JSON.stringify(meta.defaults))
      };

      layer.timbre = lc.timbre || 'glass';
      layer.defaultDecay = lc.default_decay ?? 1.5;
      layer.defaultBrightness = lc.default_brightness ?? 0.5;
      layer.loop = lc.loop ?? true;
      // convert notes → absolute startBeat (use start_beat if present, else sequential)
      let beat = 0;
      for (const n of (lc.notes || [])) {
        const note = {
          pitch: n.pitch,
          startBeat: n.start_beat != null ? n.start_beat : beat,
          beats: n.beats || 1,
          velocity: n.velocity ?? 0.7,
          brightness: n.brightness ?? layer.defaultBrightness,
          vibrato: n.vibrato ?? 0,
          extensions: [],
          delay: null
        };
        if (n.extensions && Array.isArray(n.extensions)) {
          note.extensions = n.extensions.map(ext => {
            if (ext.type === 'slide') {
              return { type: 'slide', targetPitch: ext.target_pitch, beats: ext.beats || 0.5, curve: ext.curve || 'ease-in-out' };
            }
            if (ext.type === 'hold') {
              return { type: 'hold', beats: ext.beats || 1 };
            }
            return ext;
          });
        } else if (n.slide_to != null) {
          note.extensions.push({ type: 'slide', targetPitch: n.slide_to, beats: n.slide_beats || 0.5, curve: 'ease-in-out' });
        }
        if (n.delay) {
          note.delay = { time: n.delay.time || 0.3, feedback: n.delay.feedback || 0.4, mix: n.delay.mix || 0.3 };
        }
        layer.notes.push(note);
        beat = note.startBeat + (n.beats || 1);
      }

      layer.effects = (lc.effects || []).map(fx => ({ ...fx }));

      this.layers.push(layer);
    }
    this.selectedLayerId = this.layers.length ? this.layers[0].id : null;
    this.selectedNoteIndices = [];
    this.notify('layers');
    this.notify('selection');
  },

  /* ----- event bus ----- */
  _listeners: {},
  on(event, fn) {
    (this._listeners[event] = this._listeners[event] || []).push(fn);
  },
  off(event, fn) {
    const arr = this._listeners[event];
    if (arr) this._listeners[event] = arr.filter(f => f !== fn);
  },
  notify(event) {
    if (['notes', 'layers', 'all'].includes(event)) {
      this._dirty = true;
      this._cachedMixUrl = null;
    }
    for (const fn of (this._listeners[event] || [])) fn();
  }
};
