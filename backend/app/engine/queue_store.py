from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from ..paths import JOBS_PATH, LORAS_DIR, MODELS_DIR, ensure_dirs

_LOCK = threading.Lock()
# Hot progress updates (step/ETA) live here so the UI sees them even if disk lag
_LIVE: dict[str, dict[str, Any]] = {}
_LAST_DISK_WRITE = 0.0


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


def _merged(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for job in jobs:
        live = _LIVE.get(str(job.get("id") or ""))
        out.append(dict(live) if live else job)
    # Include brand-new live jobs not yet on disk
    known = {str(j.get("id") or "") for j in out}
    for lid, live in _LIVE.items():
        if lid and lid not in known:
            out.append(dict(live))
    return out


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        jobs = _merged(_load())
        return list(reversed(jobs[-limit:]))


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        if job_id in _LIVE:
            return dict(_LIVE[job_id])
        for job in _load():
            if job.get("id") == job_id:
                return job
    return None


def upsert_job(job: dict[str, Any]) -> dict[str, Any]:
    global _LAST_DISK_WRITE
    with _LOCK:
        jid = str(job.get("id") or "")
        if jid:
            _LIVE[jid] = dict(job)

        disk = _load()
        by_id: dict[str, dict[str, Any]] = {
            str(j.get("id") or ""): j for j in disk if j.get("id")
        }
        on_disk = jid in by_id
        for lid, live in _LIVE.items():
            if lid:
                by_id[lid] = dict(live)
        jobs = list(by_id.values())

        now = time.time()
        status = str(job.get("status") or "")
        force = status in {"done", "failed", "cancelled", "queued"} or not on_disk
        if force or now - _LAST_DISK_WRITE >= 1.5:
            _save(jobs)
            _LAST_DISK_WRITE = now
            if status in {"done", "failed", "cancelled"} and jid:
                _LIVE.pop(jid, None)
        return job


def remove_job(job_id: str) -> dict[str, Any] | None:
    """Drop a job from the visible queue history (does not delete media takes)."""
    with _LOCK:
        live = _LIVE.pop(job_id, None)
        jobs = _load()
        kept: list[dict[str, Any]] = []
        removed: dict[str, Any] | None = None
        for job in jobs:
            if job.get("id") == job_id:
                removed = job
            else:
                kept.append(job)
        if removed is None and live is not None:
            removed = live
        if removed is not None:
            _save(kept)
        return removed


def models_dir() -> Path:
    ensure_dirs()
    return MODELS_DIR


def loras_dir() -> Path:
    ensure_dirs()
    return LORAS_DIR
