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
    job["message"] = "Starting"
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
