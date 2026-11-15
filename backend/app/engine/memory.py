"""Memory / VRAM placement profiles — where model weights sit during Generate."""

from __future__ import annotations

from typing import Any

from ..storage import get_preset, list_presets, load_settings

# Canonical placement strategies (Wan2GP-style)
# - cpu: everything on system RAM (preview / no GPU)
# - sequential_cpu_offload: one layer at a time on GPU (lowest VRAM)
# - model_cpu_offload: whole modules move GPU↔RAM (balanced)
# - gpu: keep the full pipeline on VRAM (fastest, needs headroom)

PLACEMENT_LABELS = {
    "cpu": "System RAM only",
    "sequential_cpu_offload": "RAM ↔ VRAM (layer-by-layer)",
    "model_cpu_offload": "RAM ↔ VRAM (module offload)",
    "gpu": "GPU VRAM (resident)",
}


def memory_from_preset(preset: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize memory block from a compute preset."""
    preset = preset or {}
    gen = preset.get("generation") or {}
    mem = dict(preset.get("memory") or {})

    placement = mem.get("placement")
    if not placement:
        if float(preset.get("target_vram_gb") or 0) <= 0:
            placement = "cpu"
        elif gen.get("cpu_offload") and gen.get("attention_slicing"):
            # Low VRAM presets historically set both flags
            placement = "sequential_cpu_offload" if gen.get("sequential", True) else "model_cpu_offload"
        elif gen.get("cpu_offload"):
            placement = "model_cpu_offload"
        else:
            placement = "gpu"

    dtype = mem.get("dtype") or (
        "float32" if placement == "cpu" else "bfloat16"
    )
    attention = mem.get("attention_slicing")
    if attention is None:
        attention = bool(gen.get("attention_slicing", placement != "gpu"))
    vae_slicing = mem.get("vae_slicing")
    if vae_slicing is None:
        vae_slicing = placement != "gpu"
    vae_tiling = mem.get("vae_tiling")
    if vae_tiling is None:
        vae_tiling = placement in {"sequential_cpu_offload", "cpu"}
    te_cpu = mem.get("text_encoder_on_cpu")
    if te_cpu is None:
        te_cpu = placement != "gpu"

    return {
        "placement": placement,
        "placement_label": PLACEMENT_LABELS.get(placement, placement),
        "dtype": dtype,
        "attention_slicing": bool(attention),
        "vae_slicing": bool(vae_slicing),
        "vae_tiling": bool(vae_tiling),
        "text_encoder_on_cpu": bool(te_cpu),
        "cpu_offload": placement in {"sequential_cpu_offload", "model_cpu_offload", "cpu"},
        "blurb": mem.get("blurb")
        or {
            "cpu": "Models stay in system RAM — slow, for preview / no GPU.",
            "sequential_cpu_offload": "Lowest VRAM: layers stream from RAM onto the GPU one at a time.",
            "model_cpu_offload": "Balanced: modules live in RAM and hop to VRAM when needed.",
            "gpu": "Fastest: keep weights resident in VRAM (needs headroom).",
        }.get(placement, ""),
    }


def list_memory_profiles() -> list[dict[str, Any]]:
    """Expose compute presets as user-facing memory profiles."""
    out: list[dict[str, Any]] = []
    for p in list_presets():
        mem = memory_from_preset(p)
        out.append(
            {
                "id": p.get("id"),
                "label": p.get("label"),
                "target_vram_gb": p.get("target_vram_gb"),
                "notes": p.get("notes"),
                "memory": mem,
                "generation": {
                    "default_width": (p.get("generation") or {}).get("default_width"),
                    "default_height": (p.get("generation") or {}).get("default_height"),
                    "default_frames": (p.get("generation") or {}).get("default_frames"),
                    "fps": (p.get("generation") or {}).get("fps"),
                    "cpu_offload": mem["cpu_offload"],
                },
            }
        )
    # Sort low → high VRAM for the picker
    out.sort(key=lambda x: float(x.get("target_vram_gb") or 0))
    return out


def resolve_memory_for_job(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = load_settings()
    payload = payload or {}
    preset_id = payload.get("preset_id") or getattr(settings, "preset_id", None) or "amd-low-vram"
    preset = get_preset(str(preset_id))
    mem = memory_from_preset(preset)
    # Allow one-off override from Generate payload
    if payload.get("memory_placement"):
        mem["placement"] = str(payload["memory_placement"])
        mem["placement_label"] = PLACEMENT_LABELS.get(mem["placement"], mem["placement"])
        mem["cpu_offload"] = mem["placement"] in {
            "sequential_cpu_offload",
            "model_cpu_offload",
            "cpu",
        }
    if "cpu_offload" in payload and payload["cpu_offload"] is not None:
        # Legacy checkbox: force module offload on, or GPU when off
        if payload["cpu_offload"] and mem["placement"] == "gpu":
            mem["placement"] = "model_cpu_offload"
            mem["cpu_offload"] = True
            mem["placement_label"] = PLACEMENT_LABELS["model_cpu_offload"]
        elif not payload["cpu_offload"] and mem["placement"] != "cpu":
            mem["placement"] = "gpu"
            mem["cpu_offload"] = False
            mem["placement_label"] = PLACEMENT_LABELS["gpu"]
    # Auto-upgrade Low VRAM offload when the live GPU is large (R9700-class).
    # Sequential offload is the usual cause of "stuck at 20% for 40 minutes".
    try:
        from .device import detect_device

        vram = detect_device().get("vram_gb")
        if (
            isinstance(vram, (int, float))
            and float(vram) >= 20
            and mem.get("placement") in {"sequential_cpu_offload", "model_cpu_offload"}
            and not payload.get("memory_placement")
        ):
            mem["placement"] = "gpu"
            mem["placement_label"] = PLACEMENT_LABELS["gpu"]
            mem["cpu_offload"] = False
            mem["attention_slicing"] = False
            # Keep VAE slicing/tiling — full VAE decode is a common AMD hang after last step
            mem["vae_slicing"] = True
            mem["vae_tiling"] = True
            mem["text_encoder_on_cpu"] = False
            mem["auto_upgraded_from_offload"] = True
    except Exception:
        pass
    mem["preset_id"] = preset.get("id") or preset_id
    return mem


def apply_memory_to_pipeline(pipe: Any, device: str, mem: dict[str, Any]) -> str:
    """Place a Diffusers pipeline according to the memory profile. Returns placement used.

    Prefers StudioNels-native mmgp (same library Wan2GP uses) when installed —
    no external Wan2GP link required.
    """
    placement = mem.get("placement") or "model_cpu_offload"
    used = placement

    # Detect VRAM for mmgp profile selection
    vram_gb = None
    try:
        from .device import detect_device

        vram_gb = detect_device().get("vram_gb")
    except Exception:
        pass

    if not str(device).startswith("cuda") or placement == "cpu":
        try:
            pipe.to("cpu")
        except Exception:
            pass
        used = "cpu"
    else:
        # Native mmgp path (fast) — load on CPU then profile
        mmgp_info = None
        try:
            from .mmgp_accel import apply_mmgp_to_pipeline, apply_runtime_env

            apply_runtime_env()
            mmgp_info = apply_mmgp_to_pipeline(
                pipe, device=device, mem=mem, vram_gb=vram_gb if isinstance(vram_gb, (int, float)) else None
            )
        except Exception:
            mmgp_info = {"used": False}

        if mmgp_info and mmgp_info.get("used"):
            used = f"mmgp:{mmgp_info.get('profile') or 'on'}"
            try:
                pipe._studionels_placement = used  # type: ignore[attr-defined]
            except Exception:
                pass
        elif placement == "sequential_cpu_offload":
            try:
                pipe.enable_sequential_cpu_offload()
                used = "sequential_cpu_offload"
            except Exception:
                try:
                    pipe.enable_model_cpu_offload()
                    used = "model_cpu_offload"
                except Exception:
                    pipe.to(device)
                    used = "gpu"
        elif placement == "model_cpu_offload":
            try:
                pipe.enable_model_cpu_offload()
                used = "model_cpu_offload"
            except Exception:
                pipe.to(device)
                used = "gpu"
        else:
            pipe.to(device)
            used = "gpu"

    # Skip attention slicing when mmgp is managing the pipe (it fights SDPA speed)
    if mem.get("attention_slicing") and not str(used).startswith("mmgp"):
        try:
            pipe.enable_attention_slicing()
        except Exception:
            pass
    if mem.get("vae_slicing"):
        try:
            if hasattr(pipe, "vae") and pipe.vae is not None:
                pipe.vae.enable_slicing()
            elif hasattr(pipe, "enable_vae_slicing"):
                pipe.enable_vae_slicing()
        except Exception:
            pass
    if mem.get("vae_tiling"):
        try:
            if hasattr(pipe, "vae") and pipe.vae is not None and hasattr(pipe.vae, "enable_tiling"):
                pipe.vae.enable_tiling()
            elif hasattr(pipe, "enable_vae_tiling"):
                pipe.enable_vae_tiling()
        except Exception:
            pass
    return used
