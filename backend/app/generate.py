from __future__ import annotations

"""Project-level generate helpers — always uses the built-in engine (no ComfyUI)."""

from .engine.runner import enqueue_job
from .models import Project
from .storage import get_preset, save_project


async def generate_takes(
    project: Project,
    shot_ids: list[str] | None = None,
    kind: str = "video",
    mode: str | None = None,
) -> Project:  # mode: t2v / i2v / etc. when generating shots
    preset = get_preset(project.preset_id)
    gen = preset.get("generation", {})

    if kind == "character_still":
        for char in project.characters:
            if char.reference_path:
                continue
            job = enqueue_job(
                {
                    "mode": "t2i",
                    "model_id": gen.get("default_t2i"),
                    "prompt": (
                        f"character portrait of {char.name}, {char.look}, {char.personality}, "
                        "cinematic still, consistent face"
                    ),
                    "project_id": project.id,
                    "cpu_offload": gen.get("cpu_offload", True),
                }
            )
            # Preview path attaches via shot; for profiles store when done by polling — sync preview:
            # For stills without shot_id, copy path after brief wait is awkward in async;
            # enqueue and let Characters tab refresh jobs. Also write pending note.
            char.tags = list(set((char.tags or []) + [f"job:{job['id']}"]))
        return save_project(project)

    if kind == "scene_still":
        for scene in project.scenes:
            if scene.reference_path:
                continue
            job = enqueue_job(
                {
                    "mode": "t2i",
                    "model_id": gen.get("default_t2i"),
                    "prompt": (
                        f"establishing shot of {scene.name}, {scene.location}, "
                        f"{scene.time_of_day}, mood {scene.mood}, {scene.visual_notes}"
                    ),
                    "project_id": project.id,
                    "cpu_offload": gen.get("cpu_offload", True),
                }
            )
            scene.tags = list(set((scene.tags or []) + [f"job:{job['id']}"]))
        return save_project(project)

    # Shot video / image generation via built-in modes
    gen_mode = mode or ("t2v" if kind == "video" else "t2i")
    targets = [s for s in project.shots if shot_ids is None or s.id in shot_ids]
    for shot in targets:
        shot.status = "queued"
        enqueue_job(
            {
                "mode": gen_mode,
                "model_id": gen.get(f"default_{gen_mode}") or gen.get("default_t2v"),
                "prompt": shot.prompt or shot.action or shot.title,
                "negative_prompt": shot.negative_prompt,
                "project_id": project.id,
                "shot_id": shot.id,
                "cpu_offload": gen.get("cpu_offload", True),
                "frames": gen.get("default_frames"),
                "width": gen.get("default_width"),
                "height": gen.get("default_height"),
                "fps": gen.get("fps"),
            }
        )
        shot.status = "generating"
    return save_project(project)
