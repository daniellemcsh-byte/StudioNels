from __future__ import annotations

from typing import Any

from .engine.catalog import get_model, list_models_for_mode
from .engine.device import detect_device
from .storage import get_preset, load_settings

# Rough local heuristics — honest ranges, not marketing.
# Peak VRAM for Diffusers+mmgp is dominated by model weights, not wall-clock seconds.
# Old formula scaled min_vram with frames so hard that a 5s draft on R9700 looked
# like it needed 32.6 GB and blocked Generate.


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
    fps = int(payload.get("fps") or preset.get("generation", {}).get("fps") or 16)
    if duration and mode in ("t2v", "i2v", "ref2v", "t2a"):
        frames = max(frames, int(float(duration) * fps))
    quality = payload.get("quality") or "balanced"
    q_scale = {"draft": 0.6, "balanced": 1.0, "high": 1.4, "max": 1.8}.get(quality, 1.0)
    steps = int(payload.get("steps") or (model or {}).get("default_steps") or 20)
    steps = max(1, int(steps * q_scale))
    cpu_offload = payload.get("cpu_offload")
    if cpu_offload is None:
        cpu_offload = preset.get("generation", {}).get("cpu_offload", True)
    placement = str(
        payload.get("memory_placement")
        or (preset.get("memory") or {}).get("placement")
        or ("model_cpu_offload" if cpu_offload else "gpu")
    )

    mmgp_on = False
    try:
        from .engine.mmgp_accel import mmgp_available

        mmgp_on = mmgp_available()
    except Exception:
        mmgp_on = False

    pixels = width * height
    pixel_scale = pixels / (768 * 432)
    min_vram = float((model or {}).get("min_vram_gb") or 6)

    # Weight-heavy base. Offload / mmgp cuts resident peak; frame count barely moves it
    # for latent video (a 5s clip is not 2.5× the VRAM of a 2s clip).
    if mmgp_on:
        vram_need = min_vram * (0.55 if placement != "gpu" else 0.78)
    elif cpu_offload or placement in {"sequential_cpu_offload", "model_cpu_offload"}:
        vram_need = min_vram * 0.65
    else:
        vram_need = min_vram * 0.92

    if mode in ("t2v", "i2v", "ref2v", "upsample_video"):
        # Soft bump for longer clips / larger frames — capped, never doubles the job
        frame_term = min(0.35, max(0.0, (frames - 49) / 200.0))
        res_term = min(0.25, max(0.0, pixel_scale - 1.0) * 0.4)
        vram_need *= 1.0 + frame_term + res_term
    elif mode in ("t2i", "ref2i", "upsample_image"):
        vram_need *= max(0.85, pixel_scale**0.5)
    elif mode == "t2a":
        vram_need = max(3.5, min_vram * 0.55)

    # Never claim a draft 768×448 short clip needs more than ~card size on big GPUs
    available = device.get("vram_gb")
    if (
        isinstance(available, (int, float))
        and float(available) >= 24
        and width * height <= 768 * 512
        and frames <= 130
    ):
        vram_need = min(vram_need, float(available) * 0.82)

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
    elif vram_need <= available * 1.05:
        # Within ~5% — warn, but still allow queue (heuristic, not a hard OOM)
        fit = "tight"
        warnings.append(
            f"Close to VRAM limit (~{vram_need:.1f} GB of {available} GB). "
            "Keep one job at a time; mmgp/offload will help."
        )
    else:
        fit = "wont_fit"
        warnings.append(
            f"Needs ~{vram_need:.1f} GB; GPU reports {available} GB. "
            "Switch model, lower resolution, or enable the low-VRAM preset."
        )

    # ETA seconds — rough (mmgp is faster than plain accelerate offload)
    kind = (model or {}).get("kind") or "video"
    if fit == "preview_only":
        eta = 2.0 + frames * 0.05
    elif kind == "audio":
        eta = 8 + steps * 0.35 * (float(duration or 8) / 8)
    elif kind == "image" or mode in ("t2i", "ref2i", "upsample_image"):
        eta = 4 + steps * 0.45 * pixel_scale
    else:
        eta = 12 + steps * 0.55 * pixel_scale * (frames / 24)
    if mmgp_on:
        eta *= 0.7
    elif cpu_offload:
        eta *= 1.55
    if fit == "cpu_slow":
        eta *= 8
    if fit == "tight":
        eta *= 1.15

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
    coach = {
        "comfortable": f"GO — {device.get('device_name') or 'GPU'} can handle this (~{_fmt_eta(eta)}).",
        "tight": f"TIGHT — close to VRAM limit. One job at a time; ETA ~{_fmt_eta(eta)}.",
        "wont_fit": "STOP — this will not fit. Drop to 16:9 draft / 9:16 draft / 1:1 draft, or AMD Low VRAM preset.",
        "cpu_slow": "CPU ONLY — expect a long wait or preview frames. Install ROCm PyTorch for AMD.",
        "preview_only": "PREVIEW MODE — PyTorch/Diffusers missing. Jobs draw placeholders until the engine is installed.",
        "unknown": "Checking your GPU… pick a draft size if unsure.",
    }
    coach_headline = coach.get(fit, coach["unknown"])
    if fit == "wont_fit":
        advice.append("Try Wan 1.3B / SDXL Turbo, 768×432 landscape draft, or 432×768 portrait draft.")
    elif fit == "tight":
        advice.append("Draft size is fine for a short clip — Generate is still allowed.")
    elif fit == "comfortable":
        advice.append("Headroom looks good — you can bump quality or length a bit.")
    if suggested_preset != (preset.get("id") or settings.preset_id):
        advice.append(f"Suggested preset: {suggested_preset}")
    if mmgp_on:
        advice.append("StudioNels mmgp is active — peak VRAM is lower than raw model size.")

    # Allow queue unless clearly impossible (not when barely over a soft estimate)
    can_queue = fit not in ("wont_fit",) or (
        isinstance(available, (int, float)) and float(available) >= 24 and frames <= 130
    )
    if fit == "wont_fit" and can_queue:
        fit = "tight"
        coach_headline = coach["tight"]
        warnings = [
            w.replace("Needs", "Estimate was high — treating as tight. Needs")
            if w.startswith("Needs")
            else w
            for w in warnings
        ] or [
            "Estimate was conservative for a short draft on a 24GB+ card — Generate allowed."
        ]

    return {
        "ok": can_queue,
        "fit": fit,
        "coach_headline": coach_headline,
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
        "mmgp": mmgp_on,
        "suggested_preset": suggested_preset,
        "warnings": warnings,
        "advice": advice,
        "can_queue": can_queue,
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
