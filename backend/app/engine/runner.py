from __future__ import annotations

import threading
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
    default_model_for_mode,
    get_model,
    list_models_for_mode,
)
from .device import detect_device
from .pipelines import run_diffusers_job, run_preview_job
from .queue_store import get_job as store_get
from .queue_store import list_jobs as store_list
from .queue_store import models_dir
from .queue_store import upsert_job

_WORKER_STARTED = False
_QUEUE: list[str] = []
_CV = threading.Condition()


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
    st = _dedupe_models(engine_status())
    return {
        "device": st.device,
        "modes": st.modes,
        "models": st.models,
        "queue_length": st.queue_length,
        "preset_id": st.preset_id,
        "models_path": st.models_path,
        "backend": "builtin",  # never ComfyUI
        "size_presets": SIZE_PRESETS,
        "quality_presets": QUALITY_PRESETS,
        "loras_path": str(models_dir() / "loras"),
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
        t = threading.Thread(target=_worker_loop, name="framewright-engine", daemon=True)
        t.start()


def enqueue_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Queue a built-in generation job."""
    _ensure_worker()
    settings = load_settings()
    preset = get_preset(payload.get("preset_id") or settings.preset_id)
    gen = preset.get("generation", {})
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
        raise ValueError("This mode needs an input image.")
    if mode_meta.get("needs_reference") and not payload.get("reference_path"):
        raise ValueError("This mode needs a reference image.")
    if mode_meta.get("needs_video") and not payload.get("video_path"):
        raise ValueError("Upsample video needs a video/clip path.")

    quality = payload.get("quality") or "balanced"
    qmeta = next((q for q in QUALITY_PRESETS if q["id"] == quality), QUALITY_PRESETS[1])
    base_steps = int(payload.get("steps") or model.get("default_steps") or 20)
    base_guidance = float(payload.get("guidance") or model.get("default_guidance") or 5)
    steps = max(1, int(base_steps * float(qmeta["steps_scale"])))
    guidance = float(base_guidance * float(qmeta["guidance_scale"]))

    duration_sec = payload.get("duration_sec")
    frames = payload.get("frames")
    fps = int(payload.get("fps") or gen.get("fps") or model.get("fps") or 16)
    if duration_sec and not frames and mode in ("t2v", "i2v", "ref2v", "upsample_video"):
        frames = max(8, int(float(duration_sec) * fps))
    if not frames:
        frames = int(gen.get("default_frames") or model.get("default_frames") or 49)
    if mode == "t2a" and not duration_sec:
        duration_sec = float(model.get("default_duration_sec") or 8)

    job = {
        "id": new_id("job"),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "queued",
        "progress": 0.0,
        "message": "Queued",
        "mode": mode,
        "model_id": model["id"],
        "model_label": model["label"],
        "prompt": payload.get("prompt") or "",
        "negative_prompt": payload.get("negative_prompt") or "",
        "width": int(payload.get("width") or gen.get("default_width") or 768),
        "height": int(payload.get("height") or gen.get("default_height") or 432),
        "steps": steps,
        "guidance": guidance,
        "quality": quality,
        "frames": int(frames),
        "fps": fps,
        "duration_sec": float(duration_sec) if duration_sec is not None else None,
        "seed": payload.get("seed"),
        "strength": payload.get("strength"),
        "cpu_offload": payload.get("cpu_offload", gen.get("cpu_offload", True)),
        "image_path": payload.get("image_path"),
        "reference_path": payload.get("reference_path"),
        "video_path": payload.get("video_path"),
        "lora_path": payload.get("lora_path"),
        "lora_scale": float(payload.get("lora_scale") if payload.get("lora_scale") is not None else 0.8),
        "project_id": payload.get("project_id"),
        "shot_id": payload.get("shot_id"),
        "media_path": None,
        "thumb_path": None,
        "error": None,
        "preview": False,
        "engine": "builtin",
    }
    upsert_job(job)
    with _CV:
        _QUEUE.append(job["id"])
        _CV.notify()
    return job


def _worker_loop() -> None:
    while True:
        with _CV:
            while not _QUEUE:
                _CV.wait()
            job_id = _QUEUE.pop(0)
        job = store_get(job_id)
        if not job:
            continue
        _run_one(job)


def _run_one(job: dict[str, Any]) -> None:
    ensure_dirs()
    job["status"] = "running"
    job["message"] = "Starting"
    job["progress"] = 0.01
    job["updated_at"] = utc_now()
    upsert_job(job)

    def cb(message: str, frac: float) -> None:
        job["message"] = message
        job["progress"] = frac
        job["updated_at"] = utc_now()
        upsert_job(job)

    out_dir = MEDIA_DIR / (job.get("project_id") or "standalone")
    out_path = out_dir / job["id"]
    device = detect_device()
    force_preview = bool(job.get("force_preview"))
    use_real = (
        not force_preview
        and device.get("ready_for_inference")
        and device.get("diffusers_available")
    )

    try:
        if use_real:
            result = run_diffusers_job(job, out_path, cb)
            job["preview"] = False
        else:
            result = run_preview_job(job, out_path, cb)
            job["preview"] = True
            if not device.get("torch_available"):
                job["message"] = (
                    "Preview only — install ROCm PyTorch + requirements-engine.txt, "
                    "then download a model."
                )
            elif not device.get("diffusers_available"):
                job["message"] = "Preview only — pip install diffusers transformers accelerate."
            else:
                job["message"] = "Preview only — no GPU visible; install AMD ROCm PyTorch."

        job["media_path"] = result.get("media_path")
        job["thumb_path"] = result.get("thumb_path")
        job["status"] = "done"
        job["progress"] = 1.0
        if not job.get("message") or job["status"] == "done" and not job["preview"]:
            job["message"] = "Complete"
        job["updated_at"] = utc_now()
        upsert_job(job)

        if job.get("project_id") and job.get("media_path"):
            _attach_to_project(job)
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = f"{exc}\n{traceback.format_exc()[-1500:]}"
        job["message"] = str(exc)
        job["updated_at"] = utc_now()
        upsert_job(job)


def _attach_to_project(job: dict[str, Any]) -> None:
    from ..models import Take
    from ..storage import load_project, save_project

    try:
        project = load_project(job["project_id"])
    except FileNotFoundError:
        return

    tag = f"job:{job['id']}"
    for char in project.characters:
        if tag in (char.tags or []) and not char.reference_path:
            char.reference_path = job.get("thumb_path") or job["media_path"]
    for scene in project.scenes:
        if tag in (scene.tags or []) and not scene.reference_path:
            scene.reference_path = job.get("thumb_path") or job["media_path"]

    if job.get("shot_id"):
        take = Take(
            shot_id=job["shot_id"],
            label=f"{job['mode'].upper()} · {job['model_label']}",
            media_path=job["media_path"],
            thumb_path=job.get("thumb_path") or job["media_path"],
            seed=job.get("seed"),
            is_placeholder=bool(job.get("preview")),
            score_note=job.get("message") or "",
        )
        project.takes.append(take)
        for shot in project.shots:
            if shot.id == job["shot_id"]:
                shot.status = "ready"
                if not shot.pinned_take_id:
                    shot.pinned_take_id = take.id
                break
    save_project(project)
