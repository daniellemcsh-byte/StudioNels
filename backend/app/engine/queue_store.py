from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..paths import JOBS_PATH, LORAS_DIR, MODELS_DIR, ensure_dirs

_LOCK = threading.Lock()


def _load() -> list[dict[str, Any]]:
    ensure_dirs()
    if not JOBS_PATH.exists():
        return []
    try:
        return json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(jobs: list[dict[str, Any]]) -> None:
    ensure_dirs()
    tmp = JOBS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    tmp.replace(JOBS_PATH)


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        jobs = _load()
        return list(reversed(jobs[-limit:]))


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        for job in _load():
            if job.get("id") == job_id:
                return job
    return None


def upsert_job(job: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        jobs = _load()
        for i, existing in enumerate(jobs):
            if existing.get("id") == job["id"]:
                jobs[i] = job
                _save(jobs)
                return job
        jobs.append(job)
        _save(jobs)
        return job


def remove_job(job_id: str) -> dict[str, Any] | None:
    """Drop a job from the visible queue history (does not delete media takes)."""
    with _LOCK:
        jobs = _load()
        kept: list[dict[str, Any]] = []
        removed: dict[str, Any] | None = None
        for job in jobs:
            if job.get("id") == job_id:
                removed = job
            else:
                kept.append(job)
        if removed is not None:
            _save(kept)
        return removed


def models_dir() -> Path:
    ensure_dirs()
    return MODELS_DIR


def loras_dir() -> Path:
    ensure_dirs()
    return LORAS_DIR
