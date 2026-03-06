"""Iterative generation loop: model -> render -> evaluate -> tweak

Usage (CLI):
    python -m tools.iterative_loop --seed 008_binaural_temple --iterations 6 --outdir artifacts/iter

Usage (programmatic, for live demo):
    from tools.iterative_loop import IterativeSession
    session = IterativeSession(seed="008_binaural_temple", outdir="artifacts/demo", ...)
    session.run()
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2

# Ensure project root is on sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from shattered_audio.log import get_logger
from shattered_audio.render_artifact import RENDER_PYTHON, WAV_HEADER_SIZE
from tools.gen_from_model import ModelAdapter
from tools.analysis import compute_metrics
from tools.event_bus import EventBus, DemoEvent, EventType

log = get_logger("iterative_loop")


def _compute_config_diff(prev: dict | None, curr: dict) -> list[dict]:
    """Compute a flat list of changed fields between two configs.

    Returns list of dicts: {"path": "master.reverb_mix", "old": 0.8, "new": 0.65, "action": "changed"}
    """
    changes: list[dict] = []

    def _walk(old: object, new: object, prefix: str = "") -> None:
        if isinstance(new, dict):
            all_keys = set(list(new.keys()) + (list(old.keys()) if isinstance(old, dict) else []))
            for k in sorted(all_keys):
                p = f"{prefix}.{k}" if prefix else k
                if k == "meta":
                    continue  # skip metadata noise
                old_v = old.get(k) if isinstance(old, dict) else None
                new_v = new.get(k) if k in new else None
                if k not in new:
                    changes.append({"path": p, "old": old_v, "new": None, "action": "removed"})
                elif not isinstance(old, dict) or k not in old:
                    changes.append({"path": p, "old": None, "new": new_v, "action": "added"})
                else:
                    _walk(old_v, new_v, p)
        elif isinstance(new, list) and isinstance(old, list):
            for idx in range(max(len(old), len(new))):
                p = f"{prefix}[{idx}]"
                if idx >= len(new):
                    changes.append({"path": p, "old": old[idx], "new": None, "action": "removed"})
                elif idx >= len(old):
                    changes.append({"path": p, "old": None, "new": new[idx], "action": "added"})
                else:
                    _walk(old[idx], new[idx], p)
        else:
            if old != new:
                changes.append({"path": prefix, "old": old, "new": new, "action": "changed"})

    _walk(prev or {}, curr)
    return changes


def run_iteration(
    seed_key: str | None,
    outdir: str,
    iter_idx: int | str,
    adapter: ModelAdapter,
    duration_override: float | None = None,
    verbose: bool = False,
    provided_cfg_path: str | None = None,
    seed_cfg: dict | None = None,
    user_prompt: str | None = None,
) -> tuple[Path, dict | None, bool]:
    """Generate (or render provided) a config, render to wav, and return metrics."""
    cfg_dir = Path(outdir) / "generated_configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    if provided_cfg_path:
        cfg_path = Path(provided_cfg_path)
        cfg_id = cfg_path.stem
    else:
        gen_cfg = adapter.propose_config(seed_key=seed_key, seed_cfg=seed_cfg, prompt=user_prompt)
        cfg_id = f"gen_{iter_idx}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        cfg_path = cfg_dir / f"{cfg_id}.json"
        cfg_path.write_text(json.dumps(gen_cfg, indent=2), encoding="utf8")

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf8"))
    except Exception as e:
        log.warning("Failed to load config %s: %s", cfg_path, e)
        cfg = None

    out_wav_dir = Path(outdir) / "renders"
    out_wav_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_wav_dir / f"{cfg_id}.wav"

    render_script = str(Path(project_root) / "shattered_audio" / "render_single.py")
    cmd = [RENDER_PYTHON, render_script, "--config-file", str(cfg_path), "--outdir", str(out_wav_dir)]
    if duration_override:
        cmd.extend(["--duration", str(duration_override)])
    if verbose:
        log.info("Running: %s", cmd)

    res = subprocess.run(cmd)
    # Treat as success if file exists and is non-trivial, even with non-zero exit (pyo teardown quirk)
    ok = out_wav.exists() and out_wav.stat().st_size > WAV_HEADER_SIZE
    if not ok:
        log.error("Render failed (exit %d) for %s", res.returncode, cfg_id)
        return cfg_path, None, False

    try:
        metrics = compute_metrics(str(out_wav))
    except Exception as e:
        log.warning("Metrics computation failed: %s", e)
        metrics = None

    return cfg_path, {"wav": str(out_wav), "metrics": metrics, "cfg": cfg}, True


def _append_log(session_log_path: Path, entry: dict) -> None:
    """Append a JSON entry to the session log file."""
    lst: list = []
    if session_log_path.exists():
        try:
            lst = json.loads(session_log_path.read_text(encoding="utf8"))
        except Exception:
            lst = []
    lst.append(entry)
    session_log_path.write_text(json.dumps(lst, indent=2), encoding="utf8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IterativeSession:
    """Programmatic interface for the generation loop, with optional SSE event emission."""

    def __init__(
        self,
        seed: str | None = None,
        outdir: str = "artifacts/demo",
        iterations: int = 5,
        adapter: ModelAdapter | None = None,
        event_bus: EventBus | None = None,
        duration_override: float | None = 15.0,
        normalize: bool = False,
        target_lufs: float = -16.0,
        visualize: bool = True,
        verbose: bool = False,
        user_prompt: str | None = None,
        input_config: dict | None = None,
    ):
        self.seed = seed or "008_binaural_temple"
        self.outdir = outdir
        self.iterations = iterations
        self.adapter = adapter or ModelAdapter()
        self.event_bus = event_bus
        self.duration_override = duration_override
        self.normalize = normalize
        self.target_lufs = target_lufs
        self.visualize = visualize
        self.verbose = verbose
        self.user_prompt = user_prompt
        self.input_config = input_config
        self.session_log_path = Path(outdir) / "session_log.json"
        self._prev_cfg: dict | None = None

    def _emit(self, event: DemoEvent) -> None:
        if self.event_bus:
            self.event_bus.publish(event)

    def run(self) -> None:
        """Execute the full generation loop."""
        Path(self.outdir).mkdir(parents=True, exist_ok=True)

        for i in range(1, self.iterations + 1):
            try:
                self._run_iteration(i)
            except Exception as e:
                log.error("Iteration %d failed: %s", i, e, exc_info=True)
                self._emit(DemoEvent(EventType.ERROR, i, {"error": str(e)}))
                break

        self._emit(DemoEvent(EventType.SESSION_COMPLETE, self.iterations, {}))
        log.info("Session complete (%d iterations)", self.iterations)

    def _run_iteration(self, i: int) -> None:
        self._emit(DemoEvent(EventType.ITERATION_START, i, {"total": self.iterations}))
        log.info("Iteration %d/%d: generating...", i, self.iterations)

        seed_cfg = self._prev_cfg
        if seed_cfg is None and self.input_config is not None:
            seed_cfg = self.input_config

        cfg_path, info, ok = run_iteration(
            self.seed, self.outdir, i, self.adapter,
            duration_override=self.duration_override,
            verbose=self.verbose,
            seed_cfg=seed_cfg,
            user_prompt=self.user_prompt,
        )

        if not ok:
            self._emit(DemoEvent(EventType.ERROR, i, {"error": "Render failed"}))
            return

        wav_path = info["wav"]
        wav_name = Path(wav_path).name
        cfg = info.get("cfg")
        log.info("Rendered: %s", wav_path)

        # Config + diff
        config_diff = _compute_config_diff(self._prev_cfg, cfg) if cfg else []
        if cfg:
            self._emit(DemoEvent(EventType.CONFIG_READY, i, {
                "config": cfg,
                "diff": config_diff,
            }))
            self._prev_cfg = cfg

        self._emit(DemoEvent(EventType.RENDER_COMPLETE, i, {
            "wav": wav_path,
            "wav_url": f"/renders/{wav_name}",
        }))

        # Metrics
        if info.get("metrics"):
            m = info["metrics"]
            log.info(
                "Metrics: RMS=%.4f dBFS=%.1f centroid=%.0f lufs=%s",
                m.get("rms", 0), m.get("dbfs", 0),
                m.get("spectral_centroid", 0), m.get("lufs"),
            )
            self._emit(DemoEvent(EventType.METRICS_READY, i, {"metrics": m}))

        # Model evaluation
        intent = None
        if cfg and isinstance(cfg, dict):
            intent = (cfg.get("meta") or {}).get("intent")

        try:
            eval_plan = self.adapter.evaluate_and_plan(
                cfg, info.get("metrics"), intent=intent,
                config_diff=config_diff, iteration=i,
                total_iterations=self.iterations,
                user_prompt=self.user_prompt,
            )
            info["commentary"] = eval_plan.get("commentary")
            info["critique"] = eval_plan.get("critique")
            info["rationale"] = eval_plan.get("rationale")
            info["plan"] = eval_plan.get("plan")
            log.info("Commentary: %s", info.get("commentary"))
            log.info("Critique: %s", info.get("critique"))
            log.info("Rationale: %s", info.get("rationale"))
            log.info("Plan: %s", info.get("plan"))
        except Exception as e:
            log.warning("Evaluation failed: %s", e)
            info["commentary"] = None
            info["critique"] = None
            info["rationale"] = None
            info["plan"] = None

        self._emit(DemoEvent(EventType.EVALUATION_READY, i, {
            "commentary": info.get("commentary", ""),
            "critique": info.get("critique", ""),
            "rationale": info.get("rationale", ""),
            "plan": info.get("plan", ""),
        }))

        # Normalization
        if self.normalize:
            try:
                from tools.analysis import normalize_to_target_lufs
                norm_out = Path(self.outdir) / "renders" / (Path(wav_path).stem + "_norm.wav")
                achieved = normalize_to_target_lufs(wav_path, self.target_lufs, str(norm_out))
                if achieved is not None:
                    log.info("Normalized to LUFS %.1f -> %s", achieved, norm_out)
                    info["wav"] = str(norm_out)
                    try:
                        info["metrics"] = compute_metrics(info["wav"])
                    except Exception:
                        pass
            except Exception as e:
                log.warning("Normalization failed: %s", e)

        # Visualization
        if self.visualize:
            try:
                from tools.analysis import generate_visualization
                png_out = Path(self.outdir) / "renders" / (Path(info["wav"]).stem + ".png")
                generate_visualization(info["wav"], str(png_out))
                png_name = png_out.name
                self._emit(DemoEvent(EventType.VISUALIZATION_READY, i, {
                    "png_url": f"/renders/{png_name}",
                }))
            except Exception as e:
                log.warning("Visualization failed: %s", e)

        # Log entry
        _append_log(self.session_log_path, {
            "time": _now_iso(),
            "iteration": i,
            "action": "auto",
            "cfg": str(cfg_path),
            "wav": info.get("wav"),
            "metrics": info.get("metrics"),
            "commentary": info.get("commentary"),
            "critique": info.get("critique"),
            "rationale": info.get("rationale"),
            "plan": info.get("plan"),
            "config_diff": config_diff,
        })


def main() -> None:
    """CLI entry point (interactive mode)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    p = argparse.ArgumentParser()
    p.add_argument("--seed", default=None, help="Seed artifact key (from CONFIGS)")
    p.add_argument("--iterations", type=int, default=6)
    p.add_argument("--outdir", default="artifacts/iter")
    p.add_argument("--provider", default="anthropic", help="Chat provider: anthropic (default), openai")
    p.add_argument("--local", action="store_true", help="Use local evolution only (no LLM)")
    p.add_argument("--model", default=None)
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--normalize", action="store_true")
    p.add_argument("--target-lufs", type=float, default=-16.0)
    p.add_argument("--visualize", action="store_true")
    p.add_argument("--auto", action="store_true", help="Run fully automated (no user prompts)")
    args = p.parse_args()

    chat_client = None
    if not args.local:
        from chat import create_client
        kwargs = {}
        if args.model:
            kwargs["model"] = args.model
        chat_client = create_client(args.provider, **kwargs)

    adapter = ModelAdapter(chat_client=chat_client)

    if args.auto:
        session = IterativeSession(
            seed=args.seed,
            outdir=args.outdir,
            iterations=args.iterations,
            adapter=adapter,
            duration_override=args.duration,
            normalize=args.normalize,
            target_lufs=args.target_lufs,
            visualize=args.visualize,
            verbose=args.verbose,
        )
        session.run()
        return

    # Interactive mode (original behavior, simplified)
    seed = args.seed
    outdir = args.outdir
    Path(outdir).mkdir(parents=True, exist_ok=True)
    session_log_path = Path(outdir) / "session_log.json"

    for i in range(args.iterations):
        log.info("Iteration %d/%d: generating...", i + 1, args.iterations)
        cfg_path, info, ok = run_iteration(
            seed, outdir, i + 1, adapter,
            duration_override=args.duration, verbose=args.verbose,
        )
        if not ok:
            cont = input("Render failed. (r)etry, (c)ontinue, (q)uit? > ").strip().lower()
            if cont == "q":
                break
            continue

        log.info("Rendered: %s", info["wav"])
        if info.get("metrics"):
            m = info["metrics"]
            log.info("Metrics: RMS=%.4f dBFS=%.1f centroid=%.0f lufs=%s",
                     m.get("rms", 0), m.get("dbfs", 0), m.get("spectral_centroid", 0), m.get("lufs"))

        try:
            intent = None
            if info.get("cfg") and isinstance(info["cfg"], dict):
                intent = (info["cfg"].get("meta") or {}).get("intent")
            eval_plan = adapter.evaluate_and_plan(info.get("cfg"), info.get("metrics"), intent=intent)
            info["commentary"] = eval_plan.get("commentary")
            info["plan"] = eval_plan.get("plan")
            log.info("Commentary: %s", info.get("commentary"))
            log.info("Plan: %s", info.get("plan"))
        except Exception as e:
            log.warning("Evaluation failed: %s", e)
            info["commentary"] = None
            info["plan"] = None

        if args.visualize:
            try:
                from tools.analysis import generate_visualization
                png_out = Path(outdir) / "renders" / (Path(info["wav"]).stem + ".png")
                generate_visualization(info["wav"], str(png_out))
            except Exception as e:
                log.warning("Visualization failed: %s", e)

        action = input("(a)ccept, (n)ext, (q)uit > ").strip().lower()
        _append_log(session_log_path, {
            "time": _now_iso(), "iteration": i + 1, "action": action,
            "cfg": str(cfg_path), "wav": info.get("wav"),
            "metrics": info.get("metrics"),
            "commentary": info.get("commentary"), "plan": info.get("plan"),
        })
        if action == "a" or action == "q":
            break

    log.info("Done.")


if __name__ == "__main__":
    main()
