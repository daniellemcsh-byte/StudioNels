"""Compat for transformers + safetensors (+ mmgp) version skew.

Newer transformers call safe_open(..., backend=...). Older safetensors and some
mmgp redirects reject that kwarg with:
  TypeError: safe_open() got an unexpected keyword argument 'backend'
"""

from __future__ import annotations

import functools
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

    if getattr(orig, "_studionels_safe_open", False):
        _repoint_safe_open(orig)
        return True

    # Already wrapped this exact function object
    if not force and id(orig) in _PATCHED_ORIG_IDS:
        return True

    from .safetensors_nommap import open_safetensors

    @functools.wraps(orig)
    def _safe_open(*args: Any, **kwargs: Any):
        return open_safetensors(orig, args, kwargs)

    _safe_open._studionels_safe_open = True  # type: ignore[attr-defined]

    try:
        st.safe_open = _safe_open  # type: ignore[attr-defined]
    except Exception:
        return False

    _PATCHED_ORIG_IDS.add(id(orig))
    _PATCHED_ORIG_IDS.add(id(_safe_open))
    _repoint_safe_open(_safe_open)
    return True


def _repoint_safe_open(wrapper) -> None:
    """Point every already-imported safe_open at the wrapper.

    diffusers, transformers, and mmgp often did `from safetensors import safe_open`
    before this patch runs. Those bindings still map the whole shard and raise
    WinError 1455 on Windows.
    """
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
        except Exception:
            continue
        if current is None or getattr(current, "_studionels_safe_open", False):
            continue
        try:
            setattr(mod, "safe_open", wrapper)
        except Exception:
            pass
