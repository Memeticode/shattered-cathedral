/* ================================================================
   DAW Waveform & Spectrogram  –  client-side audio visualization
   ================================================================ */

const DAWWaveform = (() => {
  let waveCanvas, specCanvas, waveCtx, specCtx;
  let layerSelect, analysisEl;
  let audioCtx = null;
  let audioBuffers = {};  // url → AudioBuffer

  function init() {
    waveCanvas = document.getElementById('daw-waveform');
    specCanvas = document.getElementById('daw-spectrogram');
    layerSelect = document.getElementById('daw-analysis-layer');
    analysisEl = document.getElementById('daw-analysis');

    if (waveCanvas) waveCtx = waveCanvas.getContext('2d');
    if (specCanvas) specCtx = specCanvas.getContext('2d');

    layerSelect?.addEventListener('change', onLayerChange);

    DAW.on('render', onRender);
    DAW.on('layers', updateLayerOptions);
  }

  function getAudioContext() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
  }

  function updateLayerOptions() {
    if (!layerSelect) return;
    const current = layerSelect.value;
    layerSelect.innerHTML = '<option value="__all__">All Layers (Mix)</option>';
    for (const layer of DAW.layers) {
      const meta = LAYER_TYPES[layer.type];
      const opt = document.createElement('option');
      opt.value = layer.id;
      opt.textContent = `${meta?.icon || ''} ${layer.name}`;
      if (layer.wavUrl) opt.textContent += ' ✓';
      layerSelect.appendChild(opt);
    }
    // restore selection
    if ([...layerSelect.options].some(o => o.value === current)) {
      layerSelect.value = current;
    }
  }

  function onLayerChange() {
    const val = layerSelect.value;
    let url = null;
    if (val === '__all__') {
      url = DAW._lastMixUrl;
    } else {
      const layer = DAW.getLayer(val);
      url = layer?.wavUrl;
    }
    if (url) {
      loadAndVisualize(url);
    }
  }

  async function onRender() {
    updateLayerOptions();
    // auto-visualize the most recent render
    const val = layerSelect?.value || '__all__';
    let url = null;
    if (val === '__all__') {
      url = DAW._lastMixUrl;
    } else {
      const layer = DAW.getLayer(val);
      url = layer?.wavUrl;
    }
    if (url) {
      await loadAndVisualize(url);
    }
  }

  async function loadAndVisualize(url) {
    if (!analysisEl) return;
    analysisEl.style.display = '';

    try {
      // check cache
      if (audioBuffers[url]) {
        drawWaveform(audioBuffers[url]);
        drawSpectrogram(audioBuffers[url]);
        return;
      }

      const ctx = getAudioContext();
      const resp = await fetch(url);
      const arrayBuf = await resp.arrayBuffer();
      const audioBuf = await ctx.decodeAudioData(arrayBuf);
      audioBuffers[url] = audioBuf;

      drawWaveform(audioBuf);
      drawSpectrogram(audioBuf);
    } catch (e) {
      console.warn('Waveform load failed:', e);
    }
  }

  function drawWaveform(audioBuf) {
    if (!waveCtx || !waveCanvas) return;

    const dpr = window.devicePixelRatio || 1;
    const dispW = waveCanvas.parentElement.clientWidth - 28;
    const dispH = 100;
    waveCanvas.width = dispW * dpr;
    waveCanvas.height = dispH * dpr;
    waveCanvas.style.width = dispW + 'px';
    waveCanvas.style.height = dispH + 'px';
    waveCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const data = audioBuf.getChannelData(0);
    const samples = data.length;
    const step = Math.ceil(samples / dispW);
    const midY = dispH / 2;

    waveCtx.fillStyle = '#080810';
    waveCtx.fillRect(0, 0, dispW, dispH);

    // center line
    waveCtx.strokeStyle = '#1a1c28';
    waveCtx.lineWidth = 0.5;
    waveCtx.beginPath();
    waveCtx.moveTo(0, midY);
    waveCtx.lineTo(dispW, midY);
    waveCtx.stroke();

    // waveform
    waveCtx.strokeStyle = '#4af';
    waveCtx.lineWidth = 0.8;
    waveCtx.beginPath();

    for (let i = 0; i < dispW; i++) {
      const start = i * step;
      let min = 1, max = -1;
      for (let j = 0; j < step && start + j < samples; j++) {
        const v = data[start + j];
        if (v < min) min = v;
        if (v > max) max = v;
      }
      const yMin = midY + min * midY;
      const yMax = midY + max * midY;
      waveCtx.moveTo(i, yMin);
      waveCtx.lineTo(i, yMax);
    }
    waveCtx.stroke();
  }

  function drawSpectrogram(audioBuf) {
    if (!specCtx || !specCanvas) return;

    const dpr = window.devicePixelRatio || 1;
    const dispW = specCanvas.parentElement.clientWidth - 28;
    const dispH = 120;
    specCanvas.width = dispW * dpr;
    specCanvas.height = dispH * dpr;
    specCanvas.style.width = dispW + 'px';
    specCanvas.style.height = dispH + 'px';
    specCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const data = audioBuf.getChannelData(0);
    const sr = audioBuf.sampleRate;
    const fftSize = 2048;
    const hopSize = Math.max(1, Math.floor(data.length / dispW));
    const freqBins = fftSize / 2;

    specCtx.fillStyle = '#080810';
    specCtx.fillRect(0, 0, dispW, dispH);

    // compute FFT frames
    const numFrames = Math.min(dispW, Math.floor(data.length / hopSize));
    const window_ = new Float32Array(fftSize);
    // Hann window
    for (let i = 0; i < fftSize; i++) {
      window_[i] = 0.5 * (1 - Math.cos(2 * Math.PI * i / (fftSize - 1)));
    }

    // magma-inspired colormap
    function magma(t) {
      t = Math.max(0, Math.min(1, t));
      // simplified magma: dark purple → red → yellow
      const r = Math.floor(Math.min(255, t * 3 * 255));
      const g = Math.floor(Math.min(255, Math.max(0, (t - 0.4) * 2.5) * 255));
      const b = Math.floor(Math.min(255, (t < 0.5 ? t * 2 : 1 - (t - 0.5) * 2) * 255));
      return `rgb(${r},${g},${b})`;
    }

    // use OfflineAudioContext for FFT if available, otherwise simple DFT approximation
    // For simplicity and speed, use a basic approach
    const imgData = specCtx.createImageData(numFrames, dispH);

    for (let frame = 0; frame < numFrames; frame++) {
      const offset = frame * hopSize;
      // apply window and compute power spectrum (simplified via DFT bins)
      const real = new Float32Array(fftSize);
      const imag = new Float32Array(fftSize);

      for (let i = 0; i < fftSize && offset + i < data.length; i++) {
        real[i] = data[offset + i] * window_[i];
      }

      // Simple FFT using the Cooley-Tukey algorithm
      fft(real, imag, fftSize);

      // compute magnitude and map to display
      for (let y = 0; y < dispH; y++) {
        // map y to frequency bin (log scale)
        const frac = 1 - y / dispH;
        const binIdx = Math.floor(Math.pow(frac, 2) * freqBins);
        if (binIdx >= freqBins) continue;

        const mag = Math.sqrt(real[binIdx] * real[binIdx] + imag[binIdx] * imag[binIdx]);
        const db = 20 * Math.log10(Math.max(1e-10, mag / fftSize));
        const norm = Math.max(0, Math.min(1, (db + 80) / 80));

        const px = (y * numFrames + frame) * 4;
        const t = norm;
        imgData.data[px]     = Math.min(255, t * 3 * 255) | 0;
        imgData.data[px + 1] = Math.min(255, Math.max(0, (t - 0.4) * 2.5) * 255) | 0;
        imgData.data[px + 2] = Math.min(255, (t < 0.5 ? t * 2 : 1 - (t - 0.5) * 2) * 255) | 0;
        imgData.data[px + 3] = 255;
      }
    }

    // draw scaled
    const tmpCanvas = document.createElement('canvas');
    tmpCanvas.width = numFrames;
    tmpCanvas.height = dispH;
    tmpCanvas.getContext('2d').putImageData(imgData, 0, 0);
    specCtx.drawImage(tmpCanvas, 0, 0, dispW, dispH);
  }

  // In-place Cooley-Tukey FFT (radix-2, assumes n is power of 2)
  function fft(real, imag, n) {
    // bit-reversal permutation
    for (let i = 1, j = 0; i < n; i++) {
      let bit = n >> 1;
      while (j & bit) { j ^= bit; bit >>= 1; }
      j ^= bit;
      if (i < j) {
        [real[i], real[j]] = [real[j], real[i]];
        [imag[i], imag[j]] = [imag[j], imag[i]];
      }
    }

    for (let len = 2; len <= n; len *= 2) {
      const half = len / 2;
      const angle = -2 * Math.PI / len;
      const wRe = Math.cos(angle);
      const wIm = Math.sin(angle);

      for (let i = 0; i < n; i += len) {
        let curRe = 1, curIm = 0;
        for (let j = 0; j < half; j++) {
          const tRe = curRe * real[i + j + half] - curIm * imag[i + j + half];
          const tIm = curRe * imag[i + j + half] + curIm * real[i + j + half];
          real[i + j + half] = real[i + j] - tRe;
          imag[i + j + half] = imag[i + j] - tIm;
          real[i + j] += tRe;
          imag[i + j] += tIm;
          const newRe = curRe * wRe - curIm * wIm;
          curIm = curRe * wIm + curIm * wRe;
          curRe = newRe;
        }
      }
    }
  }

  return { init };
})();
