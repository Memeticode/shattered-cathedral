"""Batch rendering orchestration.

Spawns render_single.py as a subprocess for each artifact, using the Python 3.11
interpreter (RENDER_PYTHON) that has pyo installed.
"""
import os
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from shattered_audio.log import get_logger
from shattered_audio.shattered_configs import CONFIGS

log = get_logger("render_artifact")

WAV_HEADER_SIZE = 44

# The Python interpreter used for rendering (must have pyo installed).
# Defaults to .venv311 relative to project root; override via RENDER_PYTHON env var.
_project_root = Path(__file__).resolve().parent.parent
RENDER_PYTHON = os.environ.get(
    "RENDER_PYTHON",
    str(_project_root / ".venv311" / "Scripts" / "python.exe"),
)


def _render_helper(cmd: list[str], out_path: Path) -> tuple[int, bool]:
    res = subprocess.run(cmd)
    ok = (res.returncode == 0) or (out_path.exists() and out_path.stat().st_size > WAV_HEADER_SIZE)
    return res.returncode, ok


def render_batch(
    artifact_selection,
    outdir: str = "artifacts",
    play_audio: bool = False,
    parallel: int = 1,
    outfmt: str = "wav",
    samprate: int | None = None,
    duration_override: float | None = None,
    bitdepth: int | None = None,
    verbose: bool = False,
) -> dict[str, bool]:
    """Render a batch of artifacts using subprocess workers."""
    if isinstance(artifact_selection, str) and artifact_selection.upper() == "ALL":
        names = list(CONFIGS.keys())
    else:
        names = list(artifact_selection)

    out_dir = Path(outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    render_script = str(_project_root / "shattered_audio" / "render_single.py")

    tasks: list[tuple[str, list[str], Path]] = []
    for name in names:
        if name not in CONFIGS:
            log.warning("Artifact not found in configs library: %s", name)
            continue
        out_path = out_dir / f"{name}.wav"
        cmd = [RENDER_PYTHON, render_script, name, "--outdir", str(out_dir)]
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

    results: dict[str, bool] = {}
    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            future_map = {ex.submit(_render_helper, cmd, out_path): name for name, cmd, out_path in tasks}
            for fut in as_completed(future_map):
                name = future_map[fut]
                try:
                    returncode, ok = fut.result()
                except Exception as e:
                    log.error("Rendering %s raised: %s", name, e)
                    results[name] = False
                else:
                    results[name] = ok
                    if not ok:
                        log.error("Rendering failed for %s (exit %d)", name, returncode)
    else:
        for name, cmd, out_path in tasks:
            log.info("Spawning: %s", cmd)
            returncode, ok = _render_helper(cmd, out_path)
            results[name] = ok
            if not ok:
                log.error("Rendering failed for %s (exit %d)", name, returncode)

    return results
