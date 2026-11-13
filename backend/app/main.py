from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agent import plan_project
from .captions import captions_srt, generate_captions, timeline_progress
from .continuity import build_bible, rescore_project
from .engine.device import detect_device
from .engine.runner import engine_status_public, enqueue_job, get_job, list_jobs
from .generate import generate_takes
from .gpu_estimate import estimate_job
from .llm_providers import list_providers, probe_agent
from .models import (
    AgentMessage,
    AudioClip,
    CharacterProfile,
    ContinuityRulesRequest,
    CreateProjectRequest,
    AgentPlanRequest,
    EngineGenerateRequest,
    GenerateRequest,
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
from .rehearsal import promote_rehearsal_take, run_rehearsal
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
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
            return r.status_code == 200
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


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = load_settings()
    device = detect_device()
    agent = await probe_agent(settings)
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
    )


@app.get("/api/engine")
async def engine():
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


@app.get("/api/engine/jobs")
async def engine_jobs(limit: int = 40):
    return list_jobs(limit)


@app.get("/api/engine/jobs/{job_id}")
async def engine_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/engine/generate")
async def engine_generate(body: EngineGenerateRequest):
    try:
        return enqueue_job(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/engine/estimate")
async def engine_estimate(body: GpuEstimateRequest):
    """Honest GPU fit + ETA before queueing — #5 can-my-GPU-do-this."""
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


@app.get("/api/settings")
async def get_settings():
    return settings_public()


@app.put("/api/settings")
async def put_settings(body: Settings):
    return settings_public(save_settings(body))


@app.get("/api/agent/providers")
async def agent_providers():
    settings = load_settings()
    probe = await probe_agent(settings)
    return {"providers": list_providers(), "status": probe}


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


@app.get("/api/projects")
async def projects():
    return list_projects()


@app.post("/api/projects", response_model=Project)
async def create_project(body: CreateProjectRequest):
    settings = load_settings()
    project = Project(
        title=body.title.strip() or "Untitled",
        mode=body.mode,
        logline=body.logline,
        preset_id=body.preset_id or settings.preset_id,
    )
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


@app.post("/api/projects/{project_id}/characters", response_model=Project)
async def add_character(project_id: str, body: CharacterProfile):
    project = load_project(project_id)
    if not body.id:
        body.id = new_id("char")
    project.characters.append(body)
    return save_project(project)


@app.put("/api/projects/{project_id}/characters/{character_id}", response_model=Project)
async def update_character(project_id: str, character_id: str, body: CharacterProfile):
    project = load_project(project_id)
    for i, c in enumerate(project.characters):
        if c.id == character_id:
            body.id = character_id
            project.characters[i] = body
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


@app.patch("/api/projects/{project_id}/shots/{shot_id}", response_model=Project)
async def patch_shot(project_id: str, shot_id: str, body: UpdateShotRequest):
    project = load_project(project_id)
    for shot in project.shots:
        if shot.id == shot_id:
            data = body.model_dump(exclude_unset=True)
            for key, value in data.items():
                setattr(shot, key, value)
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
    project = load_project(project_id)
    if not project.shots:
        raise HTTPException(400, "Add shots before running a rehearsal pass.")
    return run_rehearsal(project, body.shot_ids, body.takes_per_shot, body.quality)


@app.post("/api/projects/{project_id}/takes/{take_id}/promote", response_model=Project)
async def promote_take(project_id: str, take_id: str):
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
