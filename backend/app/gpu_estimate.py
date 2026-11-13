from __future__ import annotations

from typing import Any

from .engine.catalog import get_model, list_models_for_mode
from .engine.device import detect_device
from .storage import get_preset, load_settings

# Rough local heuristics — honest ranges, not marketing.
# VRAM figures are peak working set estimates for Diffusers-style loads with offload.


def estimate_job(payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    preset = get_preset(payload.get("preset_id") or settings.preset_id)
    device = detect_device()
    mode = payload.get("mode") or "t2v"
    model_id = payload.get("model_id")
    model = get_model(model_id) if model_id else None
    if not model:
        candidates = list_models_for_mode(mode)
        target = float(preset.get("target_vram_gb") or 8)
        fit = [m for m in candidates if m["min_vram_gb"] <= target] or candidates
        model = fit[0] if fit else None

    width = int(payload.get("width") or preset.get("generation", {}).get("default_width") or 768)
    height = int(payload.get("height") or preset.get("generation", {}).get("default_height") or 432)
    frames = int(payload.get("frames") or preset.get("generation", {}).get("default_frames") or 49)
    duration = payload.get("duration_sec")
    if duration and mode in ("t2v", "i2v", "ref2v", "t2a"):
        fps = int(payload.get("fps") or 16)
        frames = max(frames, int(float(duration) * fps))
    quality = payload.get("quality") or "balanced"
    q_scale = {"draft": 0.6, "balanced": 1.0, "high": 1.4, "max": 1.8}.get(quality, 1.0)
    steps = int(payload.get("steps") or (model or {}).get("default_steps") or 20)
    steps = max(1, int(steps * q_scale))
    cpu_offload = payload.get("cpu_offload")
    if cpu_offload is None:
        cpu_offload = preset.get("generation", {}).get("cpu_offload", True)

    pixels = width * height
    pixel_scale = pixels / (768 * 432)
    min_vram = float((model or {}).get("min_vram_gb") or 6)
    # Offload reduces peak VRAM but slows ETA
    vram_need = min_vram * (0.72 if cpu_offload else 1.0)
    if mode in ("t2v", "i2v", "ref2v", "upsample_video"):
        vram_need *= 1.0 + min(1.2, (frames / 49) * 0.35 * pixel_scale)
    elif mode in ("t2i", "ref2i", "upsample_image"):
        vram_need *= max(0.85, pixel_scale**0.5)
    elif mode == "t2a":
        vram_need = max(4.0, min_vram * 0.9)

    available = device.get("vram_gb")
    gpu_ready = bool(device.get("ready_for_inference"))
    torch_ok = bool(device.get("torch_available"))
    diffusers_ok = bool(device.get("diffusers_available"))

    fit = "unknown"
    warnings: list[str] = []
    if not torch_ok:
        fit = "preview_only"
        warnings.append("PyTorch not installed — job will use preview engine.")
    elif not gpu_ready:
        fit = "cpu_slow"
        warnings.append("No GPU visible — expect very slow or preview output.")
    elif available is None:
        fit = "unknown"
    elif vram_need <= available * 0.85:
        fit = "comfortable"
    elif vram_need <= available:
        fit = "tight"
        warnings.append("Close to VRAM limit — keep CPU offload on and shorten clips.")
    else:
        fit = "wont_fit"
        warnings.append(
            f"Needs ~{vram_need:.1f} GB; GPU reports {available} GB. "
            "Switch model, lower resolution, or enable the low-VRAM preset."
        )

    # ETA seconds — rough
    kind = (model or {}).get("kind") or "video"
    if fit == "preview_only":
        eta = 2.0 + frames * 0.05
    elif kind == "audio":
        eta = 8 + steps * 0.35 * (float(duration or 8) / 8)
    elif kind == "image" or mode in ("t2i", "ref2i", "upsample_image"):
        eta = 4 + steps * 0.45 * pixel_scale
    else:
        eta = 12 + steps * 0.55 * pixel_scale * (frames / 24)
    if cpu_offload:
        eta *= 1.55
    if fit == "cpu_slow":
        eta *= 8
    if fit == "tight":
        eta *= 1.25

    suggested_preset = preset.get("id") or settings.preset_id
    if available is not None:
        if available >= 24:
            suggested_preset = "amd-r9700"
        elif available >= 8:
            suggested_preset = "amd-low-vram"
        else:
            suggested_preset = "cpu-fallback"
    elif fit in ("preview_only", "cpu_slow"):
        suggested_preset = "cpu-fallback"

    advice = []
    if fit == "wont_fit":
        advice.append("Try Wan 1.3B / SDXL Turbo, 768×432, draft quality, fewer frames.")
    elif fit == "tight":
        advice.append("Use draft/balanced quality and one job at a time.")
    elif fit == "comfortable":
        advice.append("Headroom looks good — you can bump quality or length a bit.")
    if suggested_preset != (preset.get("id") or settings.preset_id):
        advice.append(f"Suggested preset: {suggested_preset}")

    return {
        "ok": fit != "wont_fit",
        "fit": fit,
        "mode": mode,
        "model_id": (model or {}).get("id"),
        "model_label": (model or {}).get("label"),
        "device_name": device.get("device_name") or "CPU",
        "vram_available_gb": available,
        "vram_estimate_gb": round(vram_need, 1),
        "eta_sec": int(round(eta)),
        "eta_label": _fmt_eta(eta),
        "steps": steps,
        "width": width,
        "height": height,
        "frames": frames,
        "quality": quality,
        "cpu_offload": bool(cpu_offload),
        "suggested_preset": suggested_preset,
        "warnings": warnings,
        "advice": advice,
        "can_queue": fit != "wont_fit",
        "will_preview": fit in ("preview_only",) or not (gpu_ready and diffusers_ok),
    }


def _fmt_eta(seconds: float) -> str:
    s = max(1, int(round(seconds)))
    if s < 60:
        return f"~{s}s"
    m, rem = divmod(s, 60)
    if m < 60:
        return f"~{m}m {rem}s" if rem else f"~{m}m"
    h, m = divmod(m, 60)
    return f"~{h}h {m}m"
