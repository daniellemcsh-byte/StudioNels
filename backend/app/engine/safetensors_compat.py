"""Compat for transformers + safetensors (+ mmgp) version skew.

Newer transformers call safe_open(..., backend=...). Older safetensors and some
mmgp redirects reject that kwarg with:
  TypeError: safe_open() got an unexpected keyword argument 'backend'
"""

from __future__ import annotations

import functools
import inspect
import sys
from typing import Any

_PATCHED_ORIG_IDS: set[int] = set()


def apply_safetensors_backend_compat(*, force: bool = False) -> bool:
    """Wrap safetensors.safe_open so a stray backend= kwarg cannot crash loads."""
    try:
        import safetensors as st
    except Exception:
        return False

    orig = getattr(st, "safe_open", None)
    if orig is None:
        return False

    # Already wrapped this exact function object
    if not force and id(orig) in _PATCHED_ORIG_IDS:
        return True

    supports_backend = False
    try:
        params = inspect.signature(orig).parameters
        supports_backend = "backend" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
    except Exception:
        supports_backend = False

    if supports_backend and not force:
        _PATCHED_ORIG_IDS.add(id(orig))
        return True

    @functools.wraps(orig)
    def _safe_open(*args: Any, **kwargs: Any):
        if "backend" not in kwargs:
            return orig(*args, **kwargs)
        try:
            return orig(*args, **kwargs)
        except TypeError as exc:
            if "backend" not in str(exc):
                raise
            stripped = {k: v for k, v in kwargs.items() if k != "backend"}
            return orig(*args, **stripped)

    try:
        st.safe_open = _safe_open  # type: ignore[attr-defined]
    except Exception:
        return False

    _PATCHED_ORIG_IDS.add(id(orig))
    _PATCHED_ORIG_IDS.add(id(_safe_open))

    # Patch modules that already did `from safetensors import safe_open`
    for mod_name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        if not (
            mod_name == "safetensors"
            or mod_name.startswith("safetensors.")
            or mod_name.startswith("transformers")
            or mod_name.startswith("diffusers")
            or mod_name.startswith("mmgp")
        ):
            continue
        try:
            current = getattr(mod, "safe_open", None)
            if current is orig or current is None:
                if current is orig:
                    setattr(mod, "safe_open", _safe_open)
        except Exception:
            pass
    return True
