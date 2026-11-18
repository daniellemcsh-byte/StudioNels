"""Long-lived Generate worker — keeps the last model warm in VRAM/RAM.

Other apps feel fast because they do not reload 10–30GB weights every click.
This daemon accepts job request files, runs Diffusers+mmgp in-process, and
reuses a cached pipeline when the model matches.

Also accepts explicit preload requests so Start / "Load into studio" can
resident-load Wan 1.3B (etc.) before the first Generate.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from .atomic_io import write_json


def _daemon_dir() -> Path:
    from ..paths import MEDIA_DIR, ensure_dirs

    ensure_dirs()
    d = MEDIA_DIR / "_engine_daemon"
    d.mkdir(parents=True, exist_ok=True)
    (d / "requests").mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload, required=False)


def _cache_labels() -> list[str]:
    try:
        from .pipe_cache import status as cache_status

        st = cache_status()
        return list(st.get("cached") or [])
    except Exception:
        return []


def _heartbeat(extra: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"pid": os.getpid(), "ts": time.time()}
    if extra:
        payload.update(extra)
    try:
        from .pipe_cache import status as cache_status

        st = cache_status()
        payload["cache"] = st
        # Flatten for API / dock consumers
        payload["cached"] = list(st.get("cached") or [])
    except Exception:
        payload.setdefault("cached", [])
    _atomic_write(_daemon_dir() / "heartbeat.json", payload)


def _handle_preload(req: dict[str, Any], req_path: Path) -> None:
    model_id = str(req.get("model_id") or (req.get("job") or {}).get("model_id") or "").strip()
    preset_id = req.get("preset_id")
    if preset_id is None:
        preset_id = (req.get("job") or {}).get("preset_id")
    progress_path = Path(str(req["progress_file"]))
    result_path = Path(str(req["result_file"]))
    cancel_path = Path(str(req.get("cancel_file") or (progress_path.parent / "cancel.flag")))

    def cb(message: str, frac: float) -> None:
        _atomic_write(
            progress_path,
            {
                "message": message,
                "progress": float(frac),
                "ts": time.time(),
                "warm": True,
                "action": "preload",
            },
        )
        _heartbeat(
            {
                "status": "preloading",
                "message": message,
                "progress": float(frac),
                "model_id": model_id,
            }
        )
        if cancel_path.exists():
            raise RuntimeError("Stopped by user")

    if not model_id:
        _atomic_write(
            result_path,
            {"ok": False, "error": "preload requires model_id", "cached": _cache_labels()},
        )
        try:
            req_path.unlink()
        except Exception:
            pass
        return

    # Friendly label for early progress (before catalog import)
    early_label = model_id
    try:
        from .catalog import get_model

        m = get_model(model_id)
        if m:
            early_label = str(m.get("label") or model_id)
    except Exception:
        pass

    cb(f"Preloading {early_label} into RAM/VRAM…", 0.04)
    try:
        from .mmgp_accel import apply_runtime_env, mmgp_available
        from .pipelines import preload_diffusers_model

        apply_runtime_env()
        if mmgp_available():
            from mmgp import offload as _mmgp_offload  # noqa: F401

        result = preload_diffusers_model(
            model_id,
            preset_id=str(preset_id) if preset_id else None,
            cb=cb,
        )
        cached = list(result.get("cached") or _cache_labels())
        label = str(result.get("label") or early_label)
        _atomic_write(
            result_path,
            {
                "ok": True,
                "label": label,
                "cached": cached,
                "already_loaded": bool(result.get("already_loaded")),
                "warm": True,
                "action": "preload",
            },
        )
        _heartbeat(
            {
                "status": "idle",
                "message": f"Model ready: {label}",
                "last_preload": model_id,
                "ok": True,
            }
        )
    except Exception as exc:  # noqa: BLE001
        _atomic_write(
            result_path,
            {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc()[-2000:],
                "cached": _cache_labels(),
                "action": "preload",
            },
        )
        try:
            cb(f"Preload failed: {exc}", 0.2)
        except Exception:
            pass
        _heartbeat(
            {
                "status": "idle",
                "ok": False,
                "error": str(exc),
                "last_preload": model_id,
            }
        )
    finally:
        try:
            req_path.unlink()
        except Exception:
            pass
        try:
            if cancel_path.exists():
                cancel_path.unlink()
        except Exception:
            pass


def _handle_request(req_path: Path) -> None:
    try:
        req = json.loads(req_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        try:
            req_path.unlink()
        except Exception:
            pass
        print(f"bad request {req_path}: {exc}", flush=True)
        return

    action = str(req.get("action") or "generate").strip().lower()
    if action == "release":
        try:
            from .pipe_cache import clear

            clear()
        except Exception:
            pass
        try:
            import gc

            gc.collect()
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        try:
            req_path.unlink()
        except Exception:
            pass
        _heartbeat({"status": "idle", "message": "Weights released. Engine still warm."})
        return
    if action == "preload":
        _handle_preload(req, req_path)
        return

    job = req.get("job") or {}
    progress_path = Path(str(req["progress_file"]))
    result_path = Path(str(req["result_file"]))
    out_path = Path(str(req["out_path"]))
    cancel_path = Path(str(req.get("cancel_file") or (progress_path.parent / "cancel.flag")))

    def cb(message: str, frac: float) -> None:
        _atomic_write(
            progress_path,
            {
                "message": message,
                "progress": float(frac),
                "ts": time.time(),
                "warm": True,
            },
        )
        if cancel_path.exists():
            raise RuntimeError("Stopped by user")

    cb("Warm engine picked up job — importing pipeline (first AMD import can take 1–2 min)…", 0.04)
    try:
        from .mmgp_accel import apply_runtime_env, mmgp_available
        from .pipelines import run_diffusers_job
        from .pipe_cache import status as cache_status

        apply_runtime_env()
        if mmgp_available():
            from mmgp import offload as _mmgp_offload  # noqa: F401

        warm = cache_status().get("count", 0) > 0
        label = "mmgp" if mmgp_available() else "Diffusers"
        cb(
            (
                f"Warm engine · reusing loaded model ({label})…"
                if warm
                else f"Warm engine · first load this session ({label})…"
            ),
            0.06 if warm else 0.05,
        )
        # Mark job so pipelines.py prefers the resident cache
        job = dict(job)
        job["warm_cache"] = True
        result = run_diffusers_job(job, out_path, cb)
        _atomic_write(
            result_path,
            {
                "ok": True,
                "result": result,
                "preview": bool(result.get("preview")),
                "warm": True,
            },
        )
        _heartbeat({"last_job": job.get("id"), "ok": True, "status": "idle"})
    except Exception as exc:  # noqa: BLE001
        _atomic_write(
            result_path,
            {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc()[-2000:],
            },
        )
        try:
            cb(f"Failed: {exc}", float(job.get("progress") or 0.2))
        except Exception:
            pass
        _heartbeat({"last_job": job.get("id"), "ok": False, "error": str(exc), "status": "idle"})
    finally:
        try:
            req_path.unlink()
        except Exception:
            pass
        try:
            if cancel_path.exists():
                cancel_path.unlink()
        except Exception:
            pass


def main() -> int:
    import faulthandler

    d = _daemon_dir()
    pid_path = d / "daemon.pid"
    # Write pid + heartbeat BEFORE importing torch — parent must not wait blindly
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        fault_log = open(d / "daemon.log", "a", encoding="utf-8")
        faulthandler.enable(fault_log, all_threads=True)
    except Exception:
        faulthandler.enable(all_threads=True)
    _heartbeat({"status": "booting"})
    print(f"StudioNels warm engine booting pid={os.getpid()}", flush=True)

    from .mmgp_accel import apply_runtime_env, mmgp_available

    apply_runtime_env()
    _heartbeat(
        {
            "status": "ready",
            "mmgp": bool(mmgp_available()),
        }
    )
    print(
        f"StudioNels warm engine ready pid={os.getpid()} mmgp={mmgp_available()}",
        flush=True,
    )

    req_dir = d / "requests"
    try:
        while True:
            _heartbeat({"status": "idle"})
            reqs = sorted(req_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
            if not reqs:
                time.sleep(0.25)
                continue
            _heartbeat({"status": "busy", "request": reqs[0].name})
            _handle_request(reqs[0])
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            from .pipe_cache import clear

            clear()
        except Exception:
            pass
        try:
            if pid_path.exists():
                pid_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main() or 0)
