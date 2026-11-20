from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agent import plan_project
from .agent_director import director_chat
from .captions import captions_srt, generate_captions, timeline_progress
from .continuity import build_bible, rescore_project
# Engine / generate / gpu_estimate are imported lazily inside routes and the
# startup warm thread so uvicorn can bind :8787 before the heavy stack loads.
from .llm_providers import list_providers, probe_agent
from .models import (
    AgentMessage,
    ApplyFrameSizeRequest,
    ApplyRecipeRequest,
    AudioClip,
    CharacterProfile,
    ContinuityRulesRequest,
    CreateProjectRequest,
    CreateShotRequest,
    AgentPlanRequest,
    EngineGenerateRequest,
    EnginePreloadRequest,
    FilmNightRequest,
    GenerateRequest,
    PromptEnhanceRequest,
    GpuEstimateRequest,
    HealthResponse,
    PersonalImportRequest,
    PersonalLinksRequest,
    Project,
    RehearsalRequest,
    SceneProfile,
    Settings,
    TimelineClip,
    UpdateShotRequest,
    new_id,
)
from .nle_export import export_nle_package
from .personal_sources import (
    get_import,
    list_imports,
    personal_profile,
    save_personal_links,
    start_import,
)
from .paths import DATA_DIR, MEDIA_DIR, UPLOADS_DIR, ensure_dirs
from .storage import (
    delete_project,
    get_preset,
    list_presets,
    list_projects,
    load_project,
    load_settings,
    save_project,
    save_settings,
    settings_public,
)


async def probe_ollama() -> bool:
    settings = load_settings()
    try:
        from .llm_providers import _ollama_get_tags

        base, payload, _ = await _ollama_get_tags(settings)
        return bool(base and payload is not None)
    except Exception:
        return False

app = FastAPI(title="StudioNels", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_dirs()
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.on_event("startup")
def _startup_engine_worker() -> None:
    """Kick off worker/warm daemon in a background thread so uvicorn binds :8787 immediately.

    Inline warm-daemon wait blocked Application startup complete for ~10s+ (and much
    longer when torch/ROCm misbehaves), which left Pinokio wait-api hung on Windows.
    Engine imports stay inside the thread so binding :8787 is not delayed by runner/pipelines.
    """
    import threading

    def _warm_in_background() -> None:
        # Start the hidden engine process so torch is already imported.
        # Do not preload weights — the GPU stays idle until Generate.
        try:
            from .engine.runner import _ensure_warm_daemon, _ensure_worker, recover_interrupted_jobs

            try:
                recover_interrupted_jobs()
            except Exception:
                pass
            _ensure_worker()
            _ensure_warm_daemon()
        except Exception:
            pass

    try:
        threading.Thread(
            target=_warm_in_background,
            name="studionels-startup-warm",
            daemon=True,
        ).start()
    except Exception:
        pass


@app.get("/api/ready")
async def ready():
    """Lightweight readiness for Pinokio wait-api — no torch/Ollama probes."""
    return {"ok": True, "ready": True}


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from .engine.device import detect_device

    settings = load_settings()
    device = detect_device()
    agent = await probe_agent(settings)
    vram = device.get("vram_gb")
    ready = bool(device.get("ready_for_inference") and device.get("diffusers_available"))
    suggested = settings.preset_id or "amd-low-vram"
    if isinstance(vram, (int, float)):
        if vram >= 24:
            suggested = "amd-r9700"
        elif vram >= 8:
            suggested = "amd-low-vram"
        else:
            suggested = "cpu-fallback"
    elif not device.get("torch_available"):
        suggested = "cpu-fallback"
    if ready and device.get("rocm"):
        headline = f"AMD ready — {device.get('device_name')} · {vram} GB"
        detail = "Real generation available. Start a project or open Film night."
    elif ready:
        headline = f"GPU ready — {device.get('device_name')}"
        detail = "Engine can load Diffusers. Pick a frame size and generate."
    elif device.get("torch_available"):
        headline = "Torch installed — Diffusers/ROCm still needed for real frames"
        detail = "Jobs may preview until engine extras + AMD ROCm PyTorch are in place."
    else:
        headline = "First run — preview mode until ROCm PyTorch is installed"
        detail = "StudioNels still plans, locks characters, and cuts. Install ROCm torch for real video."
    return HealthResponse(
        ok=True,
        ollama=await probe_ollama(),
        engine="builtin",
        torch=bool(device.get("torch_available")),
        gpu=bool(device.get("ready_for_inference")),
        device_name=str(device.get("device_name") or "CPU"),
        preset_id=settings.preset_id,
        data_dir=str(DATA_DIR),
        agent_provider=str(agent.get("provider") or settings.agent_provider),
        agent_label=str(agent.get("label") or settings.agent_provider),
        agent_reachable=bool(agent.get("reachable")),
        agent_detail=str(agent.get("detail") or ""),
        rocm=bool(device.get("rocm")),
        vram_gb=float(vram) if isinstance(vram, (int, float)) else None,
        backend=str(device.get("backend") or "none"),
        ready_for_inference=ready,
        will_preview=not ready,
        suggested_preset=suggested,
        first_run_headline=headline,
        first_run_detail=detail,
        notes=list(device.get("notes") or []),
    )


@app.get("/api/engine")
async def engine():
    from .engine.runner import engine_status_public

    return engine_status_public()


@app.get("/api/engine/loras")
async def engine_loras():
    """Scan the app loras/ folder for dropdown picks — no path pasting."""
    from .engine.models_manager import list_loras
    from .engine.queue_store import loras_dir

    items = list_loras()
    return {
        "path": str(loras_dir()),
        "loras": items,
        "count": len(items),
    }


@app.get("/api/engine/models")
async def engine_models():
    """Catalog + download status + which model is active."""
    from .engine.models_manager import get_active_model_id, list_models_with_status

    active = get_active_model_id()
    models = list_models_with_status(active)
    return {"models": models, "active_model_id": active, "count": len(models)}


@app.post("/api/engine/models/{model_id}/download")
async def engine_model_download(model_id: str, force: bool = False):
    from .engine.models_manager import download_model

    try:
        return download_model(model_id, force=force)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/engine/models/{model_id}/cancel")
async def engine_model_cancel(model_id: str):
    from .engine.models_manager import cancel_download

    try:
        return cancel_download(model_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/engine/models/{model_id}/clear")
async def engine_model_clear(model_id: str, delete_files: bool = False):
    from .engine.models_manager import clear_download

    try:
        return clear_download(model_id, delete_files=delete_files)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/engine/models/{model_id}/activate")
async def engine_model_activate(model_id: str):
    from .engine.models_manager import set_active_model

    try:
        return set_active_model(model_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/engine/models/custom")
async def engine_model_add_custom(body: dict):
    """Register any Hugging Face Diffusers repo (for big GPUs / already-downloaded packs)."""
    from .engine.custom_models import add_custom_model
    from .engine.models_manager import list_models_with_status, set_active_model

    try:
        entry = add_custom_model(
            hf_id=str(body.get("hf_id") or ""),
            label=body.get("label"),
            modes=body.get("modes"),
            kind=str(body.get("kind") or "video"),
            min_vram_gb=float(body.get("min_vram_gb") or 24),
            default_steps=int(body.get("default_steps") or 20),
            default_guidance=float(body.get("default_guidance") or 5.0),
            notes=body.get("notes"),
            local_path=body.get("local_path"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if body.get("activate"):
        set_active_model(entry["id"])
    return {"ok": True, "model": entry, "models": list_models_with_status()}


@app.get("/api/engine/templates")
async def engine_templates():
    """Comfy-style model packs: one card = model + encoders / VAEs / LoRAs."""
    from .engine.templates import list_templates

    items = list_templates()
    return {"templates": items, "count": len(items)}


@app.post("/api/engine/templates/{template_id}/install")
async def engine_template_install(template_id: str, body: dict | None = None):
    """Click a template → queue downloads for every component in the pack."""
    from .engine.templates import install_template

    body = body or {}
    try:
        return install_template(
            template_id,
            include_optional=bool(body.get("include_optional", True)),
            activate=bool(body.get("activate", True)),
            force=bool(body.get("force", False)),
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/engine/wan2gp/scan")
async def engine_wan2gp_scan():
    """Full Wan2GP inventory: video, image, audio, upsample, LoRAs, TEs, VAEs."""
    from .engine.wan2gp_assets import inventory

    inv = inventory()
    counts = inv.get("counts") or {}
    return {
        **inv,
        "packs": inv.get("video_packs") or [],
        "count": int(counts.get("video_packs") or 0),
        "total": sum(int(v or 0) for v in counts.values()),
    }


@app.post("/api/engine/wan2gp/import")
async def engine_wan2gp_import(body: dict):
    """Import a Wan2GP root / ckpts / loras folder — all asset types in one place."""
    from .engine.models_manager import list_models_with_status
    from .engine.wan2gp_assets import import_wan2gp_root

    path = str(body.get("path") or "").strip()
    if not path:
        raise HTTPException(
            400,
            "path is required (Wan2GP root, ckpts, or loras folder)",
        )
    try:
        result = import_wan2gp_root(path, activate=bool(body.get("activate", True)))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    result["models"] = list_models_with_status()
    return result


@app.get("/api/engine/assets")
async def engine_assets():
    """One payload for the Generation assets panel."""
    from .engine.wan2gp_assets import inventory
    from .storage import load_settings

    s = load_settings()
    inv = inventory()
    return {
        **inv,
        "settings": {
            "wan2gp_ckpts_path": s.wan2gp_ckpts_path or "",
            "wan2gp_loras_path": s.wan2gp_loras_path or "",
            "wan2gp_text_encoders_path": s.wan2gp_text_encoders_path or "",
            "wan2gp_assets_path": s.wan2gp_assets_path or "",
        },
    }


@app.delete("/api/engine/models/custom/{model_id}")
async def engine_model_remove_custom(model_id: str):
    from .engine.custom_models import remove_custom_model

    try:
        return remove_custom_model(model_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/engine/jobs")
async def engine_jobs(limit: int = 40):
    from .engine.runner import list_jobs

    return list_jobs(limit)


@app.get("/api/engine/jobs/{job_id}")
async def engine_job(job_id: str):
    from .engine.runner import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/engine/jobs/{job_id}/cancel")
async def engine_job_cancel(job_id: str):
    """Stop generation without wiping the prompt/settings workflow snapshot."""
    from .engine.runner import cancel_job

    try:
        return cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/engine/jobs/cancel-all")
async def engine_jobs_cancel_all():
    from .engine.runner import cancel_all_jobs

    return cancel_all_jobs()


@app.delete("/api/engine/jobs/{job_id}")
async def engine_job_dismiss(job_id: str):
    """Hide/remove a job from the generation list (cancels if still running)."""
    from .engine.runner import dismiss_job

    try:
        return dismiss_job(job_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/engine/jobs/clear-finished")
async def engine_jobs_clear_finished():
    """Remove finished / failed / cancelled jobs from the queue list."""
    from .engine.runner import dismiss_finished_jobs

    return dismiss_finished_jobs()


@app.get("/api/engine/workflows")
async def engine_workflows(limit: int = 20):
    """Stopped/failed jobs you can restore into Generate."""
    from .engine.runner import list_restorable_jobs

    return {"jobs": list_restorable_jobs(limit)}


@app.post("/api/engine/generate")
async def engine_generate(body: EngineGenerateRequest):
    from .engine.runner import enqueue_job

    try:
        return enqueue_job(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/engine/jobs/{job_id}/save-to-project")
async def engine_job_save_to_project(job_id: str, body: dict | None = None):
    """Attach a finished job’s media into the project library / Sampling (e.g. standalone audio)."""
    from .engine.runner import _attach_to_project, get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "done" or not job.get("media_path"):
        raise HTTPException(400, "Only finished jobs with media can be saved")
    project_id = (body or {}).get("project_id") or job.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id is required")
    job = dict(job)
    job["project_id"] = project_id
    if (body or {}).get("shot_id"):
        job["shot_id"] = (body or {}).get("shot_id")
    _attach_to_project(job)
    from .storage import load_project

    return {
        "ok": True,
        "take_id": job.get("_attached_take_id"),
        "project": load_project(project_id),
        "hint": "Saved to Sampling → Library / standalone generations.",
    }


@app.post("/api/engine/enhance-prompt")
async def engine_enhance_prompt(body: PromptEnhanceRequest):
    """Expand a short prompt for Generate (Agent LLM, or offline fallback)."""
    from .prompt_enhance import enhance_prompt

    try:
        return await enhance_prompt(
            body.prompt,
            mode=body.mode or "t2v",
            negative_prompt=body.negative_prompt or "",
            style=body.style,
            force_builtin=body.force_builtin,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/engine/estimate")
async def engine_estimate(body: GpuEstimateRequest):
    """Honest GPU fit + ETA before queueing — #5 can-my-GPU-do-this."""
    from .gpu_estimate import estimate_job

    return estimate_job(body.model_dump())


@app.post("/api/engine/upload")
async def engine_upload(file: UploadFile = File(...), kind: str = "image"):
    ensure_dirs()
    suffix = Path(file.filename or "upload.png").suffix or ".png"
    dest = UPLOADS_DIR / f"{new_id(kind)}{suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    dest.write_bytes(data)
    return {"path": str(dest), "url": f"/api/file?path={dest}"}


@app.get("/api/presets")
async def presets():
    return list_presets()


@app.get("/api/engine/memory-profiles")
async def engine_memory_profiles():
    """Low→high VRAM profiles: where weights sit (RAM / offload / GPU)."""
    from .engine.memory import list_memory_profiles
    from .storage import load_settings

    s = load_settings()
    profiles = list_memory_profiles()
    return {
        "profiles": profiles,
        "active_id": s.preset_id,
        "count": len(profiles),
    }


@app.get("/api/engine/warm")
async def engine_warm():
    """Warm daemon + resident model status (Wan2GP-like keep-loaded)."""
    from .engine.runner import warm_engine_status

    return warm_engine_status()


@app.post("/api/engine/preload")
async def engine_preload(body: EnginePreloadRequest = EnginePreloadRequest()):
    """Load active (or given) Ready model into the warm daemon pipe_cache."""
    from .engine.catalog import get_model
    from .engine.models_manager import get_active_model_id, list_models_with_status
    from .engine.runner import preload_model, start_preload_background, warm_engine_status

    payload = body
    model_id = str(payload.model_id or "").strip() or get_active_model_id()
    if not model_id:
        raise HTTPException(
            status_code=400,
            detail="No model_id and no active model — pick one in Models first.",
        )
    try:
        row = next(
            (m for m in list_models_with_status() if m.get("id") == model_id),
            None,
        )
    except Exception:
        row = None
    model = get_model(model_id)
    label = str((model or {}).get("label") or (row or {}).get("label") or model_id)
    if model and model.get("hf_id") and row is not None:
        if not (
            row.get("installed") or str(row.get("download_status") or "") == "installed"
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{label} is not Ready on disk. Open Models → Download until Ready, "
                    "then tap Load into studio."
                ),
            )
    if payload.wait:
        result = preload_model(
            model_id,
            preset_id=str(payload.preset_id) if payload.preset_id else None,
        )
        if not result.get("ok"):
            raise HTTPException(
                status_code=500,
                detail=str(result.get("error") or "Preload failed"),
            )
        return {**result, "warm": warm_engine_status()}
    started = start_preload_background(
        model_id,
        preset_id=str(payload.preset_id) if payload.preset_id else None,
    )
    return {
        **started,
        "ok": True,
        "label": label,
        "warm": warm_engine_status(),
    }


@app.get("/api/settings")
async def get_settings():
    return settings_public()


@app.put("/api/settings")
async def put_settings(body: Settings):
    import os

    saved = save_settings(body)
    # Reflect Keep model loaded immediately (overrides Pinokio default env for this process)
    try:
        import json

        from .engine.runner import _daemon_paths, _ensure_warm_daemon

        # The engine process stays up either way. Unchecking drops the cached
        # weights inside that process; torch stays imported.
        os.environ["STUDIONELS_WARM_ENGINE"] = "1"
        _ensure_warm_daemon()
        if not getattr(saved, "keep_model_loaded", True):
            req_dir = _daemon_paths()["requests"]
            req_dir.mkdir(parents=True, exist_ok=True)
            (req_dir / "release-cache.json").write_text(
                json.dumps({"action": "release"}),
                encoding="utf-8",
            )
    except Exception:
        pass
    return settings_public(saved)


@app.get("/api/agent/providers")
async def agent_providers():
    settings = load_settings()
    probe = await probe_agent(settings)
    return {"providers": list_providers(), "status": probe}


@app.post("/api/agent/test")
async def agent_test():
    """Test current agent provider (Ollama reachability + tiny chat ping)."""
    from .llm_providers import test_agent_ping

    settings = load_settings()
    return await test_agent_ping(settings)


@app.get("/api/personal")
async def get_personal():
    return personal_profile()


@app.put("/api/personal")
async def put_personal(body: PersonalLinksRequest):
    return save_personal_links(
        github_url=body.github_url,
        huggingface_url=body.huggingface_url,
        huggingface_token=body.huggingface_token,
        creator_display_name=body.creator_display_name,
    )


@app.post("/api/personal/import")
async def personal_import(body: PersonalImportRequest):
    try:
        return start_import(body.kind, body.source, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/personal/imports")
async def personal_imports(limit: int = 20):
    return list_imports(limit)


@app.get("/api/personal/imports/{job_id}")
async def personal_import_job(job_id: str):
    job = get_import(job_id)
    if not job:
        raise HTTPException(404, "Import not found")
    return job


@app.post("/api/personal/imports/{job_id}/cancel")
async def personal_import_cancel(job_id: str):
    from .personal_sources import cancel_import

    try:
        return cancel_import(job_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete("/api/personal/imports/{job_id}")
async def personal_import_clear(job_id: str):
    from .personal_sources import clear_import

    try:
        return clear_import(job_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/projects")
async def projects():
    return list_projects()


@app.post("/api/projects", response_model=Project)
async def create_project(body: CreateProjectRequest):
    from .frame_sizes import apply_frame_to_project

    settings = load_settings()
    project = Project(
        title=body.title.strip() or "Untitled",
        mode=body.mode,
        logline=body.logline,
        preset_id=body.preset_id or settings.preset_id,
    )
    apply_frame_to_project(project, body.frame_size_id or "16:9-draft")
    project.agent_messages.append(
        AgentMessage(
            role="assistant",
            content=(
                f"Welcome to StudioNels — your local film studio. Tell me your idea for this "
                f"{body.mode.replace('_', ' ')} and I'll break it into editable shots. "
                "Add characters and scenes in Profiles first if you already know them — "
                "or we can invent as we go. Everything stays on your machine."
            ),
        )
    )
    return save_project(project)


@app.get("/api/projects/{project_id}", response_model=Project)
async def get_project(project_id: str):
    try:
        return load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")


@app.put("/api/projects/{project_id}", response_model=Project)
async def put_project(project_id: str, body: Project):
    if body.id != project_id:
        raise HTTPException(400, "ID mismatch")
    return save_project(body)


@app.post("/api/projects/{project_id}/save", response_model=Project)
async def save_now(project_id: str):
    try:
        project = load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")
    return save_project(project)


@app.delete("/api/projects/{project_id}")
async def remove_project(project_id: str):
    delete_project(project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/agent", response_model=Project)
async def agent_plan(project_id: str, body: AgentPlanRequest):
    try:
        project = load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")
    if not body.message.strip():
        raise HTTPException(400, "Message required")
    project = await plan_project(project, body.message.strip(), body.replace_shots)
    return save_project(project)


@app.post("/api/projects/{project_id}/agent/chat")
async def agent_chat(project_id: str, body: AgentPlanRequest):
    """Conversational director: reply + apply actions, return ui_actions for the app."""
    try:
        project = load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")
    if not body.message.strip() and not body.attachments:
        raise HTTPException(400, "Message or attachment required")
    result = await director_chat(
        project,
        body.message.strip(),
        attachments=list(body.attachments or []),
    )
    proj = result["project"]
    return {
        "project": proj.model_dump() if hasattr(proj, "model_dump") else proj,
        "message": result.get("message") or "",
        "ui_actions": result.get("ui_actions") or [],
        "used_builtin": bool(result.get("used_builtin")),
        "provider": result.get("provider") or "",
    }


@app.post("/api/projects/{project_id}/characters", response_model=Project)
async def add_character(project_id: str, body: CharacterProfile):
    from .identity_lock import refresh_character_identity

    project = load_project(project_id)
    if not body.id:
        body.id = new_id("char")
    project.characters.append(refresh_character_identity(body))
    return save_project(project)


@app.put("/api/projects/{project_id}/characters/{character_id}", response_model=Project)
async def update_character(project_id: str, character_id: str, body: CharacterProfile):
    from .identity_lock import refresh_character_identity

    project = load_project(project_id)
    for i, c in enumerate(project.characters):
        if c.id == character_id:
            body.id = character_id
            project.characters[i] = refresh_character_identity(body)
            return save_project(project)
    raise HTTPException(404, "Character not found")


@app.delete("/api/projects/{project_id}/characters/{character_id}", response_model=Project)
async def delete_character(project_id: str, character_id: str):
    project = load_project(project_id)
    project.characters = [c for c in project.characters if c.id != character_id]
    return save_project(project)


@app.post("/api/projects/{project_id}/scenes", response_model=Project)
async def add_scene(project_id: str, body: SceneProfile):
    project = load_project(project_id)
    if not body.id:
        body.id = new_id("scene")
    project.scenes.append(body)
    return save_project(project)


@app.put("/api/projects/{project_id}/scenes/{scene_id}", response_model=Project)
async def update_scene(project_id: str, scene_id: str, body: SceneProfile):
    project = load_project(project_id)
    for i, s in enumerate(project.scenes):
        if s.id == scene_id:
            body.id = scene_id
            project.scenes[i] = body
            return save_project(project)
    raise HTTPException(404, "Scene not found")


@app.delete("/api/projects/{project_id}/scenes/{scene_id}", response_model=Project)
async def delete_scene(project_id: str, scene_id: str):
    project = load_project(project_id)
    project.scenes = [s for s in project.scenes if s.id != scene_id]
    return save_project(project)


@app.post("/api/projects/{project_id}/shots", response_model=Project)
async def add_shot(project_id: str, body: CreateShotRequest):
    """Add a shot by hand — storyboard / shot list without the agent."""
    from .models import Shot

    project = load_project(project_id)
    shot = Shot(
        index=len(project.shots),
        title=(body.title or "New shot").strip() or "New shot",
        action=body.action or "",
        dialogue=body.dialogue or "",
        camera=body.camera or "medium",
        duration_sec=float(body.duration_sec or 3),
        character_ids=list(body.character_ids or []),
        scene_id=body.scene_id,
        prompt=body.prompt or "",
        negative_prompt=body.negative_prompt or "",
        storyboard_note=body.storyboard_note or "",
        director_notes=body.director_notes or "",
        status="draft",
    )
    insert_at = body.insert_at
    if insert_at is None or insert_at < 0 or insert_at >= len(project.shots):
        project.shots.append(shot)
    else:
        project.shots.insert(insert_at, shot)
    for i, s in enumerate(project.shots):
        s.index = i
    return save_project(project)


@app.patch("/api/projects/{project_id}/shots/{shot_id}", response_model=Project)
async def patch_shot(project_id: str, shot_id: str, body: UpdateShotRequest):
    project = load_project(project_id)
    for shot in project.shots:
        if shot.id == shot_id:
            data = body.model_dump(exclude_unset=True)
            new_index = data.pop("index", None)
            for key, value in data.items():
                setattr(shot, key, value)
            if new_index is not None:
                ordered = [s for s in project.shots if s.id != shot_id]
                idx = max(0, min(int(new_index), len(ordered)))
                ordered.insert(idx, shot)
                project.shots = ordered
                for i, s in enumerate(project.shots):
                    s.index = i
            return save_project(project)
    raise HTTPException(404, "Shot not found")


@app.delete("/api/projects/{project_id}/shots/{shot_id}", response_model=Project)
async def delete_shot(project_id: str, shot_id: str):
    project = load_project(project_id)
    project.shots = [s for s in project.shots if s.id != shot_id]
    for i, s in enumerate(project.shots):
        s.index = i
    project.timeline = [c for c in project.timeline if c.shot_id != shot_id]
    project.takes = [t for t in project.takes if t.shot_id != shot_id]
    return save_project(project)


@app.post("/api/projects/{project_id}/generate", response_model=Project)
async def generate(project_id: str, body: GenerateRequest):
    from .generate import generate_takes

    project = load_project(project_id)
    return await generate_takes(
        project,
        body.shot_ids,
        body.kind,
        body.mode,
        is_rehearsal=body.is_rehearsal,
        inject_continuity=body.inject_continuity,
        continue_from_previous=body.continue_from_previous,
        continue_from_take_id=body.continue_from_take_id,
    )


@app.get("/api/projects/{project_id}/shots/{shot_id}/continue-source")
async def continue_source(project_id: str, shot_id: str, take_id: str | None = None):
    from .continue_video import continuation_source

    project = load_project(project_id)
    shot = next((s for s in project.shots if s.id == shot_id), None)
    if not shot:
        raise HTTPException(404, "Shot not found")
    src = continuation_source(project, shot, from_take_id=take_id)
    if not src:
        return {
            "ok": False,
            "detail": "No previous take with media — generate the prior shot first, or start with t2v.",
        }
    return {"ok": True, **src}


@app.get("/api/projects/{project_id}/continuity")
async def get_continuity(project_id: str):
    project = load_project(project_id)
    bible = build_bible(project)
    if not project.world_bible:
        project.world_bible = bible["text"]
        save_project(project)
    takes = [
        {
            "id": t.id,
            "shot_id": t.shot_id,
            "label": t.label,
            "continuity_score": t.continuity_score,
            "continuity_flags": t.continuity_flags,
            "rejected": t.rejected,
            "is_rehearsal": t.is_rehearsal,
        }
        for t in project.takes
    ]
    return {
        "bible": bible,
        "world_bible": project.world_bible,
        "rules": project.continuity_rules,
        "auto_reject_below": project.auto_reject_below,
        "takes": takes,
    }


@app.put("/api/projects/{project_id}/continuity", response_model=Project)
async def put_continuity(project_id: str, body: ContinuityRulesRequest):
    project = load_project(project_id)
    project.continuity_rules = [r.strip() for r in body.rules if r and r.strip()]
    if body.auto_reject_below is not None:
        project.auto_reject_below = max(0.0, min(1.0, float(body.auto_reject_below)))
    if body.rebuild_bible:
        project.world_bible = build_bible(project)["text"]
    project = rescore_project(project)
    return save_project(project)


@app.post("/api/projects/{project_id}/continuity/rescore", response_model=Project)
async def continuity_rescore(project_id: str):
    project = load_project(project_id)
    project.world_bible = build_bible(project)["text"]
    project = rescore_project(project)
    return save_project(project)


@app.post("/api/projects/{project_id}/rehearsal", response_model=Project)
async def rehearsal_pass(project_id: str, body: RehearsalRequest):
    from .rehearsal import run_rehearsal

    project = load_project(project_id)
    if not project.shots:
        raise HTTPException(400, "Add shots before running a rehearsal pass.")
    return run_rehearsal(project, body.shot_ids, body.takes_per_shot, body.quality)


@app.post("/api/projects/{project_id}/takes/{take_id}/promote", response_model=Project)
async def promote_take(project_id: str, take_id: str):
    from .rehearsal import promote_rehearsal_take

    project = load_project(project_id)
    try:
        return promote_rehearsal_take(project, take_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/projects/{project_id}/export/nle")
async def export_nle(project_id: str, fps: float = 24.0):
    project = load_project(project_id)
    return export_nle_package(project, fps=fps)


@app.post("/api/projects/{project_id}/takes/{take_id}/pin", response_model=Project)
async def pin_take(project_id: str, take_id: str):
    project = load_project(project_id)
    take = next((t for t in project.takes if t.id == take_id), None)
    if not take:
        raise HTTPException(404, "Take not found")
    take.rejected = False
    for shot in project.shots:
        if shot.id == take.shot_id:
            shot.pinned_take_id = take.id
            break
    # Ensure on timeline
    existing = next((c for c in project.timeline if c.shot_id == take.shot_id), None)
    if existing:
        existing.take_id = take.id
        existing.pinned = True
    else:
        project.timeline.append(
            TimelineClip(
                shot_id=take.shot_id,
                take_id=take.id,
                pinned=True,
                order=len(project.timeline),
            )
        )
    return save_project(project)


def _unlink_take_media(take) -> None:
    from .paths import MEDIA_DIR, OUTPUTS_DIR, ROOT

    for attr in ("media_path", "thumb_path"):
        raw = getattr(take, attr, None)
        if not raw:
            continue
        try:
            p = Path(raw).expanduser().resolve()
        except Exception:
            continue
        allowed = [MEDIA_DIR.resolve(), OUTPUTS_DIR.resolve(), ROOT.resolve()]
        if not any(root == p or root in p.parents for root in allowed):
            continue
        try:
            if p.is_file():
                p.unlink(missing_ok=True)
        except Exception:
            pass


@app.delete("/api/projects/{project_id}/takes/{take_id}", response_model=Project)
async def delete_take(project_id: str, take_id: str, delete_files: bool = True):
    """Remove one take (preview or real) from Sampling / timeline."""
    project = load_project(project_id)
    take = next((t for t in project.takes if t.id == take_id), None)
    if not take:
        raise HTTPException(404, "Take not found")
    if delete_files:
        _unlink_take_media(take)
    project.takes = [t for t in project.takes if t.id != take_id]
    for shot in project.shots:
        if shot.pinned_take_id == take_id:
            shot.pinned_take_id = None
            shot.status = "draft" if not any(t.shot_id == shot.id for t in project.takes) else "ready"
    project.timeline = [c for c in project.timeline if c.take_id != take_id]
    for i, c in enumerate(project.timeline):
        c.order = i
    return save_project(project)


@app.post("/api/projects/{project_id}/takes/clear-previews", response_model=Project)
async def clear_preview_takes(project_id: str, delete_files: bool = True):
    """Delete all preview/placeholder takes so Sampling isn't cluttered."""
    project = load_project(project_id)
    doomed = [t for t in project.takes if t.is_placeholder]
    doomed_ids = {t.id for t in doomed}
    if delete_files:
        for t in doomed:
            _unlink_take_media(t)
    project.takes = [t for t in project.takes if t.id not in doomed_ids]
    for shot in project.shots:
        if shot.pinned_take_id in doomed_ids:
            shot.pinned_take_id = None
            shot.status = "draft" if not any(t.shot_id == shot.id for t in project.takes) else "ready"
    project.timeline = [c for c in project.timeline if c.take_id not in doomed_ids]
    for i, c in enumerate(project.timeline):
        c.order = i
    return save_project(project)


@app.post("/api/projects/{project_id}/takes/{take_id}/add-audio")
async def take_add_audio(
    project_id: str,
    take_id: str,
    audio_path: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    """Mux audio onto an existing video take (keeps the original take, adds a new one)."""
    from .engine.pipelines import mux_audio_onto_video
    from .models import Take
    from .paths import MEDIA_DIR

    project = load_project(project_id)
    take = next((t for t in project.takes if t.id == take_id), None)
    if not take:
        raise HTTPException(404, "Take not found")
    if not take.media_path or not str(take.media_path).lower().endswith((".mp4", ".webm", ".mov")):
        raise HTTPException(400, "Take has no video to attach audio to")

    audio: str | None = audio_path
    if file is not None and file.filename:
        data = await file.read()
        dest = UPLOADS_DIR / f"{new_id('aud')}{Path(file.filename).suffix or '.wav'}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        audio = str(dest)
    if not audio:
        raise HTTPException(400, "Provide audio file upload or audio_path=")

    out_dir = MEDIA_DIR / project_id
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        muxed = mux_audio_onto_video(
            take.media_path,
            audio,
            out_path=out_dir / f"{new_id('mux')}.mp4",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc

    new_take = Take(
        shot_id=take.shot_id,
        label=f"{take.label} + audio",
        media_path=muxed,
        thumb_path=take.thumb_path,
        seed=take.seed,
        is_placeholder=False,
        score_note="Audio muxed onto video",
        prompt_used=take.prompt_used,
        is_rehearsal=False,
    )
    project.takes.append(new_take)
    save_project(project)
    return {
        "ok": True,
        "project": project.model_dump(),
        "take": new_take.model_dump(),
        "media_path": muxed,
        "message": "Audio added — new take created (original kept).",
    }


@app.put("/api/projects/{project_id}/timeline", response_model=Project)
async def set_timeline(project_id: str, clips: list[TimelineClip]):
    project = load_project(project_id)
    for i, clip in enumerate(clips):
        clip.order = i
    project.timeline = clips
    return save_project(project)


@app.put("/api/projects/{project_id}/audio-timeline", response_model=Project)
async def set_audio_timeline(project_id: str, clips: list[AudioClip]):
    project = load_project(project_id)
    for i, clip in enumerate(clips):
        clip.order = i
    project.audio_timeline = clips
    return save_project(project)


@app.post("/api/projects/{project_id}/audio-timeline", response_model=Project)
async def add_audio_clip(project_id: str, body: AudioClip):
    project = load_project(project_id)
    if not body.id:
        body.id = new_id("aud")
    body.order = len(project.audio_timeline)
    project.audio_timeline.append(body)
    return save_project(project)


@app.delete("/api/projects/{project_id}/audio-timeline/{clip_id}", response_model=Project)
async def delete_audio_clip(project_id: str, clip_id: str):
    project = load_project(project_id)
    project.audio_timeline = [c for c in project.audio_timeline if c.id != clip_id]
    for i, c in enumerate(project.audio_timeline):
        c.order = i
    return save_project(project)


@app.post("/api/projects/{project_id}/captions/generate", response_model=Project)
async def captions_generate(project_id: str, overwrite: bool = False):
    project = load_project(project_id)
    return generate_captions(project, overwrite=overwrite)


@app.get("/api/projects/{project_id}/captions.srt")
async def captions_export_srt(project_id: str):
    from fastapi.responses import PlainTextResponse

    project = load_project(project_id)
    body = captions_srt(project)
    filename = f"{project.title or 'captions'}.srt".replace(" ", "_")
    return PlainTextResponse(
        body or "1\n00:00:00,000 --> 00:00:01,000\n\n",
        media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/projects/{project_id}/timeline/progress")
async def get_timeline_progress(project_id: str):
    project = load_project(project_id)
    return timeline_progress(project)


@app.get("/api/projects/{project_id}/preset")
async def project_preset(project_id: str):
    project = load_project(project_id)
    return get_preset(project.preset_id)


@app.get("/api/frame-sizes")
async def frame_sizes():
    from .frame_sizes import list_frame_sizes

    return {"sizes": list_frame_sizes()}


@app.post("/api/projects/{project_id}/frame-size", response_model=Project)
async def set_frame_size(project_id: str, body: ApplyFrameSizeRequest):
    from .frame_sizes import apply_frame_to_project

    project = load_project(project_id)
    apply_frame_to_project(project, body.frame_size_id)
    return save_project(project)


@app.get("/api/recipes")
async def recipes():
    from .recipes import list_recipes

    return {"recipes": list_recipes()}


@app.post("/api/projects/{project_id}/recipes/apply", response_model=Project)
async def recipe_apply(project_id: str, body: ApplyRecipeRequest):
    from .recipes import apply_recipe

    project = load_project(project_id)
    try:
        return apply_recipe(project, body.recipe_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/projects/{project_id}/stitch")
async def stitch_project(project_id: str):
    from .stitch import stitch_preview

    project = load_project(project_id)
    return stitch_preview(project)


@app.post("/api/projects/{project_id}/film-night")
async def film_night(project_id: str, body: FilmNightRequest | None = None):
    from .film_night import run_film_night

    project = load_project(project_id)
    stage = (body.stage if body else "full") or "full"
    result = await run_film_night(project, stage)
    if result.get("project") and isinstance(result["project"], dict):
        # reload latest from disk if saved during pipeline
        try:
            result["project"] = load_project(project_id).model_dump()
        except Exception:
            pass
    return result


@app.post("/api/projects/{project_id}/export/pack")
async def export_pack(project_id: str):
    from .packs import export_project_pack

    project = load_project(project_id)
    return export_project_pack(project)


@app.get("/api/packs")
async def packs_list():
    from .packs import list_packs

    return {"packs": list_packs()}


@app.post("/api/packs/import", response_model=Project)
async def packs_import(path: str):
    from .packs import import_project_pack

    try:
        return import_project_pack(Path(path))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/projects/{project_id}/characters/{character_id}/identity-lock", response_model=Project)
async def character_identity_lock(project_id: str, character_id: str):
    from .identity_lock import refresh_character_identity

    project = load_project(project_id)
    for i, c in enumerate(project.characters):
        if c.id == character_id:
            project.characters[i] = refresh_character_identity(c)
            return save_project(project)
    raise HTTPException(404, "Character not found")


@app.post("/api/projects/{project_id}/director/import-video")
async def director_import_video(
    project_id: str,
    file: UploadFile | None = File(None),
    path: str | None = Form(None),
    title: str | None = Form(None),
    insert_at: int | None = Form(None),
):
    """Add an existing video clip to the Director timeline (shot + take + clip)."""
    from .director_import import import_video_clip, store_upload_bytes

    project = load_project(project_id)
    source: str | None = path
    if file is not None and file.filename:
        data = await file.read()
        if not data:
            raise HTTPException(400, "Empty file")
        stored = store_upload_bytes(file.filename, data)
        source = str(stored)
        if not title:
            title = Path(file.filename).stem
    if not source:
        raise HTTPException(400, "Provide a video file upload or path=")
    try:
        result = import_video_clip(
            project, source, title=title, insert_at=insert_at
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    proj = result.pop("project")
    return {
        "ok": True,
        "project": proj.model_dump() if hasattr(proj, "model_dump") else proj,
        **result,
    }


@app.get("/api/file")
async def get_file(path: str):
    from .paths import LORAS_DIR, MODELS_DIR, OUTPUTS_DIR, ROOT, UPLOADS_DIR

    p = Path(path).expanduser().resolve()
    allowed = [
        MEDIA_DIR.resolve(),
        OUTPUTS_DIR.resolve(),
        UPLOADS_DIR.resolve(),
        MODELS_DIR.resolve(),
        LORAS_DIR.resolve(),
        ROOT.resolve(),
    ]
    if not any(root == p or root in p.parents for root in allowed):
        raise HTTPException(403, "Outside app folders")
    if not p.exists():
        raise HTTPException(404, "Missing file")
    return FileResponse(p)
