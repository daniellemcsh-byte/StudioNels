from __future__ import annotations

"""One-click look / workflow recipes for StudioNels."""

from typing import Any

from .models import Project
from .storage import save_project

RECIPES: list[dict[str, Any]] = [
    {
        "id": "tiktok-vertical",
        "title": "TikTok vertical cut",
        "blurb": "9:16, short clips, captions on, continue-chain on.",
        "tags": ["social", "vertical"],
        "apply": {
            "image_format": "9:16",
            "video_format": "9:16",
            "continue_from_previous": True,
            "captions_enabled": True,
            "visual_style": "cinematic",
        },
    },
    {
        "id": "amd-low-vram-story",
        "title": "AMD low-VRAM story",
        "blurb": "Safe preset for 8 GB cards — draft-friendly, continue on.",
        "tags": ["amd", "vram"],
        "apply": {
            "preset_id": "amd-low-vram",
            "continue_from_previous": True,
            "image_format": "16:9",
            "video_format": "16:9",
        },
    },
    {
        "id": "character-lock-drama",
        "title": "Character-lock drama",
        "blurb": "Continuity-first: auto-reject soft takes, bible rebuild next score.",
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
        "blurb": "Greybox first: keep continue on; run Rehearsal, promote, then Generate.",
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
    for key, value in payload.items():
        if hasattr(project, key):
            setattr(project, key, value)
    if meta_flag:
        project.meta = dict(project.meta or {})
        project.meta["recipe"] = recipe_id
        project.meta["recipe_flag"] = meta_flag
    else:
        project.meta = dict(project.meta or {})
        project.meta["recipe"] = recipe_id
    return save_project(project)
