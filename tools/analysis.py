"""Audio analysis utilities with LUFS and spectral smoothing.

Typed (strict-mode) helpers for extracting metrics used by the iterative
workflow. LUFS measurement uses `pyloudnorm` when available; otherwise the
value will be `None`.
"""
from __future__ import annotations
from typing import Tuple, Dict, Optional
import wave
from pathlib import Path
import numpy as np


def _read_wav(wav_path: str) -> Tuple[np.ndarray, int]:
    p = Path(wav_path)
    if not p.exists():
        raise FileNotFoundError(wav_path)
    with wave.open(str(p), 'rb') as wf:
        nch = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        fr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sampwidth == 2:
        dtype = np.int16
    elif sampwidth == 4:
        dtype = np.int32
    else:
        dtype = np.int16

    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if nch > 1:
        data = data.reshape(-1, nch).mean(axis=1)

    # normalize to -1..1
    if dtype == np.int16:
        data = data / 32768.0
    elif dtype == np.int32:
        data = data / 2147483648.0

    return data, fr


def compute_rms(wav_path: str) -> float:
    data, _ = _read_wav(wav_path)
    rms = float(np.sqrt((data ** 2).mean()))
    return rms


def compute_dbfs(wav_path: str) -> float:
    rms = compute_rms(wav_path)
    import math
    if rms <= 1e-12:
        return -120.0
    return 20.0 * math.log10(rms)


def _framewise_spectral_centroids(data: np.ndarray, fr: int, frame_size: int = 2048, hop: int = 1024) -> np.ndarray:
    import numpy.fft as fft
    n = len(data)
    centroids = []
    for start in range(0, max(1, n - frame_size + 1), hop):
        raw_frame = data[start:start + frame_size]
        frame = raw_frame * np.hanning(len(raw_frame))
        if len(frame) < 16:
            continue
        spec = np.abs(fft.rfft(frame))
        freqs = fft.rfftfreq(len(frame), d=1.0 / fr)
        if spec.sum() <= 0:
            centroids.append(0.0)
        else:
            centroids.append(float((freqs * spec).sum() / spec.sum()))
    return np.array(centroids, dtype=float)


def smooth_array(arr: np.ndarray, window_len: int = 5) -> np.ndarray:
    if arr.size == 0:
        return arr
    if window_len <= 1:
        return arr
    window = np.ones(window_len) / float(window_len)
    return np.convolve(arr, window, mode='same')


def compute_spectral_stats(wav_path: str) -> Tuple[float, float]:
    """Return (centroid_mean, centroid_spread) using framewise analysis.

    centroid_spread is the standard deviation of framewise centroids.
    """
    data, fr = _read_wav(wav_path)
    centroids = _framewise_spectral_centroids(data, fr)
    if centroids.size == 0:
        return 0.0, 0.0
    sm = smooth_array(centroids, window_len=7)
    mean = float(np.mean(sm))
    spread = float(np.std(sm))
    return mean, spread


def compute_lufs(wav_path: str) -> Optional[float]:
    try:
        import pyloudnorm as pyln
    except Exception:
        return None
    data, sr = _read_wav(wav_path)
    meter = pyln.Meter(sr)
    try:
        loudness = float(meter.integrated_loudness(data))
    except Exception:
        loudness = None
    return loudness


def compute_duration(wav_path: str) -> float:
    with wave.open(wav_path, 'rb') as wf:
        frames = wf.getnframes()
        fr = wf.getframerate()
    return frames / float(fr)


def compute_metrics(wav_path: str) -> Dict[str, object]:
    data, fr = _read_wav(wav_path)
    rms = float(np.sqrt((data ** 2).mean()))
    import math
    if rms <= 1e-12:
        dbfs = -120.0
    else:
        dbfs = 20.0 * math.log10(rms)
    centroid_mean, centroid_spread = compute_spectral_stats(wav_path)
    lufs = compute_lufs(wav_path)

    return {
        'rms': float(rms),
        'dbfs': float(dbfs),
        'spectral_centroid': float(centroid_mean),
        'spectral_spread': float(centroid_spread),
        'duration': float(len(data) / fr),
        'samplerate': int(fr),
        'lufs': lufs,
    }


def spectral_flatness(wav_path: str) -> float:
    """Compute spectral flatness (geometric mean / arithmetic mean) of magnitude spectrum."""
    data, fr = _read_wav(wav_path)
    import numpy.fft as fft
    frame = data if len(data) < fr * 60 else data[:fr * 60]
    spec = np.abs(fft.rfft(frame)) + 1e-12
    geo_mean = float(np.exp(np.mean(np.log(spec))))
    arith_mean = float(np.mean(spec))
    if arith_mean <= 0:
        return 0.0
    return float(geo_mean / arith_mean)


def band_energy_ratios(wav_path: str, bands=(120.0, 1000.0, 5000.0)) -> Dict[str, float]:
    """Compute energy ratios for bands: low, mid, high based on band edges.

    Returns dict with keys `low`, `mid`, `high` summing to 1.0 (or 0 if silent).
    """
    data, fr = _read_wav(wav_path)
    import numpy.fft as fft
    frame = data if len(data) < fr * 60 else data[:fr * 60]
    spec = np.abs(fft.rfft(frame))
    freqs = fft.rfftfreq(len(frame), d=1.0 / fr)
    # band edges
    low_edge, mid_edge, high_edge = bands
    low_mask = freqs <= low_edge
    mid_mask = (freqs > low_edge) & (freqs <= mid_edge)
    high_mask = freqs > mid_edge
    low_e = float((spec[low_mask] ** 2).sum())
    mid_e = float((spec[mid_mask] ** 2).sum())
    high_e = float((spec[high_mask] ** 2).sum())
    total = low_e + mid_e + high_e
    if total <= 0:
        return {'low': 0.0, 'mid': 0.0, 'high': 0.0}
    return {'low': low_e / total, 'mid': mid_e / total, 'high': high_e / total}


def normalize_to_target_lufs(wav_path: str, target_lufs: float, out_path: str) -> Optional[float]:
    """Normalize WAV to `target_lufs` using pyloudnorm when available.

    Writes normalized file to `out_path`. Returns achieved LUFS or None if pyloudnorm missing.
    """
    try:
        import pyloudnorm as pyln
    except Exception:
        return None

    data, sr = _read_wav(wav_path)
    meter = pyln.Meter(sr)
    try:
        cur = float(meter.integrated_loudness(data))
    except Exception:
        return None
    gain_db = float(target_lufs - cur)
    factor = 10.0 ** (gain_db / 20.0)
    norm = data * factor
    # soft limiter to avoid harsh clipping/coloration
    peak = float(np.max(np.abs(norm))) if norm.size > 0 else 0.0
    if peak > 0.99:
        # apply gentle tanh soft-knee limiter
        # scale factor chosen so values near -1..1 are softened
        limiter_gain = 1.2
        norm = np.tanh(norm * limiter_gain) / np.tanh(limiter_gain)
    # final hard clip to ensure numeric safety
    norm = np.clip(norm, -1.0, 1.0)

    # write out as 16-bit WAV
    import wave
    import struct
    int_data = (norm * 32767.0).astype(np.int16)
    with wave.open(str(out_path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int_data.tobytes())

    # re-measure
    try:
        achieved = float(pyln.Meter(sr).integrated_loudness(norm))
    except Exception:
        achieved = None
    return achieved


def generate_visualization(wav_path: str, out_png: str) -> None:
    """Create waveform + spectrogram PNG for `wav_path` and save to `out_png`."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return

    data, sr = _read_wav(wav_path)
    duration = len(data) / sr
    t = np.linspace(0.0, duration, num=len(data))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
    ax1.plot(t, data, linewidth=0.4)
    ax1.set_title('Waveform')
    ax1.set_xlabel('s')

    Pxx, freqs, bins, im = ax2.specgram(data, NFFT=2048, Fs=sr, noverlap=1024, cmap='magma')
    ax2.set_title('Spectrogram')
    ax2.set_xlabel('s')
    plt.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)
