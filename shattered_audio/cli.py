"""CLI wrapper for batch rendering artifacts."""
import argparse
import os
import sys

# Ensure project root is on sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from shattered_audio import render_artifact as ra
from shattered_audio.log import get_logger

log = get_logger("cli")

parser = argparse.ArgumentParser(description="Shattered Cathedral batch renderer CLI")
parser.add_argument("artifacts", nargs="*", help="Artifact keys to render or ALL")
parser.add_argument("--outdir", default="artifacts", help="Output directory")
parser.add_argument("--parallel", type=int, default=1, help="Number of parallel helper processes")
parser.add_argument("--play", action="store_true", help="Play audio during rendering")
parser.add_argument("--outfmt", default="wav", choices=["wav"], help="Output file format")
parser.add_argument("--samprate", type=int, default=None, help="Sample rate override (Hz)")
parser.add_argument("--duration", type=float, default=None, help="Override artifact duration (seconds)")
parser.add_argument("--bitdepth", type=int, default=None, help="Override bit depth for output")
parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
args = parser.parse_args()

if len(args.artifacts) == 0:
    names = list(ra.CONFIGS.keys())
elif len(args.artifacts) == 1 and args.artifacts[0].upper() == "ALL":
    names = list(ra.CONFIGS.keys())
else:
    names = args.artifacts

results = ra.render_batch(
    names,
    outdir=args.outdir,
    play_audio=args.play,
    parallel=args.parallel,
    outfmt=args.outfmt,
    samprate=args.samprate,
    duration_override=args.duration,
    bitdepth=args.bitdepth,
    verbose=args.verbose,
)

log.info("Results:")
for k, v in results.items():
    log.info("  %s: %s", k, "OK" if v else "FAILED")
