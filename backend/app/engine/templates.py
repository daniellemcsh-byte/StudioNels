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
        "id": "wan21-t2v-14b",
        "label": "Wan 2.1 T2V 14B",
        "kind": "video",
        "modes": ["t2v", "i2v", "ref2v"],
        "min_vram_gb": 24,
        "tier": "big",
        "blurb": "Wan video stack — Diffusers twin + UMT5 text encoder.",
        "primary_model_id": "wan21-t2v-14b",
        "components": [
            {
                "id": "wan21-main",
                "role": "model",
                "label": "Wan 2.1 Diffusers",
                "hf_id": "Wan-AI/Wan2.1-T2V-14B-Diffusers",
                "dest": "models",
                "required": True,
            },
            {
                "id": "wan21-umt5",
                "role": "text_encoder",
                "label": "UMT5 XXL (Wan TE)",
                "hf_id": "google/umt5-xxl",
                "dest": "models",
                "required": False,
                "notes": "Optional if you swap TE in Generate; often already in the Diffusers pack.",
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
        "id": "stable-audio-open",
        "label": "Stable Audio Open",
        "kind": "audio",
        "modes": ["t2a"],
        "min_vram_gb": 8,
        "tier": "mid",
        "blurb": "Text → music / ambience. Full Diffusers audio pack.",
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


def get_template(template_id: str) -> dict[str, Any] | None:
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
