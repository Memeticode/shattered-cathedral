import sys
import os
import argparse
import sys, os
# Try package imports first (when running as a module), then fall back to script-level imports.
try:
    from shattered_audio.shattered_engine import ShatteredEngine
    from shattered_audio.shattered_configs import CONFIGS
except Exception:
    try:
        from shattered_engine import ShatteredEngine
        from shattered_configs import CONFIGS
    except Exception:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from shattered_audio.shattered_engine import ShatteredEngine
        from shattered_audio.shattered_configs import CONFIGS

parser = argparse.ArgumentParser(description="Render a single artifact (helper script)")
parser.add_argument("name", help="Artifact key to render")
parser.add_argument("--play", action="store_true", help="Play audio during rendering (opens audio device)")
parser.add_argument("--outdir", default="artifacts", help="Output directory for WAV files")
parser.add_argument("--outfmt", default="wav", choices=["wav"], help="Output format (wav)")
parser.add_argument("--samprate", type=int, default=None, help="Sample rate override (Hz)")
parser.add_argument("--duration", type=float, default=None, help="Override duration (seconds)")
parser.add_argument("--bitdepth", type=int, default=None, help="Override bit depth for output")
parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
args = parser.parse_args()

name = args.name
outdir = args.outdir
play_audio = args.play
outfmt = getattr(args, 'outfmt', 'wav')
samprate = getattr(args, 'samprate', None)
duration_override = getattr(args, 'duration', None)
bitdepth_override = getattr(args, 'bitdepth', None)
verbose = getattr(args, 'verbose', False)

if name not in CONFIGS:
    print(f"Artifact not found in configs library: {name}")
    sys.exit(2)

config = CONFIGS[name]
makedir = os.path.join
os.makedirs(outdir, exist_ok=True)
# Apply simple overrides to config if provided (before creating the engine)
if duration_override is not None:
    config.setdefault('global', {})['duration'] = float(duration_override)
if samprate is not None:
    # pyo uses Server settings; we won't attempt to reconfigure here, but
    # include samprate in the config for potential use.
    config.setdefault('global', {})['samprate'] = int(samprate)
if bitdepth_override is not None:
    config.setdefault('global', {})['bitdepth'] = int(bitdepth_override)

engine = ShatteredEngine(config, play_audio=play_audio)
out_path = os.path.join(outdir, f"{name}.wav")

try:
    engine.render(out_path)
except Exception as e:
    import traceback
    print(f"Error rendering {name}: {e}")
    traceback.print_exc()
    sys.exit(1)

# Try a clean server shutdown and remove references before exiting to reduce
# native teardown crashes in pyo.
try:
    if hasattr(engine, "server") and engine.server is not None:
        try:
            engine.server.shutdown()
        except Exception:
            pass
        try:
            del engine.server
        except Exception:
            pass
except Exception:
    pass

# Small delay and collect to help pyo clean up native resources before interpreter exit.
import time, gc
time.sleep(0.25)
gc.collect()
try:
    del engine
except Exception:
    pass
# Use os._exit to avoid running Python-level and C-extension destructors that
# sometimes crash on interpreter teardown after pyo's native cleanup. The
# recorded WAV is already written by this point.
import os
os._exit(0)
