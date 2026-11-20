from __future__ import annotations

"""Project-level generate helpers — always uses the built-in engine (no ComfyUI)."""

from typing import Any

from .continue_video import continuation_source
from .continuity import build_bible
from .engine.catalog import get_model
from .engine.runner import enqueue_job, installed_default_for_mode
from .models import Project
from .prompt_compiler import compile_shot
from .storage import get_preset, save_project


def _model_for(project: Project, mode: str, gen: dict[str, Any]) -> dict[str, Any] | None:
    """Film render model if it supports `mode`, else a downloaded one, else the preset's."""
    for mid in (project.memory.render_model_id,):
        m = get_model(mid) if mid else None
        if m and mode in (m.get("modes") or []):
            return m
    m = installed_default_for_mode(mode)
    if m:
        return m
    mid = gen.get(f"default_{mode}")
    return get_model(mid) if mid else None


async def generate_takes(
    project: Project,
    shot_ids: list[str] | None = None,
    kind: str = "video",
    mode: str | None = None,
    is_rehearsal: bool = False,
    inject_continuity: bool = True,
    continue_from_previous: bool | None = None,
    continue_from_take_id: str | None = None,
) -> Project:
    preset = get_preset(project.preset_id)
    gen = preset.get("generation", {})
    chain = (
        project.continue_from_previous
        if continue_from_previous is None
        else continue_from_previous
    )

    if inject_continuity and not project.world_bible:
        project.world_bible = build_bible(project)["text"]

    if kind == "character_still":
        for char in project.characters:
            if char.reference_path:
                continue
            lock = char.character_lock or char.look
            job = enqueue_job(
                {
                    "mode": "t2i",
                    "model_id": gen.get("default_t2i"),
                    "prompt": (
                        f"character portrait of {char.name}, {lock}, {char.personality}, "
                        "cinematic still, consistent face"
                    ),
                    "project_id": project.id,
                    "cpu_offload": gen.get("cpu_offload", True),
                    "inject_continuity": inject_continuity,
                    "is_rehearsal": is_rehearsal,
                }
            )
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
                    "inject_continuity": inject_continuity,
                    "is_rehearsal": is_rehearsal,
                }
            )
            scene.tags = list(set((scene.tags or []) + [f"job:{job['id']}"]))
        return save_project(project)

    # Shot video / image — optionally chain i2v from previous take's last frame.
    # Multi-shot chains run sequentially: first job finishes → next i2v is enqueued.
    targets = [s for s in project.shots if shot_ids is None or s.id in shot_ids]
    targets = sorted(targets, key=lambda s: s.index)
    use_chain = bool(chain and kind == "video")
    chain_ids = [s.id for s in targets] if use_chain and len(targets) > 1 else []

    for i, shot in enumerate(targets):
        # When chaining a sequence, only start the first; runner continues the rest
        if use_chain and chain_ids and i > 0:
            shot.status = "queued"
            continue

        cont = None
        if use_chain:
            cont = continuation_source(
                project,
                shot,
                from_take_id=continue_from_take_id if len(targets) == 1 else None,
            )

        gen_mode = mode
        image_path = None
        if cont and use_chain:
            gen_mode = "i2v"
            image_path = cont["image_path"]
        elif not gen_mode:
            gen_mode = "t2v" if kind == "video" else "t2i"

        # Model: the film's render model when it can do this mode, else the
        # best downloaded one (the preset default is often not downloaded).
        model = _model_for(project, gen_mode, gen)
        # Prompt written for that model from the film memory (identity locks,
        # setting, props, carried-over state…). A locked prompt is used as is.
        compiled = compile_shot(project, shot, model, gen_mode) if model else None
        prompt = compiled["prompt"] if compiled else (shot.prompt or shot.action or shot.title)
        negative = compiled["negative"] if compiled else shot.negative_prompt
        if cont and use_chain and not (compiled and compiled["motion_only"]):
            prompt = f"Seamless continuation from the previous shot, continuous motion. {prompt}"
        if cont and negative and "jump cut" not in negative:
            negative = f"cut, hard edit, flash, jump cut, {negative}"

        payload = {
            "mode": gen_mode,
            "model_id": (model or {}).get("id")
            or gen.get(f"default_{gen_mode}")
            or gen.get("default_i2v")
            or gen.get("default_t2v"),
            "prompt": prompt,
            "negative_prompt": negative or ("cut, hard edit, flash, jump cut" if cont else ""),
            "project_id": project.id,
            "shot_id": shot.id,
            "cpu_offload": gen.get("cpu_offload", True),
            "frames": gen.get("default_frames"),
            "width": getattr(project, "width", None) or gen.get("default_width"),
            "height": getattr(project, "height", None) or gen.get("default_height"),
            "fps": gen.get("fps"),
            "is_rehearsal": is_rehearsal,
            # The compiled prompt already carries the locks; the old prefix
            # ("CONTINUITY STYLE: … | RULE: …") would only eat the token budget.
            "inject_continuity": inject_continuity and not compiled,
            "quality": "draft" if is_rehearsal else None,
            "continue_from_previous": bool(cont) or bool(chain_ids),
            "continue_from_take_id": cont["from_take_id"] if cont else None,
            "chain_shot_ids": chain_ids,
            "image_format": project.image_format,
            "video_format": project.video_format,
            "visual_style": project.visual_style,
        }
        if image_path:
            payload["image_path"] = image_path
        # Attach first cast ref for ref2v-style identity when available
        if shot.character_ids:
            for cid in shot.character_ids:
                ch = next((c for c in project.characters if c.id == cid), None)
                if ch and ch.reference_path:
                    payload.setdefault("reference_path", ch.reference_path)
                    break

        enqueue_job(payload)
        shot.status = "generating"

    return save_project(project)
