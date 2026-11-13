from __future__ import annotations

"""Conversational StudioNels director — talks back and drives the UI via actions."""

import re
from typing import Any

from .agent import (
    STYLE_HINTS,
    _builtin_plan,
    _match_character_ids,
    _match_scene_id,
    _profiles_context,
)
from .frame_sizes import apply_frame_to_project
from .models import (
    AgentMessage,
    CharacterProfile,
    Project,
    SceneProfile,
    Shot,
    new_id,
)
from .storage import get_preset, load_settings, save_project

DIRECTOR_SYSTEM = """You are the StudioNels Director Agent — a warm, practical film collaborator.
You talk like Cursor chat: clear, helpful, short paragraphs. You DO things in the app for the user.

Always reply with ONLY valid JSON (no markdown) in this shape:
{
  "message": "what you say to the user (natural language)",
  "actions": [ /* zero or more actions below */ ]
}

Allowed actions (only use these types):
- {"type":"navigate","tab":"agent|profiles|time|shots|filmnight|director|generate|rehearsal|settings|learning"}
- {"type":"set_logline","logline":"string"}
- {"type":"set_style","visual_style":"cinematic|animation|clay|cartoon|anime|pixel|documentary|noir|neon_noir|dramatic"}
- {"type":"set_frame","frame_size_id":"16:9-draft|16:9-hd|9:16|9:16-draft|1:1|1:1-draft|21:9|4:5|3:4|4:3|3:2|2:3"}
- {"type":"set_duration","seconds":number}
- {"type":"set_continue","value":true|false}
- {"type":"add_character","name":"","role":"","look":"","personality":"","character_lock":""}
- {"type":"add_scene","name":"","location":"","time_of_day":"","mood":"","visual_notes":""}
- {"type":"replace_shots","shots":[ {title,action,dialogue,camera,duration_sec,character_names,scene_name,prompt,storyboard_note} ]}
- {"type":"append_shots","shots":[ ... same ... ]}
- {"type":"run_film_night","stage":"full|rehearse|promote|finals|stitch"}
- {"type":"notify","text":"short toast"}

Rules:
- Be conversational. Ask one clarifying question when the idea is vague.
- When they describe a film idea, replace_shots with 4–8 concrete shots AND navigate to shots or filmnight.
- When they say TikTok / Reels / Shorts / vertical → set_frame 9:16 (or 9:16-draft) and say so.
- When they say YouTube / landscape / film → 16:9-hd or 16:9-draft.
- When they name a character, add_character with a useful character_lock.
- When they say "let's shoot", "film night", "make it", "do it" → run_film_night full (only if shots exist) and navigate filmnight.
- When they want to edit/cut → navigate director.
- Do not invent paid cloud services. Everything stays local.
- Keep message under ~120 words unless listing beats.
"""


def _history_blob(project: Project, limit: int = 8) -> str:
    msgs = project.agent_messages[-limit:]
    lines = []
    for m in msgs:
        lines.append(f"{m.role.upper()}: {m.content}")
    return "\n".join(lines) or "(no prior chat)"


def _project_snapshot(project: Project) -> str:
    return (
        f"{_profiles_context(project)}\n"
        f"Shots now: {len(project.shots)}\n"
        f"Takes: {len(project.takes)}\n"
        f"Frame: {getattr(project, 'frame_size_id', '16:9-draft')} "
        f"({getattr(project, 'width', 768)}x{getattr(project, 'height', 432)})\n"
        f"Continue chain: {getattr(project, 'continue_from_previous', True)}\n"
        f"Recent chat:\n{_history_blob(project)}"
    )


def _apply_shots(project: Project, items: list[dict[str, Any]], replace: bool) -> None:
    built: list[Shot] = []
    for i, item in enumerate(items or []):
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
    if replace or not project.shots:
        project.shots = built
        project.timeline = []
    else:
        start = len(project.shots)
        for offset, shot in enumerate(built):
            shot.index = start + offset
            project.shots.append(shot)


def apply_actions(project: Project, actions: list[dict[str, Any]]) -> tuple[Project, list[dict[str, Any]]]:
    """Apply project-mutating actions. Return project + ui_actions for the frontend."""
    ui: list[dict[str, Any]] = []
    for raw in actions or []:
        if not isinstance(raw, dict):
            continue
        t = (raw.get("type") or "").strip()
        if t == "navigate":
            tab = raw.get("tab") or "agent"
            ui.append({"type": "navigate", "tab": tab})
        elif t == "notify":
            ui.append({"type": "notify", "text": str(raw.get("text") or "")})
        elif t == "run_film_night":
            ui.append(
                {
                    "type": "run_film_night",
                    "stage": raw.get("stage") or "full",
                }
            )
        elif t == "set_logline":
            project.logline = str(raw.get("logline") or "")[:240]
        elif t == "set_style":
            style = str(raw.get("visual_style") or "cinematic")
            project.visual_style = style
        elif t == "set_frame":
            fid = str(raw.get("frame_size_id") or "16:9-draft")
            apply_frame_to_project(project, fid)
        elif t == "set_duration":
            try:
                project.target_duration_sec = max(5.0, float(raw.get("seconds") or 60))
            except Exception:
                pass
        elif t == "set_continue":
            project.continue_from_previous = bool(raw.get("value", True))
        elif t == "add_character":
            name = (raw.get("name") or "").strip()
            if name and not any(c.name.lower() == name.lower() for c in project.characters):
                project.characters.append(
                    CharacterProfile(
                        name=name,
                        role=str(raw.get("role") or ""),
                        look=str(raw.get("look") or ""),
                        personality=str(raw.get("personality") or ""),
                        character_lock=str(raw.get("character_lock") or ""),
                    )
                )
        elif t == "add_scene":
            name = (raw.get("name") or "").strip()
            if name and not any(s.name.lower() == name.lower() for s in project.scenes):
                project.scenes.append(
                    SceneProfile(
                        name=name,
                        location=str(raw.get("location") or ""),
                        time_of_day=str(raw.get("time_of_day") or ""),
                        mood=str(raw.get("mood") or ""),
                        visual_notes=str(raw.get("visual_notes") or ""),
                    )
                )
        elif t == "replace_shots":
            _apply_shots(project, list(raw.get("shots") or []), replace=True)
        elif t == "append_shots":
            _apply_shots(project, list(raw.get("shots") or []), replace=False)
    return project, ui


def _builtin_chat(project: Project, message: str) -> dict[str, Any]:
    """Offline conversational director with real actions."""
    text = message.strip()
    low = text.lower()
    actions: list[dict[str, Any]] = []

    # Greetings / help
    if re.fullmatch(r"(hi|hello|hey|yo|sup)[!.?]*", low) or low in {
        "help",
        "what can you do",
        "what can you do?",
    }:
        return {
            "message": (
                "Hey — I’m your StudioNels director. Tell me a story idea and I’ll plan shots, "
                "set vertical/landscape, add characters, and I can send you to Film night or Director. "
                "Try: “A rainy neon chase for TikTok” or “Add a character named Mira with silver hair.”"
            ),
            "actions": [],
            "used_builtin": True,
        }

    # Frame / platform intents
    if any(k in low for k in ("tiktok", "reel", "reels", "shorts", "vertical", "9:16", "portrait")):
        actions.append({"type": "set_frame", "frame_size_id": "9:16-draft"})
        actions.append({"type": "notify", "text": "Frame → 9:16 portrait draft"})
    elif any(k in low for k in ("youtube", "landscape", "16:9", "widescreen", "film look")):
        actions.append({"type": "set_frame", "frame_size_id": "16:9-draft"})
        actions.append({"type": "notify", "text": "Frame → 16:9 landscape draft"})
    elif "1:1" in low or "square" in low:
        actions.append({"type": "set_frame", "frame_size_id": "1:1-draft"})
        actions.append({"type": "notify", "text": "Frame → 1:1 square draft"})

    # Style
    for style_id, hint in STYLE_HINTS.items():
        if style_id.replace("_", " ") in low or style_id in low:
            actions.append({"type": "set_style", "visual_style": style_id})
            break
    if "neon" in low:
        actions.append({"type": "set_style", "visual_style": "neon_noir"})

    # Add character: "add character Name ..." / "character named Name"
    m = re.search(
        r"(?:add\s+)?(?:a\s+)?character\s+(?:named\s+|called\s+)?([A-Z][a-zA-Z0-9_\-]{1,40})",
        text,
        re.I,
    )
    if not m:
        m = re.search(r"named\s+([A-Z][a-zA-Z0-9_\-]{1,40})", text)
    if m and ("character" in low or "named" in low or "cast" in low):
        name = m.group(1)
        look = ""
        if "with" in low:
            look = text[text.lower().find("with") + 4 :].strip(" .,!")[:120]
        actions.append(
            {
                "type": "add_character",
                "name": name,
                "role": "lead",
                "look": look or "memorable silhouette",
                "character_lock": f"same person every shot: {name}"
                + (f", {look}" if look else ""),
            }
        )
        actions.append({"type": "navigate", "tab": "profiles"})

    # Film night / shoot
    if any(
        k in low
        for k in (
            "film night",
            "filmnite",
            "let's shoot",
            "lets shoot",
            "make the film",
            "run film",
            "do film night",
            "stitch it",
        )
    ):
        if project.shots:
            actions.append({"type": "run_film_night", "stage": "full"})
            actions.append({"type": "navigate", "tab": "filmnight"})
            return {
                "message": (
                    "On it — opening Film night and running the pipeline "
                    "(rehearse → finals → stitch when ready)."
                ),
                "actions": actions,
                "used_builtin": True,
            }
        return {
            "message": (
                "We need shots first. Tell me the story idea and I’ll plan a shot list, "
                "then we can run Film night."
            ),
            "actions": actions,
            "used_builtin": True,
        }

    # Director / edit
    if any(k in low for k in ("director", "edit the cut", "timeline", "upload clip", "open edit")):
        actions.append({"type": "navigate", "tab": "director"})
        return {
            "message": "Opening Director — upload clips, captions, stitch & play there.",
            "actions": actions,
            "used_builtin": True,
        }

    # Story planning — if message is meaty enough
    is_idea = len(text) > 24 or any(
        k in low
        for k in (
            "film",
            "story",
            "short",
            "about",
            "scene",
            "shot",
            "music video",
            "ad",
            "plan",
        )
    )
    if is_idea and not low.startswith("add character"):
        plan = _builtin_plan(project, text)
        shots = plan.get("shots") or []
        actions.append({"type": "set_logline", "logline": re.sub(r"\s+", " ", text)[:180]})
        actions.append({"type": "replace_shots", "shots": shots})
        actions.append({"type": "set_continue", "value": True})
        actions.append({"type": "navigate", "tab": "shots"})
        actions.append({"type": "notify", "text": f"Planned {len(shots)} shots"})
        msg = (
            f"I planned {len(shots)} shots from your idea. They’re on the Shots tab — "
            "edit anything, then say “film night” and I’ll run the pipeline, or “open director” to cut."
        )
        if any(a.get("type") == "set_frame" for a in actions):
            msg += " I also set the frame size to match what you asked for."
        return {"message": msg, "actions": actions, "used_builtin": True}

    return {
        "message": (
            "Tell me more — a story idea, a character to add, TikTok vs YouTube framing, "
            "or say “film night” when shots are ready."
        ),
        "actions": actions,
        "used_builtin": True,
    }


async def _llm_chat(project: Project, message: str) -> dict[str, Any] | None:
    from .llm_providers import chat_json

    settings = load_settings()
    if (settings.agent_provider or "").lower() == "builtin":
        return None
    preset = get_preset(project.preset_id or settings.preset_id)
    agent_cfg = preset.get("agent", {})
    max_tokens = int(agent_cfg.get("max_tokens") or 1600)
    user = (
        f"Project state:\n{_project_snapshot(project)}\n\n"
        f"User says:\n{message}\n\n"
        "Respond with JSON {message, actions}."
    )
    return await chat_json(settings, DIRECTOR_SYSTEM, user, max_tokens=max_tokens)


async def director_chat(project: Project, message: str) -> dict[str, Any]:
    """Main entry: conversational reply + applied actions + ui hooks."""
    settings = load_settings()
    text = (message or "").strip()
    if not text:
        return {
            "project": project,
            "message": "Say anything — an idea, a character, or “help”.",
            "actions": [],
            "ui_actions": [],
        }

    project.agent_messages.append(AgentMessage(role="user", content=text))

    plan = await _llm_chat(project, text)
    if not plan or not isinstance(plan, dict):
        plan = _builtin_chat(project, text)
        provider = settings.agent_provider or "ollama"
        if provider not in ("builtin",) and not plan.get("used_builtin"):
            pass
        elif provider != "builtin":
            # Soft note when falling back
            note = f" (Using built-in director — connect Ollama or an API key in Settings for smarter chat.)"
            if note.strip() not in (plan.get("message") or ""):
                plan["message"] = ((plan.get("message") or "") + note).strip()
        plan["used_builtin"] = True
    else:
        plan["used_provider"] = settings.agent_provider

    reply = str(plan.get("message") or plan.get("assistant_message") or "Done.")
    actions = list(plan.get("actions") or [])

    # Legacy LLM shot-only replies
    if not actions and plan.get("shots"):
        actions.append({"type": "replace_shots", "shots": plan["shots"]})
        actions.append({"type": "navigate", "tab": "shots"})

    project, ui_actions = apply_actions(project, actions)
    project.agent_messages.append(AgentMessage(role="assistant", content=reply))
    saved = save_project(project)

    return {
        "project": saved,
        "message": reply,
        "actions": actions,
        "ui_actions": ui_actions,
        "used_builtin": bool(plan.get("used_builtin")),
        "provider": settings.agent_provider,
    }
