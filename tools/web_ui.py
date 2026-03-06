"""Flask web UI: gallery mode + live real-time demo dashboard.

Gallery mode (browse past sessions):
    python -m tools.web_ui --outdir artifacts/iter

Live mode (real-time auto-directed generation):
    python -m tools.web_ui --live --outdir artifacts/demo
"""
from __future__ import annotations

import argparse
import json
import queue
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, send_from_directory, render_template_string, Response, request, jsonify
import base64

from shattered_audio.log import get_logger
from tools.event_bus import EventBus

log = get_logger("web_ui")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
MAX_GALLERY_ITEMS = 200


def _build_items(logp: Path) -> list[dict[str, object]]:
    """Parse session_log.json into template-ready item dicts."""
    items: list[dict[str, object]] = []
    if not logp.exists():
        return items
    try:
        raw = json.loads(logp.read_text(encoding="utf8"))
        for entry in reversed(raw[-MAX_GALLERY_ITEMS:]):
            wav = entry.get("wav") or ""
            wav_name = Path(wav).name if wav else None
            png_name = None
            if wav_name:
                png_name = Path(wav_name).with_suffix(".png").name
            items.append({
                "iteration": entry.get("iteration"),
                "time": entry.get("time"),
                "note": entry.get("note", ""),
                "wav_name": wav_name,
                "png_name": png_name,
                "metrics": entry.get("metrics") or {},
                "commentary": entry.get("commentary"),
                "plan": entry.get("plan"),
            })
    except Exception as e:
        log.warning("Failed to parse session log: %s", e)
    return items


# ---------------------------------------------------------------------------
# Gallery template (existing functionality, cleaned up)
# ---------------------------------------------------------------------------
GALLERY_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Shattered Cathedral - Iterations</title>
  <style>
    body { font-family: sans-serif; margin: 20px; background: #0a0a0f; color: #e0e0e0; }
    .controls { margin-bottom: 16px; }
    .gallery { display:flex; flex-wrap:wrap; gap:12px; }
    .item { width:220px; border:1px solid #333; padding:8px; border-radius:6px; background:#151520; }
    .thumb { width:200px; height:112px; object-fit:cover; background:#111; display:block }
    .meta { font-size:12px; margin-top:6px }
    .btn { display:inline-block; margin-right:6px; padding:4px 8px; background:#2b6cff; color:#fff; text-decoration:none; border-radius:4px; cursor:pointer; border:none; font-size:13px; }
    .btn.secondary { background:#444 }
    .btn.download { background:#1a9a4a }
    audio { width:600px; }
  </style>
</head>
<body>
  <h1>Iterations: {{ path }}</h1>
  <div class="controls">
    <strong id="selected-title">No selection</strong><br/>
    <audio id="main-audio" controls preload="none"></audio>
    <div style="margin-top:8px">
      <button id="play-btn" class="btn">Play</button>
      <button id="pause-btn" class="btn secondary">Pause</button>
      <button id="stop-btn" class="btn secondary">Stop</button>
      <a id="download-current" class="btn download" href="#" download>Download WAV</a>
    </div>
  </div>
  <div class="gallery">
  {% for it in items %}
    <div class="item" data-wav="{{ it.wav_name }}" data-title="Iteration {{ it.iteration }} &mdash; {{ it.time }}">
      {% if it.png_name %}
        <img class="thumb select-thumb" src="/renders/{{ it.png_name }}" alt="viz"/>
      {% else %}
        <div style="width:200px;height:112px;background:#222;color:#555;display:flex;align-items:center;justify-content:center">No Image</div>
      {% endif %}
      <div class="meta">
        <strong>Iteration {{ it.iteration }}</strong><br/>
        {% if it.metrics %}<span>RMS={{ it.metrics.rms }} dBFS={{ it.metrics.dbfs }}</span><br/>{% endif %}
        {% if it.commentary %}<div style="margin-top:4px"><b>Commentary:</b> {{ it.commentary }}</div>{% endif %}
        {% if it.plan %}<div style="margin-top:4px"><b>Plan:</b> {{ it.plan }}</div>{% endif %}
      </div>
      <div style="margin-top:8px">
        {% if it.wav_name %}
          <a class="btn play-link" href="/renders/{{ it.wav_name }}">Preview</a>
          <a class="btn secondary" href="/renders/{{ it.wav_name }}" download>DL</a>
        {% endif %}
      </div>
    </div>
  {% endfor %}
  </div>
  <script>
    const mainAudio = document.getElementById('main-audio');
    function selectItem(el) {
      const wav = el.dataset.wav, title = el.dataset.title || 'Selection';
      document.getElementById('selected-title').textContent = title;
      if (wav) {
        mainAudio.src = '/renders/' + wav;
        document.getElementById('download-current').href = '/renders/' + wav;
      }
      mainAudio.load();
    }
    document.querySelectorAll('.select-thumb').forEach(img =>
      img.addEventListener('click', ev => selectItem(ev.currentTarget.parentElement)));
    document.querySelectorAll('.play-link').forEach(a => {
      a.addEventListener('click', ev => { ev.preventDefault(); selectItem(ev.currentTarget.closest('.item')); mainAudio.play(); });
    });
    document.getElementById('play-btn').addEventListener('click', () => mainAudio.play());
    document.getElementById('pause-btn').addEventListener('click', () => mainAudio.pause());
    document.getElementById('stop-btn').addEventListener('click', () => { mainAudio.pause(); mainAudio.currentTime = 0; });
    const first = document.querySelector('.item');
    if (first) selectItem(first);
  </script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# App template (sidebar + home + playground + live dashboard)
# ---------------------------------------------------------------------------
APP_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Shattered Cathedral</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: #08080e; color: #d0d0d0; }

    /* ===== Sidebar ===== */
    .sidebar { position: fixed; top: 0; left: 0; bottom: 0; width: 200px; background: #0c0c16;
               border-right: 1px solid #1a1a2a; z-index: 50; display: flex; flex-direction: column;
               transition: width 0.2s ease; overflow: hidden; }
    .sidebar.collapsed { width: 48px; }
    .sidebar-toggle { background: none; border: none; color: #888; font-size: 20px; cursor: pointer;
                      padding: 12px 14px; text-align: left; flex-shrink: 0; }
    .sidebar-toggle:hover { color: #ccc; }
    .sidebar-nav { display: flex; flex-direction: column; gap: 2px; padding: 8px 6px; }
    .nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 6px;
                color: #888; text-decoration: none; cursor: pointer; white-space: nowrap; font-size: 13px;
                transition: background 0.15s, color 0.15s; }
    .nav-item:hover { background: #1a1a2e; color: #ccc; }
    .nav-item.active { background: #1a2a40; color: #8af; }
    .nav-icon { font-size: 18px; flex-shrink: 0; width: 24px; text-align: center; }
    .nav-label { transition: opacity 0.2s; }
    .sidebar.collapsed .nav-label { opacity: 0; pointer-events: none; }
    .sidebar-brand { padding: 14px 12px 6px; font-size: 11px; color: #555; text-transform: uppercase;
                     letter-spacing: 1px; white-space: nowrap; }
    .sidebar.collapsed .sidebar-brand { opacity: 0; }

    .main-content { margin-left: 200px; transition: margin-left 0.2s ease; min-height: 100vh; }
    .sidebar.collapsed ~ .main-content { margin-left: 48px; }
    .page-section { display: none; }

    /* ===== Home page ===== */
    .home-container { max-width: 700px; margin: 0 auto; padding: 80px 24px; text-align: center; }
    .home-title { font-size: 32px; color: #8af; font-weight: 300; margin-bottom: 16px; }
    .home-subtitle { font-size: 15px; color: #888; line-height: 1.7; margin-bottom: 48px; max-width: 540px;
                     margin-left: auto; margin-right: auto; }
    .home-cards { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; }
    .home-card { background: #12121c; border: 1px solid #1e1e30; border-radius: 10px; padding: 28px 24px;
                 width: 280px; cursor: pointer; transition: border-color 0.2s, transform 0.15s; text-align: left; }
    .home-card:hover { border-color: #2b6cff; transform: translateY(-2px); }
    .home-card h3 { font-size: 16px; color: #8af; margin-bottom: 8px; font-weight: 500; }
    .home-card p { font-size: 13px; color: #888; line-height: 1.6; }

    /* ===== Playground ===== */
    .pg-container { max-width: 1100px; margin: 0 auto; padding: 20px 24px; }
    .pg-header { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; flex-wrap: wrap; }
    .pg-header h2 { font-size: 18px; color: #8af; font-weight: 400; }
    .pg-tabs { display: flex; gap: 2px; margin-left: 16px; }
    .pg-tab { background: #1a1a2e; border: 1px solid #333; color: #888; border-radius: 4px;
              padding: 5px 14px; cursor: pointer; font-size: 12px; }
    .pg-tab.active { background: #2b6cff; border-color: #2b6cff; color: #fff; }
    .pg-actions { margin-left: auto; display: flex; gap: 10px; align-items: center; }
    .pg-actions select { background: #1a1a2e; color: #ddd; border: 1px solid #333; border-radius: 4px;
                         padding: 5px 10px; font-size: 13px; }
    .pg-render-btn { background: #1a9a4a; color: #fff; border: none; border-radius: 4px;
                     padding: 6px 20px; cursor: pointer; font-size: 13px; font-weight: 600; }
    .pg-render-btn:disabled { background: #333; cursor: not-allowed; }
    .pg-status { font-size: 12px; color: #888; }
    .pg-tab-content { display: none; }
    .pg-tab-content.active { display: block; }
    .pg-json-area { width: 100%; min-height: 500px; background: #0a0e14; color: #ccd; border: 1px solid #1e1e30;
                    border-radius: 6px; padding: 14px; font-family: 'Cascadia Code','Fira Code',monospace;
                    font-size: 12px; resize: vertical; line-height: 1.5; }
    .pg-player { margin-top: 16px; padding: 12px 16px; background: #12121c; border: 1px solid #1e1e30;
                 border-radius: 8px; display: flex; align-items: center; gap: 14px; }
    .pg-player audio { flex: 1; max-width: 500px; height: 32px; }
    .pg-error { color: #f66; font-size: 13px; margin-top: 8px; }

    /* Playground visual controls */
    .pg-section { background: #0d0d18; border: 1px solid #1e1e30; border-radius: 8px; margin-bottom: 12px; }
    .pg-section-header { padding: 10px 16px; cursor: pointer; display: flex; align-items: center; gap: 8px;
                         user-select: none; }
    .pg-section-header:hover { background: #111120; border-radius: 8px; }
    .pg-section-title { font-size: 13px; color: #8af; font-weight: 600; text-transform: uppercase;
                        letter-spacing: 0.5px; }
    .pg-section-arrow { font-size: 10px; color: #8af; transition: transform 0.2s; }
    .pg-section-arrow.open { transform: rotate(90deg); }
    .pg-section-body { padding: 0 16px 14px; display: none; }
    .pg-section-body.open { display: block; }
    .pg-field { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .pg-field label { font-size: 12px; color: #aaa; min-width: 110px; }
    .pg-field input[type=number] { background: #1a1a2e; color: #ddd; border: 1px solid #333;
                                    border-radius: 4px; padding: 4px 8px; font-size: 12px; width: 80px; }
    .pg-field input[type=range] { flex: 1; max-width: 200px; accent-color: #2b6cff; }
    .pg-field .range-val { font-size: 11px; color: #8af; font-family: monospace; min-width: 40px; }
    .pg-field select { background: #1a1a2e; color: #ddd; border: 1px solid #333; border-radius: 4px;
                       padding: 4px 8px; font-size: 12px; }
    .pg-field input[type=text] { background: #1a1a2e; color: #ddd; border: 1px solid #333;
                                  border-radius: 4px; padding: 4px 8px; font-size: 12px; flex: 1; }
    .pg-layer-card { background: #10101a; border: 1px solid #1e1e30; border-radius: 6px;
                     margin-bottom: 8px; }
    .pg-layer-header { padding: 8px 12px; display: flex; align-items: center; gap: 8px; cursor: pointer; }
    .pg-layer-header:hover { background: #151520; }
    .pg-layer-type { font-size: 12px; color: #6a6; font-weight: 600; }
    .pg-layer-body { padding: 8px 12px 12px; display: none; }
    .pg-layer-body.open { display: block; }
    .pg-layer-remove { background: #522; color: #f88; border: 1px solid #633; border-radius: 4px;
                       padding: 2px 8px; cursor: pointer; font-size: 11px; margin-left: auto; }
    .pg-layer-arrow { font-size: 10px; color: #6a6; transition: transform 0.2s; }
    .pg-layer-arrow.open { transform: rotate(90deg); }
    .pg-add-layer { background: #1a2a1a; color: #6a6; border: 1px solid #253; border-radius: 4px;
                    padding: 6px 16px; cursor: pointer; font-size: 12px; margin-top: 4px; }
    .pg-note-table { width: 100%; border-collapse: collapse; margin-top: 6px; }
    .pg-note-table th { font-size: 10px; color: #666; text-transform: uppercase; padding: 2px 4px;
                        text-align: left; border-bottom: 1px solid #222; }
    .pg-note-table td { padding: 2px 3px; }
    .pg-note-table input { background: #1a1a2e; color: #ddd; border: 1px solid #2a2a3e; border-radius: 3px;
                           padding: 3px 5px; font-size: 11px; width: 100%; }
    .pg-note-remove { background: none; border: none; color: #f66; cursor: pointer; font-size: 14px; padding: 0 4px; }
    .pg-add-note { background: #1a1a2e; color: #888; border: 1px solid #333; border-radius: 4px;
                   padding: 3px 12px; cursor: pointer; font-size: 11px; margin-top: 4px; }

    /* Header */
    .header { padding: 12px 24px; background: #10101a; border-bottom: 1px solid #222;
              display: flex; align-items: center; gap: 16px; }
    .header h1 { font-size: 18px; color: #8af; }
    .header .header-right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
    .header .status { font-size: 13px; color: #888; }
    .header-btn { background: #2b6cff; color: #fff; border: none; border-radius: 4px;
                  padding: 6px 16px; cursor: pointer; font-size: 13px; font-weight: 600; }

    /* Layout toggle */
    .layout-toggle { display: flex; gap: 2px; }
    .layout-btn { background: #1a1a2e; border: 1px solid #333; color: #888; border-radius: 4px;
                  padding: 4px 10px; cursor: pointer; font-size: 12px; }
    .layout-btn.active { background: #2b6cff; border-color: #2b6cff; color: #fff; }
    .layout-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    /* Session bar (visible during active session) */
    .session-bar { padding: 8px 24px; background: #12121c; border-bottom: 1px solid #222;
                   display: flex; gap: 14px; align-items: center; }
    .session-bar button { border: none; border-radius: 4px; padding: 6px 18px; cursor: pointer;
                          font-size: 13px; font-weight: 600; color: #fff; }
    .session-bar button:disabled { background: #333; cursor: not-allowed; }
    .session-bar .stop { background: #c33; }
    .session-bar .continue-btn { background: #1a9a4a; }
    .progress-bar { height: 3px; background: #222; border-radius: 2px; overflow: hidden; flex: 1; min-width: 80px; }
    .progress-bar .fill { height: 100%; background: #2b6cff; transition: width 0.5s ease; }

    /* Modal overlay */
    .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.75);
                     z-index: 100; display: flex; align-items: center; justify-content: center; }
    .modal-panel { background: #12121c; border: 1px solid #2a2a3e; border-radius: 10px;
                   width: min(860px, 95vw); max-height: 85vh; display: flex; flex-direction: column; }
    .modal-header { padding: 16px 20px; border-bottom: 1px solid #1e1e30;
                    display: flex; align-items: center; justify-content: space-between; }
    .modal-header h2 { font-size: 16px; color: #8af; font-weight: 500; }
    .modal-close-btn { background: none; border: none; color: #666; font-size: 18px; cursor: pointer; }
    .modal-close-btn:hover { color: #aaa; }
    .modal-body { display: flex; flex: 1; overflow: hidden; min-height: 0; }
    .modal-left { width: 240px; border-right: 1px solid #1e1e30; overflow-y: auto; padding: 12px; }
    .modal-right { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
    .modal-footer { padding: 14px 20px; border-top: 1px solid #1e1e30; display: flex; justify-content: flex-end; }
    .modal-footer .btn-primary { background: #2b6cff; color: #fff; border: none; border-radius: 4px;
                                 padding: 8px 24px; cursor: pointer; font-size: 14px; font-weight: 600; }
    .modal-footer .btn-primary:disabled { background: #333; cursor: not-allowed; }

    /* Seed list */
    .seed-list { display: flex; flex-direction: column; gap: 4px; }
    .seed-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; border: 1px solid transparent;
                 font-size: 13px; color: #bbb; }
    .seed-item:hover { background: #1a1a2e; }
    .seed-item.selected { background: #1a2a40; border-color: #2b6cff; color: #fff; }
    .seed-item.disabled { opacity: 0.4; cursor: not-allowed; pointer-events: none; }

    /* Preset preview */
    .preset-preview { background: #0d0d18; border-radius: 6px; padding: 14px; border: 1px solid #1e1e30; }
    .preview-title { font-size: 15px; color: #8af; font-weight: 600; margin-bottom: 6px; }
    .preview-tags { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
    .preview-tag { font-size: 10px; background: #1a1a30; color: #66a; padding: 2px 7px;
                   border-radius: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
    .preview-desc { font-size: 13px; line-height: 1.6; color: #999; }

    /* Modal params */
    .modal-params { display: flex; flex-direction: column; gap: 10px; }
    .modal-params label { font-size: 13px; color: #aaa; display: flex; align-items: center; gap: 8px; }
    .modal-params input[type=number] { background: #1a1a2e; color: #ddd; border: 1px solid #333;
                                        border-radius: 4px; padding: 4px 8px; font-size: 13px; width: 70px; }

    /* Sticky player bar */
    .player-bar { position: sticky; top: 0; z-index: 10; padding: 8px 24px;
                  background: #0c0c16; border-bottom: 1px solid #1a1a2a;
                  display: flex; align-items: center; gap: 12px; }
    .player-bar audio { flex: 1; max-width: 600px; height: 32px; }


    /* Timeline */
    .timeline { max-width: 820px; margin: 0 auto; padding: 24px 24px 80px; }
    .timeline.page-mode { overflow: hidden; position: relative; padding: 0;
                          height: calc(100vh - 120px); max-width: none; }
    .page-slot { position: absolute; inset: 0; overflow-y: auto;
                 padding: 24px 24px 80px; max-width: 820px; margin: 0 auto;
                 display: none; }
    .page-slot.active { display: block; }

    /* Page navigation */
    .page-nav { position: fixed; bottom: 0; left: 0; right: 0; background: #0c0c16;
                border-top: 1px solid #1a1a2a; padding: 10px 24px;
                display: none; align-items: center; justify-content: center; gap: 16px; z-index: 20; }
    .page-nav.visible { display: flex; }
    .page-nav-arrow { background: none; border: 1px solid #333; color: #aaa; border-radius: 4px;
                      padding: 4px 14px; cursor: pointer; font-size: 16px; }
    .page-nav-arrow:disabled { opacity: 0.3; cursor: not-allowed; }
    .page-nav-counter { font-size: 13px; color: #888; min-width: 80px; text-align: center; }
    .page-nav-dots { display: flex; gap: 6px; align-items: center; }
    .page-dot { width: 10px; height: 10px; border-radius: 50%; background: #333;
                cursor: pointer; transition: background 0.2s; border: none; }
    .page-dot.done { background: #2b6cff; }
    .page-dot.current { background: #8af; transform: scale(1.3); }
    .page-dot.live { background: #6f6; animation: pulse 1.5s infinite; }
    .page-dot:disabled { cursor: not-allowed; opacity: 0.3; }

    /* Shared card base */
    .card { border-radius: 8px; margin-bottom: 12px; padding: 16px 20px;
            border-left: 3px solid #333; animation: fadeIn 0.3s ease; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

    /* Iteration divider */
    .card-iter { background: none; border: none; border-left: none; padding: 20px 0 8px;
                 display: flex; align-items: center; gap: 12px; }
    .card-iter .iter-badge { background: #2b6cff; color: #fff; font-size: 12px; font-weight: 700;
                 padding: 3px 10px; border-radius: 12px; white-space: nowrap; }
    .card-iter .iter-line { flex: 1; height: 1px; background: #222; }

    /* Config / diff card */
    .card-config { background: #0d1117; border-left-color: #3a6; }
    .card-config .config-header { display: flex; align-items: center; gap: 8px; cursor: pointer;
                 user-select: none; }
    .card-config .config-header:hover { opacity: 0.8; }
    .card-config .card-label { font-size: 11px; color: #3a6; text-transform: uppercase;
                 letter-spacing: 1px; font-weight: 600; }
    .card-config .config-summary { font-size: 11px; color: #556; margin-left: auto; }
    .card-config .config-arrow { font-size: 10px; color: #3a6; transition: transform 0.2s; }
    .card-config .config-arrow.open { transform: rotate(90deg); }
    .card-config .config-body { display: none; margin-top: 8px; }
    .card-config .config-body.open { display: block; }
    .diff-row { display: flex; gap: 8px; padding: 2px 0; font-size: 12px;
                font-family: 'Cascadia Code', 'Fira Code', monospace; }
    .diff-row .path { color: #8af; min-width: 160px; }
    .diff-row .old-val { color: #f66; text-decoration: line-through; }
    .diff-row .new-val { color: #6f6; }
    .diff-row .arrow { color: #444; }
    .diff-baseline { color: #555; font-style: italic; font-size: 12px; }
    .config-expand { background: #151b26; color: #6a9; border: 1px solid #253; border-radius: 4px;
                 padding: 4px 10px; cursor: pointer; font-size: 11px; margin-top: 8px; }
    .config-pre { display: none; margin-top: 8px; background: #0a0e14; border: 1px solid #1a2a1a;
                 border-radius: 4px; padding: 12px; font-family: 'Cascadia Code', monospace;
                 font-size: 11px; max-height: 300px; overflow-y: auto;
                 white-space: pre-wrap; word-break: break-word; color: #aab; }
    .config-pre.open { display: block; }

    /* Piano roll */
    .piano-roll { margin-top: 10px; overflow-x: auto; background: #080810;
                  border: 1px solid #1a2a1a; border-radius: 4px; padding: 8px; }
    .piano-roll svg { display: block; }
    .piano-roll .pr-legend { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 6px; font-size: 11px; color: #888; }
    .piano-roll .pr-legend-item { display: flex; align-items: center; gap: 4px; }
    .piano-roll .pr-legend-swatch { width: 10px; height: 10px; border-radius: 2px; }

    /* Audio card */
    .card-audio { background: #111118; border-left-color: #66f; }
    .card-audio .card-label { font-size: 11px; color: #88f; text-transform: uppercase;
                 letter-spacing: 1px; margin-bottom: 10px; font-weight: 600; }
    .card-audio .audio-row { display: flex; gap: 14px; align-items: flex-start; }
    .card-audio .audio-left { flex: 1; min-width: 0; }
    .card-audio .audio-left audio { width: 100%; margin-bottom: 8px; }
    .card-audio .metrics-row { display: flex; gap: 12px; flex-wrap: wrap; }
    .card-audio .m-item { font-size: 12px; color: #999; }
    .card-audio .m-item .m-val { color: #8af; font-weight: 600; font-family: monospace; }
    .card-audio .viz-slot { flex-shrink: 0; width: 260px; }
    .card-audio .viz-img { width: 100%; border-radius: 4px; border: 1px solid #222; }

    /* Thought card */
    .card-thought { background: #13111a; border-left-color: #a6f; }
    .card-thought .card-label { font-size: 11px; color: #a6f; text-transform: uppercase;
                 letter-spacing: 1px; margin-bottom: 8px; font-weight: 600; }
    .card-thought .commentary { font-size: 14px; line-height: 1.6; color: #ccc; margin-bottom: 10px; }
    .card-thought .critique { font-size: 14px; line-height: 1.6; color: #f88; margin-bottom: 10px; }
    .card-thought .rationale { font-size: 13px; line-height: 1.5; color: #8a8aaa; font-style: italic;
                 margin-bottom: 10px; padding-left: 12px; border-left: 2px solid #333; }
    .card-thought .plan { font-size: 13px; line-height: 1.5; color: #6f6; font-weight: 500; }
    .card-thought .plan-label { font-size: 11px; color: #666; text-transform: uppercase;
                 letter-spacing: 0.5px; margin-bottom: 4px; }
    .card-thought .critique-label { font-size: 11px; color: #f66; text-transform: uppercase;
                 letter-spacing: 0.5px; margin-bottom: 4px; }

    /* Error card */
    .card-error { background: #1a1010; border-left-color: #c44; }
    .card-error .card-label { font-size: 11px; color: #c44; text-transform: uppercase;
                 letter-spacing: 1px; font-weight: 600; }

    /* Status card (rendering...) */
    .card-status { background: none; border: none; border-left: none; padding: 8px 0;
                 font-size: 12px; color: #555; }
    .card-status .spinner { display: inline-block; width: 12px; height: 12px;
                 border: 2px solid #333; border-top-color: #2b6cff; border-radius: 50%;
                 animation: spin 0.8s linear infinite; margin-right: 8px; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* Welcome state */
    .welcome { text-align: center; padding: 80px 20px; color: #444; }
    .welcome h2 { font-size: 24px; color: #8af; margin-bottom: 12px; font-weight: 400; }
    .welcome p { font-size: 14px; }

    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
    .pulsing { animation: pulse 1.5s infinite; }
  </style>
</head>
<body>
  <!-- Sidebar -->
  <div id="sidebar" class="sidebar">
    <button id="sidebar-toggle" class="sidebar-toggle">&#9776;</button>
    <div class="sidebar-brand">Shattered Cathedral</div>
    <nav class="sidebar-nav">
      <a class="nav-item active" data-page="home" onclick="navigate('home')">
        <span class="nav-icon">&#127968;</span><span class="nav-label">Home</span>
      </a>
      <a class="nav-item" data-page="playground" onclick="navigate('playground')">
        <span class="nav-icon">&#127911;</span><span class="nav-label">Playground</span>
      </a>
      <a class="nav-item" data-page="live" onclick="navigate('live')">
        <span class="nav-icon">&#9889;</span><span class="nav-label">Iterative Gen</span>
      </a>
    </nav>
  </div>

  <div class="main-content" id="main-content">

  <!-- ===== HOME PAGE ===== -->
  <div id="page-home" class="page-section" style="display:block">
    <div class="home-container">
      <h1 class="home-title">Shattered Cathedral</h1>
      <p class="home-subtitle">
        A modular audio engine for generative sound design. Build layered soundscapes from
        cathedral pads, expressive melodies, phantom choirs, and void bass &mdash; then
        iterate with AI-driven evolution or tweak configs by hand.
      </p>
      <div class="home-cards">
        <div class="home-card" onclick="navigate('playground')">
          <h3>&#127911; Music Playground</h3>
          <p>Edit configs with visual controls or raw JSON. Render and listen instantly.
             Great for experimenting and debugging the audio engine.</p>
        </div>
        <div class="home-card" onclick="navigate('live')">
          <h3>&#9889; Iterative Generation</h3>
          <p>AI-driven iterative sessions that evolve configs over multiple rounds.
             Watch melodies develop through critique and refinement.</p>
        </div>
      </div>
    </div>
  </div>

  <!-- ===== PLAYGROUND PAGE ===== -->
  <div id="page-playground" class="page-section">
    <div class="pg-container">
      <div class="pg-header">
        <h2>Music Playground</h2>
        <div class="pg-tabs">
          <button class="pg-tab active" data-tab="visual" onclick="pgSwitchTab('visual')">Visual Controls</button>
          <button class="pg-tab" data-tab="json" onclick="pgSwitchTab('json')">Raw JSON</button>
        </div>
        <div class="pg-actions">
          <select id="pg-preset-select" onchange="pgLoadPreset(this.value)">
            <option value="">-- Load Preset --</option>
          </select>
          <button id="pg-render-btn" class="pg-render-btn" onclick="pgRender()">Render</button>
          <span id="pg-status" class="pg-status"></span>
        </div>
      </div>
      <div id="pg-tab-visual" class="pg-tab-content active"></div>
      <div id="pg-tab-json" class="pg-tab-content">
        <textarea id="pg-json-textarea" class="pg-json-area" spellcheck="false"></textarea>
      </div>
      <div id="pg-player" class="pg-player" style="display:none">
        <audio id="pg-audio" controls preload="auto"></audio>
        <span id="pg-render-time" class="pg-status"></span>
      </div>
      <div id="pg-error" class="pg-error"></div>
    </div>
  </div>

  <!-- ===== LIVE / ITERATIVE GENERATION PAGE ===== -->
  <div id="page-live" class="page-section">
  <div class="header">
    <h1>Shattered Cathedral</h1>
    <div class="header-right">
      <div class="layout-toggle">
        <button class="layout-btn" id="btn-layout-scroll" title="Scroll view">&#9776; Scroll</button>
        <button class="layout-btn" id="btn-layout-page" title="Page view">&#9723; Page</button>
      </div>
      <span id="status" class="status">Ready</span>
      <button class="header-btn" id="btn-open-modal">New Session</button>
    </div>
  </div>

  <div class="session-bar" id="session-bar" style="display:none">
    <div class="progress-bar">
      <div id="progress-fill" class="fill" style="width:0%"></div>
    </div>
    <button id="btn-continue" class="continue-btn" style="display:none">Continue +N</button>
    <button id="btn-stop" class="stop" style="display:none" disabled>Stop</button>
  </div>

  <div class="player-bar">
    <audio id="audio-player" controls preload="none"></audio>

  </div>

  <div class="timeline" id="timeline">
    <div class="welcome" id="welcome">
      <h2>Ready to begin</h2>
      <p>Click <strong>New Session</strong> to configure and start generating.</p>
    </div>
  </div>

  <div class="page-nav" id="page-nav">
    <button class="page-nav-arrow" id="nav-prev" disabled>&#8592;</button>
    <span class="page-nav-counter" id="nav-counter"></span>
    <div class="page-nav-dots" id="nav-dots"></div>
    <button class="page-nav-arrow" id="nav-next" disabled>&#8594;</button>
  </div>

  <!-- Start / Continue modal -->
  <div id="start-modal" class="modal-overlay" style="display:none">
    <div class="modal-panel">
      <div class="modal-header">
        <h2 id="modal-title">Configure Session</h2>
        <button id="modal-close" class="modal-close-btn">&#x2715;</button>
      </div>
      <div class="modal-body">
        <div class="modal-left">
          <div id="seed-list" class="seed-list"></div>
        </div>
        <div class="modal-right">
          <div class="preset-preview" id="preset-preview">
            <div class="preview-title" id="preview-title"></div>
            <div class="preview-tags" id="preview-tags"></div>
            <div class="preview-desc" id="preview-desc"></div>
          </div>
          <div class="modal-params">
            <label>AI Provider:
              <select id="ai-provider" style="background:#1a1a2e;color:#ddd;border:1px solid #333;border-radius:4px;padding:4px 8px;font-size:13px">
                <option value="anthropic" selected>Anthropic (Claude)</option>
                <option value="openai">OpenAI</option>
                <option value="local">Local evolution (no AI)</option>
              </select>
            </label>
            <label>Iterations: <input id="iter-count" type="number" value="5" min="1" max="50"/></label>
            <div style="display:flex;gap:10px;flex-wrap:wrap">
              <label>BPM: <input id="cfg-bpm" type="number" value="72" min="30" max="240"/></label>
              <label>Measures: <input id="cfg-measures" type="number" value="8" min="1" max="64"/></label>
              <label>Duration (s): <input id="duration" type="number" value="26.67" min="1" max="600" step="0.01"/></label>
            </div>
            <label><input type="checkbox" id="cb-visualize" checked/> Generate visualizations</label>
            <label><input type="checkbox" id="cb-normalize"/> Normalize audio</label>
            <label style="flex-direction:column;align-items:flex-start;gap:4px">
              Creative direction:
              <textarea id="user-prompt" rows="3" style="width:100%;background:#1a1a2e;color:#ddd;border:1px solid #333;border-radius:4px;padding:8px;font-size:13px;resize:vertical" placeholder="Describe your musical intent... e.g. 'Dark, minimal atmosphere with a slow haunting melody that builds tension'"></textarea>
            </label>
            <label style="flex-direction:column;align-items:flex-start;gap:4px">
              Input config (optional, overrides seed):
              <textarea id="input-config" rows="3" style="width:100%;background:#1a1a2e;color:#ddd;border:1px solid #333;border-radius:4px;padding:8px;font-family:'Cascadia Code',monospace;font-size:11px;resize:vertical" placeholder="Paste a JSON config here, or leave empty to use the selected seed..."></textarea>
              <input type="file" id="input-config-file" accept=".json" style="font-size:12px;color:#888"/>
            </label>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button id="btn-start" class="btn-primary">Start Session</button>
      </div>
    </div>
  </div>

  <script>
    /* --- Preset data from server --- */
    const presetsData = {{ presets_json | safe }};
    const presetKeys = Object.keys(presetsData);
    let selectedSeed = presetKeys[0] || '';

    /* --- DOM refs --- */
    const audioPlayer = document.getElementById('audio-player');
    const statusEl = document.getElementById('status');
    const btnStart = document.getElementById('btn-start');
    const btnContinue = document.getElementById('btn-continue');
    const btnStop = document.getElementById('btn-stop');
    const btnOpenModal = document.getElementById('btn-open-modal');
    const modal = document.getElementById('start-modal');
    const modalTitle = document.getElementById('modal-title');
    const sessionBar = document.getElementById('session-bar');
    const progressFill = document.getElementById('progress-fill');
    const timeline = document.getElementById('timeline');
    const pageNav = document.getElementById('page-nav');

    /* --- State --- */
    let lastCompletedIter = 0;
    let iterOffset = 0;
    let evtSource = null;
    let sessionActive = false;
    let iterationData = {};
    let continueMode = false;

    // Layout state
    let layoutMode = localStorage.getItem('sc_layout_mode') || 'scroll';
    let pageSlots = {};
    let completedPages = new Set();
    let currentPage = 0;
    let totalPages = 0;
    let currentBuildIter = 0;

    /* --- Helpers --- */

    function setStatus(text, pulsing) {
      statusEl.textContent = text;
      statusEl.classList.toggle('pulsing', !!pulsing);
    }

    function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    function scrollToBottom() {
      if (layoutMode === 'page') return;
      setTimeout(function() { window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'}); }, 50);
    }

    function getCardTarget(gi) {
      if (layoutMode === 'page' && pageSlots[gi]) return pageSlots[gi];
      return timeline;
    }

    /* --- Modal: seed list & preview --- */

    function buildSeedList() {
      const list = document.getElementById('seed-list');
      list.innerHTML = '';
      presetKeys.forEach(function(key) {
        const item = document.createElement('div');
        item.className = 'seed-item' + (key === selectedSeed ? ' selected' : '');
        if (continueMode) item.classList.add('disabled');
        item.textContent = presetsData[key].title || key;
        item.dataset.key = key;
        if (!continueMode) {
          item.addEventListener('click', function() {
            selectedSeed = key;
            document.querySelectorAll('.seed-item').forEach(function(el) {
              el.classList.toggle('selected', el.dataset.key === key);
            });
            updatePresetPreview(key);
          });
        }
        list.appendChild(item);
      });
      updatePresetPreview(selectedSeed);
    }

    function updatePresetPreview(key) {
      var p = presetsData[key];
      if (!p) { p = {title: key, description: '', tags: []}; }
      document.getElementById('preview-title').textContent = p.title || key;
      document.getElementById('preview-desc').textContent = p.description || '';
      var tagsEl = document.getElementById('preview-tags');
      tagsEl.innerHTML = (p.tags || []).map(function(t) {
        return '<span class="preview-tag">' + esc(t) + '</span>';
      }).join('');
    }

    /* --- BPM / Measures / Duration linkage --- */
    var bpmInput = document.getElementById('cfg-bpm');
    var measuresInput = document.getElementById('cfg-measures');
    var durationInput = document.getElementById('duration');
    var beatsPerMeasure = 4;
    var _linkLock = false;

    function updateDurationFromMeasures() {
      if (_linkLock) return;
      _linkLock = true;
      var bpm = parseFloat(bpmInput.value) || 72;
      var measures = parseFloat(measuresInput.value) || 8;
      durationInput.value = (measures * beatsPerMeasure * 60 / bpm).toFixed(2);
      _linkLock = false;
    }

    function updateMeasuresFromDuration() {
      if (_linkLock) return;
      _linkLock = true;
      var bpm = parseFloat(bpmInput.value) || 72;
      var secs = parseFloat(durationInput.value) || 15;
      measuresInput.value = Math.max(1, Math.round(secs * bpm / (beatsPerMeasure * 60)));
      _linkLock = false;
    }

    bpmInput.addEventListener('input', updateDurationFromMeasures);
    measuresInput.addEventListener('input', updateDurationFromMeasures);
    durationInput.addEventListener('input', updateMeasuresFromDuration);

    /* --- Input config file upload --- */
    document.getElementById('input-config-file').addEventListener('change', function(e) {
      var file = e.target.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function(ev) { document.getElementById('input-config').value = ev.target.result; };
      reader.readAsText(file);
    });

    /* --- Modal open/close --- */

    function openModal(isContinue) {
      continueMode = !!isContinue;
      modalTitle.textContent = continueMode ? 'Continue Session' : 'Configure Session';
      btnStart.textContent = continueMode ? 'Continue' : 'Start Session';
      buildSeedList();
      modal.style.display = 'flex';
    }

    function closeModal() { modal.style.display = 'none'; }

    btnOpenModal.addEventListener('click', function() { openModal(false); });
    document.getElementById('modal-close').addEventListener('click', closeModal);
    modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });

    /* --- Layout toggle --- */

    function setLayoutMode(mode) {
      layoutMode = mode;
      localStorage.setItem('sc_layout_mode', mode);
      document.getElementById('btn-layout-scroll').classList.toggle('active', mode === 'scroll');
      document.getElementById('btn-layout-page').classList.toggle('active', mode === 'page');
      timeline.classList.toggle('page-mode', mode === 'page');
      pageNav.classList.toggle('visible', mode === 'page' && totalPages > 0);
      if (mode === 'page' && currentPage > 0) showPage(currentPage);
    }

    function setLayoutToggleEnabled(enabled) {
      document.getElementById('btn-layout-scroll').disabled = !enabled;
      document.getElementById('btn-layout-page').disabled = !enabled;
    }

    document.getElementById('btn-layout-scroll').addEventListener('click', function() {
      if (!this.disabled) setLayoutMode('scroll');
    });
    document.getElementById('btn-layout-page').addEventListener('click', function() {
      if (!this.disabled) setLayoutMode('page');
    });

    /* --- Page view navigation --- */

    function showPage(gi) {
      currentPage = gi;
      Object.entries(pageSlots).forEach(function(entry) {
        entry[1].classList.toggle('active', parseInt(entry[0]) === gi);
      });
      updateNavControls();
    }

    function updateNavControls() {
      document.getElementById('nav-counter').textContent = 'Step ' + currentPage + ' / ' + totalPages;
      document.getElementById('nav-prev').disabled = (currentPage <= 1);
      var nextExists = pageSlots[currentPage + 1] !== undefined;
      document.getElementById('nav-next').disabled = !nextExists;
      updateNavDots();
    }

    function updateNavDots() {
      var dots = document.getElementById('nav-dots');
      dots.innerHTML = '';
      var keys = Object.keys(pageSlots).map(Number).sort(function(a,b){return a-b;});
      keys.forEach(function(gi) {
        var dot = document.createElement('button');
        dot.className = 'page-dot';
        if (completedPages.has(gi)) dot.classList.add('done');
        if (gi === currentPage) dot.classList.add('current');
        if (gi === currentBuildIter && !completedPages.has(gi)) dot.classList.add('live');
        dot.addEventListener('click', function() { showPage(gi); });
        dots.appendChild(dot);
      });
    }

    document.getElementById('nav-prev').addEventListener('click', function() {
      if (currentPage > 1) showPage(currentPage - 1);
    });
    document.getElementById('nav-next').addEventListener('click', function() {
      if (pageSlots[currentPage + 1]) showPage(currentPage + 1);
    });

    /* --- Piano roll renderer --- */

    var _LAYER_COLORS = {
      'expressive_melody': '#4af',
      'cathedral_pad': '#6a6',
      'void_bass': '#a66',
      'phantom_choir': '#a6f',
      'tape_decay': '#886'
    };
    var _NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

    function midiName(n) { return _NOTE_NAMES[n % 12] + (Math.floor(n / 12) - 1); }

    function renderPianoRoll(config) {
      if (!config || !config.layers) return null;
      var melodyLayers = config.layers.filter(function(l) {
        return l.type === 'expressive_melody' && l.notes && l.notes.length > 0;
      });
      if (melodyLayers.length === 0) return null;

      // Gather pitches and compute bounds
      var allPitches = [];
      var maxBeats = 0;
      melodyLayers.forEach(function(layer) {
        var b = 0;
        layer.notes.forEach(function(n) {
          allPitches.push(n.pitch);
          if (n.slide_to != null) allPitches.push(n.slide_to);
          b += n.beats + (n.slide_beats || 0);
        });
        if (b > maxBeats) maxBeats = b;
      });

      var minP = Math.min.apply(null, allPitches) - 3;
      var maxP = Math.max.apply(null, allPitches) + 3;
      var range = maxP - minP + 1;

      var cellW = 28;  // px per beat
      var cellH = 8;   // px per semitone
      var leftM = 44;  // left margin for labels
      var topM = 18;   // top margin for beat labels
      var svgW = leftM + Math.ceil(maxBeats) * cellW + 16;
      var svgH = topM + range * cellH + 8;

      var parts = [];
      parts.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + svgW + '" height="' + svgH +
                 '" style="font-family:monospace;font-size:9px">');

      // Background
      parts.push('<rect x="0" y="0" width="' + svgW + '" height="' + svgH + '" fill="#080810"/>');

      // Grid rows (pitch lines)
      for (var p = minP; p <= maxP; p++) {
        var y = topM + (maxP - p) * cellH;
        var isC = (p % 12 === 0);
        var color = isC ? '#2a2a3a' : '#151520';
        parts.push('<line x1="' + leftM + '" y1="' + y + '" x2="' + svgW + '" y2="' + y +
                   '" stroke="' + color + '" stroke-width="' + (isC ? 1 : 0.5) + '"/>');
        if (isC || p === minP || p === maxP) {
          parts.push('<text x="' + (leftM - 4) + '" y="' + (y + 3) +
                     '" fill="#555" text-anchor="end">' + midiName(p) + '</text>');
        }
      }

      // Grid columns (beat lines)
      for (var b = 0; b <= Math.ceil(maxBeats); b++) {
        var x = leftM + b * cellW;
        parts.push('<line x1="' + x + '" y1="' + topM + '" x2="' + x + '" y2="' + svgH +
                   '" stroke="#1a1a28" stroke-width="0.5"/>');
        if (b % 4 === 0) {
          parts.push('<text x="' + x + '" y="' + (topM - 4) + '" fill="#555" text-anchor="middle">' + b + '</text>');
        }
      }

      // Draw notes for each melody layer
      var layerIdx = 0;
      melodyLayers.forEach(function(layer) {
        var baseColor = _LAYER_COLORS['expressive_melody'];
        var cursor = 0;
        layer.notes.forEach(function(n) {
          var pitch = n.pitch;
          var beats = n.beats;
          var vel = n.velocity != null ? n.velocity : 0.7;
          var opacity = 0.3 + vel * 0.7;

          var nx = leftM + cursor * cellW;
          var ny = topM + (maxP - pitch) * cellH;
          var nw = beats * cellW;

          // Note rectangle
          parts.push('<rect x="' + nx + '" y="' + (ny - cellH + 1) + '" width="' + Math.max(1, nw - 1) +
                     '" height="' + (cellH - 1) + '" rx="2" fill="' + baseColor + '" opacity="' + opacity.toFixed(2) + '"/>');

          // Vibrato indicator (wavy top border)
          if (n.vibrato && n.vibrato > 0.05) {
            parts.push('<line x1="' + nx + '" y1="' + (ny - cellH + 1) + '" x2="' + (nx + nw - 1) +
                       '" y2="' + (ny - cellH + 1) + '" stroke="#ff0" stroke-width="1.5" opacity="0.5" stroke-dasharray="2,2"/>');
          }

          cursor += beats;

          // Slide
          if (n.slide_to != null && n.slide_beats) {
            var slideBeats = n.slide_beats;
            var sx1 = leftM + cursor * cellW;
            var sy1 = topM + (maxP - pitch) * cellH - cellH / 2;
            var sx2 = leftM + (cursor + slideBeats) * cellW;
            var sy2 = topM + (maxP - n.slide_to) * cellH - cellH / 2;
            // Curved slide line
            var cpx = (sx1 + sx2) / 2;
            var cpy1 = sy1;
            var cpy2 = sy2;
            parts.push('<path d="M' + sx1 + ',' + sy1 + ' C' + cpx + ',' + cpy1 + ' ' + cpx + ',' + cpy2 + ' ' + sx2 + ',' + sy2 +
                       '" stroke="#f84" stroke-width="2" fill="none" opacity="0.8"/>');
            // Small dot at slide end
            parts.push('<circle cx="' + sx2 + '" cy="' + sy2 + '" r="2.5" fill="#f84" opacity="0.8"/>');
            cursor += slideBeats;
          }
        });
        layerIdx++;
      });

      parts.push('</svg>');

      // Build legend for non-melodic layers
      var legendParts = [];
      config.layers.forEach(function(l) {
        if (l.type === 'expressive_melody') return;
        var col = _LAYER_COLORS[l.type] || '#888';
        var info = l.type;
        if (l.freq) info += ' (' + Math.round(l.freq) + ' Hz)';
        if (l.chord) info += ' (chord)';
        legendParts.push('<span class="pr-legend-item"><span class="pr-legend-swatch" style="background:' + col + '"></span>' + esc(info) + '</span>');
      });

      var html = '<div class="piano-roll">' + parts.join('');
      if (legendParts.length > 0) {
        html += '<div class="pr-legend">' + legendParts.join('') + '</div>';
      }
      html += '</div>';
      return html;
    }

    /* --- Card builders --- */

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
      // Piano roll visualization
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

      var cardAudio = el.querySelector('audio');
      cardAudio.addEventListener('play', function() {
        audioPlayer.src = wavUrl;
        audioPlayer.currentTime = cardAudio.currentTime;
        audioPlayer.play().catch(function(){});
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

    /* --- SSE --- */

    function startSSE() {
      if (evtSource) evtSource.close();
      evtSource = new EventSource('/api/events');
      sessionActive = true;
      setLayoutToggleEnabled(false);

      evtSource.addEventListener('iteration_start', function(e) {
        var d = JSON.parse(e.data);
        var gi = d.iteration + iterOffset;
        var totalGi = d.total + iterOffset;
        currentBuildIter = gi;
        totalPages = totalGi;

        var pct = ((d.iteration - 1) / d.total * 100).toFixed(0);
        progressFill.style.width = pct + '%';
        setStatus('Iteration ' + gi + '/' + totalGi, true);
        iterationData[gi] = {};

        if (layoutMode === 'page') {
          var slot = document.createElement('div');
          slot.className = 'page-slot';
          slot.id = 'page-slot-' + gi;
          timeline.appendChild(slot);
          pageSlots[gi] = slot;
          pageNav.classList.add('visible');

          // Add iteration header inside the page slot
          var hdr = document.createElement('div');
          hdr.className = 'card card-iter';
          hdr.innerHTML = '<span class="iter-badge">Iteration ' + gi + ' / ' + totalGi + '</span><span class="iter-line"></span>';
          slot.appendChild(hdr);

          addStatusCard(gi, 'Rendering...');
          showPage(gi);
        } else {
          addIterDivider(gi, totalGi);
          addStatusCard(gi, 'Rendering...');
        }
      });

      evtSource.addEventListener('config_ready', function(e) {
        var d = JSON.parse(e.data);
        var gi = d.iteration + iterOffset;
        iterationData[gi] = iterationData[gi] || {};
        iterationData[gi].config = d.config;
        iterationData[gi].diff = d.diff;
        addConfigCard(gi, d.config, d.diff);
      });

      evtSource.addEventListener('render_complete', function(e) {
        var d = JSON.parse(e.data);
        var gi = d.iteration + iterOffset;
        iterationData[gi] = iterationData[gi] || {};
        iterationData[gi].wav_url = d.wav_url;
        removeStatusCard(gi);
        addAudioCard(gi, d.wav_url);
        setStatus('Iteration ' + gi + ' &mdash; Analyzing...', true);

      });

      evtSource.addEventListener('metrics_ready', function(e) {
        var d = JSON.parse(e.data);
        var gi = d.iteration + iterOffset;
        iterationData[gi] = iterationData[gi] || {};
        iterationData[gi].metrics = d.metrics;
        updateAudioMetrics(gi, d.metrics);
      });

      evtSource.addEventListener('evaluation_ready', function(e) {
        var d = JSON.parse(e.data);
        var gi = d.iteration + iterOffset;
        iterationData[gi] = iterationData[gi] || {};
        iterationData[gi].commentary = d.commentary;
        iterationData[gi].critique = d.critique;
        iterationData[gi].rationale = d.rationale;
        iterationData[gi].plan = d.plan;
        addThoughtCard(gi, d.commentary, d.critique, d.rationale, d.plan);
        setStatus('Iteration ' + gi + ' &mdash; Complete', false);
        completedPages.add(gi);
        if (layoutMode === 'page') updateNavControls();
      });

      evtSource.addEventListener('visualization_ready', function(e) {
        var d = JSON.parse(e.data);
        var gi = d.iteration + iterOffset;
        iterationData[gi] = iterationData[gi] || {};
        iterationData[gi].png_url = d.png_url;
        addVizToAudioCard(gi, d.png_url);
      });

      evtSource.addEventListener('error_event', function(e) {
        var d = JSON.parse(e.data);
        var gi = d.iteration + iterOffset;
        removeStatusCard(gi);
        addErrorCard(gi, d.error || 'Unknown error');
        setStatus('Error in iteration ' + gi, false);
      });

      evtSource.addEventListener('session_complete', function(e) {
        var d = JSON.parse(e.data);
        lastCompletedIter = d.iteration + iterOffset;
        progressFill.style.width = '100%';
        setStatus('Session complete (' + lastCompletedIter + ' iterations)', false);
        sessionActive = false;
        btnStop.style.display = 'none';
        btnContinue.style.display = '';
        setLayoutToggleEnabled(true);
        evtSource.close();
        evtSource = null;
        if (layoutMode === 'page') updateNavControls();
      });

      evtSource.onerror = function() {
        if (sessionActive) setStatus('Connection lost &mdash; reconnecting...', true);
      };
    }

    /* --- Session actions --- */

    btnStart.addEventListener('click', function() {
      var provider = document.getElementById('ai-provider').value;
      var iterations = parseInt(document.getElementById('iter-count').value) || 5;
      var duration = parseFloat(document.getElementById('duration').value) || 15;
      var bpm = parseInt(document.getElementById('cfg-bpm').value) || 72;
      var measures = parseInt(document.getElementById('cfg-measures').value) || 8;
      var visualize = document.getElementById('cb-visualize').checked;
      var normalize = document.getElementById('cb-normalize').checked;
      var userPrompt = document.getElementById('user-prompt').value.trim() || null;
      var inputConfigStr = document.getElementById('input-config').value.trim();
      var inputConfig = null;
      if (inputConfigStr) {
        try { inputConfig = JSON.parse(inputConfigStr); }
        catch(e) { setStatus('Invalid JSON in input config: ' + e.message, false); return; }
      }

      closeModal();
      sessionBar.style.display = 'flex';
      btnStop.style.display = '';
      btnStop.disabled = false;
      btnContinue.style.display = 'none';
      progressFill.style.width = '0%';

      if (continueMode) {
        // Continue session
        iterOffset = lastCompletedIter;
        fetch('/api/continue', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({provider: provider, iterations: iterations, duration: duration,
                                bpm: bpm, measures: measures,
                                visualize: visualize, normalize: normalize,
                                user_prompt: userPrompt})
        }).then(function(r) { return r.json(); }).then(function(d) {
          if (d.status === 'started') {
            setStatus('Continuing...', true);
            startSSE();
          } else {
            setStatus('Error: ' + (d.error || 'failed to continue'), false);
            btnContinue.style.display = '';
            btnStop.style.display = 'none';
          }
        }).catch(function(err) {
          setStatus('Error: ' + err.message, false);
          btnContinue.style.display = '';
          btnStop.style.display = 'none';
        });
      } else {
        // New session
        iterationData = {};
        iterOffset = 0;
        lastCompletedIter = 0;
        pageSlots = {};
        completedPages = new Set();
        currentPage = 0;
        totalPages = 0;
        currentBuildIter = 0;

        var welcome = document.getElementById('welcome');
        if (welcome) welcome.remove();
        timeline.innerHTML = '';
        document.getElementById('nav-dots').innerHTML = '';
        pageNav.classList.toggle('visible', false);

        fetch('/api/start', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({seed: selectedSeed, provider: provider,
                                iterations: iterations, duration: duration,
                                bpm: bpm, measures: measures,
                                visualize: visualize, normalize: normalize,
                                user_prompt: userPrompt,
                                input_config: inputConfig})
        }).then(function(r) { return r.json(); }).then(function(d) {
          if (d.status === 'started') {
            setStatus('Starting...', true);
            startSSE();
          } else {
            setStatus('Error: ' + (d.error || 'failed to start'), false);
            btnStop.style.display = 'none';
          }
        }).catch(function(err) {
          setStatus('Error: ' + err.message, false);
          btnStop.style.display = 'none';
        });
      }
    });

    btnStop.addEventListener('click', function() {
      btnStop.disabled = true;
      setStatus('Stopping...', false);
    });

    btnContinue.addEventListener('click', function() {
      openModal(true);
    });

    /* --- Init --- */
    setLayoutMode(layoutMode);

    /* ======================================================
     * SIDEBAR NAVIGATION (shared across all pages)
     * ====================================================== */

    function navigate(page) {
      var pages = ['home', 'playground', 'live'];
      if (pages.indexOf(page) === -1) page = 'home';
      pages.forEach(function(p) {
        var el = document.getElementById('page-' + p);
        if (el) el.style.display = (p === page) ? 'block' : 'none';
      });
      document.querySelectorAll('.nav-item').forEach(function(a) {
        a.classList.toggle('active', a.dataset.page === page);
      });
      history.replaceState(null, '', '#' + page);
    }

    document.getElementById('sidebar-toggle').addEventListener('click', function() {
      document.getElementById('sidebar').classList.toggle('collapsed');
    });

    // Hash routing
    window.addEventListener('hashchange', function() {
      navigate(location.hash.slice(1) || 'home');
    });

    // Initial route
    (function() {
      var hash = location.hash.slice(1);
      if (hash) navigate(hash);
    })();

    /* ======================================================
     * PLAYGROUND
     * ====================================================== */

    var playgroundConfig = null;
    var pgCurrentTab = 'visual';
    var pgPresetsData = {{ presets_json | safe }};

    // Populate preset dropdown
    (function() {
      var sel = document.getElementById('pg-preset-select');
      Object.keys(pgPresetsData).forEach(function(key) {
        var opt = document.createElement('option');
        opt.value = key;
        opt.textContent = pgPresetsData[key].title || key;
        sel.appendChild(opt);
      });
      // Load first preset by default
      var firstKey = Object.keys(pgPresetsData)[0];
      if (firstKey) {
        sel.value = firstKey;
        pgLoadPreset(firstKey);
      }
    })();

    function pgLoadPreset(key) {
      if (!key) return;
      var preset = pgPresetsData[key];
      if (preset && preset.config) {
        playgroundConfig = JSON.parse(JSON.stringify(preset.config));
        document.getElementById('pg-json-textarea').value = JSON.stringify(playgroundConfig, null, 2);
        pgRenderVisualControls(playgroundConfig);
      }
    }

    function pgSwitchTab(tab) {
      pgCurrentTab = tab;
      document.querySelectorAll('.pg-tab').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tab === tab);
      });
      document.getElementById('pg-tab-visual').classList.toggle('active', tab === 'visual');
      document.getElementById('pg-tab-json').classList.toggle('active', tab === 'json');
      if (tab === 'visual') {
        // Sync JSON -> Visual
        try {
          var cfg = JSON.parse(document.getElementById('pg-json-textarea').value);
          playgroundConfig = cfg;
          pgRenderVisualControls(cfg);
        } catch(e) {
          document.getElementById('pg-error').textContent = 'JSON parse error: ' + e.message;
        }
      } else {
        // Sync Visual -> JSON
        if (playgroundConfig) {
          document.getElementById('pg-json-textarea').value = JSON.stringify(playgroundConfig, null, 2);
        }
      }
    }

    function pgSyncToJson() {
      if (playgroundConfig) {
        document.getElementById('pg-json-textarea').value = JSON.stringify(playgroundConfig, null, 2);
      }
      document.getElementById('pg-error').textContent = '';
    }

    /* --- Render --- */
    function pgRender() {
      var btn = document.getElementById('pg-render-btn');
      var statusEl = document.getElementById('pg-status');
      var errorEl = document.getElementById('pg-error');
      errorEl.textContent = '';
      btn.disabled = true;
      statusEl.textContent = 'Rendering...';

      // Get config from JSON textarea (source of truth for rendering)
      var cfg;
      try {
        cfg = JSON.parse(document.getElementById('pg-json-textarea').value);
      } catch(e) {
        errorEl.textContent = 'Invalid JSON: ' + e.message;
        btn.disabled = false;
        statusEl.textContent = '';
        return;
      }

      var t0 = Date.now();
      fetch('/api/playground/render', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({config: cfg})
      }).then(function(r) { return r.json(); }).then(function(d) {
        btn.disabled = false;
        if (d.status === 'ok') {
          var audio = document.getElementById('pg-audio');
          audio.src = d.wav_url + '?t=' + Date.now();
          document.getElementById('pg-player').style.display = 'flex';
          var elapsed = ((Date.now() - t0) / 1000).toFixed(1);
          statusEl.textContent = 'Done (' + elapsed + 's)';
          document.getElementById('pg-render-time').textContent = elapsed + 's';
        } else {
          errorEl.textContent = 'Render error: ' + (d.error || 'unknown');
          statusEl.textContent = 'Failed';
        }
      }).catch(function(e) {
        btn.disabled = false;
        errorEl.textContent = 'Network error: ' + e.message;
        statusEl.textContent = 'Failed';
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

      // Common fields
      html += pgMakeField('Volume', pgSlider('pg-l' + idx + '-vol', layer.vol, 0, 1, 0.01));
      html += pgMakeField('Fade In', pgNumInput('pg-l' + idx + '-fi', layer.fade_in, 0, 60, 0.5));
      html += pgMakeField('Fade Out', pgNumInput('pg-l' + idx + '-fo', layer.fade_out, 0, 60, 0.5));

      // Type-specific fields
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
        // Note editor
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

      // Global
      cfg.global = cfg.global || {};
      var bpm = document.getElementById('pg-v-bpm');
      if (bpm) cfg.global.bpm = parseFloat(bpm.value) || 72;
      var meas = document.getElementById('pg-v-measures');
      if (meas) cfg.global.measures = parseInt(meas.value) || 8;
      var tsn = document.getElementById('pg-v-ts-num');
      var tsd = document.getElementById('pg-v-ts-den');
      if (tsn && tsd) cfg.global.time_sig = [parseInt(tsn.value)||4, parseInt(tsd.value)||4];

      // Master
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

      // Layers
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

          // Read notes
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
      var type = prompt('Layer type?\\n' + types.join(', '));
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
      pgBuildConfigFromForm();  // save current state first
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
      pgBuildConfigFromForm();  // save current state first
      layer.notes.splice(noteIdx, 1);
      pgRenderVisualControls(playgroundConfig);
      pgSyncToJson();
    }

  </script>
  </div><!-- /page-live -->
  </div><!-- /main-content -->
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Flask app factory
# ---------------------------------------------------------------------------
_FAVICON_PNG = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII='


def make_app(outdir: Path, live: bool = False) -> Flask:
    outdir = outdir.resolve()
    app = Flask(__name__, static_folder=str(outdir))
    event_bus = EventBus() if live else None

    @app.route("/favicon.ico")
    def favicon():
        return Response(base64.b64decode(_FAVICON_PNG), mimetype="image/png")

    @app.route("/")
    def index():
        if live:
            from shattered_audio.shattered_configs import PRESETS
            presets_data = {
                key: {"title": p["title"], "description": p.get("description", ""),
                       "tags": p.get("tags", []), "config": p.get("config")}
                for key, p in PRESETS.items()
            }
            return render_template_string(APP_TEMPLATE, presets_json=json.dumps(presets_data))
        items = _build_items(outdir / "session_log.json")
        return render_template_string(GALLERY_TEMPLATE, path=str(outdir), items=items)

    @app.route("/renders/<path:filename>")
    def renders(filename: str):
        return send_from_directory(str(outdir / "renders"), filename)

    # Playground render endpoint (works in both live and gallery mode)
    @app.route("/api/playground/render", methods=["POST"])
    def api_playground_render():
        import subprocess as _subprocess
        from shattered_audio.render_artifact import RENDER_PYTHON

        data = request.get_json(silent=True) or {}
        config = data.get("config")
        if not config or not isinstance(config, dict):
            return jsonify({"status": "error", "error": "Missing or invalid config"}), 400

        renders_dir = outdir / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        render_name = f"playground_{int(time.time())}"
        cfg_path = outdir / f"{render_name}.json"
        cfg_path.write_text(json.dumps(config, indent=2), encoding="utf8")

        render_script = str(Path(__file__).resolve().parent.parent
                            / "shattered_audio" / "render_single.py")
        cmd = [
            RENDER_PYTHON, render_script,
            render_name,
            "--config-file", str(cfg_path),
            "--outdir", str(renders_dir),
        ]

        try:
            result = _subprocess.run(cmd, timeout=120, capture_output=True)
            cfg_path.unlink(missing_ok=True)

            wav_path = renders_dir / f"{render_name}.wav"
            if wav_path.exists() and wav_path.stat().st_size > 44:
                return jsonify({"status": "ok", "wav_url": f"/renders/{render_name}.wav"})
            else:
                stderr = result.stderr.decode(errors="replace")[-500:] if result.stderr else "unknown"
                return jsonify({"status": "error", "error": f"Render failed: {stderr}"}), 500
        except _subprocess.TimeoutExpired:
            cfg_path.unlink(missing_ok=True)
            return jsonify({"status": "error", "error": "Render timed out (120s)"}), 504
        except Exception as e:
            cfg_path.unlink(missing_ok=True)
            return jsonify({"status": "error", "error": str(e)}), 500

    if live and event_bus:
        _session_state: dict = {"thread": None, "session": None}

        @app.route("/api/events")
        def api_events():
            q = event_bus.subscribe()
            def stream():
                try:
                    while True:
                        try:
                            event = q.get(timeout=30)
                            yield event.to_sse()
                        except queue.Empty:
                            yield ": keepalive\n\n"
                except GeneratorExit:
                    event_bus.unsubscribe(q)
            return Response(stream(), mimetype="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        @app.route("/api/start", methods=["POST"])
        def api_start():
            if _session_state["thread"] and _session_state["thread"].is_alive():
                return jsonify({"status": "error", "error": "Session already running"}), 409

            data = request.get_json(silent=True) or {}
            seed = data.get("seed", "008_binaural_temple")
            provider = data.get("provider", "anthropic")
            iterations = int(data.get("iterations", 5))
            duration = float(data.get("duration", 15))
            visualize = bool(data.get("visualize", True))
            normalize = bool(data.get("normalize", False))
            user_prompt = data.get("user_prompt") or None
            input_config = data.get("input_config") or None

            from tools.iterative_loop import IterativeSession
            from tools.gen_from_model import ModelAdapter
            from chat import create_client as _create_client
            session_client = None
            if provider != "local":
                try:
                    session_client = _create_client(provider)
                except Exception as e:
                    return jsonify({"status": "error", "error": str(e)}), 400
            adapter = ModelAdapter(chat_client=session_client)
            session = IterativeSession(
                seed=seed,
                outdir=str(outdir),
                iterations=iterations,
                adapter=adapter,
                event_bus=event_bus,
                duration_override=duration,
                visualize=visualize,
                normalize=normalize,
                user_prompt=user_prompt,
                input_config=input_config,
            )

            t = threading.Thread(target=session.run, daemon=True)
            t.start()
            _session_state["thread"] = t
            _session_state["session"] = session
            log.info("Started live session: seed=%s iterations=%d duration=%.0f", seed, iterations, duration)
            return jsonify({"status": "started"})

        @app.route("/api/continue", methods=["POST"])
        def api_continue():
            if _session_state["thread"] and _session_state["thread"].is_alive():
                return jsonify({"status": "error", "error": "Session still running"}), 409

            prev_session = _session_state.get("session")
            if not prev_session:
                return jsonify({"status": "error", "error": "No previous session to continue from"}), 400

            data = request.get_json(silent=True) or {}
            provider = data.get("provider", "anthropic")
            iterations = int(data.get("iterations", 5))
            duration = float(data.get("duration", 15))
            visualize = bool(data.get("visualize", True))
            normalize = bool(data.get("normalize", False))
            user_prompt = data.get("user_prompt") or None

            from tools.iterative_loop import IterativeSession
            from tools.gen_from_model import ModelAdapter
            from chat import create_client as _create_client
            session_client = None
            if provider != "local":
                try:
                    session_client = _create_client(provider)
                except Exception as e:
                    return jsonify({"status": "error", "error": str(e)}), 400
            adapter = ModelAdapter(chat_client=session_client)
            session = IterativeSession(
                seed=prev_session.seed,
                outdir=str(outdir),
                iterations=iterations,
                adapter=adapter,
                event_bus=event_bus,
                duration_override=duration,
                visualize=visualize,
                normalize=normalize,
                user_prompt=user_prompt,
            )
            # Carry forward the previous config so evolution continues
            session._prev_cfg = prev_session._prev_cfg

            t = threading.Thread(target=session.run, daemon=True)
            t.start()
            _session_state["thread"] = t
            _session_state["session"] = session
            log.info("Continuing session: +%d iterations duration=%.0f", iterations, duration)
            return jsonify({"status": "started"})

    return app


def generate_static(outdir: Path) -> Path:
    """Render a static index.html into outdir using session_log.json."""
    outdir = Path(outdir)
    items = _build_items(outdir / "session_log.json")
    outdir.mkdir(parents=True, exist_ok=True)
    static_template = GALLERY_TEMPLATE.replace("/renders/", "renders/")
    app = make_app(outdir)
    with app.app_context():
        rendered = render_template_string(static_template, path=str(outdir), items=items)
    outpath = outdir / "index.html"
    outpath.write_text(rendered, encoding="utf8")
    return outpath


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default="artifacts/iter")
    p.add_argument("--live", action="store_true", help="Start in live demo mode")
    p.add_argument("--static", action="store_true", help="Render a static index.html and exit")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5000)
    args = p.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "renders").mkdir(parents=True, exist_ok=True)

    if args.static:
        idx = generate_static(outdir)
        log.info("Wrote static index to: %s", idx)
        return

    app = make_app(outdir, live=args.live)

    def _open():
        time.sleep(0.8)
        try:
            webbrowser.open(f"http://{args.host}:{args.port}")
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()
    mode = "LIVE" if args.live else "GALLERY"
    log.info("Starting %s server at http://%s:%d", mode, args.host, args.port)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
