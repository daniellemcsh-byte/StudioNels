"""Comfy-style model templates: one click downloads the full pack.

Each template lists the primary Diffusers model plus optional extras
(text encoders, VAEs, LoRAs, upscalers) that are separate Hugging Face repos.
"""

from __future__ import annotations

from typing import Any

from .catalog import get_model
from .models_manager import (
    download_hf_asset,
    download_model,
    list_models_with_status,
    set_active_model,
)

# role → where files land under StudioNels/
# models/ for Diffusers / TE / VAE snapshots; loras/ for adapter weights
TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "ltx23-22b-distilled-v11",
        "label": "LTX-2.3 22B Distilled v1.1",
        "kind": "video",
        "modes": ["t2v", "i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Fast 8-step A/V video. Best match for Wan2GP LTX distilled on R9700-class GPUs.",
        "primary_model_id": "ltx2.3-22b-distilled-v11-diffusers",
        "components": [
            {
                "id": "ltx23-v11-main",
                "role": "model",
                "label": "Diffusers pack (DiT + bundled TE/VAE)",
                "hf_id": "rootonchair/LTX-2.3-Distilled-v1.1-Diffusers",
                "dest": "models",
                "required": True,
                "notes": "Includes text encoder + video/audio VAEs for Generate.",
            },
        ],
    },
    {
        "id": "ltx23-22b-distilled",
        "label": "LTX-2.3 22B Distilled",
        "kind": "video",
        "modes": ["t2v", "i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Official Diffusers distilled twin of the Wan2GP LTX-2.3 pack.",
        "primary_model_id": "ltx2.3-22b-distilled-diffusers",
        "components": [
            {
                "id": "ltx23-main",
                "role": "model",
                "label": "Diffusers pack",
                "hf_id": "diffusers/LTX-2.3-Distilled-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "ltx2-19b-distilled",
        "label": "LTX-2 19B Distilled",
        "kind": "video",
        "modes": ["t2v", "i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Earlier LTX-2 distilled — still strong for t2v / i2v drafts.",
        "primary_model_id": "ltx2-19b-distilled",
        "components": [
            {
                "id": "ltx2-19b-main",
                "role": "model",
                "label": "Diffusers pack",
                "hf_id": "rootonchair/LTX-2-19b-distilled",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "ltx-video-097",
        "label": "LTX-Video 0.9.7",
        "kind": "video",
        "modes": ["t2v", "i2v"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "Lighter LTX for drafts when you want less VRAM pressure.",
        "primary_model_id": "ltx-video-0.9.7",
        "components": [
            {
                "id": "ltx097-main",
                "role": "model",
                "label": "LTX-Video Diffusers",
                "hf_id": "Lightricks/LTX-Video",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "ltx25-diffusers",
        "label": "LTX-2.5 Diffusers",
        "kind": "video",
        "modes": ["t2v", "i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "LTX-2.5 Distilled Diffusers — transformer + latent upsampler. Strong next step after 2.3.",
        "primary_model_id": "ltx2.5-diffusers",
        "components": [
            {
                "id": "ltx25-main",
                "role": "model",
                "label": "LTX-2.5 Diffusers pack",
                "hf_id": "Lightricks/LTX-2.5-Diffusers",
                "dest": "models",
                "required": True,
                "notes": "Bundles distilled DiT + spatial/temporal upsampler pieces.",
            },
        ],
    },
    {
        "id": "wan21-t2v-1.3b",
        "label": "Wan 2.1 T2V 1.3B",
        "kind": "video",
        "modes": ["t2v"],
        "min_vram_gb": 6,
        "tier": "low",
        "blurb": "Light Wan text→video — good starter before the 14B packs.",
        "primary_model_id": "wan21-t2v-1.3b",
        "components": [
            {
                "id": "wan21-13b-main",
                "role": "model",
                "label": "Wan 2.1 T2V 1.3B Diffusers",
                "hf_id": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "wan21-t2v-14b",
        "label": "Wan 2.1 T2V 14B",
        "kind": "video",
        "modes": ["t2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Full Wan 2.1 text→video — Diffusers twin includes UMT5 + VAE.",
        "primary_model_id": "wan21-t2v-14b",
        "components": [
            {
                "id": "wan21-main",
                "role": "model",
                "label": "Wan 2.1 T2V 14B Diffusers",
                "hf_id": "Wan-AI/Wan2.1-T2V-14B-Diffusers",
                "dest": "models",
                "required": True,
            },
            {
                "id": "wan21-umt5",
                "role": "text_encoder",
                "label": "UMT5 XXL (optional TE swap)",
                "hf_id": "google/umt5-xxl",
                "dest": "models",
                "required": False,
                "notes": "Usually already inside the Diffusers pack.",
            },
        ],
    },
    {
        "id": "wan21-i2v-14b-480p",
        "label": "Wan 2.1 I2V 14B 480p",
        "kind": "video",
        "modes": ["i2v", "ref2v"],
        "min_vram_gb": 16,
        "tier": "mid",
        "blurb": "Wan image→video at 480p — mid/big GPU sweet spot.",
        "primary_model_id": "wan21-i2v-14b-480p",
        "components": [
            {
                "id": "wan21-i2v-480-main",
                "role": "model",
                "label": "Wan 2.1 I2V 480p Diffusers",
                "hf_id": "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "wan21-i2v-14b-720p",
        "label": "Wan 2.1 I2V 14B 720p",
        "kind": "video",
        "modes": ["i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Higher-res Wan image→video. Needs ~24GB+ (R9700 OK).",
        "primary_model_id": "wan21-i2v-14b-720p",
        "components": [
            {
                "id": "wan21-i2v-720-main",
                "role": "model",
                "label": "Wan 2.1 I2V 720p Diffusers",
                "hf_id": "Wan-AI/Wan2.1-I2V-14B-720P-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "wan21-flf2v-14b-720p",
        "label": "Wan 2.1 FLF2V 14B 720p",
        "kind": "video",
        "modes": ["i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "First/last-frame conditioned Wan video.",
        "primary_model_id": "wan21-flf2v-14b-720p",
        "components": [
            {
                "id": "wan21-flf-main",
                "role": "model",
                "label": "Wan 2.1 FLF2V Diffusers",
                "hf_id": "Wan-AI/Wan2.1-FLF2V-14B-720P-diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "wan22-t2v-a14b",
        "label": "Wan 2.2 T2V A14B",
        "kind": "video",
        "modes": ["t2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Wan 2.2 MoE text→video — newer aesthetics than 2.1. Large download.",
        "primary_model_id": "wan22-t2v-a14b",
        "components": [
            {
                "id": "wan22-t2v-main",
                "role": "model",
                "label": "Wan 2.2 T2V A14B Diffusers",
                "hf_id": "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "wan22-i2v-a14b",
        "label": "Wan 2.2 I2V A14B",
        "kind": "video",
        "modes": ["i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Wan 2.2 MoE image→video — best Wan i2v pack for big GPUs.",
        "primary_model_id": "wan22-i2v-a14b",
        "components": [
            {
                "id": "wan22-i2v-main",
                "role": "model",
                "label": "Wan 2.2 I2V A14B Diffusers",
                "hf_id": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "wan22-ti2v-5b",
        "label": "Wan 2.2 TI2V 5B",
        "kind": "video",
        "modes": ["t2v", "i2v"],
        "min_vram_gb": 12,
        "tier": "mid",
        "blurb": "Hybrid text/image→video @ 720p24 — lighter Wan 2.2 option.",
        "primary_model_id": "wan22-ti2v-5b",
        "components": [
            {
                "id": "wan22-ti2v-main",
                "role": "model",
                "label": "Wan 2.2 TI2V 5B Diffusers",
                "hf_id": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "minimax-h3",
        "label": "MiniMax H3",
        "kind": "video",
        "modes": ["t2v", "i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Omni video + stereo audio in one pass (t2va / fl2va / ref2va). Very large pack.",
        "primary_model_id": "minimax-h3",
        "components": [
            {
                "id": "minimax-h3-main",
                "role": "model",
                "label": "MiniMax-H3 Diffusers (Modular)",
                "hf_id": "MiniMaxAI/MiniMax-H3",
                "dest": "models",
                "required": True,
                "notes": "Includes Qwen3-VL conditioner, visual VAE, audio VAE, dual transformers.",
            },
        ],
    },
    {
        "id": "cogvideox-5b",
        "label": "CogVideoX-5B",
        "kind": "video",
        "modes": ["t2v"],
        "min_vram_gb": 16,
        "tier": "mid",
        "blurb": "Solid mid/high VRAM text→video.",
        "primary_model_id": "cogvideox-5b",
        "components": [
            {
                "id": "cog5b-main",
                "role": "model",
                "label": "CogVideoX-5B Diffusers",
                "hf_id": "THUDM/CogVideoX-5b",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "flux-schnell",
        "label": "FLUX.1 Schnell",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 16,
        "tier": "big",
        "blurb": "Fast stills — Diffusers pack bundles CLIP/T5 encoders + VAE.",
        "primary_model_id": "flux-schnell",
        "components": [
            {
                "id": "flux-schnell-main",
                "role": "model",
                "label": "FLUX Schnell Diffusers",
                "hf_id": "black-forest-labs/FLUX.1-schnell",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "flux-dev",
        "label": "FLUX.1 Dev",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Higher quality FLUX stills (larger download).",
        "primary_model_id": "flux-dev",
        "components": [
            {
                "id": "flux-dev-main",
                "role": "model",
                "label": "FLUX Dev Diffusers",
                "hf_id": "black-forest-labs/FLUX.1-dev",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "sdxl-turbo",
        "label": "SDXL Turbo",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 6,
        "tier": "low",
        "blurb": "Fast SDXL stills — TE + VAE included in the Diffusers folder.",
        "primary_model_id": "sdxl-turbo",
        "components": [
            {
                "id": "sdxl-turbo-main",
                "role": "model",
                "label": "SDXL Turbo Diffusers",
                "hf_id": "stabilityai/sdxl-turbo",
                "dest": "models",
                "required": True,
            },
            {
                "id": "sdxl-clip",
                "role": "text_encoder",
                "label": "CLIP ViT-L/14 (optional swap)",
                "hf_id": "openai/clip-vit-large-patch14",
                "dest": "models",
                "required": False,
            },
        ],
    },
    {
        "id": "sdxl-base",
        "label": "SDXL 1.0 Base",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "Classic SDXL — best LoRA ecosystem for stills.",
        "primary_model_id": "sdxl-base",
        "components": [
            {
                "id": "sdxl-base-main",
                "role": "model",
                "label": "SDXL Base Diffusers",
                "hf_id": "stabilityai/stable-diffusion-xl-base-1.0",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "sd15",
        "label": "Stable Diffusion 1.5",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 4,
        "tier": "low",
        "blurb": "Light classic SD1.5 — tons of community LoRAs.",
        "primary_model_id": "sd15",
        "components": [
            {
                "id": "sd15-main",
                "role": "model",
                "label": "SD 1.5 Diffusers",
                "hf_id": "runwayml/stable-diffusion-v1-5",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "sd3.5-medium",
        "label": "SD 3.5 Medium",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 12,
        "tier": "mid",
        "blurb": "SD 3.5 medium stills — good quality / VRAM balance.",
        "primary_model_id": "sd3.5-medium",
        "components": [
            {
                "id": "sd35m-main",
                "role": "model",
                "label": "SD 3.5 Medium Diffusers",
                "hf_id": "stabilityai/stable-diffusion-3.5-medium",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "sd3.5-large",
        "label": "SD 3.5 Large",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 16,
        "tier": "mid",
        "blurb": "SD 3.5 large — high quality stills.",
        "primary_model_id": "sd3.5-large",
        "components": [
            {
                "id": "sd35l-main",
                "role": "model",
                "label": "SD 3.5 Large Diffusers",
                "hf_id": "stabilityai/stable-diffusion-3.5-large",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "sd3.5-large-turbo",
        "label": "SD 3.5 Large Turbo",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 16,
        "tier": "mid",
        "blurb": "Fast 4-step SD 3.5 large turbo.",
        "primary_model_id": "sd3.5-large-turbo",
        "components": [
            {
                "id": "sd35lt-main",
                "role": "model",
                "label": "SD 3.5 Large Turbo",
                "hf_id": "stabilityai/stable-diffusion-3.5-large-turbo",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "qwen-image",
        "label": "Qwen-Image",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Qwen-Image — excellent text-in-image / stills. Needs recent Diffusers.",
        "primary_model_id": "qwen-image",
        "components": [
            {
                "id": "qwen-image-main",
                "role": "model",
                "label": "Qwen-Image Diffusers",
                "hf_id": "Qwen/Qwen-Image",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "playground-v2.5",
        "label": "Playground v2.5",
        "kind": "image",
        "modes": ["t2i", "ref2i"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "Aesthetic 1024px stills (SDXL family).",
        "primary_model_id": "playground-v2.5",
        "components": [
            {
                "id": "pg25-main",
                "role": "model",
                "label": "Playground v2.5 Diffusers",
                "hf_id": "playgroundai/playground-v2.5-1024px-aesthetic",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "pixart-sigma",
        "label": "PixArt-Σ",
        "kind": "image",
        "modes": ["t2i"],
        "min_vram_gb": 10,
        "tier": "mid",
        "blurb": "PixArt-Sigma transformer stills.",
        "primary_model_id": "pixart-sigma",
        "components": [
            {
                "id": "pixart-main",
                "role": "model",
                "label": "PixArt-Sigma Diffusers",
                "hf_id": "PixArt-alpha/PixArt-Sigma-XL-2-1024-MS",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "auraflow",
        "label": "AuraFlow v0.3",
        "kind": "image",
        "modes": ["t2i"],
        "min_vram_gb": 16,
        "tier": "mid",
        "blurb": "AuraFlow text→image Diffusers pack.",
        "primary_model_id": "auraflow",
        "components": [
            {
                "id": "auraflow-main",
                "role": "model",
                "label": "AuraFlow Diffusers",
                "hf_id": "fal/AuraFlow-v0.3",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "kandinsky-3",
        "label": "Kandinsky 3",
        "kind": "image",
        "modes": ["t2i"],
        "min_vram_gb": 12,
        "tier": "mid",
        "blurb": "Kandinsky 3 stills.",
        "primary_model_id": "kandinsky-3",
        "components": [
            {
                "id": "k3-main",
                "role": "model",
                "label": "Kandinsky 3 Diffusers",
                "hf_id": "kandinsky-community/kandinsky-3",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "hunyuan-video",
        "label": "HunyuanVideo T2V",
        "kind": "video",
        "modes": ["t2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Tencent HunyuanVideo text→video (community Diffusers).",
        "primary_model_id": "hunyuan-video",
        "components": [
            {
                "id": "hyv-main",
                "role": "model",
                "label": "HunyuanVideo Diffusers",
                "hf_id": "hunyuanvideo-community/HunyuanVideo",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "hunyuan-video-i2v",
        "label": "HunyuanVideo I2V",
        "kind": "video",
        "modes": ["i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Hunyuan image→video Diffusers pack.",
        "primary_model_id": "hunyuan-video-i2v",
        "components": [
            {
                "id": "hyv-i2v-main",
                "role": "model",
                "label": "HunyuanVideo-I2V Diffusers",
                "hf_id": "hunyuanvideo-community/HunyuanVideo-I2V",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "mochi-1",
        "label": "Mochi 1 Preview",
        "kind": "video",
        "modes": ["t2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Genmo Mochi-1 text→video — cinematic motion, huge download.",
        "primary_model_id": "mochi-1",
        "components": [
            {
                "id": "mochi-main",
                "role": "model",
                "label": "Mochi-1 Diffusers",
                "hf_id": "genmo/mochi-1-preview",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "skyreels-v2-i2v-14b-720p",
        "label": "SkyReels V2 I2V 14B",
        "kind": "video",
        "modes": ["i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "SkyReels V2 film-style image→video @ 720p.",
        "primary_model_id": "skyreels-v2-i2v-14b-720p",
        "components": [
            {
                "id": "sky-i2v-main",
                "role": "model",
                "label": "SkyReels V2 I2V Diffusers",
                "hf_id": "Skywork/SkyReels-V2-I2V-14B-720P-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "skyreels-v2-t2v-14b-720p",
        "label": "SkyReels V2 T2V 14B",
        "kind": "video",
        "modes": ["t2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "SkyReels V2 text→video @ 720p.",
        "primary_model_id": "skyreels-v2-t2v-14b-720p",
        "components": [
            {
                "id": "sky-t2v-main",
                "role": "model",
                "label": "SkyReels V2 T2V Diffusers",
                "hf_id": "Skywork/SkyReels-V2-T2V-14B-720P-Diffusers",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "cogvideox-2b",
        "label": "CogVideoX-2B",
        "kind": "video",
        "modes": ["t2v"],
        "min_vram_gb": 12,
        "tier": "mid",
        "blurb": "Lighter CogVideoX text→video.",
        "primary_model_id": "cogvideox-2b",
        "components": [
            {
                "id": "cog2b-main",
                "role": "model",
                "label": "CogVideoX-2B Diffusers",
                "hf_id": "THUDM/CogVideoX-2b",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "cogvideox-i2v-5b",
        "label": "CogVideoX-5B I2V",
        "kind": "video",
        "modes": ["i2v", "ref2v"],
        "min_vram_gb": 20,
        "tier": "big",
        "blurb": "CogVideoX image→video 5B.",
        "primary_model_id": "cogvideox-i2v-5b",
        "components": [
            {
                "id": "cog5b-i2v-main",
                "role": "model",
                "label": "CogVideoX-5B I2V Diffusers",
                "hf_id": "THUDM/CogVideoX-5b-I2V",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "ltx2-official",
        "label": "LTX-2 Official",
        "kind": "video",
        "modes": ["t2v", "i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Official Lightricks LTX-2 hub (non-distilled).",
        "primary_model_id": "ltx2-official",
        "components": [
            {
                "id": "ltx2-off-main",
                "role": "model",
                "label": "LTX-2 Diffusers",
                "hf_id": "Lightricks/LTX-2",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "stable-audio-open",
        "label": "Stable Audio Open",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "Text → music / ambience / SFX. Full Diffusers audio pack.",
        "primary_model_id": "stable-audio-open",
        "components": [
            {
                "id": "sao-main",
                "role": "model",
                "label": "Stable Audio Open",
                "hf_id": "stabilityai/stable-audio-open-1.0",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "audiogen-medium",
        "label": "AudioGen Medium",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 6,
        "tier": "low",
        "blurb": "SFX / ambience from text (Meta AudioGen).",
        "primary_model_id": "audiogen-medium",
        "components": [
            {
                "id": "audiogen-main",
                "role": "model",
                "label": "AudioGen Medium",
                "hf_id": "facebook/audiogen-medium",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "musicgen-small",
        "label": "MusicGen Small",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 4,
        "tier": "low",
        "blurb": "Light Meta MusicGen — music from a text prompt.",
        "primary_model_id": "musicgen-small",
        "components": [
            {
                "id": "mg-small-main",
                "role": "model",
                "label": "MusicGen Small",
                "hf_id": "facebook/musicgen-small",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "musicgen-medium",
        "label": "MusicGen Medium",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "Meta MusicGen medium music pack.",
        "primary_model_id": "musicgen-medium",
        "components": [
            {
                "id": "mg-med-main",
                "role": "model",
                "label": "MusicGen Medium",
                "hf_id": "facebook/musicgen-medium",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "musicgen-large",
        "label": "MusicGen Large",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 12,
        "tier": "mid",
        "blurb": "Best MusicGen quality — heavier download / VRAM.",
        "primary_model_id": "musicgen-large",
        "components": [
            {
                "id": "mg-large-main",
                "role": "model",
                "label": "MusicGen Large",
                "hf_id": "facebook/musicgen-large",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "musicgen-melody",
        "label": "MusicGen Melody",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "MusicGen with melody conditioning support.",
        "primary_model_id": "musicgen-melody",
        "components": [
            {
                "id": "mg-mel-main",
                "role": "model",
                "label": "MusicGen Melody",
                "hf_id": "facebook/musicgen-melody",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "audioldm2",
        "label": "AudioLDM 2",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "AudioLDM2 — music + SFX from text.",
        "primary_model_id": "audioldm2",
        "components": [
            {
                "id": "aldm2-main",
                "role": "model",
                "label": "AudioLDM2 Diffusers",
                "hf_id": "cvssp/audioldm2",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "audioldm2-large",
        "label": "AudioLDM 2 Large",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 12,
        "tier": "mid",
        "blurb": "Larger AudioLDM2 checkpoint.",
        "primary_model_id": "audioldm2-large",
        "components": [
            {
                "id": "aldm2l-main",
                "role": "model",
                "label": "AudioLDM2 Large",
                "hf_id": "cvssp/audioldm2-large",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "audioldm2-music",
        "label": "AudioLDM 2 Music",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "AudioLDM2 music-specialized pack.",
        "primary_model_id": "audioldm2-music",
        "components": [
            {
                "id": "aldm2m-main",
                "role": "model",
                "label": "AudioLDM2 Music",
                "hf_id": "cvssp/audioldm2-music",
                "dest": "models",
                "required": True,
            },
        ],
    },
    {
        "id": "realesrgan-x4",
        "label": "Real-ESRGAN ×4",
        "kind": "upsample",
        "modes": ["upsample_image", "upsample_video"],
        "min_vram_gb": 4,
        "tier": "low",
        "blurb": "Neural upscaler for stills and frames.",
        "primary_model_id": "realesrgan-x4",
        "components": [
            {
                "id": "realesrgan-main",
                "role": "upscaler",
                "label": "Real-ESRGAN weights",
                "hf_id": "ai-forever/Real-ESRGAN",
                "dest": "models",
                "required": True,
            },
        ],
    },
]


def _sync_catalog_templates() -> None:
    """Ensure every catalog model with an HF id appears as a one-click pack."""
    from .catalog import MODELS

    known = {t["id"] for t in TEMPLATES}
    known |= {t.get("primary_model_id") for t in TEMPLATES if t.get("primary_model_id")}
    for m in MODELS:
        mid = m.get("id")
        hf = m.get("hf_id")
        if not mid or not hf or mid in known:
            continue
        kind = str(m.get("kind") or "video")
        role = (
            "upscaler"
            if kind == "upsample"
            else "model"
        )
        TEMPLATES.append(
            {
                "id": mid,
                "label": m.get("label") or mid,
                "family": m.get("family"),
                "variant": m.get("variant"),
                "kind": kind,
                "modes": list(m.get("modes") or []),
                "min_vram_gb": float(m.get("min_vram_gb") or 8),
                "tier": m.get("tier") or "mid",
                "blurb": m.get("notes") or f"One-click Diffusers pack for {m.get('label')}.",
                "primary_model_id": mid,
                "components": [
                    {
                        "id": f"{mid}-main",
                        "role": role,
                        "label": f"{m.get('label')} Diffusers",
                        "hf_id": hf,
                        "dest": "models",
                        "required": True,
                    }
                ],
            }
        )
        known.add(mid)


def get_template(template_id: str) -> dict[str, Any] | None:
    _sync_catalog_templates()
    for t in TEMPLATES:
        if t["id"] == template_id:
            return dict(t)
    return None


def _component_status(comp: dict[str, Any], model_status_by_hf: dict[str, dict]) -> dict[str, Any]:
    hf = comp.get("hf_id") or ""
    st = model_status_by_hf.get(hf) or {}
    # Also check generic asset download key
    from .models_manager import get_asset_download

    asset = get_asset_download(comp["id"]) if comp.get("id") else None
    if asset:
        return {
            **comp,
            "download_status": asset.get("status"),
            "download_progress": asset.get("progress"),
            "download_message": asset.get("message"),
            "installed": asset.get("status") == "installed" or bool(asset.get("installed")),
            "local_path": asset.get("local_path"),
        }
    if st:
        return {
            **comp,
            "download_status": st.get("download_status"),
            "download_progress": st.get("download_progress"),
            "download_message": st.get("download_message"),
            "installed": bool(st.get("installed") or st.get("download_status") == "installed"),
            "local_path": st.get("local_path"),
        }
    # Probe disk for models/Owner__Repo
    from pathlib import Path

    from .queue_store import loras_dir, models_dir

    dest = comp.get("dest") or "models"
    root = loras_dir() if dest == "loras" else models_dir()
    folder = root / str(hf).replace("/", "__")
    installed = folder.is_dir() and any(folder.iterdir()) if folder.exists() else False
    # LoRAs sometimes land as a single file in loras/
    if dest == "loras" and not installed and hf:
        # any safetensors whose stem matches last path segment
        leaf = hf.split("/")[-1].lower()
        for p in root.glob("*"):
            if leaf in p.name.lower():
                installed = True
                folder = p
                break
    return {
        **comp,
        "download_status": "installed" if installed else "not_downloaded",
        "download_progress": 1.0 if installed else 0.0,
        "installed": installed,
        "local_path": str(folder) if installed else None,
    }


def list_templates() -> list[dict[str, Any]]:
    _sync_catalog_templates()
    models = list_models_with_status()
    by_hf = {str(m.get("hf_id")): m for m in models if m.get("hf_id")}
    out: list[dict[str, Any]] = []
    for raw in TEMPLATES:
        t = dict(raw)
        comps = [_component_status(dict(c), by_hf) for c in (t.get("components") or [])]
        t["components"] = comps
        required = [c for c in comps if c.get("required", True)]
        ready = all(c.get("installed") for c in required) if required else False
        t["ready"] = ready
        t["progress"] = (
            sum(float(c.get("download_progress") or 0) for c in comps) / max(1, len(comps))
        )
        any_dl = any(c.get("download_status") == "downloading" for c in comps)
        t["download_status"] = (
            "installed"
            if ready
            else "downloading"
            if any_dl
            else "partial"
            if any(c.get("installed") for c in comps)
            else "not_downloaded"
        )
        primary = get_model(t.get("primary_model_id") or "")
        if primary:
            t["primary_label"] = primary.get("label")
            t["primary_hf_id"] = primary.get("hf_id")
        out.append(t)
    return out


def install_template(
    template_id: str,
    *,
    include_optional: bool = True,
    activate: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Queue downloads for every component in the template."""
    t = get_template(template_id)
    if not t:
        raise ValueError(f"Unknown template {template_id}")

    started: list[dict[str, Any]] = []
    primary_id = t.get("primary_model_id")

    # Prefer catalog download for the primary model (progress shows on Models list)
    if primary_id and get_model(primary_id):
        try:
            job = download_model(primary_id, force=force)
            started.append({"role": "model", "model_id": primary_id, "job": job})
        except Exception as exc:  # noqa: BLE001
            started.append({"role": "model", "model_id": primary_id, "error": str(exc)})

    primary_hf = None
    if primary_id:
        m = get_model(primary_id)
        primary_hf = (m or {}).get("hf_id")

    for comp in t.get("components") or []:
        if not include_optional and not comp.get("required", True):
            continue
        hf = comp.get("hf_id")
        if not hf:
            continue
        # Skip duplicate of primary catalog download
        if primary_hf and hf == primary_hf and primary_id:
            continue
        try:
            job = download_hf_asset(
                asset_id=str(comp["id"]),
                hf_id=str(hf),
                dest=str(comp.get("dest") or "models"),
                label=str(comp.get("label") or hf),
                force=force,
            )
            started.append({**comp, "job": job})
        except Exception as exc:  # noqa: BLE001
            started.append({**comp, "error": str(exc)})

    if activate and primary_id:
        try:
            set_active_model(primary_id)
        except Exception:
            pass

    return {
        "ok": True,
        "template_id": template_id,
        "label": t.get("label"),
        "started": started,
        "count": len(started),
        "hint": (
            f"Downloading {t.get('label')} pack — model"
            + (", text encoders / VAEs / LoRAs" if include_optional else "")
            + ". Watch progress on the Models tab."
        ),
        "templates": list_templates(),
        "models": list_models_with_status(),
    }
