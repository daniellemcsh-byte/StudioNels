"""Discover Wan2GP-style ckpts/ component packs (LTX-2.3, etc.)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..paths import ROOT, ensure_dirs
from ..storage import load_settings

CKPTS_DIR = ROOT / "ckpts"

# Map Wan2GP packs → Diffusers twins StudioNels can actually load today.
_DIFFUSERS_TWIN = {
    "ltx2.3-22b-distilled-1.1": "rootonchair/LTX-2.3-Distilled-v1.1-Diffusers",
    "ltx2.3-22b-distilled": "diffusers/LTX-2.3-Distilled-Diffusers",
    "ltx2-19b-distilled": "rootonchair/LTX-2-19b-distilled",
}


def ckpts_roots() -> list[Path]:
    """StudioNels/ckpts plus optional external Wan2GP ckpts path from Settings."""
    ensure_dirs()
    CKPTS_DIR.mkdir(parents=True, exist_ok=True)
    roots: list[Path] = [CKPTS_DIR]
    try:
        settings = load_settings()
        extra = (getattr(settings, "wan2gp_ckpts_path", None) or "").strip()
        if extra:
            p = Path(extra)
            if p.exists() and p.is_dir() and p.resolve() not in {r.resolve() for r in roots}:
                roots.append(p)
    except Exception:
        pass
    return roots


def _find(
    root: Path,
    *needles: str,
    exclude: tuple[str, ...] = (),
) -> Path | None:
    lower_needles = [n.lower() for n in needles]
    lower_exclude = [e.lower() for e in exclude]
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name.lower()
        if not name.endswith((".safetensors", ".gguf", ".pt", ".bin")):
            continue
        if any(e in name for e in lower_exclude):
            continue
        if all(n in name for n in lower_needles):
            return path
    return None


def _has_components(root: Path) -> dict[str, Path | None]:
    return {
        "dit_distilled_11": _find(root, "ltx-2.3", "distilled-1.1", "diffusion"),
        "dit_distilled": _find(
            root,
            "ltx-2.3",
            "distilled",
            "diffusion",
            exclude=("1.1",),
        ),
        "vae": _find(root, "ltx-2.3", "_vae", exclude=("audio", "upscaler")),
        "audio_vae": _find(root, "ltx-2.3", "audio_vae")
        or _find(root, "ltx-2.3", "audio-vae"),
        "vocoder": _find(root, "ltx-2.3", "vocoder"),
        "connector": _find(root, "ltx-2.3", "embeddings_connector")
        or _find(root, "ltx-2.3", "embedding_connector"),
        "text_proj": _find(root, "ltx-2.3", "text_embedding")
        or _find(root, "ltx-2.3", "text-embedding"),
        "spatial_up": _find(root, "ltx-2.3", "spatial-upscaler")
        or _find(root, "ltx-2.3", "spatial_upscaler"),
        "temporal_up": _find(root, "ltx-2.3", "temporal-upscaler")
        or _find(root, "ltx-2.3", "temporal_upscaler"),
    }


def _pack_from_dit(
    root: Path,
    dit: Path,
    components: dict[str, Path | None],
    *,
    pack_key: str,
    label: str,
) -> dict[str, Any]:
    twin = _DIFFUSERS_TWIN.get(pack_key, "diffusers/LTX-2.3-Distilled-Diffusers")
    files = {
        "diffusion_model": str(dit),
        **{k: str(v) for k, v in components.items() if v and k not in ("dit_distilled", "dit_distilled_11")},
    }
    missing = [
        name
        for name, key in (
            ("vae", "vae"),
            ("audio_vae", "audio_vae"),
            ("vocoder", "vocoder"),
        )
        if components.get(key) is None
    ]
    return {
        "id": f"wan2gp-{pack_key}",
        "label": f"{label} (Wan2GP ckpts)",
        "modes": ["t2v", "i2v"],
        "hf_id": twin,
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
        "custom": True,
        "format": "wan2gp",
        "wan2gp": True,
        "local_path": str(root),
        "component_files": files,
        "notes": (
            f"Wan2GP ckpts pack found in {root}. "
            + (
                f"Missing components: {', '.join(missing)}. "
                if missing
                else "Core components present. "
            )
            + f"StudioNels Generate loads the Diffusers twin ({twin}) — "
            "Download that once in Models, or place the Diffusers folder under models/. "
            "Your Wan2GP files stay here for Wan2GP; no need to move them into loras/."
        ),
    }


def scan_wan2gp_ckpts() -> list[dict[str, Any]]:
    """Return catalog-ready entries for Wan2GP LTX packs on disk."""
    found: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for root in ckpts_roots():
        if not root.exists():
            continue
        comps = _has_components(root)
        # Prefer 1.1 distilled DiT when present
        if comps.get("dit_distilled_11"):
            pack = _pack_from_dit(
                root,
                comps["dit_distilled_11"],  # type: ignore[arg-type]
                comps,
                pack_key="ltx2.3-22b-distilled-1.1",
                label="LTX-2.3 22B Distilled 1.1",
            )
            if pack["id"] not in seen_ids:
                found.append(pack)
                seen_ids.add(pack["id"])
        elif comps.get("dit_distilled"):
            # Avoid matching 1.1 again via loose "distilled"
            name = comps["dit_distilled"].name.lower()  # type: ignore[union-attr]
            if "1.1" not in name:
                pack = _pack_from_dit(
                    root,
                    comps["dit_distilled"],  # type: ignore[arg-type]
                    comps,
                    pack_key="ltx2.3-22b-distilled",
                    label="LTX-2.3 22B Distilled",
                )
                if pack["id"] not in seen_ids:
                    found.append(pack)
                    seen_ids.add(pack["id"])
    return found


def import_wan2gp_path(path: str) -> dict[str, Any]:
    """Register a Wan2GP ckpts folder into settings + return discovered packs."""
    from .custom_models import _load, _save

    p = Path(path).expanduser()
    if not p.exists() or not p.is_dir():
        raise ValueError(f"Folder not found: {path}")

    from ..storage import load_settings, save_settings

    settings = load_settings()
    settings.wan2gp_ckpts_path = str(p.resolve())
    save_settings(settings)

    scanned = scan_wan2gp_ckpts()
    if not scanned:
        raise ValueError(
            "No LTX-2.3 Wan2GP diffusion_model .safetensors found in that folder. "
            "Expected names like ltx-2.3-22b-distilled-1.1_diffusion_model.safetensors "
            "plus vae / audio_vae / vocoder companions."
        )

    models = _load()
    by_id = {m.get("id"): m for m in models}
    packs = []
    for pack in scanned:
        by_id[pack["id"]] = {**by_id.get(pack["id"], {}), **pack}
        packs.append(by_id[pack["id"]])
    _save(list(by_id.values()))

    return {
        "ok": True,
        "path": str(p.resolve()),
        "packs": packs,
        "ckpts_dir": str(CKPTS_DIR),
        "hint": (
            "Wan2GP pack registered. In Models, Download the Diffusers twin once "
            f"({packs[0].get('hf_id')}) so Generate can load it — same weights, Diffusers layout. "
            "Leave your Wan2GP files where they are."
        ),
    }


def write_ckpts_readme() -> Path:
    ensure_dirs()
    CKPTS_DIR.mkdir(parents=True, exist_ok=True)
    readme = CKPTS_DIR / "README.txt"
    readme.write_text(
        "\n".join(
            [
                "StudioNels Wan2GP-compatible ckpts folder",
                "========================================",
                "",
                "Drop Wan2GP LTX-2.3 component .safetensors here (same names as Wan2GP/ckpts),",
                "OR in Settings set wan2gp_ckpts_path to your existing Wan2GP\\ckpts folder",
                "(no need to copy 19GB).",
                "",
                "Example files:",
                "  ltx-2.3-22b-distilled-1.1_diffusion_model.safetensors",
                "  ltx-2.3-22b_vae.safetensors",
                "  ltx-2.3-22b_audio_vae.safetensors",
                "  ltx-2.3-22b_vocoder.safetensors",
                "  ltx-2.3-22b_embeddings_connector....safetensors",
                "  ltx-2.3-22b_text_embedding_projection....safetensors",
                "",
                "Do NOT put these in loras/.",
                "Generate still needs the Diffusers twin under models/ (download once in Models tab).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return readme
