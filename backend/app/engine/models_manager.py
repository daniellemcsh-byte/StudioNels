from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..models import new_id, utc_now
from ..paths import MODEL_DOWNLOADS_PATH, ensure_dirs
from .catalog import MODELS, get_model
from .queue_store import loras_dir, models_dir

_LOCK = threading.Lock()
_DOWNLOADS: dict[str, dict[str, Any]] = {}


def _status_path() -> Path:
    ensure_dirs()
    return MODEL_DOWNLOADS_PATH


def _load_status() -> dict[str, Any]:
    path = _status_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_status(data: dict[str, Any]) -> None:
    path = _status_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _hf_cache_has(repo_id: str | None) -> bool:
    if not repo_id:
        return True  # local-only (lanczos)
    try:
        from huggingface_hub import try_to_load_from_cache

        # Presence of config or model index is enough signal
        for name in (
            "model_index.json",
            "config.json",
            "configuration.json",
        ):
            cached = try_to_load_from_cache(repo_id, name)
            if cached and cached != "___not_found___":
                return True
    except Exception:
        pass
    # Also check StudioNels models mirror
    mirror = models_dir() / repo_id.replace("/", "__")
    if mirror.exists() and any(mirror.iterdir()):
        return True
    return False


def list_models_with_status(active_model_id: str | None = None) -> list[dict[str, Any]]:
    status = _load_status()
    settings_active = active_model_id or status.get("active_model_id")
    out = []
    for m in MODELS:
        mid = m["id"]
        dl = status.get("downloads", {}).get(mid) or _DOWNLOADS.get(mid) or {}
        installed = bool(dl.get("installed")) or _hf_cache_has(m.get("hf_id"))
        if m.get("hf_id") is None:
            installed = True
        out.append(
            {
                **m,
                "installed": installed,
                "active": settings_active == mid,
                "download_status": dl.get("status") or ("installed" if installed else "not_downloaded"),
                "download_progress": float(dl.get("progress") or (1.0 if installed else 0.0)),
                "download_error": dl.get("error"),
                "local_path": dl.get("local_path"),
            }
        )
    return out


def get_active_model_id() -> str | None:
    return _load_status().get("active_model_id")


def set_active_model(model_id: str) -> dict[str, Any]:
    model = get_model(model_id)
    if not model:
        raise ValueError(f"Unknown model {model_id}")
    data = _load_status()
    data["active_model_id"] = model_id
    data["updated_at"] = utc_now()
    _save_status(data)
    return {"ok": True, "active_model_id": model_id, "model": model}


def _set_download(model_id: str, **fields: Any) -> dict[str, Any]:
    with _LOCK:
        data = _load_status()
        downloads = data.setdefault("downloads", {})
        cur = downloads.get(model_id) or {}
        cur.update(fields)
        downloads[model_id] = cur
        _DOWNLOADS[model_id] = cur
        _save_status(data)
        return cur


def download_model(model_id: str) -> dict[str, Any]:
    model = get_model(model_id)
    if not model:
        raise ValueError(f"Unknown model {model_id}")
    if not model.get("hf_id"):
        return _set_download(
            model_id,
            status="installed",
            progress=1.0,
            installed=True,
            message="Built-in (no download)",
        )

    existing = _DOWNLOADS.get(model_id) or _load_status().get("downloads", {}).get(model_id) or {}
    if existing.get("status") == "downloading":
        return existing

    job = _set_download(
        model_id,
        status="downloading",
        progress=0.05,
        installed=False,
        error=None,
        started_at=utc_now(),
        hf_id=model["hf_id"],
        message="Starting download…",
    )

    def worker() -> None:
        try:
            from huggingface_hub import snapshot_download

            dest = models_dir() / model["hf_id"].replace("/", "__")
            dest.mkdir(parents=True, exist_ok=True)

            def _cb(progress: Any) -> None:
                # huggingface progress callback shapes vary; keep soft updates
                try:
                    frac = float(getattr(progress, "progress", None) or 0)
                except Exception:
                    frac = 0.2
                _set_download(
                    model_id,
                    status="downloading",
                    progress=max(0.05, min(0.95, frac or 0.35)),
                    message="Downloading from Hugging Face…",
                )

            _set_download(model_id, progress=0.15, message="Fetching snapshot…")
            path = snapshot_download(
                repo_id=model["hf_id"],
                local_dir=str(dest),
                local_dir_use_symlinks=False,
            )
            _set_download(
                model_id,
                status="installed",
                progress=1.0,
                installed=True,
                local_path=str(path),
                finished_at=utc_now(),
                message="Ready",
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            _set_download(
                model_id,
                status="failed",
                progress=0.0,
                installed=False,
                error=str(exc),
                message=str(exc),
            )

    threading.Thread(target=worker, name=f"dl-{model_id}", daemon=True).start()
    return job


def list_loras() -> list[dict[str, Any]]:
    root = loras_dir()
    items = []
    for path in sorted(root.rglob("*")):
        if path.name.upper().startswith("README"):
            continue
        if path.suffix.lower() in {".safetensors", ".pt", ".bin", ".gguf"}:
            items.append(
                {
                    "id": path.stem,
                    "name": path.name,
                    "path": str(path),
                    "size_mb": round(path.stat().st_size / (1024 * 1024), 1),
                }
            )
    return items
