from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agent import plan_project
from .generate import generate_takes, probe_comfyui, probe_ollama
from .models import (
    AgentMessage,
    CharacterProfile,
    CreateProjectRequest,
    AgentPlanRequest,
    GenerateRequest,
    HealthResponse,
    Project,
    SceneProfile,
    Settings,
    TimelineClip,
    UpdateShotRequest,
    new_id,
)
from .paths import DATA_DIR, MEDIA_DIR, ensure_dirs
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
    return HealthResponse(
        ok=True,
        ollama=await probe_ollama(),
        comfyui=await probe_comfyui(),
        preset_id=settings.preset_id,
        data_dir=str(DATA_DIR),
    )


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
    return await generate_takes(project, body.shot_ids, body.kind)


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
    p = Path(path).expanduser().resolve()
    media_root = MEDIA_DIR.resolve()
    if media_root not in p.parents and p != media_root:
        raise HTTPException(403, "Outside media dir")
    if not p.exists():
        raise HTTPException(404, "Missing file")
    return FileResponse(p)
