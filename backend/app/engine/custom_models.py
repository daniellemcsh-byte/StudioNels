"""User-registered + locally discovered Diffusers models (big GPU / already downloaded)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import utc_now
from ..paths import CACHE_DIR, ensure_dirs
from .queue_store import models_dir

CUSTOM_MODELS_PATH = CACHE_DIR / "custom_models.json"


def _path() -> Path:
    ensure_dirs()
    return CUSTOM_MODELS_PATH


def _load() -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("models") or [])
    except Exception:
        return []


def _save(models: list[dict[str, Any]]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"models": models, "updated_at": utc_now()}, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def list_custom_models() -> list[dict[str, Any]]:
    return _load()


def _slug_id(hf_id: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9._-]+", "-", hf_id.strip().replace("/", "-")).strip("-").lower()
    return f"custom-{raw}"[:80]


def add_custom_model(
    *,
    hf_id: str,
    label: str | None = None,
    modes: list[str] | None = None,
    kind: str = "video",
    min_vram_gb: float = 24,
    default_steps: int = 20,
    default_guidance: float = 5.0,
    notes: str | None = None,
    local_path: str | None = None,
) -> dict[str, Any]:
    hf_id = (hf_id or "").strip().strip("/")
    if not hf_id or "/" not in hf_id:
        raise ValueError("hf_id must look like owner/repo (Hugging Face id)")
    modes = modes or (["t2v", "i2v"] if kind == "video" else ["t2i"])
    mid = _slug_id(hf_id)
    entry = {
        "id": mid,
        "label": label or hf_id.split("/")[-1],
        "modes": modes,
        "hf_id": hf_id,
        "pipeline": "DiffusionPipeline",
        "min_vram_gb": float(min_vram_gb),
        "default_steps": int(default_steps),
        "default_guidance": float(default_guidance),
        "kind": kind,
        "default_frames": 49 if kind == "video" else None,
        "fps": 24 if kind == "video" else None,
        "supports_lora": True,
        "tier": "big" if min_vram_gb >= 20 else "mid",
        "custom": True,
        "notes": notes or f"Custom Hugging Face model · {hf_id}",
        "local_path": local_path,
        "added_at": utc_now(),
    }
    models = [m for m in _load() if m.get("id") != mid and m.get("hf_id") != hf_id]
    models.append(entry)
    _save(models)
    return entry


def remove_custom_model(model_id: str) -> dict[str, Any]:
    models = _load()
    kept = [m for m in models if m.get("id") != model_id]
    if len(kept) == len(models):
        raise ValueError("Custom model not found")
    _save(kept)
    return {"ok": True, "id": model_id}


def discover_local_models(known_hf_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Scan models/ for Diffusers folders already on disk (no re-download)."""
    known = known_hf_ids or set()
    root = models_dir()
    found: list[dict[str, Any]] = []
    if not root.exists():
        return found
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        index = path / "model_index.json"
        if not index.exists():
            continue
        # Folder naming: Owner__Repo
        hf_id = path.name.replace("__", "/", 1) if "__" in path.name else path.name
        if hf_id in known:
            continue
        kind = "video"
        modes = ["t2v", "i2v"]
        try:
            meta = json.loads(index.read_text(encoding="utf-8"))
            pipe_class = str(meta.get("_class_name") or "")
            if "Audio" in pipe_class:
                kind = "audio"
                modes = ["t2a"]
            elif "Image" in pipe_class and "Video" not in pipe_class:
                kind = "image"
                modes = ["t2i", "ref2i"]
        except Exception:
            pass
        found.append(
            {
                "id": _slug_id(hf_id),
                "label": f"{path.name.split('__')[-1]} (local)",
                "modes": modes,
                "hf_id": hf_id,
                "pipeline": "DiffusionPipeline",
                "min_vram_gb": 16,
                "default_steps": 20,
                "default_guidance": 5.0,
                "kind": kind,
                "default_frames": 49 if kind == "video" else None,
                "fps": 16 if kind == "video" else None,
                "supports_lora": True,
                "tier": "big",
                "custom": True,
                "discovered": True,
                "local_path": str(path),
                "notes": f"Found on disk in models/{path.name} — already downloaded.",
            }
        )
    return found
