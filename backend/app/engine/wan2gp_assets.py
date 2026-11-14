"""Wan2GP asset discovery: ckpts, LoRAs, text encoders, VAEs, image & audio models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..paths import ROOT, ensure_dirs
from ..storage import load_settings, save_settings

_LORA_HINTS = (
    "ltx2",
    "ltxv",
    "wan",
    "hunyuan",
    "flux",
    "qwen",
    "z_image",
    "chatterbox",
)

# Image / audio filename patterns common in Wan2GP ckpts
_IMAGE_HINTS = (
    "flux",
    "sdxl",
    "qwen_image",
    "qwen-image",
    "moss_image",
    "z_image",
    "hunyuan",
)
_VIDEO_HINTS = (
    "ltx",
    "wan",
    "hunyuan",
    "skyreels",
    "cogvideo",
    "mochi",
    "hunyuanvideo",
    "i2v",
    "t2v",
    "diffusion_model",
)
_AUDIO_HINTS = (
    "stable-audio",
    "audiogen",
    "minimax",
    "chatterbox",
    "musicgen",
    "whisper",  # utility — still list under audio utils
)

# Every Generate tab StudioNels exposes
ALL_GEN_MODES = (
    "t2i",
    "t2v",
    "i2v",
    "ref2i",
    "ref2v",
    "t2a",
    "upsample_image",
    "upsample_video",
)


def _modes_for_video_name(name: str) -> list[str]:
    low = name.lower()
    if "i2v" in low and "t2v" not in low:
        return ["i2v", "ref2v"]
    if "t2v" in low and "i2v" not in low:
        return ["t2v"]
    return ["t2v", "i2v", "ref2v"]


def _modes_for_image_name(name: str) -> list[str]:
    low = name.lower()
    if "ref" in low or "ip-adapter" in low or "pulid" in low:
        return ["t2i", "ref2i"]
    return ["t2i", "ref2i"]


def _settings_path(attr: str) -> Path | None:
    try:
        settings = load_settings()
        raw = (getattr(settings, attr, None) or "").strip()
        if not raw:
            return None
        p = Path(raw).expanduser()
        return p if p.exists() and p.is_dir() else None
    except Exception:
        return None


def _dedupe_roots(*candidates: Path | None) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for c in candidates:
        if c is None or not c.exists():
            continue
        key = str(c.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def ckpts_and_extra_roots() -> list[Path]:
    from .wan2gp_ckpts import ckpts_roots

    ensure_dirs()
    roots = list(ckpts_roots())
    extra = _settings_path("wan2gp_assets_path")
    if extra:
        roots = _dedupe_roots(*roots, extra, extra / "ckpts")
    return roots


def lora_roots() -> list[Path]:
    from .queue_store import loras_dir

    ensure_dirs()
    roots = [loras_dir()]
    wan_loras = _settings_path("wan2gp_loras_path")
    if wan_loras:
        roots.append(wan_loras)
        if (wan_loras / "loras").is_dir():
            roots.append(wan_loras / "loras")
    ckpts = _settings_path("wan2gp_ckpts_path")
    if ckpts:
        sibling = ckpts.parent / "loras"
        if sibling.is_dir():
            roots.append(sibling)
    assets = _settings_path("wan2gp_assets_path")
    if assets:
        if (assets / "loras").is_dir():
            roots.append(assets / "loras")
        else:
            roots.append(assets)
    return _dedupe_roots(*roots)


def _family_from_path(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
        if len(rel.parts) > 1:
            return rel.parts[0]
    except ValueError:
        pass
    name = path.name.lower()
    for key in _LORA_HINTS:
        if key in name:
            return key
    return "misc"


def scan_loras() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    local_root = None
    try:
        from .queue_store import loras_dir

        local_root = loras_dir().resolve()
    except Exception:
        pass

    for root in lora_roots():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.name.upper().startswith("README"):
                continue
            if path.suffix.lower() not in {".safetensors", ".pt", ".bin", ".gguf"}:
                continue
            low = path.name.lower()
            if "diffusion_model" in low:
                continue
            if path.stat().st_size > 8_000_000_000:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            family = _family_from_path(path, root)
            is_local = local_root is not None and root.resolve() == local_root
            items.append(
                {
                    "id": f"{family}-{path.stem}"[:120],
                    "name": path.name,
                    "path": str(path),
                    "size_mb": round(path.stat().st_size / (1024 * 1024), 1),
                    "family": family,
                    "source": "local" if is_local else "wan2gp",
                    "root": str(root),
                }
            )
    return items


def scan_text_encoders() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    te_extra = _settings_path("wan2gp_text_encoders_path")
    roots = _dedupe_roots(*ckpts_and_extra_roots(), te_extra)

    for root in roots:
        for path in sorted(root.rglob("config.json")):
            parent = path.parent
            blob = str(parent).lower()
            if not any(k in blob for k in ("gemma", "t5", "umt5", "clip", "text_encoder")):
                continue
            key = str(parent.resolve())
            if key in seen:
                continue
            seen.add(key)
            kind = (
                "gemma"
                if "gemma" in blob
                else "t5"
                if "t5" in blob
                else "clip"
                if "clip" in blob
                else "local"
            )
            found.append(
                {
                    "id": f"local-{kind}-{parent.name}"[:80],
                    "label": f"{parent.name} (local)",
                    "hf_id": None,
                    "local_path": str(parent),
                    "slot": "text_encoder",
                    "notes": f"Text encoder folder under {root}",
                    "source": "wan2gp",
                    "kind": kind,
                }
            )

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            low = path.name.lower()
            if not low.endswith((".safetensors", ".gguf", ".bin")):
                continue
            if not any(k in low for k in ("gemma", "text_encoder", "umt5", "t5-xxl", "t5_xxl")):
                continue
            if any(k in low for k in ("diffusion", "vae", "lora", "vocoder")):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "id": f"file-{path.stem}"[:80],
                    "label": f"{path.name} (Wan2GP)",
                    "hf_id": None,
                    "local_path": str(path),
                    "slot": "text_encoder",
                    "notes": "Wan2GP text-encoder file — Auto may still be safer for Diffusers.",
                    "source": "wan2gp",
                    "kind": "gemma" if "gemma" in low else "t5" if "t5" in low else "local",
                }
            )
    return found


def list_text_encoder_presets() -> list[dict[str, Any]]:
    from .catalog import TEXT_ENCODER_PRESETS

    out = [dict(p) for p in TEXT_ENCODER_PRESETS]
    ids = {p["id"] for p in out}
    for p in scan_text_encoders():
        if p["id"] not in ids:
            out.append(p)
            ids.add(p["id"])
    return out


def _classify_component(name: str) -> str | None:
    low = name.lower()
    if "lora" in low or "ic-lora" in low or "ic_lora" in low:
        return "lora"
    if "audio_vae" in low or "audio-vae" in low:
        return "audio_vae"
    if "vocoder" in low:
        return "vocoder"
    if "spatial-upscaler" in low or "spatial_upscaler" in low:
        return "spatial_vae_upscaler"
    if "temporal-upscaler" in low or "temporal_upscaler" in low:
        return "temporal_vae_upscaler"
    if "_vae" in low or "-vae" in low or low.endswith("vae.safetensors"):
        if "audio" in low:
            return "audio_vae"
        return "video_vae"
    if "embeddings_connector" in low or "embedding_connector" in low:
        return "connector"
    if "text_embedding" in low or "text-embedding" in low:
        return "text_proj"
    if "diffusion_model" in low or "diffusion-model" in low:
        return "diffusion"
    if "gemma" in low or "text_encoder" in low:
        return "text_encoder"
    return None


def scan_vaes_and_components() -> list[dict[str, Any]]:
    """Video VAEs, audio VAEs, vocoders, upscalers from Wan2GP ckpts."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in ckpts_and_extra_roots():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".safetensors", ".pt", ".bin", ".gguf"}:
                continue
            kind = _classify_component(path.name)
            if kind not in {
                "video_vae",
                "audio_vae",
                "vocoder",
                "spatial_vae_upscaler",
                "temporal_vae_upscaler",
                "connector",
                "text_proj",
            }:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "id": f"{kind}-{path.stem}"[:120],
                    "name": path.name,
                    "path": str(path),
                    "kind": kind,
                    "label": {
                        "video_vae": "Video VAE",
                        "audio_vae": "Audio VAE",
                        "vocoder": "Vocoder",
                        "spatial_vae_upscaler": "Spatial upscaler",
                        "temporal_vae_upscaler": "Temporal upscaler",
                        "connector": "Embeddings connector",
                        "text_proj": "Text embedding projection",
                    }.get(kind, kind),
                    "size_mb": round(path.stat().st_size / (1024 * 1024), 1),
                    "source": "wan2gp",
                    "root": str(root),
                }
            )
    return items


def _guess_image_hf(name: str) -> str | None:
    low = name.lower()
    if "flux" in low and "schnell" in low:
        return "black-forest-labs/FLUX.1-schnell"
    if "flux" in low and "dev" in low:
        return "black-forest-labs/FLUX.1-dev"
    if "sdxl" in low and "turbo" in low:
        return "stabilityai/sdxl-turbo"
    if "qwen" in low and "image" in low:
        return "Qwen/Qwen-Image"
    return None


def _guess_audio_hf(name: str) -> str | None:
    low = name.lower()
    if "stable-audio" in low or "stable_audio" in low:
        return "stabilityai/stable-audio-open-1.0"
    if "audiogen" in low:
        return "facebook/audiogen-medium"
    return None


def scan_video_models() -> list[dict[str, Any]]:
    """Non-LTX (and loose) video DiTs in Wan2GP ckpts for t2v / i2v / ref2v."""
    from .wan2gp_ckpts import scan_wan2gp_ckpts

    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    # LTX packs already handled by wan2gp_ckpts — skip their diffusion_model paths
    for pack in scan_wan2gp_ckpts():
        for p in (pack.get("component_files") or {}).values():
            if p:
                seen.add(str(Path(p).resolve()))
        if pack.get("local_path"):
            seen.add(str(Path(pack["local_path"]).resolve()))

    for root in ckpts_and_extra_roots():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".safetensors", ".gguf", ".pt"}:
                continue
            low = path.name.lower()
            if any(
                k in low
                for k in (
                    "vae",
                    "lora",
                    "text_encoder",
                    "audio",
                    "vocoder",
                    "upscaler",
                    "gemma",
                    "connector",
                )
            ):
                continue
            is_dit = "diffusion_model" in low or "diffusion-model" in low
            is_named = any(h in low for h in _VIDEO_HINTS) and path.stat().st_size > 500_000_000
            if not is_dit and not is_named:
                continue
            if path.stat().st_size < 100_000_000:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            modes = _modes_for_video_name(path.name)
            found.append(
                {
                    "id": f"wan2gp-vid-{path.stem}"[:80],
                    "label": f"{path.stem} (Wan2GP video)",
                    "modes": modes,
                    "hf_id": f"local/{path.stem}",
                    "pipeline": "DiffusionPipeline",
                    "min_vram_gb": 16,
                    "default_steps": 20,
                    "default_guidance": 5.0,
                    "kind": "video",
                    "default_frames": 49,
                    "fps": 16,
                    "supports_lora": True,
                    "tier": "big" if path.stat().st_size > 8_000_000_000 else "mid",
                    "custom": True,
                    "wan2gp": True,
                    "format": "wan2gp",
                    "local_path": str(path),
                    "notes": (
                        f"Wan2GP video checkpoint for {', '.join(modes)}. "
                        "Add a Diffusers HF twin in Models if Generate cannot load this file directly."
                    ),
                }
            )
    return found


def scan_image_models() -> list[dict[str, Any]]:
    """Image diffusion weights sitting in Wan2GP ckpts (Flux, Qwen Image, etc.)."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in ckpts_and_extra_roots():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".safetensors", ".gguf", ".pt"}:
                continue
            low = path.name.lower()
            if not any(h in low for h in _IMAGE_HINTS):
                continue
            if any(k in low for k in ("vae", "lora", "text_encoder", "audio", "vocoder", "upscaler", "video")):
                continue
            if "diffusion_model" in low and "image" not in low and "flux" not in low:
                continue
            if path.stat().st_size < 50_000_000:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            twin = _guess_image_hf(path.name)
            modes = _modes_for_image_name(path.name)
            found.append(
                {
                    "id": f"wan2gp-img-{path.stem}"[:80],
                    "label": f"{path.stem} (Wan2GP image)",
                    "modes": modes,
                    "hf_id": twin or f"local/{path.stem}",
                    "pipeline": "DiffusionPipeline",
                    "min_vram_gb": 12,
                    "default_steps": 20,
                    "default_guidance": 3.5,
                    "kind": "image",
                    "supports_lora": True,
                    "tier": "big" if path.stat().st_size > 10_000_000_000 else "mid",
                    "custom": True,
                    "wan2gp": True,
                    "format": "wan2gp",
                    "local_path": str(path),
                    "notes": (
                        "Wan2GP image checkpoint. "
                        + (
                            f"Generate prefers Diffusers twin {twin}."
                            if twin
                            else "Add a Diffusers HF id if generation cannot load this file directly."
                        )
                    ),
                }
            )
    return found


def scan_audio_models() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in ckpts_and_extra_roots():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".safetensors", ".gguf", ".pt", ".bin"}:
                continue
            low = path.name.lower()
            if not any(h in low for h in _AUDIO_HINTS):
                continue
            if "whisper" in low:
                kind_tag = "utility"
            else:
                kind_tag = "audio"
            if "vae" in low and "minimax" not in low and "stable" not in low:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            twin = _guess_audio_hf(path.name)
            found.append(
                {
                    "id": f"wan2gp-aud-{path.stem}"[:80],
                    "label": f"{path.stem} (Wan2GP audio)",
                    "modes": ["t2a"],
                    "hf_id": twin or f"local/{path.stem}",
                    "pipeline": "StableAudioPipeline"
                    if twin and "stable-audio" in (twin or "")
                    else "DiffusionPipeline",
                    "min_vram_gb": 8,
                    "default_steps": 100,
                    "default_guidance": 7.0,
                    "kind": "audio",
                    "default_duration_sec": 8,
                    "supports_lora": False,
                    "tier": "mid",
                    "custom": True,
                    "wan2gp": True,
                    "format": "wan2gp",
                    "local_path": str(path),
                    "utility": kind_tag == "utility",
                    "notes": (
                        "Wan2GP audio / speech asset. "
                        + (
                            f"Diffusers twin: {twin}."
                            if twin
                            else "May require matching Diffusers pack for Generate."
                        )
                    ),
                }
            )
    return found


def scan_upsample_models() -> list[dict[str, Any]]:
    """RIFE / Real-ESRGAN / LTX spatial+temporal upscalers from Wan2GP folders."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    hints = (
        "realesrgan",
        "real-esrgan",
        "esrgan",
        "rife",
        "upscaler",
        "upsample",
        "spatial-upscaler",
        "temporal-upscaler",
        "latent.upsampler",
        "latent_upsampler",
    )
    for root in ckpts_and_extra_roots():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".safetensors", ".pt", ".pth", ".pkl", ".bin", ".onnx"}:
                continue
            low = path.name.lower()
            if not any(h in low for h in hints):
                continue
            if "diffusion_model" in low:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            if "rife" in low:
                pipe, scale, label_kind = "rife", 1, "frame-interp"
            elif "temporal" in low:
                pipe, scale, label_kind = "ltx_temporal_upscaler", 2, "temporal"
            elif "spatial" in low or "latent" in low:
                pipe, scale, label_kind = "ltx_spatial_upscaler", 2, "spatial"
            elif "esrgan" in low:
                pipe, scale, label_kind = "realesrgan", 4, "image"
            else:
                pipe, scale, label_kind = "upsample", 2, "generic"
            found.append(
                {
                    "id": f"wan2gp-up-{path.stem}"[:80],
                    "label": f"{path.stem} (Wan2GP {label_kind} upscale)",
                    "modes": ["upsample_image", "upsample_video"],
                    "hf_id": None,
                    "pipeline": pipe,
                    "min_vram_gb": 4 if pipe != "lanczos" else 0,
                    "default_steps": 1,
                    "default_guidance": 0,
                    "kind": "upsample",
                    "scale": scale,
                    "supports_lora": False,
                    "tier": "mid",
                    "custom": True,
                    "wan2gp": True,
                    "format": "wan2gp",
                    "local_path": str(path),
                    "notes": f"Wan2GP upsampling asset ({label_kind}) at {path.name}.",
                }
            )
    # Also surface VAE upscalers already classified as components
    for comp in scan_vaes_and_components():
        if "upscaler" not in comp["kind"]:
            continue
        mid = f"wan2gp-up-comp-{comp['id']}"[:80]
        if mid in seen:
            continue
        found.append(
            {
                "id": mid,
                "label": f"{comp['name']} (Wan2GP {comp['label']})",
                "modes": ["upsample_video"],
                "hf_id": None,
                "pipeline": "ltx_spatial_upscaler"
                if "spatial" in comp["kind"]
                else "ltx_temporal_upscaler",
                "min_vram_gb": 8,
                "default_steps": 1,
                "default_guidance": 0,
                "kind": "upsample",
                "scale": 2,
                "supports_lora": False,
                "custom": True,
                "wan2gp": True,
                "format": "wan2gp",
                "local_path": comp["path"],
                "notes": "LTX latent upscaler from Wan2GP ckpts.",
            }
        )
    return found


def inventory() -> dict[str, Any]:
    """One payload for the Generation assets panel."""
    from .wan2gp_ckpts import CKPTS_DIR, scan_wan2gp_ckpts

    loras = scan_loras()
    tes = list_text_encoder_presets()
    local_tes = [t for t in tes if t.get("local_path")]
    components = scan_vaes_and_components()
    image_models = scan_image_models()
    audio_models = scan_audio_models()
    upsample_models = scan_upsample_models()
    video_extra = scan_video_models()
    video_packs = scan_wan2gp_ckpts() + video_extra
    by_mode: dict[str, int] = {m: 0 for m in ALL_GEN_MODES}
    for pack in video_packs + image_models + audio_models + upsample_models:
        for mode in pack.get("modes") or []:
            if mode in by_mode:
                by_mode[mode] += 1
    return {
        "ckpts_dir": str(CKPTS_DIR),
        "roots": {
            "ckpts": [str(r) for r in ckpts_and_extra_roots()],
            "loras": [str(r) for r in lora_roots()],
        },
        "modes": list(ALL_GEN_MODES),
        "by_mode": by_mode,
        "video_packs": video_packs,
        "image_models": image_models,
        "audio_models": audio_models,
        "upsample_models": upsample_models,
        "loras": loras,
        "text_encoders": tes,
        "local_text_encoders": local_tes,
        "components": components,
        "counts": {
            "video_packs": len(video_packs),
            "image_models": len(image_models),
            "audio_models": len(audio_models),
            "upsample_models": len(upsample_models),
            "loras": len(loras),
            "text_encoders": len(local_tes),
            "video_vaes": len([c for c in components if c["kind"] == "video_vae"]),
            "audio_vaes": len([c for c in components if c["kind"] == "audio_vae"]),
            "vocoders": len([c for c in components if c["kind"] == "vocoder"]),
            "upscalers": len([c for c in components if "upscaler" in c["kind"]]),
        },
    }


def import_wan2gp_root(path: str, *, activate: bool = True) -> dict[str, Any]:
    """Point StudioNels at a Wan2GP install (or ckpts/loras folder) and register everything."""
    from .custom_models import _load, _save
    from .wan2gp_ckpts import import_wan2gp_path

    p = Path(path).expanduser()
    if not p.exists() or not p.is_dir():
        raise ValueError(f"Folder not found: {path}")

    settings = load_settings()
    # Detect whether user pasted Wan2GP root, ckpts, or loras
    if (p / "wgp.py").is_file() or ((p / "ckpts").is_dir() and (p / "loras").is_dir()):
        settings.wan2gp_assets_path = str(p.resolve())
        settings.wan2gp_ckpts_path = str((p / "ckpts").resolve()) if (p / "ckpts").is_dir() else str(p.resolve())
        if (p / "loras").is_dir():
            settings.wan2gp_loras_path = str((p / "loras").resolve())
        settings.wan2gp_text_encoders_path = str(
            (p / "ckpts").resolve() if (p / "ckpts").is_dir() else p.resolve()
        )
        ckpts_path = p / "ckpts" if (p / "ckpts").is_dir() else p
    elif p.name.lower() == "loras" or any((p / s).is_dir() for s in _LORA_HINTS):
        settings.wan2gp_loras_path = str(p.resolve())
        # Parent may be Wan2GP root
        if (p.parent / "wgp.py").is_file():
            settings.wan2gp_assets_path = str(p.parent.resolve())
        ckpts_path = None
    else:
        # Treat as ckpts (or flat dump of safetensors)
        settings.wan2gp_ckpts_path = str(p.resolve())
        settings.wan2gp_text_encoders_path = str(p.resolve())
        sibling = p.parent / "loras"
        if sibling.is_dir():
            settings.wan2gp_loras_path = str(sibling.resolve())
        # Prefer the install that has wgp.py so Generate can use mmgp
        if (p.parent / "wgp.py").is_file():
            settings.wan2gp_assets_path = str(p.parent.resolve())
        elif (p / "wgp.py").is_file():
            settings.wan2gp_assets_path = str(p.resolve())
        ckpts_path = p
    save_settings(settings)

    packs_result: dict[str, Any] = {"packs": []}
    if ckpts_path is not None:
        try:
            packs_result = import_wan2gp_path(str(ckpts_path))
        except ValueError:
            packs_result = {"packs": [], "hint": "No LTX video pack in that folder (ok if image/audio only)."}

    # Register every generation-mode discovery into custom models
    models = _load()
    by_id = {m.get("id"): m for m in models}
    for pack in (
        scan_video_models()
        + scan_image_models()
        + scan_audio_models()
        + scan_upsample_models()
    ):
        by_id[pack["id"]] = {**by_id.get(pack["id"], {}), **pack}
    for pack in packs_result.get("packs") or []:
        by_id[pack["id"]] = {**by_id.get(pack["id"], {}), **pack}
    _save(list(by_id.values()))

    inv = inventory()
    if activate:
        preferred = (
            (packs_result.get("packs") or [None])[0]
            or (inv["image_models"] or [None])[0]
            or (inv["audio_models"] or [None])[0]
            or (inv["upsample_models"] or [None])[0]
        )
        if preferred and preferred.get("id"):
            try:
                from .models_manager import set_active_model

                set_active_model(preferred["id"])
            except Exception:
                pass

    counts = inv.get("counts") or {}
    try:
        from .wan2gp_runtime import clear_architecture_cache, wan2gp_available

        clear_architecture_cache()
        engine_info = wan2gp_available()
    except Exception:
        engine_info = {"available": False}
    root_hint = settings.wan2gp_assets_path or str(p.resolve())
    return {
        "ok": True,
        "path": str(p.resolve()),
        "packs": packs_result.get("packs") or [],
        "inventory": inv,
        "counts": counts,
        "wan2gp_engine": engine_info,
        "hint": (
            "Imported Wan2GP assets. "
            + (
                f"Generate will use the Wan2GP mmgp engine at {engine_info.get('root')}."
                if engine_info.get("available")
                else (
                    f"Linked {root_hint}. For ~1‑min gens, point at the folder that contains "
                    "wgp.py (and its venv), then Generate again."
                )
            )
        ),
    }
