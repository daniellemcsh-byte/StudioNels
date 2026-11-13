from __future__ import annotations

"""Video / image frame sizes: landscape, portrait, square, and friends."""

from typing import Any

# Orientation groups for the UI
FRAME_SIZES: list[dict[str, Any]] = [
    # Landscape
    {
        "id": "16:9-hd",
        "label": "16:9 Landscape HD",
        "orientation": "landscape",
        "ratio": "16:9",
        "width": 1280,
        "height": 720,
        "blurb": "YouTube / film default",
    },
    {
        "id": "16:9-draft",
        "label": "16:9 Landscape draft",
        "orientation": "landscape",
        "ratio": "16:9",
        "width": 768,
        "height": 432,
        "blurb": "Low VRAM friendly",
    },
    {
        "id": "16:9-1080",
        "label": "16:9 Full HD",
        "orientation": "landscape",
        "ratio": "16:9",
        "width": 1920,
        "height": 1080,
        "blurb": "1080p — needs more VRAM",
    },
    {
        "id": "21:9",
        "label": "21:9 Ultrawide",
        "orientation": "landscape",
        "ratio": "21:9",
        "width": 1280,
        "height": 548,
        "blurb": "Cinematic letterbox feel",
    },
    {
        "id": "4:3",
        "label": "4:3 Classic",
        "orientation": "landscape",
        "ratio": "4:3",
        "width": 1024,
        "height": 768,
        "blurb": "TV / retro frame",
    },
    {
        "id": "3:2",
        "label": "3:2 Photo",
        "orientation": "landscape",
        "ratio": "3:2",
        "width": 1152,
        "height": 768,
        "blurb": "Still-camera landscape",
    },
    # Square
    {
        "id": "1:1",
        "label": "1:1 Square",
        "orientation": "square",
        "ratio": "1:1",
        "width": 1024,
        "height": 1024,
        "blurb": "Instagram feed / equal crop",
    },
    {
        "id": "1:1-draft",
        "label": "1:1 Square draft",
        "orientation": "square",
        "ratio": "1:1",
        "width": 512,
        "height": 512,
        "blurb": "Fast square for low VRAM",
    },
    # Portrait
    {
        "id": "9:16",
        "label": "9:16 Portrait",
        "orientation": "portrait",
        "ratio": "9:16",
        "width": 720,
        "height": 1280,
        "blurb": "TikTok / Reels / Shorts",
    },
    {
        "id": "9:16-draft",
        "label": "9:16 Portrait draft",
        "orientation": "portrait",
        "ratio": "9:16",
        "width": 432,
        "height": 768,
        "blurb": "Vertical, gentler on VRAM",
    },
    {
        "id": "4:5",
        "label": "4:5 Portrait",
        "orientation": "portrait",
        "ratio": "4:5",
        "width": 864,
        "height": 1080,
        "blurb": "Instagram portrait post",
    },
    {
        "id": "3:4",
        "label": "3:4 Portrait",
        "orientation": "portrait",
        "ratio": "3:4",
        "width": 768,
        "height": 1024,
        "blurb": "Tall still / soft vertical",
    },
    {
        "id": "2:3",
        "label": "2:3 Portrait photo",
        "orientation": "portrait",
        "ratio": "2:3",
        "width": 768,
        "height": 1152,
        "blurb": "Still-camera portrait",
    },
]

DEFAULT_FRAME_ID = "16:9-draft"


def list_frame_sizes() -> list[dict[str, Any]]:
    return list(FRAME_SIZES)


def get_frame_size(frame_id: str | None) -> dict[str, Any]:
    if not frame_id:
        return next(f for f in FRAME_SIZES if f["id"] == DEFAULT_FRAME_ID)
    found = next((f for f in FRAME_SIZES if f["id"] == frame_id), None)
    if found:
        return found
    # allow raw "16:9" / "9:16" / "1:1" shorthand → first match
    by_ratio = next((f for f in FRAME_SIZES if f["ratio"] == frame_id), None)
    if by_ratio:
        return by_ratio
    return next(f for f in FRAME_SIZES if f["id"] == DEFAULT_FRAME_ID)


def apply_frame_to_project(project: Any, frame_id: str) -> Any:
    frame = get_frame_size(frame_id)
    project.frame_size_id = frame["id"]
    project.aspect_ratio = frame["ratio"]
    project.width = int(frame["width"])
    project.height = int(frame["height"])
    return project


def size_presets_for_engine() -> list[dict[str, Any]]:
    """Flat list for Generate dropdown (compatible with old SIZE_PRESETS shape)."""
    return [
        {
            "id": f["id"],
            "width": f["width"],
            "height": f["height"],
            "label": f"{f['label']} ({f['width']}×{f['height']})",
            "orientation": f["orientation"],
            "ratio": f["ratio"],
        }
        for f in FRAME_SIZES
    ]
