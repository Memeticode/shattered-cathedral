"""Shared helpers for the web UI."""
from __future__ import annotations

import json
from pathlib import Path

from shattered_audio.log import get_logger

log = get_logger("web_ui")

MAX_GALLERY_ITEMS = 200

_FAVICON_PNG = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII='


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


def generate_static(outdir: Path) -> Path:
    """Render a static index.html into outdir using session_log.json."""
    from flask import render_template

    from tools.web_ui.app import make_app

    outdir = Path(outdir)
    items = _build_items(outdir / "session_log.json")
    outdir.mkdir(parents=True, exist_ok=True)

    app = make_app(outdir)
    with app.app_context():
        rendered = render_template("gallery.html", path=str(outdir), items=items,
                                   render_prefix="renders/")
    outpath = outdir / "index.html"
    outpath.write_text(rendered, encoding="utf8")
    return outpath
