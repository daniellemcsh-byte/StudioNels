"""Continuity supervisor for the storyboard — offline, rule based.

Looks across the whole board the way a script supervisor would: time of day
jumps, props that vanish, characters with no defined look, new locations with
no establishing shot, repeated framing, dialogue too long for the shot, total
runtime against the target, and prompts too long for the chosen model.
"""

from __future__ import annotations

import re
from typing import Any

from .models import Project
from .prompt_compiler import compile_shot, shot_cast, shot_props, shot_scene

_NIGHT = ("night", "midnight", "evening", "dusk", "late")
_DAY = ("day", "morning", "noon", "afternoon", "dawn", "sunrise", "daylight")


def _phase(text: str) -> str:
    low = (text or "").lower()
    if any(k in low for k in _NIGHT):
        return "night"
    if any(k in low for k in _DAY):
        return "day"
    return ""


def _issue(level: str, code: str, message: str, shot=None, fix: str = "") -> dict[str, Any]:
    return {
        "level": level,  # error | warn | info
        "code": code,
        "message": message,
        "fix": fix,
        "shot_id": shot.id if shot is not None else None,
        "shot_number": (shot.index + 1) if shot is not None else None,
    }


_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "with", "into", "through", "from", "over",
    "under", "as", "is", "are", "was", "be", "it", "its", "his", "her", "their", "they", "she", "he", "we",
    "this", "that", "then", "while", "shot", "close", "wide", "medium", "camera", "frame", "scene", "slow",
    "image", "moment", "something", "story", "world", "final", "quiet", "small", "detail", "main", "character",
    "establishing", "sets", "changes", "choice", "clue", "clash", "movement", "space", "stakes", "rise", "heart",
    "lands", "theme", "human", "makes", "them", "close-up", "tracking",
}
_SENT_START = re.compile(r"(?:^|[.!?:]\s+)([A-Z][a-z]+)")


def learn_memory(project: Project) -> list[dict[str, str]]:
    """Suggest memory entries from the board: unnamed recurring characters and
    objects, and the world from the logline. The user accepts each one."""
    shots = sorted(project.shots, key=lambda s: s.index)
    texts = [" ".join((s.action, s.title, s.storyboard_note, s.dialogue)) for s in shots]
    known = {c.name.lower() for c in project.characters} | {p.name.lower() for p in project.props}
    known |= {s.name.lower() for s in project.scenes}
    suggestions: list[dict[str, str]] = []

    # Proper names used in 2+ shots (skipping words that only start sentences)
    name_hits: dict[str, int] = {}
    for t in texts:
        starts = set(_SENT_START.findall(t))
        for name in set(re.findall(r"\b([A-Z][a-z]{2,})\b", t)):
            if name in starts and t.count(name) == 1:
                continue
            if name.lower() in known or name.lower() in _STOPWORDS:
                continue
            name_hits[name] = name_hits.get(name, 0) + 1
    for name, n in sorted(name_hits.items(), key=lambda kv: -kv[1]):
        if n >= 2:
            suggestions.append({"kind": "character", "value": name, "reason": f"named in {n} shots"})

    # Recurring two-word object phrases ("glowing jars") in 2+ shots
    phrase_hits: dict[str, int] = {}
    for t in texts:
        words = re.findall(r"[a-z]+", t.lower())
        seen: set[str] = set()
        for a, b in zip(words, words[1:]):
            if a in _STOPWORDS or b in _STOPWORDS or len(a) < 4 or len(b) < 4:
                continue
            phrase = f"{a} {b}"
            if phrase not in seen:
                seen.add(phrase)
                phrase_hits[phrase] = phrase_hits.get(phrase, 0) + 1
    for phrase, n in sorted(phrase_hits.items(), key=lambda kv: -kv[1])[:8]:
        if n >= 2 and phrase not in known:
            suggestions.append({"kind": "prop", "value": phrase, "reason": f"appears in {n} shots"})

    if project.logline and not project.memory.world:
        suggestions.append({"kind": "world", "value": project.logline[:200], "reason": "from the logline"})
    return suggestions[:12]


def check_storyboard(project: Project, model: dict[str, Any] | None = None) -> dict[str, Any]:
    shots = sorted(project.shots, key=lambda s: s.index)
    issues: list[dict[str, Any]] = []
    total = round(sum(float(s.duration_sec or 0) for s in shots), 1)
    target = float(project.target_duration_sec or 0)

    mem = project.memory
    if shots and not any((mem.world, mem.tone, mem.palette)):
        issues.append(
            _issue(
                "info",
                "memory_empty",
                "Film memory is empty — world, tone and palette make every shot more consistent.",
                fix="Fill in Film memory (world, tone, palette).",
            )
        )
    if target and shots:
        if total > target * 1.25:
            issues.append(_issue("info", "runtime_long", f"Board runs {total}s against a {target:.0f}s target."))
        elif total < target * 0.6:
            issues.append(_issue("info", "runtime_short", f"Board runs {total}s against a {target:.0f}s target."))

    prev = None
    camera_run: list[str] = []
    for shot in shots:
        cast = shot_cast(project, shot)
        props = shot_props(project, shot)
        scene = shot_scene(project, shot)
        if not (shot.action or shot.storyboard_note or shot.prompt).strip():
            issues.append(_issue("error", "no_action", "No action written for this shot.", shot, "Describe what happens."))
        for c in cast:
            if not (c.character_lock or c.look):
                issues.append(
                    _issue("warn", "no_look", f"{c.name} has no look defined, so they may change between shots.", shot,
                           f"Add {c.name}'s look / identity lock.")
                )
        tagged = set(shot.character_ids or [])
        for c in cast:
            if c.id not in tagged:
                issues.append(_issue("info", "untagged", f"{c.name} is mentioned but not tagged in this shot.", shot,
                                     f"Tag {c.name} so their look is applied."))
        words = len((shot.dialogue or "").split())
        if words and words > max(1.0, float(shot.duration_sec or 3)) * 3:
            issues.append(
                _issue("warn", "dialogue_long",
                       f"{words} words of dialogue in {shot.duration_sec}s — too fast to say naturally.", shot,
                       "Lengthen the shot or trim the line.")
            )
        for p in props:
            if p.owner_id and p.owner_id not in {c.id for c in cast}:
                owner = next((c.name for c in project.characters if c.id == p.owner_id), "its owner")
                issues.append(_issue("info", "prop_owner", f"The {p.name} appears without {owner}.", shot))
        if model is not None:
            compiled = compile_shot(project, shot, model)
            if compiled["over_budget"]:
                issues.append(_issue("warn", "prompt_budget", compiled["warnings"][0], shot,
                                     "Shorten the action or memory notes, or pick a model with a longer prompt."))

        if prev is not None:
            prev_scene = shot_scene(project, prev)
            same_scene = (prev.scene_id or None) == (shot.scene_id or None)
            t_prev = _phase(prev.time_of_day or (prev_scene.time_of_day if prev_scene else ""))
            t_now = _phase(shot.time_of_day or (scene.time_of_day if scene else ""))
            time_noted = bool(
                re.search(r"\b(later|hours?|passes|passed|by (morning|night|dawn|dusk)|next day|overnight|time)\b",
                          prev.state_after or "", re.I)
            )
            if same_scene and t_prev and t_now and t_prev != t_now and not time_noted:
                issues.append(
                    _issue("warn", "time_jump", f"Time of day jumps from {t_prev} to {t_now} inside the same scene.", shot,
                           "Set the same time of day, or note the time passing in the previous shot's “state after”.")
                )
            if not same_scene and shot.scene_id and (shot.camera or "").lower() not in ("wide", "aerial", "overhead"):
                issues.append(
                    _issue("info", "no_establishing",
                           f"New location ({scene.name if scene else 'scene'}) starts without a wide shot.", shot,
                           "Consider a wide / establishing shot first.")
                )
            prev_props = {p.id for p in shot_props(project, prev)}
            now_props = {p.id for p in props}
            shared_people = {c.id for c in shot_cast(project, prev)} & {c.id for c in cast}
            for pid in prev_props - now_props:
                prop = next((p for p in project.props if p.id == pid), None)
                if prop and prop.owner_id and prop.owner_id in shared_people:
                    owner = next((c.name for c in project.characters if c.id == prop.owner_id), "the owner")
                    if prop.name.lower() not in (prev.state_after or "").lower():
                        issues.append(
                            _issue("info", "prop_vanished", f"{owner} had the {prop.name} last shot; it's gone now.", shot,
                                   f"Tag the {prop.name} here, or say what happened to it in the previous shot.")
                        )
            if prev.state_after and shared_people:
                issues.append(_issue("info", "carry_state", f"Carrying over from shot {prev.index + 1}: {prev.state_after}", shot))

        cam = (shot.camera or "").lower()
        camera_run = camera_run + [cam] if camera_run and camera_run[-1] == cam else [cam]
        if len(camera_run) == 3:
            issues.append(_issue("info", "same_framing", f"Three {cam} shots in a row.", shot,
                                 "Vary the framing to keep the cut lively."))
        prev = shot

    counts = {lvl: sum(1 for i in issues if i["level"] == lvl) for lvl in ("error", "warn", "info")}
    return {
        "issues": issues,
        "counts": counts,
        "total_sec": total,
        "target_sec": target,
        "shot_count": len(shots),
    }
