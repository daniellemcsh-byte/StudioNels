from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import new_id, utc_now
from ..paths import MEDIA_DIR, ensure_dirs
from ..storage import get_preset, load_settings
from .catalog import (
    GENERATION_MODES,
    QUALITY_PRESETS,
    SIZE_PRESETS,
    TEXT_ENCODER_PRESETS,
    default_model_for_mode,
    get_model,
    list_models_for_mode,
)
from .device import detect_device
from .pipelines import mux_audio_onto_video, run_diffusers_job, run_preview_job
from .queue_store import get_job as store_get
from .queue_store import list_jobs as store_list
from .queue_store import loras_dir, models_dir
from .queue_store import remove_job as store_remove
from .queue_store import upsert_job

_WORKER_STARTED = False
_QUEUE: list[str] = []
_CV = threading.Condition()
_CANCEL: dict[str, bool] = {}
_CURRENT_JOB_ID: str | None = None
_CURRENT_PROC: Any = None
_PROC_LOCK = threading.Lock()

# If Diffusers/ROCm stops writing progress this long, treat as hung.
_STALL_SEC = 120
# Hard cap for a whole job.
_MAX_JOB_SEC = 30 * 60
# First denoise step should arrive well before this on a healthy GPU path.
_FIRST_STEP_SEC = 8 * 60
# Safety cap only. A warm mmgp load should finish well inside this.
_LOAD_MAX_SEC = 8 * 60
# After last denoise step, VAE decode can be slow on AMD — but not forever.
_POST_STEP_MAX_SEC = 10 * 60


def _text_encoder_presets() -> list[dict[str, Any]]:
    try:
        from .wan2gp_assets import list_text_encoder_presets

        return list_text_encoder_presets()
    except Exception:
        return list(TEXT_ENCODER_PRESETS)


def _memory_profiles_public() -> list[dict[str, Any]]:
    try:
        from .memory import list_memory_profiles

        return list_memory_profiles()
    except Exception:
        return []


def _snap_job_dim(value: Any, multiple: int = 32) -> int:
    """LTX / Wan need width & height divisible by 32."""
    from .pipelines import snap_dim

    try:
        return snap_dim(int(value), multiple)
    except Exception:
        return snap_dim(768 if multiple else 768, multiple)


class JobCancelled(Exception):
    """Raised when the user stops a generation job."""


@dataclass
class EngineStatus:
    device: dict[str, Any]
    modes: list[dict[str, Any]]
    models: list[dict[str, Any]]
    queue_length: int
    preset_id: str
    models_path: str


def engine_status() -> EngineStatus:
    settings = load_settings()
    device = detect_device()
    return EngineStatus(
        device=device,
        modes=GENERATION_MODES,
        models=list_models_for_mode("t2i")
        + list_models_for_mode("t2v")
        + list_models_for_mode("i2v")
        + list_models_for_mode("ref2i")
        + list_models_for_mode("ref2v"),
        queue_length=len(_QUEUE),
        preset_id=settings.preset_id,
        models_path=str(models_dir()),
    )


def _dedupe_models(status: EngineStatus) -> EngineStatus:
    seen = set()
    unique = []
    for m in status.models:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        unique.append(m)
    status.models = unique
    return status


def engine_status_public() -> dict[str, Any]:
    from .models_manager import get_active_model_id, list_loras, list_models_with_status

    st = _dedupe_models(engine_status())
    loras = list_loras()
    active = get_active_model_id()
    # Merge download / active flags onto catalog models shown in Generate
    status_by_id = {m["id"]: m for m in list_models_with_status(active)}
    enriched = []
    for m in st.models:
        extra = status_by_id.get(m["id"]) or {}
        enriched.append(
            {
                **m,
                "installed": extra.get("installed", False),
                "active": extra.get("active", False),
                "download_status": extra.get("download_status"),
                "download_progress": extra.get("download_progress"),
                "download_error": extra.get("download_error"),
                "download_message": extra.get("download_message"),
            }
        )
    try:
        from .wan2gp_runtime import wan2gp_available

        wan_info = wan2gp_available()
    except Exception:
        wan_info = {"available": False}
    try:
        from .mmgp_accel import mmgp_status

        mmgp_info = mmgp_status()
    except Exception:
        mmgp_info = {"available": False}
    backend = "studionels-mmgp" if mmgp_info.get("available") else "builtin"
    return {
        "device": st.device,
        "modes": st.modes,
        "models": enriched,
        "active_model_id": active,
        "queue_length": st.queue_length,
        "preset_id": st.preset_id,
        "models_path": st.models_path,
        "backend": backend,
        "mmgp": mmgp_info,
        "wan2gp": wan_info,
        "size_presets": SIZE_PRESETS,
        "quality_presets": QUALITY_PRESETS,
        "loras_path": str(loras_dir()),
        "loras": loras,
        "lora_count": len(loras),
        "text_encoders": _text_encoder_presets(),
        "memory_profiles": _memory_profiles_public(),
        "current_job_id": _CURRENT_JOB_ID,
    }


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    return store_list(limit)


def get_job(job_id: str) -> dict[str, Any] | None:
    return store_get(job_id)


def _ensure_worker() -> None:
    global _WORKER_STARTED
    with _CV:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True
        t = threading.Thread(target=_worker_loop, name="studionels-engine", daemon=True)
        t.start()


def enqueue_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Queue a built-in generation job."""
    _ensure_worker()
    from .memory import resolve_memory_for_job

    settings = load_settings()
    preset = get_preset(payload.get("preset_id") or settings.preset_id)
    gen = preset.get("generation", {})
    mem = resolve_memory_for_job(
        {**payload, "preset_id": payload.get("preset_id") or settings.preset_id}
    )
    mode = payload["mode"]
    model_id = payload.get("model_id")
    model = get_model(model_id) if model_id else None
    if not model:
        model = default_model_for_mode(mode, float(preset.get("target_vram_gb") or 8))
    if not model:
        raise ValueError(f"No model available for mode {mode}")

    # Validate inputs
    mode_meta = next((m for m in GENERATION_MODES if m["id"] == mode), None)
    if not mode_meta:
        raise ValueError(f"Unknown mode {mode}")
    if mode_meta.get("needs_image") and not payload.get("image_path"):
        raise ValueError("Image → Video needs a start photo / still. Add a file in Generate.")
    if mode_meta.get("needs_reference"):
        has_ref = bool(payload.get("reference_path"))
        has_ref_video = bool(payload.get("video_path")) and mode_meta.get("accepts_ref_video")
        if not has_ref and not has_ref_video:
            raise ValueError(
                "Reference mode needs a reference photo"
                + (" or reference video." if mode_meta.get("accepts_ref_video") else ".")
            )
    if mode_meta.get("needs_video") and not payload.get("video_path"):
        raise ValueError("Upsample video needs a video/clip — add a file in Generate.")

    # Default Draft for video on small cards. R9700-class stays on full model steps
    # (draft ×0.4 broke distilled sigma schedules and made Wan look failed).
    video_modes = {"t2v", "i2v", "ref2v", "upsample_video"}
    vram_gb = None
    try:
        vram_gb = detect_device().get("vram_gb")
    except Exception:
        vram_gb = None
    large_gpu = isinstance(vram_gb, (int, float)) and float(vram_gb) >= 20
    if payload.get("quality"):
        quality = payload.get("quality")
    elif large_gpu:
        quality = "balanced"
    else:
        quality = "draft" if mode in video_modes else "balanced"
    qmeta = next((q for q in QUALITY_PRESETS if q["id"] == quality), QUALITY_PRESETS[0])
    base_steps = int(payload.get("steps") or model.get("default_steps") or 20)
    base_guidance = float(
        payload.get("guidance")
        if payload.get("guidance") is not None
        else (model.get("default_guidance") if model.get("default_guidance") is not None else 5)
    )
    steps = max(1, int(base_steps * float(qmeta["steps_scale"])))
    guidance = float(base_guidance * float(qmeta["guidance_scale"]))
    # Distilled schedules are a fixed length — scaling steps down crashes the sampler.
    if model.get("distilled") and not payload.get("steps"):
        steps = int(model.get("default_steps") or 8)
        if model.get("default_guidance") is not None and payload.get("guidance") is None:
            guidance = float(model.get("default_guidance"))

    duration_sec = payload.get("duration_sec")
    frames = payload.get("frames")
    fps = int(payload.get("fps") or gen.get("fps") or model.get("fps") or 16)
    # Typed length wins. A preset frame count (often 81) must not stretch a
    # 1–3s test into a ~10s clip.
    if mode in video_modes and duration_sec:
        frames = max(9, int(round(float(duration_sec) * max(1, fps))))
    elif not frames:
        frames = int(gen.get("default_frames") or model.get("default_frames") or 49)
        max_frames = qmeta.get("max_frames")
        if max_frames and mode in video_modes:
            frames = min(int(frames), int(max_frames))
    if mode in video_modes:
        from .pipelines import snap_video_frames

        family = f"{model.get('pipeline') or ''} {model.get('id') or ''}"
        frames = snap_video_frames(int(frames), family)
    if mode == "t2a" and not duration_sec:
        duration_sec = float(model.get("default_duration_sec") or 8)

    prompt = payload.get("prompt") or ""
    negative = payload.get("negative_prompt") or ""
    is_rehearsal = bool(payload.get("is_rehearsal"))
    inject_continuity = payload.get("inject_continuity", True)

    # Inject continuity + identity locks when this job is tied to a shot.
    # A one-off test has a project but no shot — keep the prompt as written.
    if inject_continuity and payload.get("project_id") and payload.get("shot_id"):
        try:
            from ..continuity import continuity_prompt_prefix
            from ..identity_lock import identity_prompt_suffix, primary_identity_ref
            from ..storage import load_project

            project = load_project(payload["project_id"])
            shot = None
            if payload.get("shot_id"):
                shot = next((s for s in project.shots if s.id == payload["shot_id"]), None)
            prefix = continuity_prompt_prefix(project, shot)
            if prefix and prefix not in prompt:
                prompt = f"{prefix} | {prompt}" if prompt else prefix
            id_suffix = identity_prompt_suffix(
                project, shot.character_ids if shot else None
            )
            if id_suffix and id_suffix not in prompt:
                prompt = f"{prompt} | {id_suffix}" if prompt else id_suffix
            if project.visual_style and project.visual_style.lower() not in prompt.lower():
                prompt = f"{prompt}, {project.visual_style}" if prompt else project.visual_style
            # Prefer character ref still for IP-Adapter / ref2* style paths
            if not payload.get("reference_path"):
                ref = primary_identity_ref(
                    project, shot.character_ids if shot else None
                )
                if ref:
                    payload["reference_path"] = ref
            # Harden negatives against face drift
            drift = "different person, face swap, changed face, wrong identity, aged, younger"
            if drift not in (negative or ""):
                negative = f"{negative}, {drift}" if negative else drift
        except Exception:
            pass

    if is_rehearsal:
        # Greybox: fewer steps, draft quality, short clips
        quality = "draft"
        steps = max(4, min(steps, 10))
        frames = min(int(frames), 24)
        prompt = f"REHEARSAL GREYBOX, simple blocking, muted colors, {prompt}"

    job = {
        "id": new_id("job"),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "queued",
        "progress": 0.0,
        "message": "Queued (rehearsal)" if is_rehearsal else "Queued",
        "mode": mode,
        "model_id": model["id"],
        "model_label": model["label"],
        "prompt": prompt,
        "negative_prompt": negative,
        "width": _snap_job_dim(payload.get("width") or gen.get("default_width") or 768),
        "height": _snap_job_dim(payload.get("height") or gen.get("default_height") or 448),
        "steps": steps,
        "guidance": guidance,
        "quality": quality,
        "frames": int(frames),
        "fps": fps,
        "duration_sec": float(duration_sec) if duration_sec is not None else None,
        "seed": payload.get("seed"),
        "strength": payload.get("strength"),
        "cpu_offload": mem.get(
            "cpu_offload",
            payload.get("cpu_offload", gen.get("cpu_offload", True)),
        ),
        "memory": mem,
        "memory_placement": mem.get("placement"),
        "preset_id": mem.get("preset_id") or settings.preset_id,
        "image_path": payload.get("image_path"),
        "reference_path": payload.get("reference_path"),
        "video_path": payload.get("video_path"),
        "lora_path": payload.get("lora_path"),
        "lora_scale": float(payload.get("lora_scale") if payload.get("lora_scale") is not None else 0.8),
        "text_encoder": payload.get("text_encoder") or "auto",
        "audio_path": payload.get("audio_path"),
        "project_id": payload.get("project_id"),
        "shot_id": payload.get("shot_id"),
        "is_rehearsal": is_rehearsal,
        "continue_from_previous": bool(payload.get("continue_from_previous")),
        "continue_from_take_id": payload.get("continue_from_take_id"),
        "chain_shot_ids": list(payload.get("chain_shot_ids") or []),
        # Full form snapshot so Stop can restore the workflow without losing input
        "workflow": dict(payload),
        "media_path": None,
        "thumb_path": None,
        "last_frame_path": None,
        "error": None,
        "preview": False,
        "engine": "builtin",
        "cancel_requested": False,
    }
    _CANCEL[job["id"]] = False
    upsert_job(job)
    with _CV:
        _QUEUE.append(job["id"])
        _CV.notify()
    return job


def cancel_job(job_id: str) -> dict[str, Any]:
    """Stop a queued/running job. Keeps the job + workflow snapshot for restore."""
    job = store_get(job_id)
    if not job:
        raise ValueError("Job not found")
    _CANCEL[job_id] = True
    with _CV:
        if job_id in _QUEUE:
            _QUEUE[:] = [j for j in _QUEUE if j != job_id]
    # Kill isolated Diffusers subprocess if this is the live job
    with _PROC_LOCK:
        global _CURRENT_PROC
        if _CURRENT_JOB_ID == job_id and _CURRENT_PROC is not None:
            try:
                _CURRENT_PROC.terminate()
            except Exception:
                pass
            try:
                _CURRENT_PROC.kill()
            except Exception:
                pass
    status = job.get("status")
    if status in ("queued", "running"):
        job["cancel_requested"] = True
        job["status"] = "cancelled"
        job["message"] = (
            "Stopped — your prompt and settings are saved. "
            "Open Generate → Restore workflow to continue."
        )
        job["updated_at"] = utc_now()
        job["progress"] = float(job.get("progress") or 0)
        upsert_job(job)
    return job


def _daemon_paths() -> dict[str, Path]:
    d = MEDIA_DIR / "_engine_daemon"
    d.mkdir(parents=True, exist_ok=True)
    (d / "requests").mkdir(parents=True, exist_ok=True)
    return {
        "root": d,
        "pid": d / "daemon.pid",
        "heartbeat": d / "heartbeat.json",
        "requests": d / "requests",
    }


def _daemon_alive() -> bool:
    paths = _daemon_paths()
    if not paths["pid"].exists():
        return False
    try:
        pid = int(paths["pid"].read_text(encoding="utf-8").strip())
    except Exception:
        return False
    # A live pid is enough. Torch import on AMD can go quiet for a minute
    # before the heartbeat updates; a stale file must not start a second engine.
    return _pid_is_engine(pid)


def _pid_is_engine(pid: int) -> bool:
    """True when pid is a running engine_daemon.

    Not os.kill(pid, 0): on Windows signal 0 is CTRL_C_EVENT, which fails from
    the console-less API process. Every check then said "dead", so each job
    started another engine and ran in a cold worker that reloaded the model.
    """
    try:
        import psutil
    except Exception:
        if os.name == "nt":
            return False
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False
    try:
        proc = psutil.Process(pid)
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return False
        try:
            return "engine_daemon" in " ".join(proc.cmdline())
        except psutil.AccessDenied:
            return True
    except Exception:
        return False


def _ensure_warm_daemon() -> bool:
    """Start the long-lived engine process. Returns True when it is usable.

    Wan2GP is fast because the process is already imported and the last model
    stays in memory. This daemon does that. It does not load weights until
    Generate, so opening the app does not fill the GPU. Opt out with
    STUDIONELS_COLD_WORKER=1.
    """
    if os.environ.get("STUDIONELS_COLD_WORKER", "").strip().lower() in {"1", "true", "yes"}:
        return False
    if _daemon_alive():
        return True
    backend_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TORCHINDUCTOR_DISABLE", "1")
    env.setdefault("TORCH_COMPILE_DISABLE", "1")
    env.setdefault("MIOPEN_FIND_MODE", "FAST")
    log_path = _daemon_paths()["root"] / "daemon.log"
    try:
        log_f = open(log_path, "a", encoding="utf-8")
    except Exception:
        log_f = subprocess.DEVNULL
    try:
        _popen_hidden(
            [sys.executable, "-m", "app.engine.engine_daemon"],
            cwd=str(backend_root),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        _kill_daemon_on_exit()
    except Exception:
        return False
    # Wait briefly for heartbeat
    for _ in range(40):
        if _daemon_alive():
            return True
        time.sleep(0.25)
    return _daemon_alive()


def _kill_warm_daemon() -> None:
    paths = _daemon_paths()
    if not paths["pid"].exists():
        return
    try:
        pid = int(paths["pid"].read_text(encoding="utf-8").strip())
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
        else:
            os.kill(pid, 15)
            time.sleep(0.4)
            try:
                os.kill(pid, 9)
            except Exception:
                pass
    except Exception:
        pass
    try:
        paths["pid"].unlink()
    except Exception:
        pass


_KILL_ON_EXIT = False


def _kill_daemon_on_exit() -> None:
    global _KILL_ON_EXIT
    if _KILL_ON_EXIT:
        return
    _KILL_ON_EXIT = True
    atexit.register(_kill_warm_daemon)


def _popen_hidden(cmd: list[str], **kwargs: Any) -> subprocess.Popen:
    """Start a worker without a console window (Windows python.exe pops one)."""
    if os.name == "nt":
        flags = int(kwargs.pop("creationflags", 0) or 0)
        flags |= 0x08000000  # CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
    return subprocess.Popen(cmd, **kwargs)


_PRELOAD_STATE: dict[str, Any] = {
    "busy": False,
    "model_id": None,
    "message": None,
    "progress": 0.0,
    "error": None,
    "started_at": None,
}
_PRELOAD_LOCK = threading.Lock()


def warm_engine_status() -> dict[str, Any]:
    """What the warm daemon has resident — for dock / Models / Settings."""
    from .models_manager import get_active_model_id

    settings = load_settings()
    keep = bool(getattr(settings, "keep_model_loaded", True))
    alive = _daemon_alive()
    cached: list[str] = []
    message: str | None = None
    daemon_status = "down"
    if alive:
        try:
            hb = json.loads(_daemon_paths()["heartbeat"].read_text(encoding="utf-8"))
            cached = list(hb.get("cached") or (hb.get("cache") or {}).get("cached") or [])
            daemon_status = str(hb.get("status") or "idle")
            message = hb.get("message")
        except Exception:
            daemon_status = "starting"
    with _PRELOAD_LOCK:
        preloading = bool(_PRELOAD_STATE.get("busy"))
        preload_msg = _PRELOAD_STATE.get("message")
        preload_model_id = _PRELOAD_STATE.get("model_id")
        preload_progress = float(_PRELOAD_STATE.get("progress") or 0)
        preload_error = _PRELOAD_STATE.get("error")
    if preloading and preload_msg:
        message = str(preload_msg)
        daemon_status = "preloading"
    elif daemon_status == "preloading" and not message:
        message = "Preloading model into RAM/VRAM…"
    return {
        "keep_model_loaded": keep,
        "daemon_alive": alive,
        "daemon_status": daemon_status,
        "cached": cached,
        "active_model_id": get_active_model_id(),
        "preloading": preloading or daemon_status == "preloading",
        "message": message,
        "preload_model_id": preload_model_id,
        "progress": preload_progress,
        "error": preload_error,
    }


def preload_model(
    model_id: str,
    preset_id: str | None = None,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    """Ensure warm daemon, send preload request, wait for result.

    Returns ``{ok, label, cached, error?}``.
    """
    from .catalog import get_model
    from .models_manager import list_models_with_status

    mid = str(model_id or "").strip()
    if not mid:
        return {"ok": False, "label": "", "cached": [], "error": "model_id required"}

    model = get_model(mid)
    if not model:
        return {"ok": False, "label": mid, "cached": [], "error": f"Unknown model {mid}"}
    label = str(model.get("label") or mid)

    # Must be Ready on disk — no silent HF fetch during preload
    try:
        status_row = next(
            (m for m in list_models_with_status() if m.get("id") == mid),
            None,
        )
    except Exception:
        status_row = None
    if (
        model.get("hf_id")
        and status_row is not None
        and not status_row.get("installed")
        and str(status_row.get("download_status") or "") != "installed"
    ):
        err = (
            f"{label} is not Ready on disk. Open Models → Download until Ready, "
            "then tap Load into studio."
        )
        return {"ok": False, "label": label, "cached": [], "error": err}

    if model.get("pipeline") == "lanczos" or model.get("kind") == "upsample":
        return {
            "ok": False,
            "label": label,
            "cached": [],
            "error": f"{label} does not use a Diffusers weight cache.",
        }

    def _cb(msg: str, frac: float = 0.0) -> None:
        with _PRELOAD_LOCK:
            _PRELOAD_STATE["message"] = msg
            _PRELOAD_STATE["progress"] = float(frac)
        if progress_cb:
            try:
                progress_cb(msg, float(frac))
            except Exception:
                pass

    with _PRELOAD_LOCK:
        if _PRELOAD_STATE.get("busy"):
            return {
                "ok": False,
                "label": label,
                "cached": warm_engine_status().get("cached") or [],
                "error": "A preload is already running — wait for it to finish.",
            }
        _PRELOAD_STATE.update(
            {
                "busy": True,
                "model_id": mid,
                "message": f"Preloading {label} into RAM/VRAM…",
                "progress": 0.02,
                "error": None,
                "started_at": time.time(),
            }
        )

    try:
        os.environ["STUDIONELS_WARM_ENGINE"] = "1"
        if not _ensure_warm_daemon():
            err = "Warm engine daemon failed to start. Check daemon.log under media/_engine_daemon/."
            _cb(err, 0.0)
            return {"ok": False, "label": label, "cached": [], "error": err}

        ensure_dirs()
        work = MEDIA_DIR / "_workers" / f"preload-{mid}-{int(time.time())}"
        work.mkdir(parents=True, exist_ok=True)
        progress_file = work / "progress.json"
        result_file = work / "result.json"
        cancel_file = work / "cancel.flag"
        for p in (progress_file, result_file, cancel_file):
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        settings = load_settings()
        req = {
            "action": "preload",
            "model_id": mid,
            "preset_id": preset_id or getattr(settings, "preset_id", None),
            "progress_file": str(progress_file),
            "result_file": str(result_file),
            "cancel_file": str(cancel_file),
        }
        req_path = _daemon_paths()["requests"] / f"preload-{mid}-{int(time.time() * 1000)}.json"
        req_path.write_text(json.dumps(req), encoding="utf-8")
        _cb(f"Preloading {label} into RAM/VRAM…", 0.04)

        started = time.time()
        last_payload: dict[str, Any] = {}
        while True:
            if progress_file.exists():
                try:
                    payload = json.loads(progress_file.read_text(encoding="utf-8"))
                    if payload != last_payload:
                        last_payload = payload
                        _cb(
                            str(payload.get("message") or f"Preloading {label}…"),
                            float(payload.get("progress") or 0),
                        )
                except Exception:
                    pass

            if result_file.exists():
                try:
                    result = json.loads(result_file.read_text(encoding="utf-8"))
                except Exception as exc:
                    return {
                        "ok": False,
                        "label": label,
                        "cached": [],
                        "error": f"Bad preload result: {exc}",
                    }
                if result.get("ok"):
                    cached = list(result.get("cached") or [])
                    out_label = str(result.get("label") or label)
                    _cb(f"Model ready: {out_label}", 1.0)
                    return {
                        "ok": True,
                        "label": out_label,
                        "cached": cached,
                        "already_loaded": bool(result.get("already_loaded")),
                    }
                err = str(result.get("error") or "Preload failed")
                _cb(err, float(last_payload.get("progress") or 0.2))
                return {
                    "ok": False,
                    "label": label,
                    "cached": list(result.get("cached") or []),
                    "error": err,
                }

            if not _daemon_alive():
                return {
                    "ok": False,
                    "label": label,
                    "cached": [],
                    "error": "Warm engine died during preload. Stop → Start StudioNels and retry.",
                }

            if time.time() - started > _LOAD_MAX_SEC + 60:
                try:
                    cancel_file.write_text("1", encoding="utf-8")
                except Exception:
                    pass
                return {
                    "ok": False,
                    "label": label,
                    "cached": [],
                    "error": (
                        f"Preload timed out after {int(time.time() - started)}s. "
                        "Confirm this model is Ready in Models, then Generate again."
                    ),
                }
            time.sleep(0.35)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "label": label, "cached": [], "error": str(exc)}
    finally:
        with _PRELOAD_LOCK:
            _PRELOAD_STATE["busy"] = False
            if _PRELOAD_STATE.get("progress", 0) < 1.0 and not _PRELOAD_STATE.get("error"):
                # leave last message; clear busy
                pass


def start_preload_background(model_id: str, preset_id: str | None = None) -> dict[str, Any]:
    """Fire-and-forget preload for API startup / Settings toggle."""
    mid = str(model_id or "").strip()
    if not mid:
        return {"ok": False, "started": False, "error": "model_id required"}
    with _PRELOAD_LOCK:
        if _PRELOAD_STATE.get("busy"):
            return {
                "ok": True,
                "started": False,
                "model_id": mid,
                "message": _PRELOAD_STATE.get("message") or "Preload already running",
            }

    def _run() -> None:
        try:
            preload_model(mid, preset_id=preset_id)
        except Exception:
            pass

    threading.Thread(target=_run, name=f"studionels-preload-{mid}", daemon=True).start()
    return {
        "ok": True,
        "started": True,
        "model_id": mid,
        "message": f"Preloading {mid} into RAM/VRAM…",
    }


def _run_diffusers_isolated(
    job: dict[str, Any],
    out_path: Path,
    cb,
) -> dict[str, Any]:
    """Run Diffusers out-of-process — prefer warm daemon (cached model) for speed."""
    global _CURRENT_PROC
    ensure_dirs()
    work = MEDIA_DIR / "_workers" / str(job["id"])
    work.mkdir(parents=True, exist_ok=True)
    job_file = work / "job.json"
    progress_file = work / "progress.json"
    result_file = work / "result.json"
    cancel_file = work / "cancel.flag"
    for p in (progress_file, result_file, cancel_file):
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
    job_file.write_text(json.dumps(job), encoding="utf-8")

    cb("Starting GPU worker…", 0.031)
    use_daemon = _ensure_warm_daemon()
    backend_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TORCHINDUCTOR_DISABLE", "1")
    env.setdefault("TORCH_COMPILE_DISABLE", "1")
    env.setdefault("MIOPEN_FIND_MODE", "FAST")

    proc: subprocess.Popen | None = None
    # Worker stderr goes to a file, never a pipe. Nothing reads a pipe until the
    # worker exits, so the transformers/tqdm load bars filled the Windows pipe
    # buffer and froze the load thread forever ("stuck at 18%", 0% CPU).
    err_log_path = progress_file.parent / "worker_stderr.log"
    err_log = None
    if use_daemon:
        # File-based IPC to the long-lived warm engine (model stays loaded)
        req = {
            "job": job,
            "out_path": str(out_path),
            "progress_file": str(progress_file),
            "result_file": str(result_file),
            "cancel_file": str(cancel_file),
        }
        req_path = _daemon_paths()["requests"] / f"{job['id']}.json"
        req_path.write_text(json.dumps(req), encoding="utf-8")
        cb("Queued on warm engine — waiting for first worker progress…", 0.035)

        class _DaemonHandle:
            """Stop cancels the job; stall kill restarts the daemon."""

            def terminate(self) -> None:
                try:
                    cancel_file.write_text("1", encoding="utf-8")
                except Exception:
                    pass

            def kill(self) -> None:
                try:
                    cancel_file.write_text("1", encoding="utf-8")
                except Exception:
                    pass
                _kill_warm_daemon()

        with _PROC_LOCK:
            _CURRENT_PROC = _DaemonHandle()
    else:
        cmd = [
            sys.executable,
            "-m",
            "app.engine.gen_worker",
            "--job-file",
            str(job_file),
            "--progress-file",
            str(progress_file),
            "--result-file",
            str(result_file),
            "--out-path",
            str(out_path),
        ]
        err_log = open(err_log_path, "wb")
        proc = _popen_hidden(
            cmd,
            cwd=str(backend_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=err_log,
        )
        with _PROC_LOCK:
            _CURRENT_PROC = proc

    started = time.time()
    last_child_touch = started
    last_parent_pulse = 0.0
    last_payload: dict[str, Any] = {}
    saw_step = False
    gen_started_at: float | None = None
    code: int | None = None

    def _stop_worker(kill: bool = False) -> None:
        handle = proc if proc is not None else _CURRENT_PROC
        if handle is None:
            return
        try:
            if kill:
                handle.kill()
            else:
                handle.terminate()
        except Exception:
            pass
        if proc is not None and not kill:
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    try:
        while True:
            if _CANCEL.get(job["id"]):
                try:
                    cancel_file.write_text("1", encoding="utf-8")
                except Exception:
                    pass
                _stop_worker(kill=False)
                raise JobCancelled("Stopped by user")

            # Mirror child progress into the job store (API stays responsive)
            if progress_file.exists():
                try:
                    payload = json.loads(progress_file.read_text(encoding="utf-8"))
                    if payload != last_payload:
                        last_payload = payload
                        last_child_touch = time.time()
                        msg = str(payload.get("message") or "")
                        frac = float(payload.get("progress") or 0)
                        if "step " in msg.lower() and "step 0/" not in msg.lower():
                            saw_step = True
                        if gen_started_at is None and (
                            frac >= 0.2
                            or "generating" in msg.lower()
                            or "denoise" in msg.lower()
                            or "warm model" in msg.lower()
                        ):
                            gen_started_at = time.time()
                        cb(msg, frac)
                except Exception:
                    pass

            if result_file.exists():
                code = 0
                break

            if proc is not None:
                code = proc.poll()
                if code is not None:
                    break
            elif use_daemon and not _daemon_alive() and not result_file.exists():
                # Daemon died mid-job (usually a ROCm native crash — no Python traceback)
                code = 1
                break

            now = time.time()
            elapsed = now - started
            child_silent = now - last_child_touch

            # Parent-side pulse so UI never sits mute if the child is wedged in HIP
            if child_silent >= 5 and (now - last_parent_pulse) >= 5:
                last_msg_pulse = str((last_payload or {}).get("message") or job.get("message") or "")
                last_frac_pulse = float((last_payload or {}).get("progress") or job.get("progress") or 0)
                loading = last_frac_pulse < 0.2 or "load" in last_msg_pulse.lower() or "reading" in last_msg_pulse.lower()
                if loading:
                    cb(
                        f"Loading {job.get('model_label') or 'this model'} with mmgp… {int(elapsed)}s",
                        max(0.06, min(0.18, last_frac_pulse)),
                    )
                else:
                    soft = min(0.55, 0.2 + child_silent / 600.0)
                    cb(
                        f"Waiting on GPU… {int(elapsed)}s elapsed · "
                        f"{job.get('model_label') or 'this model'} is still on the current step",
                        max(float(job.get("progress") or 0.2), soft),
                    )
                last_parent_pulse = now

            # Boot watchdog — jobs stuck at ~3% "Starting…" with no worker pulse
            last_msg = str((last_payload or {}).get("message") or job.get("message") or "")
            last_frac = float((last_payload or {}).get("progress") or job.get("progress") or 0)
            if (not saw_step) and last_frac < 0.08 and elapsed >= 180:
                _stop_worker(kill=True)
                raise RuntimeError(
                    "Engine never left boot (stuck near 3%). "
                    "Stop → Models → confirm the model is Ready → Pinokio Update / Install AMD engine → "
                    "Stop → Start, then Generate again."
                )

            # Load-phase watchdog: heartbeats alone used to keep ~18% alive forever
            still_loading = (not saw_step) and (
                last_frac < 0.2
                or "loading pipeline" in last_msg.lower()
                or "reading weights" in last_msg.lower()
                or "first amd load" in last_msg.lower()
            )
            if still_loading and elapsed >= _LOAD_MAX_SEC:
                _stop_worker(kill=True)
                raise RuntimeError(
                    f"Model load stuck for {_LOAD_MAX_SEC // 60}+ min (still before generate). "
                    "VRAM often stays 0 until weights finish reading into RAM. "
                    "Stop → Models → confirm this model is Ready, then Generate again."
                )

            if child_silent >= _STALL_SEC and not saw_step:
                _stop_worker(kill=True)
                raise RuntimeError(
                    "Generation stalled — GPU made no denoise progress for "
                    f"{_STALL_SEC // 60} minutes. Use a shorter clip and Draft quality, then Generate again."
                )

            # Stuck after last denoise step (VAE decode / export)
            post_decode = False
            if saw_step and last_frac >= 0.88:
                low = last_msg.lower()
                if any(
                    s in low
                    for s in ("decod", "denoise done", "assembling", "exporting")
                ):
                    post_decode = True
                else:
                    import re as _re

                    m_done = _re.search(r"step\s+(\d+)\s*/\s*(\d+)", last_msg, _re.I)
                    if m_done and int(m_done.group(1)) >= int(m_done.group(2)):
                        post_decode = True
            if post_decode and elapsed >= _POST_STEP_MAX_SEC:
                _stop_worker(kill=True)
                raise RuntimeError(
                    f"Stuck after denoise for {_POST_STEP_MAX_SEC // 60}+ min (VAE decode/export). "
                    "Try fewer frames / Draft, or Memory with VAE slicing. "
                    "Stop and retry — denoise had already finished."
                )
            if (
                gen_started_at
                and not saw_step
                and (now - gen_started_at) >= _FIRST_STEP_SEC
            ):
                _stop_worker(kill=True)
                raise RuntimeError(
                    "First denoise step never started (8+ min). "
                    "Large models stream from RAM — Stop, keep the clip at 2–3 seconds and 768×432, then Generate again."
                )
            if elapsed >= _MAX_JOB_SEC:
                _stop_worker(kill=True)
                raise RuntimeError(
                    f"Job exceeded {_MAX_JOB_SEC // 60} minutes and was stopped. "
                    "Use fewer frames / Draft quality / GPU-resident memory."
                )
            time.sleep(0.75)

        stderr = ""
        if proc is not None:
            try:
                if err_log is not None:
                    err_log.flush()
                with open(err_log_path, "rb") as fh:
                    fh.seek(0, os.SEEK_END)
                    fh.seek(max(0, fh.tell() - 2000))
                    stderr = fh.read().decode("utf-8", errors="replace")
            except Exception:
                stderr = ""

        if result_file.exists():
            data = json.loads(result_file.read_text(encoding="utf-8"))
            if data.get("ok"):
                return dict(data.get("result") or {})
            err = data.get("error") or "Worker failed"
            tb = data.get("traceback") or ""
            raise RuntimeError(f"{err}\n{tb}\n{stderr}".strip())

        if code not in (0, None):
            log_tail = ""
            try:
                log_path = _daemon_paths()["root"] / "daemon.log"
                if log_path.exists():
                    raw = log_path.read_text(encoding="utf-8", errors="replace")
                    log_tail = raw[-1800:].strip()
            except Exception:
                log_tail = ""
            detail = stderr.strip() or log_tail or "No stderr — GPU process crashed (often ROCm flash-attn)."
            raise RuntimeError(f"Diffusers worker exited {code}. {detail}")
        raise RuntimeError("Diffusers worker finished with no result file.")
    finally:
        with _PROC_LOCK:
            _CURRENT_PROC = None
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        if err_log is not None:
            try:
                err_log.close()
            except Exception:
                pass


def cancel_all_jobs() -> dict[str, Any]:
    active = [
        j
        for j in store_list(80)
        if j.get("status") in ("queued", "running")
    ]
    stopped = [cancel_job(j["id"]) for j in active]
    return {"ok": True, "stopped": len(stopped), "jobs": stopped}


def dismiss_job(job_id: str) -> dict[str, Any]:
    """Remove a job from the generation list UI. Cancels first if still active.
    Does not delete Sampling takes / media files.
    """
    job = store_get(job_id)
    if not job:
        raise ValueError("Job not found")
    if job.get("status") in ("queued", "running"):
        cancel_job(job_id)
    removed = store_remove(job_id)
    if not removed:
        raise ValueError("Job not found")
    return {"ok": True, "id": job_id, "removed": removed}


def dismiss_finished_jobs() -> dict[str, Any]:
    """Remove done / failed / cancelled jobs from the queue list."""
    removed_ids: list[str] = []
    for job in store_list(200):
        if job.get("status") in ("done", "failed", "cancelled"):
            jid = str(job.get("id") or "")
            if jid and store_remove(jid):
                removed_ids.append(jid)
    return {"ok": True, "removed": len(removed_ids), "ids": removed_ids}


def list_restorable_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """Cancelled / failed jobs that still carry a workflow snapshot."""
    out = []
    for job in store_list(80):
        if job.get("workflow") and job.get("status") in ("cancelled", "failed", "done"):
            out.append(job)
        if len(out) >= limit:
            break
    return out


def _worker_loop() -> None:
    global _CURRENT_JOB_ID
    while True:
        with _CV:
            while not _QUEUE:
                _CV.wait()
            job_id = _QUEUE.pop(0)
        if _CANCEL.get(job_id):
            job = store_get(job_id)
            if job and job.get("status") not in ("cancelled",):
                job["status"] = "cancelled"
                job["message"] = "Stopped before start — workflow saved."
                job["updated_at"] = utc_now()
                upsert_job(job)
            continue
        job = store_get(job_id)
        if not job:
            continue
        _CURRENT_JOB_ID = job_id
        try:
            _run_one(job)
        finally:
            if _CURRENT_JOB_ID == job_id:
                _CURRENT_JOB_ID = None


def _run_one(job: dict[str, Any]) -> None:
    ensure_dirs()
    if _CANCEL.get(job["id"]):
        job["status"] = "cancelled"
        job["message"] = "Stopped — workflow saved."
        job["updated_at"] = utc_now()
        upsert_job(job)
        return

    job["status"] = "running"
    job["message"] = "Booting engine…"
    job["progress"] = 0.01
    job["started_at"] = utc_now()
    job["elapsed_sec"] = 0
    job["updated_at"] = utc_now()
    upsert_job(job)

    def cb(message: str, frac: float) -> None:
        if _CANCEL.get(job["id"]):
            raise JobCancelled("Stopped by user")
        job["message"] = message
        job["progress"] = frac
        job["updated_at"] = utc_now()
        try:
            from datetime import datetime
            import re

            start = job.get("started_at")
            if isinstance(start, str) and start:
                t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
                job["elapsed_sec"] = max(0, int((datetime.now(t0.tzinfo) - t0).total_seconds()))
            m = re.search(r"step\s+(\d+)\s*/\s*(\d+)", message or "", re.I)
            if m:
                job["step"] = int(m.group(1))
                job["steps_total"] = int(m.group(2))
            eta_m = re.search(r"~\s*(\d+)m(\d+)s\s*left", message or "", re.I)
            eta_s = re.search(r"~\s*(\d+)s\s*left", message or "", re.I)
            if eta_m:
                job["eta_sec"] = int(eta_m.group(1)) * 60 + int(eta_m.group(2))
            elif eta_s:
                job["eta_sec"] = int(eta_s.group(1))
        except Exception:
            pass
        upsert_job(job)

    out_dir = MEDIA_DIR / (job.get("project_id") or "standalone")
    out_path = out_dir / job["id"]

    # detect_device() imports torch — can take 1–2 min on first AMD load with no UI pulse
    cb("Checking GPU / PyTorch (first boot can take 1–2 min)…", 0.02)
    device_box: dict[str, Any] = {}

    def _detect() -> None:
        device_box["device"] = detect_device()

    det_t = threading.Thread(target=_detect, name="studionels-detect-device", daemon=True)
    det_t.start()
    det_started = time.time()
    while det_t.is_alive():
        if _CANCEL.get(job["id"]):
            raise JobCancelled("Stopped by user")
        elapsed = int(time.time() - det_started)
        if elapsed >= 3 and elapsed % 3 == 0:
            cb(f"Checking GPU / PyTorch… {elapsed}s (first AMD import is slow)…", 0.02)
        if elapsed >= 180:
            raise RuntimeError(
                "PyTorch/GPU check hung for 3+ minutes. In Pinokio run Install AMD engine, "
                "then Stop → Start StudioNels."
            )
        det_t.join(timeout=1.0)
    device = device_box.get("device") or detect_device()

    force_preview = bool(job.get("force_preview"))
    from .catalog import get_model
    from .mmgp_accel import mmgp_status
    from .models_manager import list_models_with_status

    model_meta = get_model(str(job.get("model_id") or "")) or {}
    # Block silent HF fetches during Generate — that looks like a stuck download at 3%
    try:
        status_row = next(
            (m for m in list_models_with_status() if m.get("id") == model_meta.get("id")),
            None,
        )
    except Exception:
        status_row = None
    if (
        model_meta.get("hf_id")
        and status_row is not None
        and not status_row.get("installed")
        and str(status_row.get("download_status") or "") != "installed"
    ):
        raise RuntimeError(
            f"{model_meta.get('label') or model_meta.get('id')} is not Ready on disk. "
            "Open Models → Download until the progress bar finishes (Ready), then Generate."
        )
    # StudioNels owns Generate: Diffusers + native mmgp.
    # Wan2GP is only used when the model has no Diffusers weights, or when
    # STUDIONELS_PREFER_WAN2GP=1. LTX used to be forced onto Wan2GP, which
    # fails offline when the quanto int8 file was never downloaded.
    wan_only = (
        str(model_meta.get("format") or "") == "wan2gp-engine"
        or str(job.get("model_id") or "").startswith("wgp-")
        or (model_meta.get("wan2gp") and not model_meta.get("hf_id"))
    )
    mid = str(job.get("model_id") or model_meta.get("id") or "").lower()
    pipe_name = str(model_meta.get("pipeline") or "")
    ltx2_like = "LTX2" in pipe_name or mid.startswith("ltx2")
    explicit_wan = os.environ.get("STUDIONELS_PREFER_WAN2GP", "").strip().lower() in {
        "1",
        "true",
        "yes",
    } or bool(job.get("prefer_wan2gp"))

    can_diffusers = (
        not force_preview
        and not wan_only
        and bool(model_meta.get("hf_id") or model_meta.get("local_path") or model_meta.get("pipeline"))
        and device.get("ready_for_inference")
        and device.get("diffusers_available")
    )
    use_wan2gp = False
    if (explicit_wan or wan_only) and not force_preview:
        try:
            from .wan2gp_runtime import wan2gp_available

            use_wan2gp = bool(wan2gp_available().get("available"))
        except Exception:
            use_wan2gp = False
    use_diffusers = can_diffusers and not use_wan2gp
    use_real = use_diffusers or use_wan2gp

    def _run_external_wan() -> dict[str, Any] | None:
        from .wan2gp_runtime import run_wan2gp_job

        holder: dict[str, Any] = {}

        def _cancel() -> bool:
            return bool(_CANCEL.get(job["id"]))

        class _HolderProc:
            def terminate(self) -> None:
                p = holder.get("proc")
                if p:
                    p.terminate()

            def kill(self) -> None:
                p = holder.get("proc")
                if p:
                    p.kill()

        with _PROC_LOCK:
            global _CURRENT_PROC
            _CURRENT_PROC = _HolderProc()
        try:
            return run_wan2gp_job(
                job,
                out_path,
                cb,
                cancel_check=_cancel,
                proc_holder=holder,
            )
        finally:
            with _PROC_LOCK:
                if _CURRENT_PROC is not None:
                    _CURRENT_PROC = None

    try:
        if wan_only and not use_wan2gp:
            raise RuntimeError(
                "That model is Wan2GP-only. Pick a StudioNels catalog model with a "
                "Hugging Face id (e.g. Wan 1.3B, Wan I2V, LTX Distilled), Download it "
                "in Models until Ready, then Generate."
            )
        if use_diffusers:
            mm = mmgp_status()
            job["engine"] = "studionels-mmgp" if mm.get("available") else "diffusers"
            if mm.get("available"):
                cb("StudioNels engine · starting warm worker…", 0.03)
            else:
                cb(
                    "Starting worker — mmgp not installed yet (Pinokio: Update, or Install AMD engine). "
                    "First PyTorch import can take 1–2 min with no step yet…",
                    0.03,
                )
            result = _run_diffusers_isolated(job, out_path, cb)
            job["preview"] = bool(result.get("preview"))
        elif use_wan2gp:
            job["engine"] = "wan2gp"
            if ltx2_like:
                wan_msg = "Using Wan2GP for LTX (weights already managed there)…"
            else:
                wan_msg = "Starting Wan2GP (opt-in)…"
            job["message"] = wan_msg
            upsert_job(job)
            cb(wan_msg, 0.03)
            try:
                result = _run_external_wan()
                if result is None:
                    raise RuntimeError("Wan2GP returned no video")
            except Exception as exc:
                if not can_diffusers:
                    raise
                cb(
                    "Wan2GP is missing that checkpoint. StudioNels engine is running this instead…",
                    0.03,
                )
                job["engine"] = "studionels-mmgp"
                job["message"] = f"Wan2GP skipped ({exc.__class__.__name__}). Using StudioNels engine."
                upsert_job(job)
                result = _run_diffusers_isolated(job, out_path, cb)
            job["preview"] = bool(result.get("preview"))
        else:
            result = run_preview_job(job, out_path, cb)
            job["preview"] = True
            if not device.get("torch_available"):
                job["message"] = (
                    "Preview only — install ROCm PyTorch + requirements-engine.txt, "
                    "then download a model in Models."
                )
            elif not device.get("diffusers_available"):
                job["message"] = "Preview only — pip install -r requirements-engine.txt (includes mmgp)."
            else:
                job["message"] = "Preview only — no GPU visible; install AMD ROCm PyTorch."

        if _CANCEL.get(job["id"]):
            raise JobCancelled("Stopped by user")

        # Optional: mux audio bed onto finished video
        audio_path = job.get("audio_path")
        media = result.get("media_path")
        if (
            audio_path
            and media
            and str(media).lower().endswith((".mp4", ".webm", ".mov"))
        ):
            try:
                muxed = mux_audio_onto_video(
                    media,
                    str(audio_path),
                    out_path=Path(media).with_name(Path(media).stem + "_audio.mp4"),
                    cb=cb,
                )
                result["media_path"] = muxed
                job["message"] = "Complete (audio attached)"
            except Exception as mux_exc:  # noqa: BLE001
                job["message"] = f"Complete — audio mux skipped ({mux_exc})"

        job["media_path"] = result.get("media_path")
        job["thumb_path"] = result.get("thumb_path")
        try:
            from ..continue_video import ensure_last_frame_sidecar

            job["last_frame_path"] = ensure_last_frame_sidecar(job.get("media_path"))
        except Exception:
            job["last_frame_path"] = None
        job["status"] = "done"
        job["progress"] = 1.0
        if not job.get("message") or (job["status"] == "done" and not job.get("preview") and "audio" not in (job.get("message") or "").lower()):
            msg = "Complete"
            if job.get("continue_from_previous"):
                msg = "Complete (continued from previous)"
            job["message"] = msg
        job["updated_at"] = utc_now()
        upsert_job(job)

        if job.get("project_id") and job.get("media_path") and not _CANCEL.get(job["id"]):
            _attach_to_project(job)
            _maybe_chain_next(job)
    except JobCancelled:
        job["status"] = "cancelled"
        job["cancel_requested"] = True
        job["error"] = None
        job["message"] = (
            "Stopped — your prompt and settings are saved. "
            "Restore workflow in Generate to pick up where you left off."
        )
        job["updated_at"] = utc_now()
        upsert_job(job)
    except Exception as exc:  # noqa: BLE001
        if _CANCEL.get(job["id"]) or "Stopped" in str(exc):
            job["status"] = "cancelled"
            job["error"] = None
            job["message"] = "Stopped — workflow saved."
        else:
            job["status"] = "failed"
            job["error"] = f"{exc}\n{traceback.format_exc()[-1500:]}"
            job["message"] = str(exc)
            low = str(exc).lower()
            if "out of memory" in low or "outofmemory" in low or "hip error: out of memory" in low:
                # Next run of this model uses the proven low-VRAM mmgp path.
                try:
                    from .mmgp_accel import mark_model_safe

                    mark_model_safe(job.get("model_id"))
                    job["message"] = (
                        "Ran out of GPU memory with the fast memory profile. "
                        "This model now uses the safe low-VRAM profile — Generate again."
                    )
                except Exception:
                    pass
        job["updated_at"] = utc_now()
        upsert_job(job)


# Takes without a storyboard shot land here so Sampling / Audio can still find them
LIBRARY_SHOT_ID = "__library__"


def _attach_to_project(job: dict[str, Any]) -> None:
    from ..models import Take
    from ..storage import load_project, save_project

    try:
        project = load_project(job["project_id"])
    except FileNotFoundError:
        return

    if not job.get("media_path"):
        return

    tag = f"job:{job['id']}"
    for char in project.characters:
        if tag in (char.tags or []) and not char.reference_path:
            char.reference_path = job.get("thumb_path") or job["media_path"]
    for scene in project.scenes:
        if tag in (scene.tags or []) and not scene.reference_path:
            scene.reference_path = job.get("thumb_path") or job["media_path"]

    # Avoid duplicate attaches if a job is replayed / saved twice
    if any(job["id"] in (t.score_note or "") for t in project.takes):
        return

    from ..continuity import score_take_continuity

    prompt_used = job.get("prompt") or ""
    is_rehearsal = bool(job.get("is_rehearsal"))
    shot_id = job.get("shot_id") or LIBRARY_SHOT_ID
    shot = next((s for s in project.shots if s.id == shot_id), None)
    label = (
        f"REHEARSAL · {job['mode'].upper()}"
        if is_rehearsal
        else f"{job['mode'].upper()} · {job['model_label']}"
    )
    if shot_id == LIBRARY_SHOT_ID:
        label = f"Library · {label}"
    take = Take(
        shot_id=shot_id,
        label=label,
        media_path=job["media_path"],
        thumb_path=job.get("thumb_path") or job["media_path"],
        seed=job.get("seed"),
        is_placeholder=bool(job.get("preview")),
        score_note=f"job:{job['id']} · {job.get('message') or ''}",
        prompt_used=prompt_used,
        is_rehearsal=is_rehearsal,
    )
    if shot:
        scored = score_take_continuity(
            project, shot, prompt_used, take.label, take=take
        )
        take.continuity_score = scored["continuity_score"]
        take.continuity_flags = scored["continuity_flags"]
        take.vision_score = scored.get("vision_score")
        take.identity_score = scored.get("identity_score")
        take.rejected = scored["rejected"]
        take.score_note = f"job:{job['id']} · {scored['score_note']}"
        shot.status = "ready"
        # Auto-pin best non-rejected final take; never auto-pin rehearsals
        if not is_rehearsal and not take.rejected and not shot.pinned_take_id:
            shot.pinned_take_id = take.id
        if take.rejected:
            take.label = f"{take.label} · REJECT"
    project.takes.append(take)
    job["_attached_take_id"] = take.id
    save_project(project)


def _maybe_chain_next(job: dict[str, Any]) -> None:
    """After a chained shot finishes, queue the next shot as i2v from this last frame."""
    chain = list(job.get("chain_shot_ids") or [])
    shot_id = job.get("shot_id")
    if not chain or not shot_id or shot_id not in chain:
        return
    idx = chain.index(shot_id)
    if idx >= len(chain) - 1:
        return
    next_id = chain[idx + 1]
    from ..continue_video import extract_last_frame
    from ..storage import get_preset, load_project, save_project

    try:
        project = load_project(job["project_id"])
    except FileNotFoundError:
        return

    next_shot = next((s for s in project.shots if s.id == next_id), None)
    if not next_shot:
        return

    frame = job.get("last_frame_path") or extract_last_frame(job.get("media_path"))
    if not frame:
        next_shot.status = "failed"
        save_project(project)
        return

    preset = get_preset(project.preset_id)
    gen = preset.get("generation", {})
    prompt = next_shot.prompt or next_shot.action or next_shot.title
    prompt = (
        f"seamless continuation from previous shot, same camera world, "
        f"continuous motion, {prompt}"
    )
    enqueue_job(
        {
            "mode": "i2v",
            "model_id": gen.get("default_i2v") or gen.get("default_t2v"),
            "prompt": prompt,
            "negative_prompt": next_shot.negative_prompt
            or "cut, hard edit, flash, jump cut",
            "project_id": project.id,
            "shot_id": next_shot.id,
            "image_path": frame,
            "cpu_offload": gen.get("cpu_offload", True),
            "frames": gen.get("default_frames"),
            "width": gen.get("default_width"),
            "height": gen.get("default_height"),
            "fps": gen.get("fps"),
            "is_rehearsal": bool(job.get("is_rehearsal")),
            "inject_continuity": True,
            "continue_from_previous": True,
            "continue_from_take_id": job.get("_attached_take_id"),
            "chain_shot_ids": chain,
            "quality": job.get("quality") if job.get("is_rehearsal") else None,
        }
    )
    next_shot.status = "generating"
    save_project(project)
