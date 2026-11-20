from __future__ import annotations

import re
from typing import Any

from .models import (
    AgentMessage,
    CharacterProfile,
    Project,
    SceneProfile,
    Shot,
    new_id,
)
from .storage import get_preset, load_settings


SYSTEM_PROMPT = """You are StudioNels, a friendly film director assistant for people who are new to AI video.
You help turn a story idea into a clear shot list. Keep language warm and plain — this is StudioNels.
Reply with ONLY valid JSON (no markdown) using this shape:
{
  "assistant_message": "short friendly summary",
  "shots": [
    {
      "title": "string",
      "action": "what happens",
      "dialogue": "optional",
      "camera": "wide|medium|close-up|tracking|pov",
      "duration_sec": 3,
      "character_names": ["optional names from profiles"],
      "scene_name": "optional scene name",
      "prompt": "visual prompt for local video model",
      "storyboard_note": "simple board note"
    }
  ]
}
Keep 4–8 shots unless the user asks for more. Fit shot duration_sec values so they roughly add up to the project's target total runtime. Bake the visual style into every prompt. Be concrete and visual. Use existing character/scene names when provided.
"""


STYLE_HINTS = {
    "cinematic": "cinematic lighting, film grain, naturalistic color",
    "animation": "stylized 3D animation",
    "clay": "claymation stop-motion, plasticine textures",
    "cartoon": "2D cartoon, bold outlines, flat colors",
    "anime": "anime style, cel shading",
    "pixel": "pixel art, retro game aesthetic",
    "documentary": "documentary, natural light, handheld feel",
    "noir": "film noir, high contrast shadows",
}


def _profiles_context(project: Project) -> str:
    chars = [
        f"- {c.name}: role={c.role}; look={c.look}; "
        f"lock={getattr(c, 'character_lock', '') or '(none)'}; personality={c.personality}"
        for c in project.characters
    ]
    scenes = [
        f"- {s.name}: {s.location}, {s.time_of_day}, mood={s.mood}; {s.visual_notes}"
        for s in project.scenes
    ]
    total = float(getattr(project, "target_duration_sec", 60) or 60)
    style = getattr(project, "visual_style", "cinematic") or "cinematic"
    style_hint = STYLE_HINTS.get(style, style)
    return (
        f"Mode: {project.mode}\nLogline: {project.logline or '(none)'}\n"
        f"Target total runtime: {total:.0f} seconds "
        f"(divide across shots so they roughly add up).\n"
        f"Visual style: {style} — bake into every shot prompt ({style_hint}).\n"
        f"Characters:\n{chr(10).join(chars) or '- (none yet)'}\n"
        f"Scenes:\n{chr(10).join(scenes) or '- (none yet)'}"
    )


async def _llm_plan(project: Project, message: str) -> dict[str, Any] | None:
    from .llm_providers import chat_json

    settings = load_settings()
    if (settings.agent_provider or "").lower() == "builtin":
        return None
    preset = get_preset(project.preset_id or settings.preset_id)
    agent_cfg = preset.get("agent", {})
    max_tokens = int(agent_cfg.get("max_tokens") or 1200)
    user = f"{_profiles_context(project)}\n\nUser idea:\n{message}"
    return await chat_json(settings, SYSTEM_PROMPT, user, max_tokens=max_tokens)


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def requested_shot_count(text: str) -> int | None:
    """'a 3-shot short', 'five shots', '4 scenes' -> 3 / 5 / 4 (1..12)."""
    m = re.search(r"\b(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")[\s-]*(?:shots?|scenes?)\b", text, re.I)
    if not m:
        return None
    raw = m.group(1).lower()
    n = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
    return max(1, min(12, n))


def story_from_request(text: str) -> str:
    """Strip the command around the idea: 'Plan a 3-shot short: X' -> 'X'."""
    s = re.sub(r"\s+", " ", text).strip()
    s = re.sub(
        r"^(?:please\s+)?(?:can you\s+)?(?:plan|make|create|write|sketch|do|give me|i want)\s+(?:me\s+)?"
        r"(?:an?\s+)?(?:(?:\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")[\s-]*(?:shots?|scenes?)\s*)?"
        r"(?:short(?:\s+film)?|film|video|ad|advert|music video|story|scene|sequence)?\s*(?:about|of|where|:|-|–|—)?\s*",
        "",
        s,
        flags=re.I,
    )
    return s.strip(" .:-–—") or text.strip()


def _pick_beats(beats: list, n: int | None) -> list:
    """Keep the story shape (open ... close) at any requested length."""
    if not n or n == len(beats):
        return beats
    if n < len(beats):
        if n == 1:
            return [beats[0]]
        step = (len(beats) - 1) / (n - 1)
        return [beats[round(i * step)] for i in range(n)]
    extra = []
    middle = beats[1:-1] or beats
    for i in range(n - len(beats)):
        title, action, camera, dur = middle[i % len(middle)]
        extra.append((f"{title} {i // len(middle) + 2}", action, camera, dur))
    return beats[:-1] + extra + beats[-1:]


def _builtin_plan(project: Project, message: str) -> dict[str, Any]:
    """Deterministic friendly planner — works offline with no LLM.

    Every shot carries the user's actual idea; with no characters/scenes yet
    it used to fall back to "Lead in Opening location" and lose the story.
    """
    text = message.strip()
    story = story_from_request(text)
    count = requested_shot_count(text)
    mode = project.mode
    chars = project.characters
    scenes = project.scenes
    who = ", ".join(c.name for c in chars[:2]) if chars else "the main character"
    style = getattr(project, "visual_style", "cinematic") or "cinematic"
    style_hint = STYLE_HINTS.get(style, style)

    beats = [
        ("Cold open", "Establishing image that sets the world", "wide", 3.0),
        ("Character beat", f"Close on {who} — a small human detail", "close-up", 2.5),
        ("Story turn", "Something changes — a choice, a clue, or a clash", "medium", 3.5),
        ("Momentum", "Movement through the space as the stakes rise", "tracking", 3.0),
        ("Emotional peak", f"{who.capitalize()} at the heart of the moment", "close-up", 3.0),
        ("Resolution beat", "A quiet final image that lands the theme", "wide", 3.0),
    ]
    if mode == "ad":
        beats = [
            ("Hook", "Bold visual hook in the first second", "close-up", 2.0),
            ("Product in use", "The thing in action, clearly readable", "medium", 3.0),
            ("Payoff", "The feeling it delivers", "tracking", 3.0),
            ("Logo beat", "Clean hero image to end on", "wide", 2.0),
        ]
    elif mode == "music_video":
        beats = [
            ("Verse visual", "Rhythmic opener", "wide", 4.0),
            ("Character refrain", f"{who.capitalize()} as the song's face", "medium", 3.0),
            ("Chorus lift", "Bigger motion, stronger light", "tracking", 4.0),
            ("Bridge", "Intimate break from the pattern", "close-up", 3.0),
            ("Final chorus", "Payoff image locked to the beat", "wide", 4.0),
        ]
    beats = _pick_beats(beats, count)

    shots = []
    for title, beat_action, camera, dur in beats:
        scene = scenes[len(shots) % len(scenes)] if scenes else None
        char_names = [c.name for c in chars[:2]]
        action = f"{beat_action}: {story}"
        where = f" in {scene.name}" if scene else ""
        prompt = (
            f"{camera} shot{where}. {story}. {beat_action}. "
            f"{style_hint}, coherent faces, natural motion."
        )
        shots.append(
            {
                "title": title,
                "action": action,
                "dialogue": "",
                "camera": camera,
                "duration_sec": dur,
                "character_names": char_names,
                "scene_name": scene.name if scene else "",
                "prompt": prompt,
                "storyboard_note": f"{camera.title()} — {title.lower()}",
            }
        )

    return {
        "assistant_message": (
            "I sketched a simple shot list from your idea. You can edit every shot, "
            "swap characters, or ask me to replan. No cloud needed — this used the "
            "built-in local planner"
            + (" (Ollama was offline)." if True else ".")
        ),
        "shots": shots,
        "used_builtin": True,
    }


def _match_character_ids(project: Project, names: list[str]) -> list[str]:
    ids: list[str] = []
    for name in names:
        key = name.strip().lower()
        for c in project.characters:
            if c.name.lower() == key or key in c.name.lower():
                ids.append(c.id)
                break
    return ids


def _match_scene_id(project: Project, name: str | None) -> str | None:
    if not name:
        return project.scenes[0].id if project.scenes else None
    key = name.strip().lower()
    for s in project.scenes:
        if s.name.lower() == key or key in s.name.lower():
            return s.id
    return project.scenes[0].id if project.scenes else None


def apply_plan(
    project: Project,
    plan: dict[str, Any],
    user_message: str,
    replace_shots: bool,
) -> Project:
    project.agent_messages.append(
        AgentMessage(role="user", content=user_message)
    )
    assistant = plan.get("assistant_message") or "Here's a shot list you can edit."
    if plan.get("used_builtin"):
        assistant += (
            " Tip: install Ollama with llama3.2:3b for smarter local planning."
        )
    project.agent_messages.append(AgentMessage(role="assistant", content=assistant))

    raw_shots = plan.get("shots") or []
    built: list[Shot] = []
    for i, item in enumerate(raw_shots):
        built.append(
            Shot(
                index=i,
                title=item.get("title") or f"Shot {i + 1}",
                action=item.get("action") or "",
                dialogue=item.get("dialogue") or "",
                camera=item.get("camera") or "medium",
                duration_sec=float(item.get("duration_sec") or 3),
                character_ids=_match_character_ids(
                    project, item.get("character_names") or []
                ),
                scene_id=_match_scene_id(project, item.get("scene_name")),
                prompt=item.get("prompt") or "",
                storyboard_note=item.get("storyboard_note") or "",
            )
        )

    if replace_shots or not project.shots:
        project.shots = built
        project.timeline = []
    else:
        start = len(project.shots)
        for offset, shot in enumerate(built):
            shot.index = start + offset
            project.shots.append(shot)

    if not project.logline and user_message:
        project.logline = re.sub(r"\s+", " ", user_message)[:180]

    return project


async def plan_project(
    project: Project, message: str, replace_shots: bool = True
) -> Project:
    settings = load_settings()
    plan = await _llm_plan(project, message)
    if not plan:
        plan = _builtin_plan(project, message)
        plan["used_builtin"] = True
        provider = settings.agent_provider or "ollama"
        if provider != "builtin":
            plan["assistant_message"] = (
                (plan.get("assistant_message") or "")
                + f" (Fell back to built-in planner — check {provider} settings/API key.)"
            ).strip()
    else:
        plan["used_provider"] = settings.agent_provider
    return apply_plan(project, plan, message, replace_shots)
