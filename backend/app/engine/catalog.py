from __future__ import annotations

from typing import Any, Literal

GenMode = Literal["t2i", "t2v", "i2v", "ref2i", "ref2v", "t2a", "upsample_image", "upsample_video"]

GENERATION_MODES: list[dict[str, Any]] = [
    {
        "id": "t2i",
        "label": "Text → Image",
        "needs_image": False,
        "needs_reference": False,
        "output": "image",
        "blurb": "Prompt only. Best for character/scene stills.",
        "supports_lora": True,
    },
    {
        "id": "t2v",
        "label": "Text → Video",
        "needs_image": False,
        "needs_reference": False,
        "output": "video",
        "blurb": "Prompt only. Draft shots from words.",
        "supports_lora": True,
    },
    {
        "id": "i2v",
        "label": "Image → Video",
        "needs_image": True,
        "needs_reference": False,
        "needs_video": False,
        "output": "video",
        "blurb": "Animate a still / photo into a short clip.",
        "supports_lora": True,
    },
    {
        "id": "ref2i",
        "label": "Reference → Image",
        "needs_image": False,
        "needs_reference": True,
        "needs_video": False,
        "output": "image",
        "blurb": "Keep identity/look from a reference photo.",
        "supports_lora": True,
    },
    {
        "id": "ref2v",
        "label": "Reference → Video",
        "needs_image": False,
        "needs_reference": True,
        "needs_video": False,
        "accepts_ref_video": True,
        "accepts_start_image": True,
        "output": "video",
        "blurb": "Consistent video from a reference photo (optional start frame / ref clip).",
        "supports_lora": True,
    },
    {
        "id": "t2a",
        "label": "Text → Audio",
        "needs_image": False,
        "needs_reference": False,
        "output": "audio",
        "blurb": "Music, ambience, or SFX from a text prompt.",
        "supports_lora": False,
    },
    {
        "id": "upsample_image",
        "label": "Upsample Image",
        "needs_image": True,
        "needs_reference": False,
        "output": "image",
        "blurb": "Enlarge / sharpen an existing still.",
        "supports_lora": False,
    },
    {
        "id": "upsample_video",
        "label": "Upsample Video",
        "needs_image": False,
        "needs_reference": False,
        "needs_video": True,
        "output": "video",
        "blurb": "Upscale a clip and optionally boost frame rate.",
        "supports_lora": False,
    },
]

def _frame_size_presets() -> list[dict]:
    try:
        from ..frame_sizes import size_presets_for_engine

        return size_presets_for_engine()
    except Exception:
        return [
            {"id": "512x512", "width": 512, "height": 512, "label": "512² square"},
            {"id": "768x432", "width": 768, "height": 432, "label": "768×432 (16:9 draft)"},
            {"id": "1024x576", "width": 1024, "height": 576, "label": "1024×576"},
            {"id": "1280x720", "width": 1280, "height": 720, "label": "1280×720 HD"},
            {"id": "1024x1024", "width": 1024, "height": 1024, "label": "1024² square"},
            {"id": "9:16", "width": 720, "height": 1280, "label": "720×1280 (9:16 portrait)"},
        ]


SIZE_PRESETS = _frame_size_presets()

QUALITY_PRESETS = [
    {"id": "draft", "label": "Draft (fast)", "steps_scale": 0.6, "guidance_scale": 0.85},
    {"id": "balanced", "label": "Balanced", "steps_scale": 1.0, "guidance_scale": 1.0},
    {"id": "high", "label": "High", "steps_scale": 1.4, "guidance_scale": 1.1},
    {"id": "max", "label": "Max (slow)", "steps_scale": 1.8, "guidance_scale": 1.2},
]

# Optional text-encoder swap when building Diffusers pipelines.
# "auto" keeps whatever ships with the checkpoint.
TEXT_ENCODER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "auto",
        "label": "Auto (model default)",
        "hf_id": None,
        "slot": "default",
        "notes": "Use the encoder bundled with the selected model.",
    },
    {
        "id": "clip",
        "label": "CLIP ViT-L/14",
        "hf_id": "openai/clip-vit-large-patch14",
        "slot": "text_encoder",
        "notes": "Classic CLIP — good for SDXL / many still models.",
    },
    {
        "id": "openclip",
        "label": "OpenCLIP bigG (SDXL TE2)",
        "hf_id": "laion/CLIP-ViT-bigG-14-laion2B-39B-b160k",
        "slot": "text_encoder_2",
        "notes": "Second encoder slot used by SDXL-style pipelines.",
    },
    {
        "id": "t5-base",
        "label": "T5 Base (lighter)",
        "hf_id": "google/t5-v1_1-base",
        "slot": "text_encoder",
        "notes": "Smaller T5 — tries first encoder slot; may not fit every pipeline.",
    },
    {
        "id": "t5-xxl",
        "label": "T5 XXL (heavy)",
        "hf_id": "google/t5-v1_1-xxl",
        "slot": "text_encoder",
        "notes": "Large T5 used by some video / FLUX-style stacks. Needs lots of VRAM.",
    },
    {
        "id": "umt5-xxl",
        "label": "UMT5 XXL (Wan-style)",
        "hf_id": "google/umt5-xxl",
        "slot": "text_encoder",
        "notes": "Multilingual T5 often paired with Wan video models.",
    },
]


def get_text_encoder_preset(encoder_id: str | None) -> dict[str, Any] | None:
    if not encoder_id or encoder_id in ("auto", "default"):
        return TEXT_ENCODER_PRESETS[0]
    for p in TEXT_ENCODER_PRESETS:
        if p["id"] == encoder_id:
            return p
    # Treat unknown id as a custom Hugging Face repo for text_encoder
    return {
        "id": "custom",
        "label": encoder_id,
        "hf_id": encoder_id,
        "slot": "text_encoder",
        "notes": "Custom Hugging Face text encoder id.",
    }

MODELS: list[dict[str, Any]] = [
    {
        "id": "sdxl-turbo",
        "label": "SDXL Turbo (fast T2I)",
        "modes": ["t2i", "ref2i"],
        "hf_id": "stabilityai/sdxl-turbo",
        "pipeline": "AutoPipelineForText2Image",
        "min_vram_gb": 6,
        "default_steps": 4,
        "default_guidance": 0.0,
        "kind": "image",
        "supports_lora": True,
        "notes": "Fast stills. Good default for low VRAM.",
    },
    {
        "id": "flux-schnell",
        "label": "FLUX.1 Schnell",
        "modes": ["t2i"],
        "hf_id": "black-forest-labs/FLUX.1-schnell",
        "pipeline": "FluxPipeline",
        "min_vram_gb": 12,
        "default_steps": 4,
        "default_guidance": 0.0,
        "kind": "image",
        "supports_lora": True,
        "notes": "Higher quality stills when you have headroom.",
    },
    {
        "id": "wan21-t2v-1.3b",
        "label": "Wan 2.1 T2V 1.3B",
        "modes": ["t2v"],
        "hf_id": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
        "pipeline": "WanPipeline",
        "min_vram_gb": 6,
        "default_steps": 20,
        "default_guidance": 5.0,
        "kind": "video",
        "default_frames": 49,
        "fps": 16,
        "supports_lora": True,
        "notes": "Wan2GP-style default text-to-video.",
    },
    {
        "id": "wan21-i2v-14b-480p",
        "label": "Wan 2.1 I2V 14B 480p",
        "modes": ["i2v", "ref2v"],
        "hf_id": "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers",
        "pipeline": "WanImageToVideoPipeline",
        "min_vram_gb": 16,
        "default_steps": 20,
        "default_guidance": 5.0,
        "kind": "video",
        "default_frames": 49,
        "fps": 16,
        "supports_lora": True,
        "tier": "mid",
        "notes": "Image/reference driven video.",
    },
    {
        "id": "wan21-t2v-14b",
        "label": "Wan 2.1 T2V 14B (big GPU)",
        "modes": ["t2v"],
        "hf_id": "Wan-AI/Wan2.1-T2V-14B-Diffusers",
        "pipeline": "WanPipeline",
        "min_vram_gb": 24,
        "default_steps": 20,
        "default_guidance": 5.0,
        "kind": "video",
        "default_frames": 49,
        "fps": 16,
        "supports_lora": True,
        "tier": "big",
        "notes": "Full Wan text-to-video — aimed at 24GB+ (R9700 32GB OK).",
    },
    {
        "id": "wan21-i2v-14b-720p",
        "label": "Wan 2.1 I2V 14B 720p (big GPU)",
        "modes": ["i2v", "ref2v"],
        "hf_id": "Wan-AI/Wan2.1-I2V-14B-720P-Diffusers",
        "pipeline": "WanImageToVideoPipeline",
        "min_vram_gb": 24,
        "default_steps": 20,
        "default_guidance": 5.0,
        "kind": "video",
        "default_frames": 49,
        "fps": 16,
        "supports_lora": True,
        "tier": "big",
        "notes": "Higher-res image→video. Needs ~24GB+ VRAM.",
    },
    {
        "id": "flux-dev",
        "label": "FLUX.1 Dev (big GPU)",
        "modes": ["t2i"],
        "hf_id": "black-forest-labs/FLUX.1-dev",
        "pipeline": "FluxPipeline",
        "min_vram_gb": 24,
        "default_steps": 28,
        "default_guidance": 3.5,
        "kind": "image",
        "supports_lora": True,
        "tier": "big",
        "notes": "High-quality FLUX stills. Prefer Schnell on smaller cards.",
    },
    {
        "id": "sd3.5-large",
        "label": "SD 3.5 Large (big GPU)",
        "modes": ["t2i", "ref2i"],
        "hf_id": "stabilityai/stable-diffusion-3.5-large",
        "pipeline": "StableDiffusion3Pipeline",
        "min_vram_gb": 16,
        "default_steps": 28,
        "default_guidance": 4.5,
        "kind": "image",
        "supports_lora": True,
        "tier": "mid",
        "notes": "SD3.5 large — strong stills when you have headroom.",
    },
    {
        "id": "cogvideox-5b",
        "label": "CogVideoX-5B (big GPU)",
        "modes": ["t2v"],
        "hf_id": "THUDM/CogVideoX-5b",
        "pipeline": "CogVideoXPipeline",
        "min_vram_gb": 20,
        "default_steps": 50,
        "default_guidance": 6.0,
        "kind": "video",
        "default_frames": 49,
        "fps": 8,
        "supports_lora": True,
        "tier": "big",
        "notes": "5B text-to-video — happier on 24GB+ with offload.",
    },
    {
        "id": "cogvideox-2b",
        "label": "CogVideoX-2B",
        "modes": ["t2v"],
        "hf_id": "THUDM/CogVideoX-2b",
        "pipeline": "CogVideoXPipeline",
        "min_vram_gb": 12,
        "default_steps": 50,
        "default_guidance": 6.0,
        "kind": "video",
        "default_frames": 49,
        "fps": 8,
        "supports_lora": True,
        "tier": "mid",
        "notes": "Lighter CogVideoX for mid-range GPUs.",
    },
    {
        "id": "ltx-video-0.9.7",
        "label": "LTX-Video 0.9.7",
        "modes": ["t2v", "i2v"],
        "hf_id": "Lightricks/LTX-Video",
        "pipeline": "LTXPipeline",
        "min_vram_gb": 8,
        "default_steps": 30,
        "default_guidance": 3.0,
        "kind": "video",
        "default_frames": 49,
        "fps": 24,
        "supports_lora": True,
        "tier": "mid",
        "notes": "Strong alternative for drafts on AMD.",
    },
    {
        "id": "ltx2-19b-distilled",
        "label": "LTX-2 19B Distilled (big GPU)",
        "modes": ["t2v", "i2v"],
        "hf_id": "rootonchair/LTX-2-19b-distilled",
        "pipeline": "LTX2Pipeline",
        "min_vram_gb": 24,
        "default_steps": 8,
        "default_guidance": 1.0,
        "kind": "video",
        "default_frames": 121,
        "fps": 24,
        "supports_lora": True,
        "tier": "big",
        "distilled": True,
        "notes": "LTX-2 distilled — fast 8-step A/V video. Needs ~24GB+; use if you already downloaded it.",
    },
    {
        "id": "ltx2-official",
        "label": "LTX-2 (Lightricks / Diffusers)",
        "modes": ["t2v", "i2v"],
        "hf_id": "Lightricks/LTX-2",
        "pipeline": "LTX2Pipeline",
        "min_vram_gb": 24,
        "default_steps": 20,
        "default_guidance": 3.0,
        "kind": "video",
        "default_frames": 97,
        "fps": 24,
        "supports_lora": True,
        "tier": "big",
        "notes": "Official LTX-2 weights hub. Prefer Distilled for speed on R9700-class GPUs.",
    },
    {
        "id": "ltx2.5-diffusers",
        "label": "LTX-2.5 Diffusers (big GPU)",
        "modes": ["t2v", "i2v"],
        "hf_id": "Lightricks/LTX-2.5-Diffusers",
        "pipeline": "LTX2Pipeline",
        "min_vram_gb": 24,
        "default_steps": 8,
        "default_guidance": 1.0,
        "kind": "video",
        "default_frames": 121,
        "fps": 24,
        "supports_lora": True,
        "tier": "big",
        "distilled": True,
        "notes": "LTX-2.5 Diffusers pack (distilled transformer + upsampler). Large download.",
    },
    {
        "id": "ltx2.3-22b-distilled-diffusers",
        "label": "LTX-2.3 22B Distilled (Diffusers)",
        "modes": ["t2v", "i2v", "ref2v"],
        "hf_id": "diffusers/LTX-2.3-Distilled-Diffusers",
        "pipeline": "LTX2Pipeline",
        "min_vram_gb": 24,
        "default_steps": 8,
        "default_guidance": 1.0,
        "kind": "video",
        "default_frames": 121,
        "fps": 24,
        "supports_lora": True,
        "tier": "big",
        "distilled": True,
        "notes": (
            "Use this Diffusers folder — not the single ltx-2.3-22b-distilled.safetensors file. "
            "Put the full pack under models/diffusers__LTX-2.3-Distilled-Diffusers/."
        ),
    },
    {
        "id": "ltx2.3-22b-distilled-v11-diffusers",
        "label": "LTX-2.3 22B Distilled v1.1 (Diffusers)",
        "modes": ["t2v", "i2v", "ref2v"],
        "hf_id": "rootonchair/LTX-2.3-Distilled-v1.1-Diffusers",
        "pipeline": "LTX2Pipeline",
        "min_vram_gb": 24,
        "default_steps": 8,
        "default_guidance": 1.0,
        "kind": "video",
        "default_frames": 121,
        "fps": 24,
        "supports_lora": True,
        "tier": "big",
        "distilled": True,
        "notes": "Newer distilled v1.1 Diffusers conversion (audio/aesthetic updates).",
    },
    {
        "id": "stable-audio-open",
        "label": "Stable Audio Open",
        "modes": ["t2a"],
        "hf_id": "stabilityai/stable-audio-open-1.0",
        "pipeline": "StableAudioPipeline",
        "min_vram_gb": 8,
        "default_steps": 100,
        "default_guidance": 7.0,
        "kind": "audio",
        "default_duration_sec": 8,
        "supports_lora": False,
        "tags": ["music", "ambience", "sfx", "score"],
        "notes": "Music / ambience / SFX from text.",
    },
    {
        "id": "stable-audio-song",
        "label": "Stable Audio (songs / vocals bed)",
        "modes": ["t2a"],
        "hf_id": "stabilityai/stable-audio-open-1.0",
        "pipeline": "StableAudioPipeline",
        "min_vram_gb": 8,
        "default_steps": 120,
        "default_guidance": 7.5,
        "kind": "audio",
        "default_duration_sec": 12,
        "supports_lora": False,
        "tags": ["song", "music"],
        "notes": "Longer cue for song-style prompts with vocal accent hints.",
    },
    {
        "id": "audiogen-medium",
        "label": "AudioGen Medium (SFX)",
        "modes": ["t2a"],
        "hf_id": "facebook/audiogen-medium",
        "pipeline": "AudioGen",
        "min_vram_gb": 6,
        "default_steps": 50,
        "default_guidance": 3.0,
        "kind": "audio",
        "default_duration_sec": 5,
        "supports_lora": False,
        "tags": ["sfx", "ambience"],
        "notes": "Sound effects and environmental audio.",
    },
    {
        "id": "lanczos-2x",
        "label": "Lanczos 2× (fast)",
        "modes": ["upsample_image", "upsample_video"],
        "hf_id": None,
        "pipeline": "lanczos",
        "min_vram_gb": 0,
        "default_steps": 1,
        "default_guidance": 0,
        "kind": "upsample",
        "scale": 2,
        "supports_lora": False,
        "notes": "Instant classic upscale — no neural net.",
    },
    {
        "id": "realesrgan-x4",
        "label": "Real-ESRGAN ×4",
        "modes": ["upsample_image", "upsample_video"],
        "hf_id": "ai-forever/Real-ESRGAN",
        "pipeline": "realesrgan",
        "min_vram_gb": 4,
        "default_steps": 1,
        "default_guidance": 0,
        "kind": "upsample",
        "scale": 4,
        "supports_lora": False,
        "notes": "Neural upscaler when installed.",
    },
]


def _all_models() -> list[dict[str, Any]]:
    """Built-in catalog + user-added customs + Diffusers mirrors + Wan2GP ckpts."""
    by_id = {m["id"]: dict(m) for m in MODELS}
    known_hf = {str(m.get("hf_id")) for m in MODELS if m.get("hf_id")}
    try:
        from .custom_models import discover_local_models, list_custom_models

        for m in list_custom_models():
            by_id[m["id"]] = m
            if m.get("hf_id"):
                known_hf.add(str(m["hf_id"]))
        for m in discover_local_models(known_hf):
            matched = next((x for x in by_id.values() if x.get("hf_id") == m.get("hf_id")), None)
            if matched:
                matched["local_path"] = m.get("local_path")
            else:
                by_id[m["id"]] = m
                if m.get("hf_id"):
                    known_hf.add(str(m["hf_id"]))
    except Exception:
        pass
    try:
        from .wan2gp_ckpts import scan_wan2gp_ckpts

        for m in scan_wan2gp_ckpts():
            existing = by_id.get(m["id"])
            if existing:
                existing.update({k: v for k, v in m.items() if v is not None})
            else:
                by_id[m["id"]] = m
            if m.get("hf_id"):
                known_hf.add(str(m["hf_id"]))
    except Exception:
        pass
    try:
        from .wan2gp_assets import (
            scan_audio_models,
            scan_image_models,
            scan_upsample_models,
            scan_video_models,
        )

        for m in (
            scan_video_models()
            + scan_image_models()
            + scan_audio_models()
            + scan_upsample_models()
        ):
            existing = by_id.get(m["id"])
            if existing:
                existing.update({k: v for k, v in m.items() if v is not None})
            else:
                by_id[m["id"]] = m
            if m.get("hf_id"):
                known_hf.add(str(m["hf_id"]))
    except Exception:
        pass
    return list(by_id.values())


def list_models_for_mode(mode: str) -> list[dict[str, Any]]:
    return [m for m in _all_models() if mode in m["modes"]]


def get_model(model_id: str) -> dict[str, Any] | None:
    for m in _all_models():
        if m["id"] == model_id:
            return m
    return None


def default_model_for_mode(mode: str, target_vram_gb: float = 8) -> dict[str, Any] | None:
    candidates = list_models_for_mode(mode)
    fit = [m for m in candidates if m["min_vram_gb"] <= target_vram_gb]
    pool = fit or candidates
    # Prefer smaller models when VRAM is limited
    pool = sorted(pool, key=lambda m: float(m.get("min_vram_gb") or 0))
    return pool[0] if pool else None
