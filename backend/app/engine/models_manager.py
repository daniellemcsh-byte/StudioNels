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

        # A real config file AND weights next to it. try_to_load_from_cache
        # returns a truthy "_CACHED_NO_EXIST" marker for files the hub said are
        # missing, and a config alone is not a model: both used to count as
        # installed, so Generate silently downloaded the weights instead.
        for name in (
            "model_index.json",
            "config.json",
            "configuration.json",
        ):
            cached = try_to_load_from_cache(repo_id, name)
            if not isinstance(cached, str) or not Path(cached).is_file():
                continue
            snapshot = Path(cached).parent
            for pattern in ("*.safetensors", "*.bin", "*.pt", "*.ckpt", "*.gguf"):
                if any(p.is_file() and p.stat().st_size > 1024 for p in snapshot.rglob(pattern)):
                    return True
    except Exception:
        pass
    # Also check StudioNels models mirror
    mirror = models_dir() / repo_id.replace("/", "__")
    if mirror.exists() and any(mirror.iterdir()):
        return True
    return False


def _one_weight_copy_per_folder(files: list[str]) -> list[str]:
    """Some repos ship the same weights twice per folder: a single file plus a
    sharded set, or two shard sets (LTX-2.5: -of-00004 and -of-00008). Keep one:
    the single file if present (and drop the shard index so it is the one that
    loads), otherwise the set with the fewest shards."""
    import re

    shard = re.compile(r"^(.*)-\d{5}-of-(\d{5})(\.safetensors)$")
    by_dir: dict[str, list[str]] = {}
    for f in files:
        by_dir.setdefault(f.rsplit("/", 1)[0] if "/" in f else "", []).append(f)
    out: list[str] = []
    for folder, names in by_dir.items():
        sets: dict[str, list[str]] = {}
        singles = set()
        for f in names:
            m = shard.match(f.rsplit("/", 1)[-1])
            if m:
                sets.setdefault(m.group(2), []).append(f)
            elif f.endswith(".safetensors"):
                singles.add(f.rsplit("/", 1)[-1])
        has_single_twin = any(
            s.replace(".safetensors", "") == (shard.match(f.rsplit("/", 1)[-1]).group(1) if shard.match(f.rsplit("/", 1)[-1]) else "")
            for s in singles
            for group in sets.values()
            for f in group
        )
        keep_set = None if has_single_twin else (min(sets, key=int) if sets else None)
        for f in names:
            base = f.rsplit("/", 1)[-1]
            m = shard.match(base)
            if m:
                if m.group(2) == keep_set:
                    out.append(f)
                continue
            if has_single_twin and base.endswith(".safetensors.index.json"):
                continue
            out.append(f)
    return out


def _slim_files(repo_id: str) -> list[str] | None:
    """Files worth downloading from a Diffusers pipeline repo, or None for "all".

    Repos like stabilityai/stable-diffusion-xl-base-1.0 also carry root single-file
    checkpoints, ONNX/OpenVINO/Flax exports and fp32 + fp16 copies of every weight
    (~70 GB) when the pipeline needs ~7 GB.
    """
    try:
        from huggingface_hub import HfApi

        files = HfApi().list_repo_files(repo_id)
    except Exception:
        return None
    if "model_index.json" not in files:
        return None
    keep = []
    for f in files:
        low = f.lower()
        if "/" not in f and low.endswith((".safetensors", ".ckpt", ".bin", ".pt", ".pth")):
            continue  # single-file checkpoint duplicating the folders
        if any(x in low for x in ("onnx", "openvino", "flax_model", ".msgpack", ".h5", "tf_model")):
            continue
        keep.append(f)
    # Optional extras StudioNels never loads: LTX-2.5's full/SFT DiT (38 GB), its
    # 10 GB prompt enhancer (we write prompts ourselves) and the diffusion decoder
    # (needs a CUDA-only NATTEN kernel).
    skip_dirs = ("transformer_full/", "prompt_enhancer/", "diffusion_decoder/")
    keep = [f for f in keep if not f.startswith(skip_dirs)]
    keep = _one_weight_copy_per_folder(keep)
    kept = set(keep)
    out = []
    for f in keep:
        if ".fp16." not in f:
            for ext in (".safetensors", ".bin"):
                if f.endswith(ext) and f[: -len(ext)] + ".fp16" + ext in kept:
                    break  # an fp16 copy exists; skip the fp32 one
            else:
                if f.endswith(".bin") and f[:-4] + ".safetensors" in kept:
                    continue
                out.append(f)
            continue
        out.append(f)
    return out


def apply_download_swap(folder: Path, swap: dict[str, str]) -> None:
    """Put an alternative component where the pipeline loads from, e.g. LTX-2.5's
    transformer_full/ into transformer/. Anything already there is removed first
    (it is the variant the user chose not to use)."""
    import shutil

    for src_name, dst_name in (swap or {}).items():
        src, dst = Path(folder) / src_name, Path(folder) / dst_name
        if not src.is_dir() or not any(src.glob("*.safetensors")):
            continue
        if dst.exists():
            shutil.rmtree(dst)
        src.rename(dst)
        # Its saved 8-bit copy is for the old weights
        for cached in (Path(folder) / "_studionels_int8").glob(f"*/{dst_name}"):
            shutil.rmtree(cached, ignore_errors=True)


def _slim_snapshot(repo_id: str, folder: Path, swap: dict[str, str] | None = None) -> str:
    """snapshot_download limited to what the pipeline loads; fp16 files renamed
    to plain names so from_pretrained finds them without variant=."""
    from huggingface_hub import snapshot_download

    allow = _slim_files(repo_id)
    if allow is not None and swap:
        # Fetch the chosen variant (e.g. transformer_full/) instead of the default one
        try:
            from huggingface_hub import HfApi

            every = HfApi().list_repo_files(repo_id)
        except Exception:
            every = []
        wanted = tuple(f"{s}/" for s in swap)
        replaced = tuple(f"{d}/" for d in swap.values())
        allow = [f for f in allow if not f.startswith(replaced)] + _one_weight_copy_per_folder(
            [f for f in every if f.startswith(wanted)]
        )
    path = snapshot_download(
        repo_id=repo_id,
        local_dir=str(folder),
        local_dir_use_symlinks=False,
        resume_download=True,
        allow_patterns=allow,
    )
    if allow is not None:
        for f in Path(folder).rglob("*.fp16.*"):
            plain = f.with_name(f.name.replace(".fp16.", "."))
            if not plain.exists():
                f.rename(plain)
    if swap:
        apply_download_swap(Path(folder), swap)
    return path


_STATUS_CACHE: dict[str, Any] = {"at": 0.0, "key": None, "rows": None}


def list_models_with_status(active_model_id: str | None = None) -> list[dict[str, Any]]:
    now = time.time()
    key = active_model_id or ""
    cached = _STATUS_CACHE.get("rows")
    if (
        cached is not None
        and _STATUS_CACHE.get("key") == key
        and now - float(_STATUS_CACHE.get("at") or 0) < 3
    ):
        return [dict(row) for row in cached]
    rows = _list_models_with_status(active_model_id)
    _STATUS_CACHE["at"] = now
    _STATUS_CACHE["key"] = key
    _STATUS_CACHE["rows"] = rows
    return [dict(row) for row in rows]


def _list_models_with_status(active_model_id: str | None = None) -> list[dict[str, Any]]:
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
            # Built-in tools; ones with weights (RIFE) only count when the file is there
            installed = all((models_dir() / f).is_file() for f in (m.get("local_files") or []))
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

            # Rough expected pack size from catalog (weights often ≈ min_vram × 0.55–0.9)
            expect = max(1.5, float(model.get("min_vram_gb") or 4) * 0.7) * (1024**3)

            def heartbeat() -> None:
                while not stop_beat.wait(1.0):
                    if _is_cancelled(model_id):
                        return
                    cur = _DOWNLOADS.get(model_id) or {}
                    if cur.get("status") != "downloading":
                        return
                    have = _dir_bytes(dest)
                    by_size = 0.08 + 0.84 * min(1.0, have / expect)
                    elapsed = int(time.time() - started)
                    # Soft crawl so the bar never looks frozen while HF is quiet
                    crawl = 0.08 + min(0.35, elapsed / 600.0)
                    tick = min(0.95, max(float(cur.get("progress") or 0.05), by_size, crawl))
                    if have >= 1024**3:
                        size_lbl = f"{have / (1024**3):.2f} GB"
                    else:
                        size_lbl = f"{have / (1024 * 1024):.0f} MB"
                    pct = int(tick * 100)
                    _set_download(
                        model_id,
                        progress=tick,
                        message=f"{pct}% · {size_lbl} on disk · {elapsed}s",
                    )

            beat = threading.Thread(target=heartbeat, name=f"dl-beat-{model_id}", daemon=True)
            beat.start()
            try:
                path = _slim_snapshot(model["hf_id"], dest, model.get("download_swap"))
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
                path = _slim_snapshot(hf_id, folder)
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
