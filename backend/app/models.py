from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


Mode = Literal["film", "short", "music_video", "ad", "experiment"]
TabHint = Literal[
    "agent",
    "profiles",
    "shots",
    "storyboard",
    "characters",
    "sampling",
    "director",
    "settings",
]


class CharacterProfile(BaseModel):
    id: str = Field(default_factory=lambda: new_id("char"))
    name: str
    role: str = ""
    look: str = ""
    personality: str = ""
    voice_notes: str = ""
    reference_path: str | None = None
    tags: list[str] = Field(default_factory=list)


class SceneProfile(BaseModel):
    id: str = Field(default_factory=lambda: new_id("scene"))
    name: str
    location: str = ""
    time_of_day: str = ""
    mood: str = ""
    visual_notes: str = ""
    reference_path: str | None = None
    tags: list[str] = Field(default_factory=list)


class Shot(BaseModel):
    id: str = Field(default_factory=lambda: new_id("shot"))
    index: int = 0
    title: str
    action: str = ""
    dialogue: str = ""
    camera: str = "medium"
    duration_sec: float = 3.0
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    prompt: str = ""
    negative_prompt: str = ""
    status: Literal["draft", "queued", "generating", "ready", "failed"] = "draft"
    pinned_take_id: str | None = None
    storyboard_note: str = ""
    director_notes: str = ""


class Take(BaseModel):
    id: str = Field(default_factory=lambda: new_id("take"))
    shot_id: str
    label: str = "Take A"
    media_path: str | None = None
    thumb_path: str | None = None
    seed: int | None = None
    score_note: str = ""
    created_at: str = Field(default_factory=utc_now)
    is_placeholder: bool = True


class TimelineClip(BaseModel):
    id: str = Field(default_factory=lambda: new_id("clip"))
    shot_id: str
    take_id: str | None = None
    start_sec: float = 0.0
    end_sec: float | None = None
    pinned: bool = False
    order: int = 0


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str = Field(default_factory=utc_now)


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("proj"))
    title: str
    mode: Mode = "short"
    logline: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    characters: list[CharacterProfile] = Field(default_factory=list)
    scenes: list[SceneProfile] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    takes: list[Take] = Field(default_factory=list)
    timeline: list[TimelineClip] = Field(default_factory=list)
    agent_messages: list[AgentMessage] = Field(default_factory=list)
    preset_id: str = "amd-low-vram"
    # Whole-piece timing + look (Time tab)
    target_duration_sec: float = 60.0
    visual_style: str = "cinematic"
    image_format: Literal["png", "jpg", "webp"] = "png"
    video_format: Literal["mp4", "webm", "gif"] = "mp4"
    audio_format: Literal["wav", "mp3"] = "wav"
    meta: dict[str, Any] = Field(default_factory=dict)


class ProjectSummary(BaseModel):
    id: str
    title: str
    mode: Mode
    updated_at: str
    shot_count: int
    preset_id: str


class Settings(BaseModel):
    preset_id: str = "amd-low-vram"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    auto_save: bool = True
    friendly_mode: bool = True
    default_gen_mode: str = "t2v"
    cpu_offload: bool = True


class EngineGenerateRequest(BaseModel):
    mode: Literal[
        "t2i",
        "t2v",
        "i2v",
        "ref2i",
        "ref2v",
        "t2a",
        "upsample_image",
        "upsample_video",
    ]
    prompt: str = ""
    negative_prompt: str = ""
    model_id: str | None = None
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    guidance: float | None = None
    frames: int | None = None
    fps: int | None = None
    duration_sec: float | None = None
    quality: Literal["draft", "balanced", "high", "max"] | None = "balanced"
    seed: int | None = None
    strength: float | None = None
    cpu_offload: bool | None = None
    image_path: str | None = None
    reference_path: str | None = None
    video_path: str | None = None
    lora_path: str | None = None
    lora_scale: float | None = 0.8
    project_id: str | None = None
    shot_id: str | None = None
    force_preview: bool = False
    image_format: Literal["png", "jpg", "webp"] | None = None
    video_format: Literal["mp4", "webm", "gif"] | None = None
    audio_format: Literal["wav", "mp3"] | None = None
    visual_style: str | None = None


class AgentInstallRequest(BaseModel):
    model: str = "llama3.2:3b"


class CreateProjectRequest(BaseModel):
    title: str
    mode: Mode = "short"
    logline: str = ""
    preset_id: str | None = None


class AgentPlanRequest(BaseModel):
    message: str
    replace_shots: bool = True


class UpdateShotRequest(BaseModel):
    title: str | None = None
    action: str | None = None
    dialogue: str | None = None
    camera: str | None = None
    duration_sec: float | None = None
    character_ids: list[str] | None = None
    scene_id: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    storyboard_note: str | None = None
    director_notes: str | None = None
    status: str | None = None
    pinned_take_id: str | None = None


class GenerateRequest(BaseModel):
    shot_ids: list[str] | None = None
    kind: Literal["video", "character_still", "scene_still"] = "video"
    mode: Literal["t2i", "t2v", "i2v", "ref2i", "ref2v"] | None = None


class HealthResponse(BaseModel):
    ok: bool
    ollama: bool
    engine: str
    torch: bool
    gpu: bool
    device_name: str
    preset_id: str
    data_dir: str
