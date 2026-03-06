#!/usr/bin/env python3
"""CLI wrapper for batch rendering artifacts.

This script moves argument parsing out of `render_artifact.py` and provides
options: --outdir and --parallel.
"""
import argparse
import os, sys
# Ensure project root is on sys.path so absolute imports work when running as -m
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from shattered_audio import render_artifact as ra

parser = argparse.ArgumentParser(description="Shattered Cathedral batch renderer CLI")
parser.add_argument("artifacts", nargs="*", help="Artifact keys to render or ALL")
parser.add_argument("--outdir", default="artifacts", help="Output directory")
parser.add_argument("--parallel", type=int, default=1, help="Number of parallel helper processes")
parser.add_argument("--play", action="store_true", help="Play audio during rendering (not recommended for batch)")
parser.add_argument("--outfmt", default="wav", choices=["wav"], help="Output file format (default: wav)")
parser.add_argument("--samprate", type=int, default=None, help="Sample rate override for rendering (Hz)")
parser.add_argument("--duration", type=float, default=None, help="Override artifact duration (seconds)")
parser.add_argument("--bitdepth", type=int, default=None, help="Override bitdepth/sample type for output")
parser.add_argument("--verbose", action="store_true", help="Enable verbose helper output")
args = parser.parse_args()

if len(args.artifacts) == 0:
    names = ["004_glass_ocean"]
elif len(args.artifacts) == 1 and args.artifacts[0].upper() == "ALL":
    names = "ALL"
else:
    names = args.artifacts

results = ra.render_batch(names, outdir=args.outdir, play_audio=args.play, parallel=args.parallel,
                          outfmt=args.outfmt, samprate=args.samprate, duration_override=args.duration,
                          bitdepth=args.bitdepth, verbose=args.verbose)
print("Results:")
for k, v in results.items():
    print(f"  {k}: {'OK' if v else 'FAILED'}")
