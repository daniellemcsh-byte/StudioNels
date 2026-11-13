from __future__ import annotations

"""One-button film night: rehearse → promote → finals → captions → stitch."""

from typing import Any

from .captions import generate_captions
from .generate import generate_takes
from .models import Project
from .rehearsal import promote_rehearsal_take, run_rehearsal
from .stitch import stitch_preview
from .storage import save_project


def _best_rehearsal_per_shot(project: Project) -> list[str]:
    by_shot: dict[str, list] = {}
    for t in project.takes:
        if not t.is_rehearsal or t.rejected:
            continue
        by_shot.setdefault(t.shot_id, []).append(t)
    winners: list[str] = []
    for _shot_id, takes in by_shot.items():
        takes_sorted = sorted(
            takes,
            key=lambda x: (
                x.continuity_score is not None,
                x.continuity_score or 0.0,
                x.created_at or "",
            ),
            reverse=True,
        )
        winners.append(takes_sorted[0].id)
    return winners


async def queue_finals_from_pins(project: Project) -> Project:
    project.continue_from_previous = True
    project = save_project(project)
    shot_ids = [s.id for s in sorted(project.shots, key=lambda s: s.index)]
    if not shot_ids:
        return project
    return await generate_takes(
        project,
        shot_ids=shot_ids,
        kind="video",
        mode=None,
        is_rehearsal=False,
        inject_continuity=True,
        continue_from_previous=True,
    )


async def run_film_night(project: Project, stage: str = "full") -> dict[str, Any]:
    steps: list[str] = []
    stitch_result = None
    stage = (stage or "full").lower().strip()

    if stage in ("rehearse", "full") and not any(t.is_rehearsal for t in project.takes):
        if not project.shots:
            return {"ok": False, "message": "Add shots first (Agent).", "steps": steps}
        n = len(project.shots) * 2
        project = run_rehearsal(project, None, takes_per_shot=2, quality="draft")
        steps.append(f"Queued {n} rehearsal draft job(s) — watch the Generation dock.")
        if stage == "rehearse":
            return {
                "ok": True,
                "project": project.model_dump(),
                "steps": steps,
                "message": (
                    f"Rehearsal queued ({n} jobs). Watch the Generation dock at the bottom. "
                    "When jobs say done, run Film night again to promote → finals."
                ),
                "next": "promote",
                "queued_jobs": n,
            }

    if stage in ("promote", "full"):
        winners = _best_rehearsal_per_shot(project)
        if winners:
            for tid in winners:
                try:
                    project = promote_rehearsal_take(project, tid)
                except ValueError:
                    continue
            steps.append(f"Promoted {len(winners)} rehearsal winner(s) to Director pins.")
        elif stage == "promote":
            return {
                "ok": False,
                "project": project.model_dump(),
                "steps": steps,
                "message": "No rehearsal takes to promote yet — run Rehearse first.",
                "next": "rehearse",
            }

    if stage in ("finals", "full"):
        if not project.shots:
            return {"ok": False, "project": project.model_dump(), "steps": steps, "message": "No shots."}
        if stage == "full" and steps and "rehearsal" in (steps[0] or "").lower():
            return {
                "ok": True,
                "project": project.model_dump(),
                "steps": steps,
                "message": (
                    "Film night · rehearsal jobs are running now (see Generation dock). "
                    "When they finish, press Film night again for promote → finals → stitch."
                ),
                "next": "promote",
            }
        project = await queue_finals_from_pins(project)
        steps.append(
            f"Queued final continue-chain for {len(project.shots)} shot(s) — watch Generation dock."
        )
        if stage == "finals":
            return {
                "ok": True,
                "project": project.model_dump(),
                "steps": steps,
                "message": "Finals queued. Watch the Generation dock; when done, run Stitch.",
                "next": "stitch",
            }

    if stage in ("stitch", "full"):
        project = generate_captions(project, overwrite=False)
        steps.append("Captions filled from dialogue where empty.")
        stitch_result = stitch_preview(project)
        steps.append(stitch_result.get("message") or "Stitch done.")
        return {
            "ok": True,
            "project": project.model_dump(),
            "steps": steps,
            "stitch": stitch_result,
            "message": " · ".join(steps),
            "next": None,
        }

    return {
        "ok": True,
        "project": project.model_dump(),
        "steps": steps,
        "message": " · ".join(steps) if steps else f"Unknown stage: {stage}",
        "next": None,
    }
