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
from .queue_store import loras_dir, models_dir
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
    return {
        "device": st.device,
        "modes": st.modes,
        "models": enriched,
        "active_model_id": active,
        "queue_length": st.queue_length,
        "preset_id": st.preset_id,
        "models_path": st.models_path,
        "backend": "builtin",  # never ComfyUI
        "size_presets": SIZE_PRESETS,
        "quality_presets": QUALITY_PRESETS,
        "loras_path": str(loras_dir()),
        "loras": loras,
        "lora_count": len(loras),
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

    prompt = payload.get("prompt") or ""
    negative = payload.get("negative_prompt") or ""
    is_rehearsal = bool(payload.get("is_rehearsal"))
    inject_continuity = payload.get("inject_continuity", True)

    # Inject continuity + identity locks when attached to a project shot
    if inject_continuity and payload.get("project_id"):
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
        "is_rehearsal": is_rehearsal,
        "continue_from_previous": bool(payload.get("continue_from_previous")),
        "continue_from_take_id": payload.get("continue_from_take_id"),
        "chain_shot_ids": list(payload.get("chain_shot_ids") or []),
        "media_path": None,
        "thumb_path": None,
        "last_frame_path": None,
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
        try:
            from ..continue_video import ensure_last_frame_sidecar

            job["last_frame_path"] = ensure_last_frame_sidecar(job.get("media_path"))
        except Exception:
            job["last_frame_path"] = None
        job["status"] = "done"
        job["progress"] = 1.0
        if not job.get("message") or job["status"] == "done" and not job["preview"]:
            msg = "Complete"
            if job.get("continue_from_previous"):
                msg = "Complete (continued from previous)"
            job["message"] = msg
        job["updated_at"] = utc_now()
        upsert_job(job)

        if job.get("project_id") and job.get("media_path"):
            _attach_to_project(job)
            _maybe_chain_next(job)
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
        from ..continuity import score_take_continuity

        prompt_used = job.get("prompt") or ""
        is_rehearsal = bool(job.get("is_rehearsal"))
        label = (
            f"REHEARSAL · {job['mode'].upper()}"
            if is_rehearsal
            else f"{job['mode'].upper()} · {job['model_label']}"
        )
        take = Take(
            shot_id=job["shot_id"],
            label=label,
            media_path=job["media_path"],
            thumb_path=job.get("thumb_path") or job["media_path"],
            seed=job.get("seed"),
            is_placeholder=bool(job.get("preview")),
            score_note=job.get("message") or "",
            prompt_used=prompt_used,
            is_rehearsal=is_rehearsal,
        )
        shot = next((s for s in project.shots if s.id == job["shot_id"]), None)
        if shot:
            scored = score_take_continuity(
                project, shot, prompt_used, take.label, take=take
            )
            take.continuity_score = scored["continuity_score"]
            take.continuity_flags = scored["continuity_flags"]
            take.vision_score = scored.get("vision_score")
            take.identity_score = scored.get("identity_score")
            take.rejected = scored["rejected"]
            take.score_note = scored["score_note"]
            shot.status = "ready"
            # Auto-pin best non-rejected final take; never auto-pin rehearsals
            if not is_rehearsal and not take.rejected and not shot.pinned_take_id:
                shot.pinned_take_id = take.id
            # If rejected, keep generating? — mark shot ready but unpinned for Sampling
            if take.rejected:
                take.label = f"{take.label} · REJECT"
        project.takes.append(take)
        # Kick sequential continuation for remaining shots in the chain
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
