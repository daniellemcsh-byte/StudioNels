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
    AgentAttachment,
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
- {"type":"navigate","tab":"agent|profiles|time|shots|filmnight|director|generate|rehearsal|settings|learning|characters"}
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
- When they describe a film idea, replace_shots with 4–8 concrete shots. Stay in the agent chat — do NOT navigate away.
- Only use navigate when the user clearly asks to open another tab (“open director”, “go to shots”, “film night”, “open settings”).
- When they say TikTok / Reels / Shorts / vertical → set_frame 9:16 (or 9:16-draft) and say so.
- When they say YouTube / landscape / film → 16:9-hd or 16:9-draft.
- When they name a character, add_character with a useful character_lock (no navigate).
- When the user attaches character/image references, put those character_names on EVERY shot and mention face/ref lock in prompts.
- When they say "let's shoot", "film night", "make it", "do it" → run_film_night full (only if shots exist) and navigate filmnight.
- When they want to edit/cut → navigate director.
- Do not invent paid cloud services. Everything stays local.
- Keep message under ~120 words unless listing beats.
"""


def _attachment_lines(attachments: list[AgentAttachment]) -> str:
    if not attachments:
        return ""
    lines = ["Attached references this turn:"]
    for a in attachments:
        kind = a.kind or "image"
        name = a.name or a.character_id or a.scene_id or "untitled"
        path = a.path or "(no file)"
        lines.append(f"- {kind}: {name} @ {path}")
    return "\n".join(lines)


def apply_attachments(
    project: Project, attachments: list[AgentAttachment] | None
) -> tuple[Project, list[str], list[str], list[AgentAttachment]]:
    """Wire chat attachments into characters/scenes. Returns char ids, scene ids, normalized atts."""
    if not attachments:
        return project, [], [], []
    char_ids: list[str] = []
    scene_ids: list[str] = []
    normalized: list[AgentAttachment] = []
    orphan_images: list[AgentAttachment] = []

    for raw in attachments:
        if not isinstance(raw, AgentAttachment):
            try:
                att = AgentAttachment.model_validate(raw)
            except Exception:
                continue
        else:
            att = raw

        if att.kind == "character" and att.character_id:
            char = next((c for c in project.characters if c.id == att.character_id), None)
            if char:
                if att.path and not char.reference_path:
                    char.reference_path = att.path
                    try:
                        from .identity_lock import refresh_character_identity

                        refresh_character_identity(char)
                    except Exception:
                        pass
                if not att.path and char.reference_path:
                    att.path = char.reference_path
                if not att.name:
                    att.name = char.name
                char_ids.append(char.id)
                normalized.append(att)
            continue

        if att.kind == "scene" and att.scene_id:
            scene = next((s for s in project.scenes if s.id == att.scene_id), None)
            if scene:
                if att.path and not scene.reference_path:
                    scene.reference_path = att.path
                if not att.path and scene.reference_path:
                    att.path = scene.reference_path
                if not att.name:
                    att.name = scene.name
                scene_ids.append(scene.id)
                normalized.append(att)
            continue

        if att.kind in ("image", "file") and att.path:
            orphan_images.append(att)
            normalized.append(att)

    # Loose image uploads become a reference character (or update "Reference" lead)
    for i, att in enumerate(orphan_images):
        label = (att.name or "").strip() or f"Ref {i + 1}"
        existing = next(
            (c for c in project.characters if c.name.lower() == label.lower()),
            None,
        )
        if existing:
            existing.reference_path = att.path
            if not existing.character_lock:
                existing.character_lock = f"same person every shot: {existing.name}, match reference still"
            try:
                from .identity_lock import refresh_character_identity

                refresh_character_identity(existing)
            except Exception:
                pass
            char_ids.append(existing.id)
            att.kind = "character"
            att.character_id = existing.id
            att.name = existing.name
        else:
            char = CharacterProfile(
                name=label if label != f"Ref {i + 1}" else "Lead ref",
                role="reference lead",
                look="match attached reference still",
                character_lock="same person every shot — match the attached reference face/look",
                reference_path=att.path,
                tags=["agent-upload"],
            )
            try:
                from .identity_lock import refresh_character_identity

                refresh_character_identity(char)
            except Exception:
                pass
            project.characters.append(char)
            char_ids.append(char.id)
            att.kind = "character"
            att.character_id = char.id
            att.name = char.name

    # de-dupe preserving order
    def _uniq(ids: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in ids:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return project, _uniq(char_ids), _uniq(scene_ids), normalized


def _inject_refs_into_shots(
    project: Project, char_ids: list[str], scene_ids: list[str]
) -> None:
    if not char_ids and not scene_ids:
        return
    names = [c.name for c in project.characters if c.id in char_ids]
    for shot in project.shots:
        if char_ids:
            merged = list(dict.fromkeys([*(shot.character_ids or []), *char_ids]))
            shot.character_ids = merged
            lock_bits = []
            for c in project.characters:
                if c.id in char_ids:
                    bit = c.character_lock or c.look or c.name
                    if bit:
                        lock_bits.append(bit)
            if lock_bits and lock_bits[0] not in (shot.prompt or ""):
                shot.prompt = (
                    f"{shot.prompt}, consistent character: {', '.join(lock_bits)}".strip(", ")
                )
            if names and not any(n.lower() in (shot.action or "").lower() for n in names):
                shot.action = f"{names[0]} — {shot.action}".strip(" —")
        if scene_ids and not shot.scene_id:
            shot.scene_id = scene_ids[0]


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
        actions.append({"type": "notify", "text": f"Added character {name}"})

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

    # Director / edit — only leave chat when they ask to open it
    if any(
        k in low
        for k in (
            "open director",
            "go to director",
            "edit the cut",
            "open timeline",
            "open edit",
        )
    ):
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
        actions.append({"type": "notify", "text": f"Planned {len(shots)} shots"})
        msg = (
            f"I planned {len(shots)} shots from your idea — they stay on the Shots tab when you want them. "
            "Say “film night” to shoot, or “open shots” / “open director” if you want me to switch tabs."
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


async def _llm_chat(
    project: Project, message: str, attachments: list[AgentAttachment] | None = None
) -> dict[str, Any] | None:
    from .llm_providers import chat_json

    settings = load_settings()
    if (settings.agent_provider or "").lower() == "builtin":
        return None
    preset = get_preset(project.preset_id or settings.preset_id)
    agent_cfg = preset.get("agent", {})
    max_tokens = int(agent_cfg.get("max_tokens") or 1600)
    att_blob = _attachment_lines(attachments or [])
    user = (
        f"Project state:\n{_project_snapshot(project)}\n\n"
        f"{att_blob}\n\n" if att_blob else f"Project state:\n{_project_snapshot(project)}\n\n"
    ) + f"User says:\n{message}\n\nRespond with JSON {{message, actions}}."
    return await chat_json(settings, DIRECTOR_SYSTEM, user, max_tokens=max_tokens)


async def director_chat(
    project: Project,
    message: str,
    attachments: list[AgentAttachment] | None = None,
) -> dict[str, Any]:
    """Main entry: conversational reply + applied actions + ui hooks."""
    settings = load_settings()
    text = (message or "").strip()
    atts_in = list(attachments or [])

    project, char_ids, scene_ids, normalized = apply_attachments(project, atts_in)

    if not text and not normalized:
        return {
            "project": project,
            "message": "Say anything — an idea, attach a character/image, or “help”.",
            "actions": [],
            "ui_actions": [],
        }
    if not text and normalized:
        names = ", ".join(a.name or a.kind for a in normalized)
        text = f"Use these attached references for the film: {names}."

    project.agent_messages.append(
        AgentMessage(role="user", content=text, attachments=normalized)
    )

    plan = await _llm_chat(project, text, normalized)
    if not plan or not isinstance(plan, dict):
        plan = _builtin_chat(project, text)
        # Prefer attached character names when planning shots
        if char_ids and plan.get("actions"):
            names = [c.name for c in project.characters if c.id in char_ids]
            for act in plan["actions"]:
                if act.get("type") in ("replace_shots", "append_shots"):
                    for sh in act.get("shots") or []:
                        if isinstance(sh, dict):
                            existing = list(sh.get("character_names") or [])
                            sh["character_names"] = list(dict.fromkeys([*existing, *names]))
        provider = settings.agent_provider or "ollama"
        if provider != "builtin":
            note = (
                " (Using built-in director — connect Ollama or an API key in Settings "
                "for smarter chat.)"
            )
            if note.strip() not in (plan.get("message") or ""):
                plan["message"] = ((plan.get("message") or "") + note).strip()
        plan["used_builtin"] = True
    else:
        plan["used_provider"] = settings.agent_provider

    reply = str(plan.get("message") or plan.get("assistant_message") or "Done.")
    if normalized and "reference" not in reply.lower() and "attach" not in reply.lower():
        label = ", ".join(a.name or a.kind for a in normalized[:4])
        reply = f"{reply}\n\nLocked in your refs: {label}."

    actions = list(plan.get("actions") or [])

    # Legacy LLM shot-only replies — stay in chat
    if not actions and plan.get("shots"):
        actions.append({"type": "replace_shots", "shots": plan["shots"]})

    # Drop casual navigates so chat doesn't yank the tab away every send
    allow_nav = {
        "filmnight",
        "director",
    }
    explicit_nav = any(
        k in text.lower()
        for k in (
            "open ",
            "go to ",
            "show ",
            "switch to ",
            "film night",
            "director",
        )
    )
    filtered: list[dict[str, Any]] = []
    for a in actions:
        if a.get("type") != "navigate":
            filtered.append(a)
            continue
        tab = str(a.get("tab") or "")
        if tab == "filmnight" and any(
            x.get("type") == "run_film_night" for x in actions
        ):
            filtered.append(a)
        elif explicit_nav and (tab in allow_nav or tab in {"shots", "agent", "settings", "characters", "profiles"}):
            filtered.append(a)
    actions = filtered

    project, ui_actions = apply_actions(project, actions)
    _inject_refs_into_shots(project, char_ids, scene_ids)
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
