from __future__ import annotations

from .models import Project, TimelineClip
from .storage import get_preset, save_project


def run_rehearsal(
    project: Project,
    shot_ids: list[str] | None = None,
    takes_per_shot: int = 2,
    quality: str = "draft",
) -> Project:
    """Greybox pass: queue cheap draft takes for blocking before final gen."""
    # Lazy: importing runner at module load pulled pipelines into uvicorn boot.
    from .engine.runner import enqueue_job

    preset = get_preset(project.preset_id)
    gen = preset.get("generation", {})
    targets = [s for s in project.shots if shot_ids is None or s.id in shot_ids]
    takes_per_shot = max(1, min(4, int(takes_per_shot)))

    for shot in targets:
        shot.status = "queued"
        for i in range(takes_per_shot):
            enqueue_job(
                {
                    "mode": "t2v",
                    "model_id": gen.get("default_t2v"),
                    "prompt": shot.prompt or shot.action or shot.title,
                    "negative_prompt": shot.negative_prompt,
                    "project_id": project.id,
                    "shot_id": shot.id,
                    "cpu_offload": gen.get("cpu_offload", True),
                    "frames": min(int(gen.get("default_frames") or 49), 24),
                    "width": min(
                        int(getattr(project, "width", None) or gen.get("default_width") or 768),
                        768,
                    ),
                    "height": min(
                        int(getattr(project, "height", None) or gen.get("default_height") or 432),
                        768,
                    ),
                    "fps": gen.get("fps") or 12,
                    "quality": quality,
                    "is_rehearsal": True,
                    "inject_continuity": True,
                    "seed": (shot.index + 1) * 1000 + i,
                }
            )
        shot.status = "generating"
    return save_project(project)


def promote_rehearsal_take(project: Project, take_id: str) -> Project:
    """Promote a rehearsal winner: pin it and clear rejected siblings of same shot."""
    take = next((t for t in project.takes if t.id == take_id), None)
    if not take:
        raise ValueError("Take not found")
    take.is_rehearsal = False
    take.rejected = False
    if take.label.startswith("REHEARSAL"):
        take.label = take.label.replace("REHEARSAL", "PROMOTED", 1)
    for shot in project.shots:
        if shot.id == take.shot_id:
            shot.pinned_take_id = take.id
            shot.status = "ready"
            break
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
