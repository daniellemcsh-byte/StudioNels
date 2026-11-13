from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agent import plan_project
from .engine.device import detect_device
from .engine.runner import engine_status_public, enqueue_job, get_job, list_jobs
from .generate import generate_takes
from .models import (
    AgentMessage,
    CharacterProfile,
    CreateProjectRequest,
    AgentPlanRequest,
    EngineGenerateRequest,
    GenerateRequest,
    HealthResponse,
    Project,
    SceneProfile,
    Settings,
    TimelineClip,
    UpdateShotRequest,
    new_id,
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
)


async def probe_ollama() -> bool:
    settings = load_settings()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
            return r.status_code == 200
    except Exception:
        return False

app = FastAPI(title="Framewright", version="0.1.0")
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
    return HealthResponse(
        ok=True,
        ollama=await probe_ollama(),
        engine="builtin",
        torch=bool(device.get("torch_available")),
        gpu=bool(device.get("ready_for_inference")),
        device_name=str(device.get("device_name") or "CPU"),
        preset_id=settings.preset_id,
        data_dir=str(DATA_DIR),
    )


@app.get("/api/engine")
async def engine():
    return engine_status_public()


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


@app.get("/api/settings", response_model=Settings)
async def get_settings():
    return load_settings()


@app.put("/api/settings", response_model=Settings)
async def put_settings(body: Settings):
    return save_settings(body)


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
                f"Welcome to Framewright. Tell me your idea for this {body.mode.replace('_', ' ')} "
                "and I'll break it into editable shots. Add characters and scenes in Profiles first "
                "if you already know them — or we can invent as we go."
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
    return await generate_takes(project, body.shot_ids, body.kind, body.mode)


@app.post("/api/projects/{project_id}/takes/{take_id}/pin", response_model=Project)
async def pin_take(project_id: str, take_id: str):
    project = load_project(project_id)
    take = next((t for t in project.takes if t.id == take_id), None)
    if not take:
        raise HTTPException(404, "Take not found")
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
