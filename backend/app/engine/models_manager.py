from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from ..models import utc_now
from ..paths import MODEL_DOWNLOADS_PATH, ensure_dirs
from .catalog import _all_models, get_model
from .queue_store import loras_dir, models_dir

_LOCK = threading.Lock()
_DOWNLOADS: dict[str, dict[str, Any]] = {}
_CANCEL: dict[str, bool] = {}
_THREADS: dict[str, threading.Thread] = {}


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
    for m in _all_models():
        mid = m["id"]
        dl = status.get("downloads", {}).get(mid) or _DOWNLOADS.get(mid) or {}
        local = dl.get("local_path") or m.get("local_path")
        wan2gp_ready = bool(m.get("wan2gp") and m.get("component_files", {}).get("diffusion_model"))
        installed = (
            bool(dl.get("installed"))
            or bool(local and Path(str(local)).exists() and (m.get("format") != "wan2gp" or wan2gp_ready))
            or _hf_cache_has(m.get("hf_id"))
            or bool(m.get("discovered"))
            or wan2gp_ready
        )
        if m.get("hf_id") is None:
            installed = True
        # Stuck "downloading" with no live thread → expose as stalled so UI can clear it
        dl_status = dl.get("status") or ("installed" if installed else "not_downloaded")
        if dl_status == "downloading":
            live = _THREADS.get(mid)
            if live is None or not live.is_alive():
                dl_status = "stalled"
        if installed and dl_status == "not_downloaded":
            dl_status = "installed"
        out.append(
            {
                **m,
                "installed": installed,
                "active": settings_active == mid,
                "download_status": dl_status,
                "download_progress": float(dl.get("progress") or (1.0 if installed else 0.0)),
                "download_error": dl.get("error"),
                "download_message": dl.get("message")
                or ("Ready on disk" if installed and not dl.get("message") else dl.get("message")),
                "local_path": local,
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
        return dict(cur)


def _is_cancelled(model_id: str) -> bool:
    return bool(_CANCEL.get(model_id))


def cancel_download(model_id: str) -> dict[str, Any]:
    """Mark an in-flight or stuck download as cancelled so the UI can recover."""
    model = get_model(model_id)
    if not model:
        raise ValueError(f"Unknown model {model_id}")
    _CANCEL[model_id] = True
    cur = _set_download(
        model_id,
        status="cancelled",
        progress=0.0,
        installed=False,
        error=None,
        message="Cancelled — tap Download to retry",
        finished_at=utc_now(),
    )
    return {"ok": True, "model_id": model_id, "download": cur}


def clear_download(model_id: str, *, delete_files: bool = False) -> dict[str, Any]:
    """Clear stuck/cancelled/failed download state (optionally wipe partial files)."""
    model = get_model(model_id)
    if not model:
        raise ValueError(f"Unknown model {model_id}")
    _CANCEL[model_id] = True
    if delete_files and model.get("hf_id"):
        dest = models_dir() / str(model["hf_id"]).replace("/", "__")
        if dest.exists():
            try:
                shutil.rmtree(dest, ignore_errors=True)
            except Exception:
                pass
    with _LOCK:
        data = _load_status()
        downloads = data.setdefault("downloads", {})
        downloads.pop(model_id, None)
        _DOWNLOADS.pop(model_id, None)
        _save_status(data)
    _CANCEL.pop(model_id, None)
    return {"ok": True, "model_id": model_id, "cleared": True}


def download_model(model_id: str, *, force: bool = False) -> dict[str, Any]:
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
    live = _THREADS.get(model_id)
    if existing.get("status") == "downloading" and live and live.is_alive() and not force:
        return existing

    if force:
        _CANCEL[model_id] = True
        # brief pause so an old worker can notice cancel before we reset
        time.sleep(0.05)

    _CANCEL[model_id] = False
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

            _set_download(model_id, progress=0.08, message="Connecting to Hugging Face…")
            if _is_cancelled(model_id):
                raise RuntimeError("cancelled")

            # Soft heartbeat + folder-size estimate while snapshot_download blocks.
            stop_beat = threading.Event()
            started = time.time()

            def _dir_bytes(root: Path) -> int:
                total = 0
                try:
                    for p in root.rglob("*"):
                        if p.is_file():
                            try:
                                total += p.stat().st_size
                            except OSError:
                                pass
                except OSError:
                    pass
                return total

            # Rough expected size from catalog VRAM hint (GB weights ≈ min_vram * 0.6) — floor 2GB
            expect = max(2.0, float(model.get("min_vram_gb") or 4) * 0.75) * (1024**3)

            def heartbeat() -> None:
                while not stop_beat.wait(2.0):
                    if _is_cancelled(model_id):
                        return
                    cur = _DOWNLOADS.get(model_id) or {}
                    if cur.get("status") != "downloading":
                        return
                    have = _dir_bytes(dest)
                    by_size = 0.08 + 0.82 * min(1.0, have / expect)
                    elapsed = int(time.time() - started)
                    # Never go backwards; never claim 100% until snapshot finishes
                    tick = min(0.92, max(float(cur.get("progress") or 0.05), by_size))
                    mb = have / (1024 * 1024)
                    _set_download(
                        model_id,
                        progress=tick,
                        message=f"Downloading… {mb:.0f} MB on disk · {elapsed}s",
                    )

            beat = threading.Thread(target=heartbeat, name=f"dl-beat-{model_id}", daemon=True)
            beat.start()
            try:
                path = snapshot_download(
                    repo_id=model["hf_id"],
                    local_dir=str(dest),
                    local_dir_use_symlinks=False,
                    resume_download=True,
                )
            finally:
                stop_beat.set()

            if _is_cancelled(model_id):
                _set_download(
                    model_id,
                    status="cancelled",
                    progress=0.0,
                    installed=False,
                    message="Cancelled — tap Download to retry",
                    finished_at=utc_now(),
                )
                return

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
            if _is_cancelled(model_id) or "cancelled" in str(exc).lower():
                _set_download(
                    model_id,
                    status="cancelled",
                    progress=0.0,
                    installed=False,
                    error=None,
                    message="Cancelled — tap Download to retry",
                    finished_at=utc_now(),
                )
            else:
                _set_download(
                    model_id,
                    status="failed",
                    progress=0.0,
                    installed=False,
                    error=str(exc),
                    message=str(exc),
                    finished_at=utc_now(),
                )
        finally:
            _THREADS.pop(model_id, None)

    t = threading.Thread(target=worker, name=f"dl-{model_id}", daemon=True)
    _THREADS[model_id] = t
    t.start()
    return job


def list_loras() -> list[dict[str, Any]]:
    """StudioNels loras/ plus optional Wan2GP loras folders from Settings."""
    try:
        from .wan2gp_assets import scan_loras

        return scan_loras()
    except Exception:
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


def get_asset_download(asset_id: str) -> dict[str, Any] | None:
    """Status for a non-catalog HF asset (TE / VAE / LoRA / upscaler)."""
    key = f"asset:{asset_id}"
    return _DOWNLOADS.get(key) or _load_status().get("downloads", {}).get(key)


def download_hf_asset(
    *,
    asset_id: str,
    hf_id: str,
    dest: str = "models",
    label: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Download any Hugging Face repo into models/ or loras/ (template extras)."""
    hf_id = (hf_id or "").strip().strip("/")
    if not hf_id or "/" not in hf_id:
        raise ValueError("hf_id must look like owner/repo")
    key = f"asset:{asset_id}"
    existing = get_asset_download(asset_id) or {}
    live = _THREADS.get(key)
    if existing.get("status") == "downloading" and live and live.is_alive() and not force:
        return existing
    if existing.get("status") == "installed" and not force:
        return existing

    if force:
        _CANCEL[key] = True
        time.sleep(0.05)
    _CANCEL[key] = False

    root = loras_dir() if dest == "loras" else models_dir()
    folder = root / hf_id.replace("/", "__")
    job = _set_download(
        key,
        status="downloading",
        progress=0.05,
        installed=False,
        error=None,
        started_at=utc_now(),
        hf_id=hf_id,
        label=label or hf_id,
        dest=dest,
        message=f"Starting {label or hf_id}…",
    )

    def worker() -> None:
        try:
            from huggingface_hub import snapshot_download

            folder.mkdir(parents=True, exist_ok=True)
            _set_download(key, progress=0.08, message=f"Connecting… {hf_id}")
            if _is_cancelled(key):
                raise RuntimeError("cancelled")

            stop_beat = threading.Event()
            started = time.time()

            def _dir_bytes(p: Path) -> int:
                total = 0
                try:
                    for f in p.rglob("*"):
                        if f.is_file():
                            try:
                                total += f.stat().st_size
                            except OSError:
                                pass
                except OSError:
                    pass
                return total

            def heartbeat() -> None:
                while not stop_beat.wait(2.0):
                    if _is_cancelled(key):
                        return
                    cur = _DOWNLOADS.get(key) or {}
                    if cur.get("status") != "downloading":
                        return
                    have = _dir_bytes(folder)
                    elapsed = int(time.time() - started)
                    tick = min(0.92, max(float(cur.get("progress") or 0.05), 0.08 + min(0.8, have / (8 * 1024**3))))
                    _set_download(
                        key,
                        progress=tick,
                        message=f"{label or hf_id}: {have / (1024 * 1024):.0f} MB · {elapsed}s",
                    )

            beat = threading.Thread(target=heartbeat, name=f"dl-beat-{key}", daemon=True)
            beat.start()
            try:
                path = snapshot_download(
                    repo_id=hf_id,
                    local_dir=str(folder),
                    local_dir_use_symlinks=False,
                    resume_download=True,
                )
            finally:
                stop_beat.set()

            if _is_cancelled(key):
                _set_download(
                    key,
                    status="cancelled",
                    progress=0.0,
                    installed=False,
                    message="Cancelled",
                    finished_at=utc_now(),
                )
                return

            _set_download(
                key,
                status="installed",
                progress=1.0,
                installed=True,
                local_path=str(path),
                finished_at=utc_now(),
                message="Ready",
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_cancelled(key) or "cancelled" in str(exc).lower():
                _set_download(
                    key,
                    status="cancelled",
                    progress=0.0,
                    installed=False,
                    message="Cancelled",
                    finished_at=utc_now(),
                )
            else:
                _set_download(
                    key,
                    status="failed",
                    progress=0.0,
                    installed=False,
                    error=str(exc),
                    message=str(exc),
                    finished_at=utc_now(),
                )
        finally:
            _THREADS.pop(key, None)

    t = threading.Thread(target=worker, name=f"dl-{key}", daemon=True)
    _THREADS[key] = t
    t.start()
    return job
