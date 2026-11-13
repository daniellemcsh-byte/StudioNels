from __future__ import annotations

from typing import Any


def detect_device() -> dict[str, Any]:
    """Detect torch + AMD ROCm / CUDA / CPU for in-app inference."""
    info: dict[str, Any] = {
        "torch_available": False,
        "torch_version": None,
        "backend": "none",
        "device": "cpu",
        "device_name": "CPU",
        "vram_gb": None,
        "rocm": False,
        "cuda": False,
        "diffusers_available": False,
        "huggingface_hub_available": False,
        "ready_for_inference": False,
        "notes": [],
    }
    try:
        import torch

        info["torch_available"] = True
        info["torch_version"] = getattr(torch, "__version__", "?")
        if hasattr(torch.version, "hip") and torch.version.hip:
            info["rocm"] = True
            info["notes"].append(f"ROCm/HIP {torch.version.hip}")
        if torch.cuda.is_available():
            info["cuda"] = True
            # On ROCm, torch.cuda is the AMD device API.
            name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram = getattr(props, "total_memory", 0) / (1024**3)
            info["device"] = "cuda:0"
            info["device_name"] = name
            info["vram_gb"] = round(vram, 1)
            info["backend"] = "rocm" if info["rocm"] else "cuda"
            info["ready_for_inference"] = True
        else:
            info["backend"] = "cpu"
            info["device"] = "cpu"
            info["device_name"] = "CPU"
            info["notes"].append("No GPU visible to torch — install ROCm PyTorch for AMD.")
    except Exception as exc:  # noqa: BLE001
        info["notes"].append(f"PyTorch not installed ({exc.__class__.__name__}).")

    try:
        import diffusers  # noqa: F401

        info["diffusers_available"] = True
    except Exception:
        info["notes"].append("diffusers not installed yet.")

    try:
        import huggingface_hub  # noqa: F401

        info["huggingface_hub_available"] = True
    except Exception:
        info["notes"].append("huggingface_hub not installed (needed to download models).")

    if info["ready_for_inference"] and info["diffusers_available"]:
        info["notes"].append("Engine can load Diffusers pipelines in-process.")
    elif info["torch_available"] and not info["diffusers_available"]:
        info["notes"].append("Install engine extras: pip install -r requirements-engine.txt")

    return info
