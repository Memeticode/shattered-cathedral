"""Flask app factory and all routes."""
from __future__ import annotations

import base64
import json
import math
import queue
import struct as _struct
import threading
import time
import wave as _wave
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from shattered_audio.log import get_logger
from tools.event_bus import EventBus
from tools.web_ui.helpers import _build_items, _FAVICON_PNG

log = get_logger("web_ui")

_PKG_DIR = Path(__file__).resolve().parent


def make_app(outdir: Path, live: bool = False) -> Flask:
    outdir = outdir.resolve()
    app = Flask(
        __name__,
        template_folder=str(_PKG_DIR / "templates"),
        static_folder=str(_PKG_DIR / "static"),
        static_url_path="/app-static",
    )
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
            return render_template("app.html", presets_json=json.dumps(presets_data))
        items = _build_items(outdir / "session_log.json")
        return render_template("gallery.html", path=str(outdir), items=items,
                               render_prefix="/renders/")

    @app.route("/renders/<path:filename>")
    def renders(filename: str):
        return send_from_directory(str(outdir / "renders"), filename)

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

        render_script = str(_PKG_DIR.parent.parent / "shattered_audio" / "render_single.py")
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
                # Measure peak amplitude for diagnostics
                peak_db = None
                try:
                    with _wave.open(str(wav_path), "rb") as wf:
                        sw = wf.getsampwidth()
                        raw = wf.readframes(wf.getnframes())
                        if sw == 2:
                            samples = _struct.unpack(f"<{len(raw)//2}h", raw)
                            peak = max(abs(s) for s in samples) if samples else 0
                            peak_db = round(20 * math.log10(peak / 32768) if peak > 0 else -100, 1)
                except Exception:
                    pass
                return jsonify({"status": "ok", "wav_url": f"/renders/{render_name}.wav", "peak_db": peak_db})
            else:
                stderr = result.stderr.decode(errors="replace")[-500:] if result.stderr else "unknown"
                return jsonify({"status": "error", "error": f"Render failed: {stderr}"}), 500
        except _subprocess.TimeoutExpired:
            cfg_path.unlink(missing_ok=True)
            return jsonify({"status": "error", "error": "Render timed out (120s)"}), 504
        except Exception as e:
            cfg_path.unlink(missing_ok=True)
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/api/playground/render-layer", methods=["POST"])
    def api_render_layer():
        import subprocess as _subprocess

        from shattered_audio.render_artifact import RENDER_PYTHON

        data = request.get_json(silent=True) or {}
        layer_id = data.get("layer_id", "")
        config = data.get("config")
        if not config or not isinstance(config, dict):
            return jsonify({"status": "error", "error": "Missing or invalid config"}), 400

        renders_dir = outdir / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        render_name = f"layer_{layer_id}_{int(time.time())}"
        cfg_path = outdir / f"{render_name}.json"
        cfg_path.write_text(json.dumps(config, indent=2), encoding="utf8")

        render_script = str(_PKG_DIR.parent.parent / "shattered_audio" / "render_single.py")
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
                return jsonify({"status": "ok", "wav_url": f"/renders/{render_name}.wav",
                                "layer_id": layer_id})
            else:
                stderr = result.stderr.decode(errors="replace")[-500:] if result.stderr else "unknown"
                return jsonify({"status": "error", "error": f"Render failed: {stderr}",
                                "layer_id": layer_id}), 500
        except _subprocess.TimeoutExpired:
            cfg_path.unlink(missing_ok=True)
            return jsonify({"status": "error", "error": "Render timed out (120s)",
                            "layer_id": layer_id}), 504
        except Exception as e:
            cfg_path.unlink(missing_ok=True)
            return jsonify({"status": "error", "error": str(e), "layer_id": layer_id}), 500

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

            return Response(
                stream(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

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

            from chat import create_client as _create_client
            from tools.gen_from_model import ModelAdapter
            from tools.iterative_loop import IterativeSession

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

            from chat import create_client as _create_client
            from tools.gen_from_model import ModelAdapter
            from tools.iterative_loop import IterativeSession

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
            session._prev_cfg = prev_session._prev_cfg

            t = threading.Thread(target=session.run, daemon=True)
            t.start()
            _session_state["thread"] = t
            _session_state["session"] = session
            log.info("Continuing session: +%d iterations duration=%.0f", iterations, duration)
            return jsonify({"status": "started"})

    return app
