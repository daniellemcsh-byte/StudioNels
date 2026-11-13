from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .models import (
    AgentMessage,
    CharacterProfile,
    Project,
    SceneProfile,
    Shot,
    new_id,
)
from .storage import get_preset, load_settings


SYSTEM_PROMPT = """You are Framewright, a friendly film director assistant for people who are new to AI video.
You help turn a story idea into a clear shot list.
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
Keep 4–8 shots unless the user asks for more. Be concrete and visual. Use existing character/scene names when provided.
"""


def _profiles_context(project: Project) -> str:
    chars = [
        f"- {c.name}: role={c.role}; look={c.look}; personality={c.personality}"
        for c in project.characters
    ]
    scenes = [
        f"- {s.name}: {s.location}, {s.time_of_day}, mood={s.mood}; {s.visual_notes}"
        for s in project.scenes
    ]
    return (
        f"Mode: {project.mode}\nLogline: {project.logline or '(none)'}\n"
        f"Characters:\n{chr(10).join(chars) or '- (none yet)'}\n"
        f"Scenes:\n{chr(10).join(scenes) or '- (none yet)'}"
    )


async def _ollama_plan(project: Project, message: str) -> dict[str, Any] | None:
    settings = load_settings()
    preset = get_preset(project.preset_id or settings.preset_id)
    agent_cfg = preset.get("agent", {})
    if agent_cfg.get("provider") == "builtin":
        return None

    model = settings.ollama_model or agent_cfg.get("model") or "llama3.2:3b"
    base = settings.ollama_url or agent_cfg.get("base_url") or "http://127.0.0.1:11434"
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{_profiles_context(project)}\n\nUser idea:\n{message}",
            },
        ],
        "options": {"num_predict": agent_cfg.get("max_tokens", 1200)},
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            res = await client.post(f"{base.rstrip('/')}/api/chat", json=payload)
            if res.status_code != 200:
                return None
            content = res.json().get("message", {}).get("content", "")
            return json.loads(content)
    except Exception:
        return None


def _builtin_plan(project: Project, message: str) -> dict[str, Any]:
    """Deterministic friendly planner — works offline with no LLM."""
    text = message.strip()
    mode = project.mode
    chars = project.characters or [
        CharacterProfile(name="Lead", role="protagonist", look="memorable silhouette")
    ]
    scenes = project.scenes or [
        SceneProfile(name="Opening location", location="unspecified", mood="curious")
    ]
    lead = chars[0].name
    place = scenes[0].name

    beats = [
        (
            "Cold open",
            f"{lead} enters {place}. We sense the idea: {text[:120]}",
            "wide",
            3.0,
        ),
        (
            "Character beat",
            f"Close on {lead}. A detail that makes them human.",
            "close-up",
            2.5,
        ),
        (
            "Story turn",
            "Something changes — a choice, a clue, or a clash.",
            "medium",
            3.5,
        ),
        (
            "Momentum",
            "Tracking movement through the space; stakes rise.",
            "tracking",
            3.0,
        ),
        (
            "Emotional peak",
            f"{lead} faces the heart of the story.",
            "close-up",
            3.0,
        ),
        (
            "Resolution beat",
            "A quiet final image that lands the theme.",
            "wide",
            3.0,
        ),
    ]

    if mode == "ad":
        beats = beats[:4]
        beats[0] = ("Hook", f"Bold visual hook for: {text[:100]}", "close-up", 2.0)
    elif mode == "music_video":
        beats = [
            ("Verse visual", f"Rhythmic opener in {place}.", "wide", 4.0),
            ("Character refrain", f"{lead} as the song's face.", "medium", 3.0),
            ("Chorus lift", "Bigger motion, stronger light.", "tracking", 4.0),
            ("Bridge", "Intimate break from the pattern.", "close-up", 3.0),
            ("Final chorus", "Payoff image locked to the beat.", "wide", 4.0),
        ]

    shots = []
    for title, action, camera, dur in beats:
        scene = scenes[min(len(shots) % max(len(scenes), 1), len(scenes) - 1)]
        char_names = [c.name for c in chars[:2]]
        prompt = (
            f"{mode.replace('_', ' ')} shot, {camera} shot of {', '.join(char_names)} "
            f"in {scene.name}: {action}. Cinematic lighting, coherent faces, natural motion."
        )
        shots.append(
            {
                "title": title,
                "action": action,
                "dialogue": "",
                "camera": camera,
                "duration_sec": dur,
                "character_names": char_names,
                "scene_name": scene.name,
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
    plan = await _ollama_plan(project, message)
    if not plan:
        plan = _builtin_plan(project, message)
        plan["used_builtin"] = True
    return apply_plan(project, plan, message, replace_shots)
