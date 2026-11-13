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
        "output": "video",
        "blurb": "Animate a still into a short clip.",
        "supports_lora": True,
    },
    {
        "id": "ref2i",
        "label": "Reference → Image",
        "needs_image": False,
        "needs_reference": True,
        "output": "image",
        "blurb": "Keep identity/look from a reference image.",
        "supports_lora": True,
    },
    {
        "id": "ref2v",
        "label": "Reference → Video",
        "needs_image": False,
        "needs_reference": True,
        "output": "video",
        "blurb": "Character/scene consistent video from a reference.",
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
        "notes": "Image/reference driven video.",
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
        "notes": "Strong alternative for drafts on AMD.",
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


def list_models_for_mode(mode: str) -> list[dict[str, Any]]:
    return [m for m in MODELS if mode in m["modes"]]


def get_model(model_id: str) -> dict[str, Any] | None:
    for m in MODELS:
        if m["id"] == model_id:
            return m
    return None


def default_model_for_mode(mode: str, target_vram_gb: float = 8) -> dict[str, Any] | None:
    candidates = list_models_for_mode(mode)
    fit = [m for m in candidates if m["min_vram_gb"] <= target_vram_gb]
    pool = fit or candidates
    return pool[0] if pool else None
