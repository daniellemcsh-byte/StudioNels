from __future__ import annotations

"""One-click look / workflow recipes for StudioNels."""

from typing import Any

from .frame_sizes import apply_frame_to_project
from .models import Project
from .storage import save_project

RECIPES: list[dict[str, Any]] = [
    {
        "id": "tiktok-vertical",
        "title": "TikTok vertical cut",
        "blurb": "9:16 portrait, captions on, continue-chain on.",
        "tags": ["social", "vertical"],
        "apply": {
            "frame_size_id": "9:16",
            "continue_from_previous": True,
            "captions_enabled": True,
            "visual_style": "cinematic",
        },
    },
    {
        "id": "youtube-landscape",
        "title": "YouTube landscape",
        "blurb": "16:9 HD landscape — classic watch-later cut.",
        "tags": ["social", "landscape"],
        "apply": {
            "frame_size_id": "16:9-hd",
            "continue_from_previous": True,
            "captions_enabled": True,
        },
    },
    {
        "id": "square-feed",
        "title": "1:1 square feed",
        "blurb": "Equal crop for feed posts and experiments.",
        "tags": ["social", "square"],
        "apply": {
            "frame_size_id": "1:1",
            "continue_from_previous": True,
        },
    },
    {
        "id": "amd-low-vram-story",
        "title": "AMD low-VRAM story",
        "blurb": "Safe preset for 8 GB cards — draft-friendly, continue on.",
        "tags": ["amd", "vram"],
        "apply": {
            "preset_id": "amd-low-vram",
            "frame_size_id": "16:9-draft",
            "continue_from_previous": True,
        },
    },
    {
        "id": "character-lock-drama",
        "title": "Character-lock drama",
        "blurb": "Continuity-first: stricter auto-reject, continue on.",
        "tags": ["continuity"],
        "apply": {
            "auto_reject_below": 0.62,
            "continue_from_previous": True,
            "visual_style": "dramatic",
        },
    },
    {
        "id": "rehearsal-then-final",
        "title": "Rehearse → final",
        "blurb": "Greybox first: keep continue on; run Film night after drafts.",
        "tags": ["workflow"],
        "apply": {
            "continue_from_previous": True,
            "meta_flag": "rehearsal_workflow",
        },
    },
    {
        "id": "night-neon",
        "title": "Night neon look",
        "blurb": "Neon / night palette baked into visual style.",
        "tags": ["look"],
        "apply": {
            "visual_style": "neon_noir",
            "continue_from_previous": True,
        },
    },
]


def list_recipes() -> list[dict[str, Any]]:
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "blurb": r["blurb"],
            "tags": r.get("tags") or [],
        }
        for r in RECIPES
    ]


def apply_recipe(project: Project, recipe_id: str) -> Project:
    recipe = next((r for r in RECIPES if r["id"] == recipe_id), None)
    if not recipe:
        raise ValueError(f"Unknown recipe: {recipe_id}")
    payload = dict(recipe.get("apply") or {})
    meta_flag = payload.pop("meta_flag", None)
    frame_id = payload.pop("frame_size_id", None)
    for key, value in payload.items():
        if hasattr(project, key):
            setattr(project, key, value)
    if frame_id:
        apply_frame_to_project(project, frame_id)
    project.meta = dict(project.meta or {})
    project.meta["recipe"] = recipe_id
    if meta_flag:
        project.meta["recipe_flag"] = meta_flag
    return save_project(project)
