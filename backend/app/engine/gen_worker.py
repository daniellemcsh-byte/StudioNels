"""Subprocess worker for Diffusers jobs.

Runs outside the API process so a ROCm/HIP hang cannot freeze job polling,
and the parent can kill a stuck generate (Stop / stall timeout).
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
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

    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _atomic_write(
            result_path,
            {"ok": False, "error": f"Bad job file: {exc}", "traceback": ""},
        )
        return 2

    def cb(message: str, frac: float) -> None:
        _atomic_write(
            progress_path,
            {
                "message": message,
                "progress": float(frac),
                "ts": __import__("time").time(),
            },
        )

    try:
        # Ensure imports resolve when launched as `python -m app.engine.gen_worker`
        from .pipelines import run_diffusers_job

        cb("Worker started — loading engine…", 0.02)
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
            cb(f"Failed: {exc}", float(job.get("progress") or 0.2))
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    # Allow `python -m app.engine.gen_worker` from backend/
    sys.exit(main())
