"""Wan2GP-style model family → variant grouping for the Generate picker."""

from __future__ import annotations

from typing import Any

from .catalog import _all_models

# Preferred display order for families in the three-box selector
_FAMILY_ORDER = [
    "Wan2.2",
    "Wan2.1",
    "LTX",
    "MiniMax",
    "Hunyuan",
    "CogVideoX",
    "SkyReels",
    "Kandinsky",
    "LongCat",
    "Mochi",
    "Image",
    "Audio",
    "Upsample",
    "Other",
]

_CONFIG_PRESETS = [
    {"id": "default", "label": "Default"},
    {"id": "fast", "label": "Fast (fewer steps)"},
    {"id": "quality", "label": "Quality (more steps)"},
    {"id": "low_vram", "label": "Low VRAM (offload)"},
]


def _infer_family(m: dict[str, Any]) -> str:
    if m.get("family"):
        return str(m["family"])
    mid = str(m.get("id") or "").lower()
    label = str(m.get("label") or "").lower()
    if mid.startswith("wan22") or "wan 2.2" in label or "wan2.2" in label:
        return "Wan2.2"
    if mid.startswith("wan21") or "wan 2.1" in label or "wan2.1" in label:
        return "Wan2.1"
    if "ltx" in mid or "ltx" in label:
        return "LTX"
    if "minimax" in mid or "minimax" in label or "hailuo" in mid:
        return "MiniMax"
    if "hunyuan" in mid or "hunyuan" in label:
        return "Hunyuan"
    if "cogvideo" in mid or "cogvideo" in label:
        return "CogVideoX"
    if "skyreels" in mid or "skyreels" in label:
        return "SkyReels"
    if "kandinsky" in mid or "kandinsky" in label:
        return "Kandinsky"
    if "longcat" in mid or "longcat" in label:
        return "LongCat"
    if "mochi" in mid or "mochi" in label:
        return "Mochi"
    kind = str(m.get("kind") or "")
    if kind == "image" or mid.startswith(("sd", "flux", "krea", "qwen", "pixart", "aura", "playground")):
        return "Image"
    if kind == "audio" or "t2a" in (m.get("modes") or []) or mid.startswith(("musicgen", "audioldm", "ace", "index")):
        return "Audio"
    if "upsample" in mid or kind == "upsample" or "esrgan" in mid or "swinir" in mid or "seedvr" in mid:
        return "Upsample"
    return "Other"


def _infer_variant(m: dict[str, Any]) -> str:
    if m.get("variant"):
        return str(m["variant"])
    label = str(m.get("label") or m.get("id") or "Model")
    # Strip common suffixes for compact Wan2GP-style names
    for junk in (" (big GPU)", " (Wan2GP ckpts)", " (video+audio)"):
        label = label.replace(junk, "")
    return label.strip()


def list_model_families(mode: str | None = None) -> dict[str, Any]:
    models = _all_models()
    if mode:
        models = [m for m in models if mode in (m.get("modes") or [])]

    families: dict[str, list[dict[str, Any]]] = {}
    for m in models:
        fam = _infer_family(m)
        entry = {
            **m,
            "family": fam,
            "variant": _infer_variant(m),
        }
        families.setdefault(fam, []).append(entry)

    ordered = []
    seen = set()
    for name in _FAMILY_ORDER:
        if name in families:
            ordered.append(
                {
                    "id": name,
                    "label": name,
                    "variants": sorted(
                        families[name],
                        key=lambda x: (str(x.get("variant") or "").lower(), x.get("id")),
                    ),
                }
            )
            seen.add(name)
    for name in sorted(families.keys()):
        if name in seen:
            continue
        ordered.append(
            {
                "id": name,
                "label": name,
                "variants": sorted(
                    families[name],
                    key=lambda x: (str(x.get("variant") or "").lower(), x.get("id")),
                ),
            }
        )

    return {
        "families": ordered,
        "configs": _CONFIG_PRESETS,
        "count": sum(len(f["variants"]) for f in ordered),
    }


def apply_config_preset(job_fields: dict[str, Any], config_id: str) -> dict[str, Any]:
    """Mutate generate payload hints from a config preset id."""
    out = dict(job_fields)
    cid = (config_id or "default").lower()
    if cid == "fast":
        out["quality"] = out.get("quality") or "draft"
        if not out.get("steps"):
            out["steps"] = 8
    elif cid == "quality":
        out["quality"] = "high"
        if not out.get("steps"):
            out["steps"] = 30
    elif cid == "low_vram":
        out["cpu_offload"] = True
        out["memory_profile"] = out.get("memory_profile") or "vram-12"
    return out
