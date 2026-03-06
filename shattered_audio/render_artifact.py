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
        # As a last resort, ensure project root is on sys.path and retry package import
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from shattered_audio.shattered_engine import ShatteredEngine
        from shattered_audio.shattered_configs import CONFIGS
from os import path, makedirs
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed


def _render_helper(cmd, out_path):
    res = subprocess.run(cmd)
    # Treat as success if output exists despite non-zero exit (pyo teardown quirk)
    ok = (res.returncode == 0) or (path.exists(out_path) and path.getsize(out_path) > 44)
    return res.returncode, ok


def render_batch(artifact_selection, outdir="artifacts", play_audio=False, parallel=1,
                 outfmt="wav", samprate=None, duration_override=None, bitdepth=None, verbose=False):
    """Render a batch of artifacts.

    artifact_selection: iterable of artifact keys, or single key string 'ALL'.
    outdir: output directory for WAV files.
    play_audio: if True, run helper with audio playback enabled.
    parallel: number of worker threads to spawn helper processes concurrently.
    """
    if isinstance(artifact_selection, str) and artifact_selection.upper() == "ALL":
        names = list(CONFIGS.keys())
    else:
        names = list(artifact_selection)

    makedirs(outdir, exist_ok=True)

    tasks = []
    for name in names:
        if name not in CONFIGS:
            print(f"Artifact not found in configs library: {name}")
            continue
        out_path = path.join(outdir, f"{name}.wav")
        cmd = [sys.executable, path.join("shattered_audio", "render_single.py"), name, "--outdir", outdir]
        if play_audio:
            cmd.append("--play")
        if outfmt:
            cmd.extend(["--outfmt", outfmt])
        if samprate:
            cmd.extend(["--samprate", str(samprate)])
        if duration_override:
            cmd.extend(["--duration", str(duration_override)])
        if bitdepth:
            cmd.extend(["--bitdepth", str(bitdepth)])
        if verbose:
            cmd.append("--verbose")
        tasks.append((name, cmd, out_path))

    results = {}
    if parallel and parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            future_map = {ex.submit(_render_helper, cmd, out_path): name for name, cmd, out_path in tasks}
            for fut in as_completed(future_map):
                name = future_map[fut]
                try:
                    returncode, ok = fut.result()
                except Exception as e:
                    print(f"Rendering {name} raised: {e}")
                    results[name] = False
                else:
                    results[name] = ok
                    if not ok:
                        print(f"Rendering failed for {name} (exit {returncode})")
    else:
        for name, cmd, out_path in tasks:
            print(f"Spawning: {cmd}")
            returncode, ok = _render_helper(cmd, out_path)
            results[name] = ok
            if not ok:
                print(f"Rendering failed for {name} (exit {returncode})")

    return results


if __name__ == "__main__":
    # Backwards-compatible quick run: render default single item
    render_batch(["004_glass_ocean"], outdir="artifacts", play_audio=False, parallel=1)
