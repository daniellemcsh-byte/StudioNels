"""In-process warm pipeline cache — why other apps feel fast after the first run.

Cold-loading Wan/LTX Diffusers weights every job is the main StudioNels delay.
Keep one resident pipeline in the warm engine daemon and reuse it when the
model + memory profile match.
"""

from __future__ import annotations

from typing import Any


_CACHE: dict[str, Any] = {}
_CACHE_META: dict[str, str] = {}


def cache_key(model_id: str, mem: dict[str, Any] | None, dtype_name: str) -> str:
    mem = mem or {}
    return "|".join(
        [
            str(model_id or ""),
            str(mem.get("placement") or ""),
            str(mem.get("preset_id") or ""),
            str(dtype_name or ""),
            "q1" if mem.get("quantize_transformer", True) else "q0",
        ]
    )


def get(key: str) -> Any | None:
    return _CACHE.get(key)


def put(key: str, pipe: Any, label: str = "") -> None:
    # Only keep one resident model — swapping is cheaper than RAM blow-ups
    for old in list(_CACHE.keys()):
        if old == key:
            continue
        try:
            old_pipe = _CACHE.pop(old, None)
            if old_pipe is not None:
                _release(old_pipe)
        except Exception:
            pass
        _CACHE_META.pop(old, None)
    _CACHE[key] = pipe
    _CACHE_META[key] = label or key


def clear() -> None:
    for key in list(_CACHE.keys()):
        try:
            _release(_CACHE.pop(key, None))
        except Exception:
            pass
    _CACHE_META.clear()


def status() -> dict[str, Any]:
    return {
        "cached": list(_CACHE_META.values()) or list(_CACHE.keys()),
        "count": len(_CACHE),
    }


def _release(pipe: Any) -> None:
    if pipe is None:
        return
    try:
        import gc

        import torch

        del pipe
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
