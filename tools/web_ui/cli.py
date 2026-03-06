"""CLI entry point for the web UI."""
from __future__ import annotations

import argparse
import threading
import time
import webbrowser
from pathlib import Path

from shattered_audio.log import get_logger

log = get_logger("web_ui")


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
        from tools.web_ui.helpers import generate_static
        idx = generate_static(outdir)
        log.info("Wrote static index to: %s", idx)
        return

    from tools.web_ui.app import make_app
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
