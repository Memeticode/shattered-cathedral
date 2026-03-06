"""Tiny Flask web UI to browse and preview generated iterations.

Run with:
    python -m tools.web_ui --outdir artifacts/iter --host 0.0.0.0 --port 5000

It serves `session_log.json` and the `renders` folder as a simple gallery.
"""
from __future__ import annotations
from typing import Optional
import argparse
import json
from pathlib import Path
from flask import Flask, send_from_directory, render_template_string, Response
import base64
import threading
import time
import webbrowser

TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Shattered Cathedral - Iterations</title>
  <style>
    body { font-family: sans-serif; margin: 20px; }
    .controls { margin-bottom: 16px; }
    .gallery { display:flex; flex-wrap:wrap; gap:12px; }
    .item { width:220px; border:1px solid #ddd; padding:8px; border-radius:6px; }
    .thumb { width:200px; height:112px; object-fit:cover; background:#111; display:block }
    .meta { font-size:12px; margin-top:6px }
    .btn { display:inline-block; margin-right:6px; padding:4px 8px; background:#2b6cff; color:#fff; text-decoration:none; border-radius:4px }
    .btn.secondary { background:#666 }
    .download { background:#1a9a4a }
  </style>
</head>
<body>
  <h1>Iterations: {{ path }}</h1>

  <div class="controls">
    <strong id="selected-title">No selection</strong><br/>
    <audio id="main-audio" controls preload="none" style="width:600px"></audio>
    <div style="margin-top:8px">
      <button id="play-btn" class="btn">Play</button>
      <button id="pause-btn" class="btn secondary">Pause</button>
      <button id="stop-btn" class="btn secondary">Stop</button>
      <a id="download-current" class="btn download" href="#" download>Download WAV</a>
    </div>
  </div>

  <div class="gallery">
  {% for it in items %}
    <div class="item" data-wav="{{ it.wav_name }}" data-title="Iteration {{ it.iteration }} — {{ it.time }}">
      {% if it.png_name %}
        <img class="thumb select-thumb" src="/renders/{{ it.png_name }}" alt="viz"/>
      {% else %}
        <div style="width:200px;height:112px;background:#222;color:#ddd;display:flex;align-items:center;justify-content:center">No Image</div>
      {% endif %}
      <div class="meta">
        <strong>Iteration {{ it.iteration }}</strong><br/>
        <em>{{ it.note }}</em><br/>
        <span>RMS={{ it.metrics.rms }} DBFS={{ it.metrics.dbfs }}</span>
        {% if it.commentary %}
          <div style="margin-top:6px; font-size:12px"><strong>Model commentary:</strong> {{ it.commentary }}</div>
        {% endif %}
        {% if it.plan %}
          <div style="margin-top:6px; font-size:12px"><strong>Model plan:</strong> {{ it.plan }}</div>
        {% endif %}
      </div>
      <div style="margin-top:8px">
        {% if it.wav_name %}
          <a class="btn play-link" href="/renders/{{ it.wav_name }}">Preview</a>
          <a class="btn secondary" href="/renders/{{ it.wav_name }}" download>Download WAV</a>
        {% endif %}
        {% if it.png_name %}
          <a class="btn secondary" href="/renders/{{ it.png_name }}" download>Download Image</a>
        {% endif %}
      </div>
    </div>
  {% endfor %}
  </div>

  <script>
    const mainAudio = document.getElementById('main-audio');
    const playBtn = document.getElementById('play-btn');
    const pauseBtn = document.getElementById('pause-btn');
    const stopBtn = document.getElementById('stop-btn');
    const downloadCurrent = document.getElementById('download-current');
    const selectedTitle = document.getElementById('selected-title');

    function selectItem(el) {
      const wav = el.dataset.wav;
      const title = el.dataset.title || 'Selection';
      selectedTitle.textContent = title;
      if (wav) {
        mainAudio.src = '/renders/' + wav;
        downloadCurrent.href = '/renders/' + wav;
        downloadCurrent.style.display = '';
      } else {
        mainAudio.removeAttribute('src');
        downloadCurrent.href = '#';
        downloadCurrent.style.display = 'none';
      }
      mainAudio.load();
    }

    document.querySelectorAll('.select-thumb').forEach(img => {
      img.addEventListener('click', ev => selectItem(ev.currentTarget.parentElement));
    });

    document.querySelectorAll('.play-link').forEach(a => {
      a.addEventListener('click', ev => {
        ev.preventDefault();
        const parent = ev.currentTarget.closest('.item');
        selectItem(parent);
        mainAudio.play();
      });
    });

    playBtn.addEventListener('click', () => { mainAudio.play(); });
    pauseBtn.addEventListener('click', () => { mainAudio.pause(); });
    stopBtn.addEventListener('click', () => { mainAudio.pause(); mainAudio.currentTime = 0; });

    // Preselect first item if exists
    const first = document.querySelector('.item');
    if (first) selectItem(first);
  </script>
</body>
</html>
"""


def make_app(outdir: Path) -> Flask:
    app = Flask(__name__, static_folder=str(outdir))
    # tiny 1x1 transparent PNG (base64)
    _FAVICON_PNG = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII='

    @app.route('/favicon.ico')
    def favicon():
        data = base64.b64decode(_FAVICON_PNG)
        return Response(data, mimetype='image/png')

    @app.route('/')
    def index():
        logp = outdir / 'session_log.json'
        items = []
        if logp.exists():
            try:
                raw = json.loads(logp.read_text(encoding='utf8'))
                for entry in reversed(raw[-200:]):
                    wav = entry.get('wav') or ''
                    wav_name = Path(wav).name if wav else None
                    png_name = None
                    if wav_name:
                        png_name = Path(wav_name).with_suffix('.png').name
                    metrics = entry.get('metrics') or {}
                    items.append({'iteration': entry.get('iteration'), 'time': entry.get('time'), 'note': entry.get('note', ''), 'wav_name': wav_name, 'png_name': png_name, 'metrics': metrics, 'commentary': entry.get('commentary'), 'plan': entry.get('plan')})
            except Exception:
                items = []
        return render_template_string(TEMPLATE, path=str(outdir), items=items)

    @app.route('/renders/<path:filename>')
    def renders(filename: str):
        return send_from_directory(str(outdir / 'renders'), filename)

    return app


STATIC_TEMPLATE = TEMPLATE.replace('/renders/', 'renders/')


def generate_static(outdir: Path) -> Path:
    """Render a static `index.html` into `outdir` using session_log.json."""
    outdir = Path(outdir)
    logp = outdir / 'session_log.json'
    items = []
    if logp.exists():
        try:
            raw = json.loads(logp.read_text(encoding='utf8'))
            for entry in reversed(raw[-200:]):
                wav = entry.get('wav') or ''
                wav_name = Path(wav).name if wav else None
                png_name = None
                if wav_name:
                    png_name = Path(wav_name).with_suffix('.png').name
                metrics = entry.get('metrics') or {}
                items.append({'iteration': entry.get('iteration'), 'time': entry.get('time'), 'note': entry.get('note', ''), 'wav_name': wav_name, 'png_name': png_name, 'metrics': metrics, 'commentary': entry.get('commentary'), 'plan': entry.get('plan')})
        except Exception:
            items = []

    outdir.mkdir(parents=True, exist_ok=True)
    # render using an app context so Jinja functions properly
    app = make_app(outdir)
    with app.app_context():
        rendered = render_template_string(STATIC_TEMPLATE, path=str(outdir), items=items)
    outpath = outdir / 'index.html'
    outpath.write_text(rendered, encoding='utf8')
    return outpath


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', default='artifacts/iter')
    p.add_argument('--static', action='store_true', help='Render a static index.html into --outdir and exit')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=5000)
    args = p.parse_args()
    outdir = Path(args.outdir)

    if getattr(args, 'static', False):
        idx = generate_static(outdir)
        print(f'Wrote static index to: {idx}')
        return

    app = make_app(outdir)
    # open the browser shortly after server starts
    def _open():
        time.sleep(0.4)
        try:
            webbrowser.open(f'http://{args.host}:{args.port}')
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()
    app.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
