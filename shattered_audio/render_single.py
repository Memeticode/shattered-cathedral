"""Render a single artifact (helper subprocess).

This script is invoked as a subprocess by render_artifact.py.
It must be run with a Python environment that has pyo installed (e.g. .venv311).
"""
import sys
import os
import argparse
import json
import time
import gc
from pathlib import Path

# Ensure project root is on sys.path (this script runs as a standalone subprocess)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from shattered_audio.log import get_logger
from shattered_audio.shattered_engine import ShatteredEngine
from shattered_audio.shattered_configs import CONFIGS

log = get_logger("render_single")

parser = argparse.ArgumentParser(description="Render a single artifact (helper script)")
parser.add_argument("name", nargs="?", help="Artifact key to render")
parser.add_argument("--config-file", help="Path to a JSON config to render (overrides name)")
parser.add_argument("--play", action="store_true", help="Play audio during rendering")
parser.add_argument("--outdir", default="artifacts", help="Output directory for WAV files")
parser.add_argument("--outfmt", default="wav", choices=["wav"], help="Output format")
parser.add_argument("--samprate", type=int, default=None, help="Sample rate override (Hz)")
parser.add_argument("--duration", type=float, default=None, help="Override duration (seconds)")
parser.add_argument("--bitdepth", type=int, default=None, help="Override bit depth for output")
parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
args = parser.parse_args()

name: str | None = args.name
config_file: str | None = getattr(args, "config_file", None)
outdir = Path(args.outdir)
play_audio: bool = args.play

config: dict | None = None
if config_file:
    cfg_path = Path(config_file)
    if not cfg_path.exists():
        log.error("Config file not found: %s", config_file)
        sys.exit(2)
    config = json.loads(cfg_path.read_text(encoding="utf8"))
    if name is None:
        name = cfg_path.stem
else:
    if not name or name not in CONFIGS:
        log.error("Artifact not found in configs library: %s", name)
        sys.exit(2)
    config = CONFIGS[name]

outdir.mkdir(parents=True, exist_ok=True)

# Apply overrides
if args.duration is not None:
    config.setdefault("global", {})["duration"] = float(args.duration)
if args.samprate is not None:
    config.setdefault("global", {})["samprate"] = int(args.samprate)
if args.bitdepth is not None:
    config.setdefault("global", {})["bitdepth"] = int(args.bitdepth)

engine = ShatteredEngine(config, play_audio=play_audio)
out_path = outdir / f"{name}.wav"

try:
    engine.render(str(out_path))
except Exception as e:
    log.error("Error rendering %s: %s", name, e, exc_info=True)
    sys.exit(1)

# Clean shutdown to reduce pyo native teardown crashes
try:
    if hasattr(engine, "server") and engine.server is not None:
        try:
            engine.server.shutdown()
        except Exception:
            pass
        del engine.server
except Exception:
    pass

time.sleep(0.25)
gc.collect()

try:
    del engine
except Exception:
    pass

# Use os._exit to avoid pyo C-extension destructor crashes on interpreter teardown
os._exit(0)
