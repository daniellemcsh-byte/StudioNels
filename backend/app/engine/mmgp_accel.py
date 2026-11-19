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


# ---------------------------------------------------------------------------
# Hardware-aware mmgp plan.
#
# Before: every card got Wan2GP profile 4 (the 12 GB-card setup) with a 100 MB
# GPU budget, and the transformer + text encoder were re-quantized to int8 on
# every load. On a 32 GB R9700 that meant (a) minutes of CPU quantization even
# for models that fit, and (b) streaming weights from RAM on every single step.
#
# Now: measure the model and the machine, then pick the fastest profile that
# fits. A model that ran out of GPU memory once is remembered and drops back to
# the old profile-4 "safe" path automatically. STUDIONELS_MMGP_PROFILE=1..5
# forces a profile by hand.
# ---------------------------------------------------------------------------

_GB = 1024**3
_SAFE_FILE = "mmgp_safe_models.json"


def system_ram_gb() -> float | None:
    try:
        import psutil

        return psutil.virtual_memory().total / _GB
    except Exception:
        pass
    try:  # Windows fallback without psutil
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("t", ctypes.c_ulonglong),
                        ("a", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                        ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]

        st = _MS()
        st.l = ctypes.sizeof(_MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
        return st.t / _GB
    except Exception:
        return None


def _safe_path():
    from ..paths import CACHE_DIR

    return CACHE_DIR / _SAFE_FILE


def safe_models() -> set[str]:
    import json

    try:
        p = _safe_path()
        return set(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else set()
    except Exception:
        return set()


def mark_model_safe(model_id: str | None) -> None:
    """After a GPU out-of-memory error, run this model on the low-VRAM path next time."""
    import json

    if not model_id:
        return
    try:
        ids = safe_models()
        ids.add(str(model_id))
        p = _safe_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sorted(ids)), encoding="utf-8")
    except Exception:
        pass


def clear_safe_models() -> None:
    try:
        _safe_path().unlink(missing_ok=True)
    except Exception:
        pass


def _module_gb(mod: Any) -> float:
    try:
        total = 0
        for t in list(mod.parameters()) + list(mod.buffers()):
            total += t.numel() * t.element_size()
        return total / _GB
    except Exception:
        return 0.0


def plan_mmgp(
    sizes_gb: dict[str, float],
    vram_gb: float | None,
    ram_gb: float | None,
    placement: str = "gpu",
    safe: bool = False,
    prequantized: set[str] | None = None,
) -> dict[str, Any]:
    """Pick the mmgp profile + overrides for these component sizes (16-bit GB).

    Pure function (no torch) so it is easy to test.
    """
    forced = os.environ.get("STUDIONELS_MMGP_PROFILE", "").strip()
    pre = set(prequantized or ())
    # Already int8 from the RAM-safe loader: count them at half size, never re-quantize.
    sizes_gb = {n: (g / 2 if n in pre else g) for n, g in sizes_gb.items()}
    text_names = [n for n in sizes_gb if n.startswith("text_encoder")]
    t_gb = float(sizes_gb.get("transformer") or sizes_gb.get("unet") or 0.0)

    if safe or placement == "sequential_cpu_offload" or not vram_gb:
        why = (
            "safe mode (this model ran out of GPU memory before)" if safe
            else "low-VRAM preset" if placement == "sequential_cpu_offload"
            else "GPU size unknown"
        )
        # Exactly the previous behaviour: proven to run, slowest.
        return {
            "profile_no": 4,
            "quantize_transformer": not ({"transformer", "unet"} & pre),
            "quantize_extra": [n for n in text_names if n not in pre],
            "budgets": {"transformer": 100, "text_encoder": 100, "text_encoder_2": 100, "*": 3000},
            "reason": why,
        }

    usable = max(4.0, float(vram_gb) - 6.0)  # room for activations + VAE decode
    quant_t = t_gb > usable * 0.85 and not ({"transformer", "unet"} & pre)
    quant_text = [n for n in text_names if n not in pre and float(sizes_gb.get(n) or 0) > usable * 0.7]
    after = {
        n: (g / 2 if (n in ("transformer", "unet") and quant_t) or n in quant_text else g)
        for n, g in sizes_gb.items()
    }
    largest = max(after.values()) if after else 0.0
    total = sum(after.values())
    fits = largest <= usable
    # Profile 1/2 pin every model in page-locked RAM. Leave Windows + the app
    # ~20 GB, so a 64 GB PC pins everything for Wan 14B but only the
    # transformer (profile 3) for LTX 22B + its 12B text encoder.
    high_ram = bool(ram_gb) and float(ram_gb) >= total * 1.3 + 20

    if fits:
        profile_no = 1 if high_ram else 3
        budgets = None
    else:
        profile_no = 2 if high_ram else 4
        # Keep as much of the model resident as fits (old code: 100 MB).
        budgets = {"transformer": int((usable - 2) * 1024), "*": 3000}

    if forced in {"1", "2", "3", "4", "5"}:
        profile_no = int(forced)
        budgets = None if profile_no in (1, 3) else budgets or {"transformer": 1200, "*": 3000}

    return {
        "profile_no": profile_no,
        "quantize_transformer": quant_t,
        "quantize_extra": quant_text,
        "budgets": budgets,
        "reason": (
            f"{'fits' if fits else 'too big for'} {usable:.0f} GB usable VRAM"
            f" · RAM {ram_gb:.0f} GB" if ram_gb else f"{'fits' if fits else 'too big for'} {usable:.0f} GB usable VRAM"
        ) + (" · int8 transformer" if quant_t else "") + (f" · int8 {', '.join(quant_text)}" if quant_text else ""),
    }


def wan2gp_profile_number(vram_gb: float | None) -> int:
    """Profile for the external Wan2GP runtime (Wan2GP's own guidance):
    1 = 64 GB RAM + 24 GB VRAM, 3 = 32 GB RAM + 24 GB VRAM, 4 = 12 GB cards.
    """
    forced = os.environ.get("STUDIONELS_MMGP_PROFILE", "").strip()
    if forced in {"1", "2", "3", "4", "5"}:
        return int(forced)
    if not isinstance(vram_gb, (int, float)) or vram_gb < 20:
        return 4
    ram = system_ram_gb() or 0
    return 1 if ram >= 64 else 3


def _profile_enum(number: int):
    from mmgp import profile_type

    return {
        1: profile_type.HighRAM_HighVRAM,
        2: profile_type.HighRAM_LowVRAM,
        3: profile_type.LowRAM_HighVRAM,
        4: profile_type.LowRAM_LowVRAM,
        5: profile_type.VerylowRAM_LowVRAM,
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

    components = getattr(pipe, "components", {}) or {}
    sizes = {
        name: _module_gb(mod)
        for name, mod in components.items()
        if hasattr(mod, "parameters")
    }
    gb = float(vram_gb) if isinstance(vram_gb, (int, float)) else None
    safe = mem.get("mmgp_mode") == "safe"
    pre = set(getattr(pipe, "_studionels_prequantized", None) or ())
    plan = plan_mmgp(sizes, gb, system_ram_gb(), placement, safe=safe, prequantized=pre)
    number = int(plan["profile_no"])
    profile = _profile_enum(number)
    profile_name = getattr(profile, "name", str(profile))

    try:
        import torch

        weight_dtype = torch.float16
    except Exception:
        weight_dtype = None
    kwargs: dict[str, Any] = {
        "quantizeTransformer": bool(plan["quantize_transformer"]),
        "compile": False,
        "verboseLevel": 1,
        # Profile 3/4 auto-quantize any text encoder named t5/llama/llm; pass the
        # plan's list explicitly (empty = keep the encoder in 16-bit, no slow
        # re-quantization at load).
        "extraModelsToQuantize": list(plan["quantize_extra"]),
    }
    if plan["budgets"] is not None:
        kwargs["budgets"] = plan["budgets"]
    if weight_dtype is not None:
        kwargs["convertWeightsFloatTo"] = weight_dtype

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
    detail = f"mmgp profile {number} {profile_name} · {plan['reason']}"
    if dropped:
        detail += f" (older mmgp skipped {', '.join(dropped)})"
    try:
        print(f"[studionels] {detail}", flush=True)
    except Exception:
        pass
    return {
        "used": True,
        "profile": profile_name,
        "profile_no": number,
        "detail": detail,
        "quantize_transformer": bool(plan["quantize_transformer"]),
    }
