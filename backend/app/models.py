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
    "continuity",
    "rehearsal",
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
    character_lock: str = ""
    reference_path: str | None = None
    # Offline identity fingerprint from reference still (palette / histogram)
    identity_fingerprint: list[float] | None = None
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
    continuity_score: float | None = None
    continuity_flags: list[str] = Field(default_factory=list)
    vision_score: float | None = None
    identity_score: float | None = None
    prompt_used: str = ""
    is_rehearsal: bool = False
    rejected: bool = False


class TimelineClip(BaseModel):
    id: str = Field(default_factory=lambda: new_id("clip"))
    shot_id: str
    take_id: str | None = None
    # Source trim window inside the take
    start_sec: float = 0.0
    end_sec: float | None = None
    trim_in: float = 0.0
    trim_out: float | None = None
    speed: float = 1.0
    pinned: bool = False
    order: int = 0
    # Captions (editable in Director / on-video)
    caption: str = ""
    caption_style: str = "bottom"
    caption_x: float = 0.0  # -1 .. 1 relative nudge
    caption_y: float = 0.0
    caption_start: float = 0.0  # within clip
    caption_end: float | None = None
    # Look filter over this clip
    filter_id: str = "none"
    filter_intensity: float = 1.0
    director_note: str = ""
    # TikTok-style reframing
    scale: float = 1.0
    pan_x: float = 0.0  # -1 .. 1
    pan_y: float = 0.0
    volume: float = 1.0  # clip audio if present
    fade_in: float = 0.0
    fade_out: float = 0.0
    # Transition INTO this clip from the previous one
    transition: str = "none"  # none|cut|fade|dissolve|wipe|slide|zoom|flash
    transition_dur: float = 0.35


class AudioClip(BaseModel):
    """Independent audio under the video timeline (music / VO / SFX)."""

    id: str = Field(default_factory=lambda: new_id("aud"))
    label: str = "Audio"
    kind: Literal["music", "song", "score", "ambience", "sfx", "vo", "other"] = "music"
    media_path: str | None = None
    # Placement on the master timeline (seconds from cut start)
    timeline_start: float = 0.0
    duration_sec: float = 8.0
    trim_in: float = 0.0
    trim_out: float | None = None
    volume: float = 0.85
    fade_in: float = 0.0
    fade_out: float = 0.5
    muted: bool = False
    track: int = 0  # 0 = music bed, 1 = SFX/VO overlay
    order: int = 0


class AgentAttachment(BaseModel):
    """Image, file, or Characters-tab person/scene linked into agent chat."""

    id: str = Field(default_factory=lambda: new_id("att"))
    kind: Literal["image", "file", "character", "scene"] = "image"
    path: str | None = None
    name: str = ""
    character_id: str | None = None
    scene_id: str | None = None
    mime: str = ""


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str = Field(default_factory=utc_now)
    attachments: list[AgentAttachment] = Field(default_factory=list)


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
    audio_timeline: list[AudioClip] = Field(default_factory=list)
    agent_messages: list[AgentMessage] = Field(default_factory=list)
    preset_id: str = "amd-low-vram"
    # Whole-piece timing + look (Time tab)
    target_duration_sec: float = 60.0
    visual_style: str = "cinematic"
    image_format: Literal["png", "jpg", "webp"] = "png"
    video_format: Literal["mp4", "webm", "gif"] = "mp4"
    audio_format: Literal["wav", "mp3"] = "wav"
    # Frame size / aspect (landscape, portrait, 1:1, …)
    frame_size_id: str = "16:9-draft"
    aspect_ratio: str = "16:9"
    width: int = 768
    height: int = 432
    world_bible: str = ""
    continuity_rules: list[str] = Field(default_factory=list)
    auto_reject_below: float = 0.55
    # When true, multi-shot generate chains i2v from each prior take's last frame
    continue_from_previous: bool = True
    # Director defaults
    default_filter_id: str = "none"
    captions_enabled: bool = True
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
    # Agent LLM: builtin | ollama | openai | anthropic | openrouter | custom
    agent_provider: Literal[
        "builtin", "ollama", "openai", "anthropic", "openrouter", "custom"
    ] = "ollama"
    agent_model: str = ""
    agent_api_base: str = ""
    agent_api_key: str = ""
    # Personal hubs — where the user keeps / shares their own packs
    github_url: str = ""
    huggingface_url: str = ""
    huggingface_token: str = ""
    creator_display_name: str = "VIPNells"
    auto_save: bool = True
    friendly_mode: bool = True
    default_gen_mode: str = "t2v"
    cpu_offload: bool = True


class PersonalLinksRequest(BaseModel):
    github_url: str | None = None
    huggingface_url: str | None = None
    huggingface_token: str | None = None
    creator_display_name: str | None = None


class PersonalImportRequest(BaseModel):
    kind: Literal["model", "lora", "addon"] = "model"
    source: str
    name: str | None = None


class PromptEnhanceRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    mode: str = "t2v"
    style: str | None = None
    force_builtin: bool = False


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
    text_encoder: str | None = "auto"
    audio_path: str | None = None
    project_id: str | None = None
    shot_id: str | None = None
    force_preview: bool = False
    image_format: Literal["png", "jpg", "webp"] | None = None
    video_format: Literal["mp4", "webm", "gif"] | None = None
    audio_format: Literal["wav", "mp3"] | None = None
    visual_style: str | None = None
    is_rehearsal: bool = False
    inject_continuity: bool = True
    continue_from_previous: bool = False
    continue_from_take_id: str | None = None


class GpuEstimateRequest(BaseModel):
    mode: str = "t2v"
    model_id: str | None = None
    width: int | None = None
    height: int | None = None
    frames: int | None = None
    duration_sec: float | None = None
    fps: int | None = None
    quality: Literal["draft", "balanced", "high", "max"] | None = "balanced"
    steps: int | None = None
    cpu_offload: bool | None = None
    preset_id: str | None = None


class RehearsalRequest(BaseModel):
    shot_ids: list[str] | None = None
    takes_per_shot: int = 2
    quality: Literal["draft", "balanced"] = "draft"


class ContinuityRulesRequest(BaseModel):
    rules: list[str] = Field(default_factory=list)
    auto_reject_below: float | None = None
    rebuild_bible: bool = True


class AgentInstallRequest(BaseModel):
    model: str = "llama3.2:3b"


class CreateProjectRequest(BaseModel):
    title: str
    mode: Mode = "short"
    logline: str = ""
    preset_id: str | None = None
    frame_size_id: str | None = None


class FilmNightRequest(BaseModel):
    stage: Literal["full", "rehearse", "promote", "finals", "stitch"] = "full"


class ApplyRecipeRequest(BaseModel):
    recipe_id: str


class ApplyFrameSizeRequest(BaseModel):
    frame_size_id: str


class AgentPlanRequest(BaseModel):
    message: str
    replace_shots: bool = True
    attachments: list[AgentAttachment] = Field(default_factory=list)


class CreateShotRequest(BaseModel):
    """Manual storyboard / shot list entry — no LLM required."""

    title: str = "New shot"
    action: str = ""
    dialogue: str = ""
    camera: str = "medium"
    duration_sec: float = 3.0
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    prompt: str = ""
    negative_prompt: str = ""
    storyboard_note: str = ""
    director_notes: str = ""
    insert_at: int | None = None  # None = append


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
    index: int | None = None


class GenerateRequest(BaseModel):
    shot_ids: list[str] | None = None
    kind: Literal["video", "character_still", "scene_still"] = "video"
    mode: Literal["t2i", "t2v", "i2v", "ref2i", "ref2v"] | None = None
    is_rehearsal: bool = False
    inject_continuity: bool = True
    # None = use project.continue_from_previous; True/False overrides
    continue_from_previous: bool | None = None
    continue_from_take_id: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    ollama: bool
    engine: str
    torch: bool
    gpu: bool
    device_name: str
    preset_id: str
    data_dir: str
    agent_provider: str = "ollama"
    agent_label: str = "Ollama"
    agent_reachable: bool = False
    agent_detail: str = ""
    # AMD / first-run coach
    rocm: bool = False
    vram_gb: float | None = None
    backend: str = "none"
    ready_for_inference: bool = False
    will_preview: bool = True
    suggested_preset: str = "amd-low-vram"
    first_run_headline: str = ""
    first_run_detail: str = ""
    notes: list[str] = Field(default_factory=list)
