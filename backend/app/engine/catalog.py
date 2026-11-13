from __future__ import annotations

from typing import Any, Literal

GenMode = Literal["t2i", "t2v", "i2v", "ref2i", "ref2v"]

GENERATION_MODES: list[dict[str, Any]] = [
    {
        "id": "t2i",
        "label": "Text → Image",
        "needs_image": False,
        "needs_reference": False,
        "output": "image",
        "blurb": "Prompt only. Best for character/scene stills.",
    },
    {
        "id": "t2v",
        "label": "Text → Video",
        "needs_image": False,
        "needs_reference": False,
        "output": "video",
        "blurb": "Prompt only. Draft shots from words.",
    },
    {
        "id": "i2v",
        "label": "Image → Video",
        "needs_image": True,
        "needs_reference": False,
        "output": "video",
        "blurb": "Animate a still into a short clip.",
    },
    {
        "id": "ref2i",
        "label": "Reference → Image",
        "needs_image": False,
        "needs_reference": True,
        "output": "image",
        "blurb": "Keep identity/look from a reference image.",
    },
    {
        "id": "ref2v",
        "label": "Reference → Video",
        "needs_image": False,
        "needs_reference": True,
        "output": "video",
        "blurb": "Character/scene consistent video from a reference.",
    },
]

# Built-in model catalog — downloaded into ~/.framewright/models (not ComfyUI).
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
        "notes": "Image/reference driven video. Use low-VRAM offload on smaller cards.",
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
        "notes": "Strong alternative for drafts on AMD.",
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
