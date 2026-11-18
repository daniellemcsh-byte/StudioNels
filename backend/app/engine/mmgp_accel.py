"""StudioNels native speed path — mmgp inside our Diffusers engine.

Wan2GP linking is optional. This module brings the same memory/offload
library (mmgp) into StudioNels so Generate is fast without an external app.
"""

from __future__ import annotations

import os
from typing import Any


def apply_runtime_env() -> None:
    """ROCm / BLAS defaults Wan2GP also sets — safe no-ops elsewhere."""
    os.environ.setdefault("TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(min(8, os.cpu_count() or 8)))
    os.environ.setdefault("TRITON_DEFAULT_FP_FUSION", "1")
    # Avoid accidental torch.compile hangs on first AMD kernel
    os.environ.setdefault("TORCHINDUCTOR_DISABLE", "1")
    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
    # Faster MIOpen autotune path — reduces post-denoise VAE stalls on ROCm
    os.environ.setdefault("MIOPEN_FIND_MODE", "FAST")
    tune_amd_inference()
    # transformers↔safetensors(+mmgp) version skew on Windows ROCm installs
    try:
        from .safetensors_compat import apply_safetensors_backend_compat

        apply_safetensors_backend_compat()
    except Exception:
        pass


def tune_amd_inference() -> None:
    """Stable matmul path for Windows ROCm.

    Flash and memory-efficient SDPA segfault mid-step on Radeon (Wan dies around
    step 6 with no Python traceback). Math SDPA is the fast path that stays up.
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return
        hip = bool(getattr(getattr(torch, "version", None), "hip", None))
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        # benchmark=True runs a GPU search the first time a conv shows up and
        # can sit at 100% while the app is just open. Off on AMD.
        torch.backends.cudnn.benchmark = not hip
        try:
            torch.set_float32_matmul_precision("high")
        except Exception:
            pass
        # Wan2GP on AMD uses SDPA. AOTriton (set above) is the fast kernel.
        # Forcing the math kernel is the slow fallback Wan2GP turns off.
        try:
            torch.backends.cuda.enable_flash_sdp(True)
            torch.backends.cuda.enable_mem_efficient_sdp(True)
            torch.backends.cuda.enable_math_sdp(True)
        except Exception:
            pass
    except Exception:
        pass


def mmgp_available() -> bool:
    try:
        from .safetensors_compat import apply_safetensors_backend_compat

        apply_safetensors_backend_compat()
    except Exception:
        pass
    try:
        import mmgp  # noqa: F401

        # mmgp may replace safetensors.safe_open — re-apply compat after import
        try:
            from .safetensors_compat import apply_safetensors_backend_compat

            apply_safetensors_backend_compat(force=True)
        except Exception:
            pass
        return True
    except Exception:
        return False


_MMGP_STATUS: dict[str, Any] = {"at": 0.0, "info": None}


def mmgp_status() -> dict[str, Any]:
    import time

    now = time.time()
    cached = _MMGP_STATUS.get("info")
    if isinstance(cached, dict) and now - float(_MMGP_STATUS.get("at") or 0) < 30:
        return dict(cached)
    ok = mmgp_available()
    info = {
        "available": ok,
        "package": "mmgp",
        "blurb": (
            "StudioNels native mmgp acceleration is active."
            if ok
            else "Install engine extras (pip install -r requirements-engine.txt) for native mmgp speed."
        ),
    }
    _MMGP_STATUS["info"] = info
    _MMGP_STATUS["at"] = now
    return dict(info)


def wan2gp_profile_number(vram_gb: float | None) -> int:
    """Same profile map Wan2GP is launched with in wan2gp_runtime.

    1 HighRAM_HighVRAM — 24 GB and up, the fast path on an R9700.
    3 LowRAM_HighVRAM — 16 GB.
    2 HighRAM_LowVRAM — 10 GB.
    4 LowRAM_LowVRAM — smaller cards.
    """
    if vram_gb is None:
        return 3
    if float(vram_gb) >= 24:
        return 1
    if float(vram_gb) >= 16:
        return 3
    if float(vram_gb) >= 10:
        return 2
    return 4


def _profile_enum(vram_gb: float | None, placement: str, mem: dict[str, Any] | None = None):
    from mmgp import profile_type

    number = wan2gp_profile_number(vram_gb if isinstance(vram_gb, (int, float)) else None)
    if placement == "sequential_cpu_offload":
        number = 4
    return {
        1: profile_type.HighRAM_HighVRAM,
        2: profile_type.HighRAM_LowVRAM,
        3: profile_type.LowRAM_HighVRAM,
        4: profile_type.LowRAM_LowVRAM,
    }[number]


def apply_mmgp_to_pipeline(
    pipe: Any,
    *,
    device: str,
    mem: dict[str, Any] | None = None,
    vram_gb: float | None = None,
) -> dict[str, Any]:
    """Load weights via mmgp.offload.profile. Pipe should be on CPU first.

    Returns info dict: {used: bool, profile: str, detail: str}
    """
    mem = mem or {}
    placement = str(mem.get("placement") or "gpu")
    if not str(device).startswith("cuda"):
        return {"used": False, "profile": None, "detail": "CPU-only — mmgp skipped"}
    if not mmgp_available():
        return {"used": False, "profile": None, "detail": "mmgp not installed"}

    try:
        from mmgp import offload
    except Exception as exc:  # noqa: BLE001
        return {"used": False, "profile": None, "detail": f"mmgp import failed: {exc}"}

    # Ensure CPU residency before profiling (mmgp requirement)
    try:
        pipe.to("cpu")
    except Exception:
        pass

    gb = float(vram_gb) if isinstance(vram_gb, (int, float)) else None
    number = wan2gp_profile_number(gb)
    if placement == "sequential_cpu_offload":
        number = 4
    profile = _profile_enum(gb, placement, mem)
    profile_name = getattr(profile, "name", str(profile))

    # Wan2GP init_pipe + offload.profile: fp16 weights, no compile, no quantize
    # at profile time, text encoder kept in the same profile, profiles 1 and 3
    # preload whatever fits on the card.
    try:
        import torch

        weight_dtype = torch.float16
    except Exception:
        weight_dtype = None
    kwargs: dict[str, Any] = {
        "quantizeTransformer": False,
        "compile": False,
        "verboseLevel": 1,
        "budgets": {
            "transformer": 100,
            "text_encoder": 100,
            "text_encoder_2": 100,
            "*": 3000,
        },
        "smartPinning": 0,
    }
    if weight_dtype is not None:
        kwargs["convertWeightsFloatTo"] = weight_dtype
    if number in (1, 3):
        kwargs["autoPreload"] = True

    import re

    dropped: list[str] = []
    while True:
        try:
            offload.profile(pipe, profile, **kwargs)
            break
        except TypeError as exc:
            match = re.search(r"unexpected keyword argument '([^']+)'", str(exc))
            key = match.group(1) if match else ""
            if not key or key not in kwargs:
                try:
                    offload.profile(pipe, profile)
                    kwargs = {}
                    break
                except Exception as inner:  # noqa: BLE001
                    return {"used": False, "profile": profile_name, "detail": f"mmgp failed: {inner}"}
            kwargs.pop(key, None)
            dropped.append(key)
        except Exception as exc:  # noqa: BLE001
            return {"used": False, "profile": profile_name, "detail": f"mmgp failed: {exc}"}

    pipe._studionels_mmgp = True  # type: ignore[attr-defined]
    pipe._studionels_mmgp_profile = profile_name  # type: ignore[attr-defined]
    detail = f"mmgp profile {number} {profile_name}"
    if dropped:
        detail += f" (older mmgp skipped {', '.join(dropped)})"
    return {
        "used": True,
        "profile": profile_name,
        "profile_no": number,
        "detail": detail,
        "quantize_transformer": False,
    }
