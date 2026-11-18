"""JSON writes that survive Windows locking the destination.

os.replace raises WinError 5 (Access is denied) when the API is reading
progress.json, or when the load thread and the heartbeat thread replace the
same .tmp at once. A progress update must not abort generation.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = os.path.normcase(os.path.abspath(str(path)))
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def write_json(path: Path, payload: dict[str, Any], *, required: bool = True) -> bool:
    """Write payload as JSON. Returns False when a non-required write could not land."""
    path = Path(path)
    data = json.dumps(payload)
    lock = _lock_for(path)
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(data, encoding="utf-8")
            for attempt in range(10):
                try:
                    os.replace(tmp, path)
                    return True
                except PermissionError:
                    time.sleep(0.02 * (attempt + 1))
            try:
                path.write_text(data, encoding="utf-8")
                return True
            except PermissionError:
                if required:
                    raise
                return False
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
