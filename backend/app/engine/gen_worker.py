"""Subprocess worker for Diffusers jobs.

Runs outside the API process so a ROCm/HIP hang cannot freeze job polling,
and the parent can kill a stuck generate (Stop / stall timeout).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    import faulthandler

    faulthandler.enable(all_threads=True)
    parser = argparse.ArgumentParser(description="StudioNels Diffusers job worker")
    parser.add_argument("--job-file", required=True)
    parser.add_argument("--progress-file", required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--out-path", required=True)
    args = parser.parse_args(argv)

    job_path = Path(args.job_file)
    progress_path = Path(args.progress_file)
    result_path = Path(args.result_file)
    out_path = Path(args.out_path)

    def cb(message: str, frac: float) -> None:
        _atomic_write(
            progress_path,
            {
                "message": message,
                "progress": float(frac),
                "ts": time.time(),
            },
        )

    # Progress BEFORE heavy imports — first torch/diffusers import can take minutes on AMD
    cb("Worker boot — importing PyTorch / Diffusers (first time can take 1–2 min)…", 0.03)

    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _atomic_write(
            result_path,
            {"ok": False, "error": f"Bad job file: {exc}", "traceback": ""},
        )
        return 2

    try:
        from .safetensors_compat import apply_safetensors_backend_compat
        from .mmgp_accel import apply_runtime_env, mmgp_available

        apply_safetensors_backend_compat()
        apply_runtime_env()
        cb(
            (
                "Imports… mmgp ready — loading pipeline code…"
                if mmgp_available()
                else "Imports… mmgp missing — Pinokio Update or Install AMD engine, then retry…"
            ),
            0.04,
        )
        if mmgp_available():
            from mmgp import offload as _mmgp_offload  # noqa: F401
        apply_safetensors_backend_compat(force=True)

        from .pipelines import run_diffusers_job

        label = "mmgp" if mmgp_available() else "Diffusers"
        cb(f"Worker started — StudioNels {label} engine…", 0.05)
        result = run_diffusers_job(job, out_path, cb)
        _atomic_write(
            result_path,
            {
                "ok": True,
                "result": result,
                "preview": bool(result.get("preview")),
            },
        )
        return 0
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
            cb(f"Failed: {exc}", 0.2)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
