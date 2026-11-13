from __future__ import annotations

import re
from typing import Any

from .models import Project, Shot, Take

# Lightweight continuity brain: builds a cast/world bible and scores takes
# against character locks + scene rules without needing a vision model.


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(t) > 2}


# Words that are too generic to count as lock features
_STOP = {
    "the",
    "and",
    "with",
    "from",
    "that",
    "this",
    "very",
    "soft",
    "look",
    "face",
    "hair",
    "eyes",
    "skin",
    "shot",
    "cinematic",
    "lighting",
    "character",
    "portrait",
    "style",
    "same",
    "keep",
    "identical",
    "every",
    "time",
    "lock",
}


def build_bible(project: Project) -> dict[str, Any]:
    cast = []
    for c in project.characters:
        cast.append(
            {
                "id": c.id,
                "name": c.name,
                "role": c.role,
                "look": c.look,
                "lock": c.character_lock or "",
                "must_keep": _lock_features(c.character_lock or c.look or ""),
            }
        )
    world = []
    for s in project.scenes:
        world.append(
            {
                "id": s.id,
                "name": s.name,
                "location": s.location,
                "time_of_day": s.time_of_day,
                "mood": s.mood,
                "visual_notes": s.visual_notes,
                "must_keep": _lock_features(
                    " ".join([s.location, s.time_of_day, s.mood, s.visual_notes])
                ),
            }
        )
    rules = list(project.continuity_rules or [])
    if project.visual_style:
        rules.append(f"Visual style must stay: {project.visual_style}")
    text = _bible_text(project, cast, world, rules)
    return {
        "title": project.title,
        "style": project.visual_style,
        "logline": project.logline,
        "cast": cast,
        "world": world,
        "rules": rules,
        "auto_reject_below": float(getattr(project, "auto_reject_below", 0.55) or 0.55),
        "text": text,
    }


def _lock_features(text: str) -> list[str]:
    toks = [t for t in sorted(_tokens(text) - _STOP)]
    # Prefer distinctive multi-signal locks; keep top features
    return toks[:16]


def _bible_text(project: Project, cast: list[dict], world: list[dict], rules: list[str]) -> str:
    lines = [
        f"# Continuity Bible — {project.title}",
        f"Style: {project.visual_style}",
        f"Logline: {project.logline or '(none)'}",
        "",
        "## Cast",
    ]
    for c in cast:
        lines.append(
            f"- {c['name']} ({c['role'] or 'role?'}): look={c['look'] or '—'}; "
            f"LOCK={c['lock'] or '—'}; keep={', '.join(c['must_keep']) or '—'}"
        )
    lines.append("")
    lines.append("## World")
    for s in world:
        lines.append(
            f"- {s['name']}: {s['location']} / {s['time_of_day']} / {s['mood']}; "
            f"{s['visual_notes']}; keep={', '.join(s['must_keep']) or '—'}"
        )
    if rules:
        lines.append("")
        lines.append("## Rules")
        for r in rules:
            lines.append(f"- {r}")
    return "\n".join(lines)


def continuity_prompt_prefix(project: Project, shot: Shot | None = None) -> str:
    bible = build_bible(project)
    bits = [f"CONTINUITY STYLE: {bible['style']}"]
    if shot:
        chars = [c for c in project.characters if c.id in (shot.character_ids or [])]
        for c in chars:
            if c.character_lock:
                bits.append(f"CHARACTER LOCK {c.name}: {c.character_lock}")
            elif c.look:
                bits.append(f"CHARACTER LOOK {c.name}: {c.look}")
        scene = next((s for s in project.scenes if s.id == shot.scene_id), None)
        if scene:
            bits.append(
                f"SCENE LOCK {scene.name}: {scene.location}, {scene.time_of_day}, "
                f"{scene.mood}, {scene.visual_notes}"
            )
    for rule in bible["rules"][:6]:
        bits.append(f"RULE: {rule}")
    return " | ".join(bits)


def score_take_continuity(
    project: Project,
    shot: Shot,
    prompt_used: str,
    take_label: str = "",
) -> dict[str, Any]:
    """
    Heuristic continuity score: do the shot's character/scene lock features
    appear in the prompt that produced the take?
    (Vision scoring can plug in later; this keeps the studio useful offline.)
    """
    prompt_toks = _tokens(prompt_used)
    flags: list[str] = []
    checks = 0
    hits = 0

    chars = [c for c in project.characters if c.id in (shot.character_ids or [])]
    if not chars and project.characters:
        # If shot has no cast linked, still check primary lock characters lightly
        chars = project.characters[:1]

    for c in chars:
        features = _lock_features(c.character_lock or c.look or "")
        if not features:
            continue
        for feat in features:
            checks += 1
            if feat in prompt_toks:
                hits += 1
            else:
                flags.append(f"Possible lock drift ({c.name}): missing “{feat}” in gen prompt")

    scene = next((s for s in project.scenes if s.id == shot.scene_id), None)
    if scene:
        for feat in _lock_features(
            " ".join([scene.location, scene.time_of_day, scene.mood, scene.visual_notes])
        ):
            checks += 1
            if feat in prompt_toks:
                hits += 1
            else:
                flags.append(f"Scene drift ({scene.name}): missing “{feat}”")

    style = (project.visual_style or "").lower()
    if style:
        checks += 1
        if style in prompt_toks or any(style in p for p in prompt_toks):
            hits += 1
        else:
            flags.append(f"Style not reinforced: {project.visual_style}")

    score = 1.0 if checks == 0 else hits / checks
    # Soften: too many flags from generic misses — clamp presentation
    score = round(max(0.0, min(1.0, score)), 3)
    threshold = float(getattr(project, "auto_reject_below", 0.55) or 0.55)
    rejected = score < threshold and checks > 0

    note = (
        f"Continuity {int(score * 100)}%"
        + (f" · {len(flags)} flags" if flags else " · clean")
        + (f" · auto-reject" if rejected else "")
    )
    if take_label:
        note = f"{take_label} · {note}"

    return {
        "continuity_score": score,
        "continuity_flags": flags[:12],
        "rejected": rejected,
        "score_note": note,
        "checks": checks,
        "hits": hits,
    }


def rescore_project(project: Project) -> Project:
    by_shot = {s.id: s for s in project.shots}
    for take in project.takes:
        shot = by_shot.get(take.shot_id)
        if not shot:
            continue
        prompt = take.prompt_used or shot.prompt or shot.action or ""
        result = score_take_continuity(project, shot, prompt, take.label)
        take.continuity_score = result["continuity_score"]
        take.continuity_flags = result["continuity_flags"]
        take.rejected = result["rejected"]
        take.score_note = result["score_note"]
    return project
