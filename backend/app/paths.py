from __future__ import annotations

from pathlib import Path

# App root = the folder people download (Pinokio-style layout).
ROOT = Path(__file__).resolve().parents[2]

# Straight-forward drop folders next to backend/frontend — not hidden in ~/.something
MODELS_DIR = ROOT / "models"
LORAS_DIR = ROOT / "loras"
OUTPUTS_DIR = ROOT / "outputs"
UPLOADS_DIR = ROOT / "uploads"
PROJECTS_DIR = ROOT / "projects"
ADDONS_DIR = ROOT / "addons"
PLUGINS_DIR = ADDONS_DIR / "plugins"
SKILLS_DIR = ADDONS_DIR / "skills"
CACHE_DIR = ROOT / "cache"

# Back-compat aliases used across the codebase
DATA_DIR = CACHE_DIR
MEDIA_DIR = OUTPUTS_DIR
PRESETS_DIR = ROOT / "presets"
SETTINGS_PATH = CACHE_DIR / "settings.json"
JOBS_PATH = CACHE_DIR / "jobs.json"
MODEL_DOWNLOADS_PATH = CACHE_DIR / "model_downloads.json"
ENABLED_ADDONS_PATH = CACHE_DIR / "addons_enabled.json"


FOLDER_GUIDE = [
    {
        "id": "models",
        "path": "models/",
        "title": "Models",
        "put_here": "AI checkpoints downloaded in-app (Wan, SDXL, LTX, audio…). One folder per model.",
        "examples": ["models/Wan-AI__Wan2.1-T2V-1.3B-Diffusers/", "models/stabilityai__sdxl-turbo/"],
    },
    {
        "id": "loras",
        "path": "loras/",
        "title": "LoRAs",
        "put_here": "Drop .safetensors / .pt LoRA files here. Optional — pick them in Generate.",
        "examples": ["loras/my_style.safetensors", "loras/character_face.safetensors"],
    },
    {
        "id": "outputs",
        "path": "outputs/",
        "title": "Outputs",
        "put_here": "Everything the app generates (images, videos, audio, previews).",
        "examples": ["outputs/<project_id>/", "outputs/standalone/", "outputs/uploads/"],
    },
    {
        "id": "uploads",
        "path": "uploads/",
        "title": "Uploads",
        "put_here": "Images/videos you upload for i2v, ref2i/ref2v, or upsample.",
        "examples": ["uploads/image_….png", "uploads/clip_….mp4"],
    },
    {
        "id": "projects",
        "path": "projects/",
        "title": "Projects",
        "put_here": "Saved studio projects (JSON). Created when you hit Save.",
        "examples": ["projects/proj_….json"],
    },
    {
        "id": "addons",
        "path": "addons/",
        "title": "Add-ons",
        "put_here": "Plugins (JSON) and Skills (JSON/Markdown) that extend the agent and workflows.",
        "examples": ["addons/plugins/my-plugin.json", "addons/skills/my-skill.md"],
    },
    {
        "id": "cache",
        "path": "cache/",
        "title": "Cache",
        "put_here": "App settings, job queue, download status. Usually leave alone.",
        "examples": ["cache/settings.json", "cache/jobs.json"],
    },
]


def ensure_dirs() -> None:
    for path in (
        MODELS_DIR,
        LORAS_DIR,
        OUTPUTS_DIR,
        UPLOADS_DIR,
        PROJECTS_DIR,
        PLUGINS_DIR,
        SKILLS_DIR,
        CACHE_DIR,
        OUTPUTS_DIR / "uploads",
        OUTPUTS_DIR / "standalone",
    ):
        path.mkdir(parents=True, exist_ok=True)


def folder_map() -> dict:
    ensure_dirs()
    return {
        "root": str(ROOT),
        "models": str(MODELS_DIR),
        "loras": str(LORAS_DIR),
        "outputs": str(OUTPUTS_DIR),
        "uploads": str(UPLOADS_DIR),
        "projects": str(PROJECTS_DIR),
        "addons": str(ADDONS_DIR),
        "plugins": str(PLUGINS_DIR),
        "skills": str(SKILLS_DIR),
        "cache": str(CACHE_DIR),
        "guide": FOLDER_GUIDE,
    }
