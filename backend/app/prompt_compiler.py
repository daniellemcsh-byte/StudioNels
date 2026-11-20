"""Model-aware shot prompts built from the film's memory.

Every model reads prompts differently:
- LTX-2 / LTX-2.3: one flowing present-tense paragraph, action first, then
  appearance, setting, camera, light; it also generates audio, so describe
  sound and quote dialogue.
- Wan / SkyReels: subject → scene → motion → camera → style, plus Wan's
  standard negative prompt.
- Flux / Qwen-Image: natural language, subject first; negative prompts are
  ignored, so exclusions go nowhere.
- SD 1.5 / SDXL: comma tags; CLIP reads ~77 tokens, so subject and identity
  go first and the list is trimmed to fit.
- Image → Video: the picture is already given, so describe motion, not looks.

compile_shot() turns a Shot + the project's memory into the prompt, negative
prompt, token count and warnings for one model. Pure functions, no I/O.
"""

from __future__ import annotations

import re
from typing import Any

from .models import CharacterProfile, Project, PropProfile, SceneProfile, Shot

STYLE_HINTS = {
    "cinematic": "cinematic lighting, film grain, naturalistic color",
    "animation": "stylized 3D animation",
    "clay": "claymation stop-motion, plasticine textures",
    "cartoon": "2D cartoon, bold outlines, flat colors",
    "anime": "anime style, cel shading",
    "pixel": "pixel art, retro game aesthetic",
    "neon_noir": "neon noir, wet reflections, deep shadows, magenta and cyan light",
}

CAMERA_PHRASE = {
    "wide": "wide establishing shot",
    "medium": "medium shot",
    "close-up": "close-up",
    "extreme close-up": "extreme close-up",
    "tracking": "tracking shot following the subject",
    "pov": "point-of-view shot",
    "overhead": "overhead top-down shot",
    "aerial": "aerial drone shot",
    "low-angle": "low-angle shot",
    "insert": "extreme close-up insert shot",
    "handheld": "handheld shot",
}

WAN_NEGATIVE = (
    "bright tones, overexposed, static, blurred details, subtitles, text, watermark, "
    "worst quality, low quality, JPEG artifacts, ugly, incomplete, extra fingers, poorly drawn hands, "
    "poorly drawn faces, deformed, disfigured, misshapen limbs, fused fingers, still picture, "
    "messy background, three legs, many people in the background, walking backwards"
)
SD_NEGATIVE = (
    "lowres, bad anatomy, bad hands, missing fingers, extra digit, fewer digits, cropped, "
    "worst quality, low quality, jpeg artifacts, signature, watermark, text, blurry, deformed face"
)
VIDEO_NEGATIVE = (
    "blurry, low quality, distorted face, flicker, jitter, morphing, extra limbs, text, watermark"
)

# family -> how prompts should be written for it
PROFILES: dict[str, dict[str, Any]] = {
    "ltx2": {
        "label": "LTX-2 / LTX-2.3",
        "format": "prose",
        "kind": "video",
        "budget": 220,  # words; LTX recommends detailed paragraphs under ~200 words
        "negative": True,
        "audio": True,
        "tips": [
            "One flowing paragraph in present tense, starting with the main action.",
            "Describe appearance, setting, camera and lighting literally, in time order.",
            "LTX-2 also makes sound: ambience and quoted dialogue are written in.",
        ],
    },
    "ltx": {
        "label": "LTX-Video 0.9",
        "format": "prose",
        "kind": "video",
        "budget": 200,
        "negative": True,
        "audio": False,
        "tips": [
            "Detailed chronological paragraph, action first.",
            "Literal descriptions of movement, appearance, camera and light.",
        ],
    },
    "wan": {
        "label": "Wan 2.x / SkyReels",
        "format": "prose",
        "kind": "video",
        "budget": 120,
        "negative": True,
        "audio": False,
        "tips": [
            "Subject → scene → motion → camera → style, in that order.",
            "Uses Wan's standard negative prompt to stop static, over-bright frames.",
        ],
    },
    "video": {
        "label": "Video (Hunyuan / CogVideoX / other)",
        "format": "prose",
        "kind": "video",
        "budget": 160,
        "negative": True,
        "audio": False,
        "tips": ["Detailed descriptive paragraph: subject, action, setting, camera, light."],
    },
    "flux": {
        "label": "Flux / Qwen-Image",
        "format": "prose",
        "kind": "image",
        "budget": 180,
        "negative": False,
        "audio": False,
        "tips": [
            "Natural sentences, subject first — Flux reads language, not tags.",
            "Negative prompts are ignored by Flux, so none is sent.",
        ],
    },
    "sd3": {
        "label": "Stable Diffusion 3.5",
        "format": "prose",
        "kind": "image",
        "budget": 150,
        "negative": True,
        "audio": False,
        "tips": ["Natural-language description with a negative prompt."],
    },
    "sdxl": {
        "label": "SDXL / Playground / Lightning",
        "format": "tags",
        "kind": "image",
        "token_limit": 75,
        "negative": True,
        "audio": False,
        "tips": [
            "Comma-separated tags; CLIP only reads ~77 tokens.",
            "Subject and identity go first, extras are trimmed to fit.",
        ],
    },
    "sd15": {
        "label": "Stable Diffusion 1.5",
        "format": "tags",
        "kind": "image",
        "token_limit": 75,
        "negative": True,
        "audio": False,
        "quality": "masterpiece, best quality, highly detailed",
        "tips": [
            "Tags with quality words; CLIP only reads ~77 tokens.",
            "Subject and identity go first, extras are trimmed to fit.",
        ],
    },
    "image": {
        "label": "Image (natural language)",
        "format": "prose",
        "kind": "image",
        "budget": 150,
        "negative": True,
        "audio": False,
        "tips": ["Descriptive sentences: subject, setting, light, style."],
    },
    "audio": {
        "label": "Audio (MusicGen / Stable Audio / AudioLDM)",
        "format": "audio",
        "kind": "audio",
        "budget": 60,
        "negative": False,
        "audio": True,
        "tips": ["Genre, instruments, tempo and mood — no visuals."],
    },
}


def model_family(model: dict[str, Any] | None) -> str:
    """Map a catalog model to a prompt family."""
    if not model:
        return "ltx2"
    key = f"{model.get('id') or ''} {model.get('pipeline') or ''} {model.get('hf_id') or ''}".lower()
    kind = str(model.get("kind") or "")
    if kind == "audio" or any(k in key for k in ("musicgen", "audioldm", "stable-audio", "stableaudio", "audiogen")):
        return "audio"
    if "ltx2" in key or "ltx-2" in key:
        return "ltx2"
    if "ltx" in key:
        return "ltx"
    if "wan" in key or "skyreels" in key:
        return "wan"
    if "flux" in key or "qwen-image" in key or "qwen_image" in key:
        return "flux"
    if "sd3" in key or "stable-diffusion-3" in key or "stablediffusion3" in key:
        return "sd3"
    if "sd15" in key or "stable-diffusion-v1" in key or "sd-1" in key:
        return "sd15"
    if any(k in key for k in ("sdxl", "playground", "lightning", "xl-base", "stablediffusionxl")):
        return "sdxl"
    if kind == "video" or any(k in key for k in ("hunyuan", "cogvideo", "mochi", "video")):
        return "video"
    return "image"


def count_tokens(text: str) -> int:
    """Rough CLIP/T5-style token estimate (words + punctuation)."""
    return len(re.findall(r"[A-Za-z0-9']+|[^\sA-Za-z0-9]", text or ""))


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text.strip(" ,;")


def _sentence(text: str) -> str:
    text = _clean(text)
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?\"'" else text + "."


def _dedupe_against(style: str, already: str) -> str:
    """Drop style phrases whose words are all already said (palette/lighting)."""
    have = set(re.findall(r"[a-z]+", already.lower()))
    keep = []
    for part in (p.strip() for p in style.split(",")):
        words = set(re.findall(r"[a-z]+", part.lower())) - {"and", "light", "lighting"}
        if part and not (words and words <= have):
            keep.append(part)
    return ", ".join(keep)


def _mentions(name: str, *texts: str) -> bool:
    if not name:
        return False
    pat = re.compile(rf"\b{re.escape(name)}\b", re.I)
    return any(pat.search(t or "") for t in texts)


def shot_cast(project: Project, shot: Shot) -> list[CharacterProfile]:
    """Tagged characters, plus any whose name appears in the shot text."""
    texts = (shot.action, shot.title, shot.storyboard_note, shot.dialogue, shot.prompt)
    out = [c for c in project.characters if c.id in (shot.character_ids or [])]
    for c in project.characters:
        if c not in out and _mentions(c.name, *texts):
            out.append(c)
    return out


def shot_props(project: Project, shot: Shot) -> list[PropProfile]:
    texts = (shot.action, shot.title, shot.storyboard_note)
    out = [p for p in project.props if p.id in (shot.prop_ids or [])]
    for p in project.props:
        if p not in out and _mentions(p.name, *texts):
            out.append(p)
    return out


def shot_scene(project: Project, shot: Shot) -> SceneProfile | None:
    return next((s for s in project.scenes if s.id == shot.scene_id), None)


def previous_shot(project: Project, shot: Shot) -> Shot | None:
    ordered = sorted(project.shots, key=lambda s: s.index)
    for i, s in enumerate(ordered):
        if s.id == shot.id:
            return ordered[i - 1] if i > 0 else None
    return None


def _character_phrase(c: CharacterProfile, short: bool = False) -> str:
    look = _clean(c.character_lock or c.look)
    # character_lock often starts with "same person every shot: Name, ..." — drop that preamble
    look = re.sub(r"^same person every shot:\s*", "", look, flags=re.I)
    look = re.sub(rf"^{re.escape(c.name)}\s*,?\s*", "", look, flags=re.I)
    parts = [c.name]
    if not short:
        bits = [b for b in (_clean(c.age), look) if b]
        if bits:
            parts.append(", ".join(bits))
        if c.wardrobe:
            parts.append(f"wearing {_clean(c.wardrobe)}")
        if len(parts) == 1:
            return f"{c.name} is in the shot"
    elif look:
        parts.append(look.split(",")[0])
    return ", ".join(parts)


def _shot_context(project: Project, shot: Shot) -> dict[str, Any]:
    mem = project.memory
    scene = shot_scene(project, shot)
    prev = previous_shot(project, shot)
    cast = shot_cast(project, shot)
    props = shot_props(project, shot)
    action = _clean(shot.action or shot.storyboard_note or shot.title)
    camera_key = (shot.camera or "medium").strip().lower()
    carry = ""
    if prev and prev.state_after:
        prev_cast = {c.id for c in shot_cast(project, prev)}
        same_people = bool(prev_cast & {c.id for c in cast}) or not cast
        same_place = (prev.scene_id or None) == (shot.scene_id or None)
        if same_people or same_place:
            carry = _clean(prev.state_after)
    return {
        "mem": mem,
        "scene": scene,
        "cast": cast,
        "props": props,
        "action": action,
        "camera": CAMERA_PHRASE.get(camera_key, f"{camera_key} shot" if camera_key else "medium shot"),
        "lens": _clean(shot.lens),
        "movement": _clean(shot.movement),
        "time": _clean(shot.time_of_day or (scene.time_of_day if scene else "")),
        "weather": _clean(scene.weather if scene else ""),
        "lighting": _clean(scene.lighting if scene else ""),
        "location": _clean(" ".join(x for x in ((scene.location or scene.name) if scene else "", scene.visual_notes if scene else "") if x)),
        "mood": _clean(shot.mood or (scene.mood if scene else "") or mem.tone),
        "style": _dedupe_against(
            STYLE_HINTS.get(project.visual_style or "", (project.visual_style or "").replace("_", " ")),
            " ".join((mem.palette, scene.lighting if scene else "")),
        ),
        "palette": _clean(mem.palette),
        "camera_language": _clean(mem.camera_language),
        "world": _clean(mem.world),
        "era": _clean(mem.era),
        "motifs": _clean(mem.motifs),
        "sound": _clean(shot.sound or mem.sound_world),
        "dialogue": _clean(shot.dialogue),
        "carry": carry,
        "avoid": _clean(mem.avoid),
        # Pinned facts that concern someone/something in this shot (not all of them)
        "facts": [
            _clean(f)
            for f in (mem.facts or [])
            if any(
                _mentions(n, f)
                for n in [c.name for c in cast] + [p.name for p in props] + ([scene.name] if scene else [])
            )
        ],
    }


def _prose_video(ctx: dict[str, Any], family: str, motion_only: bool) -> str:
    """LTX / Wan / generic video paragraph."""
    cast = ctx["cast"]
    parts: list[str] = []
    cam = ctx["camera"] + (f" with a {ctx['lens']} lens" if ctx["lens"] else "")
    move = f", {ctx['movement']}" if ctx["movement"] else ""
    if family == "wan":
        # Wan: subject -> scene -> motion -> camera -> style
        subject = "; ".join(_character_phrase(c, short=motion_only) for c in cast)
        parts.append(_sentence(f"{subject}: {ctx['action']}" if subject else ctx["action"]))
        place = ", ".join(x for x in (ctx["location"], ctx["time"], ctx["weather"]) if x)
        if place:
            parts.append(_sentence(f"Setting: {place}"))
        if ctx["carry"]:
            parts.append(_sentence(f"Continuity: {ctx['carry']}"))
        parts.append(_sentence(f"Camera: {cam}{move}"))
        look = ", ".join(x for x in (ctx["lighting"], ctx["palette"], ctx["style"], ctx["mood"]) if x)
        if look:
            parts.append(_sentence(look))
        return " ".join(p for p in parts if p)

    # LTX family + generic video: action first, chronological, literal.
    if motion_only:
        parts.append(_sentence(f"The scene comes to life from the start frame: {ctx['action']}"))
    else:
        parts.append(_sentence(ctx["action"]))
    for c in cast:
        if motion_only:
            parts.append(_sentence(f"{c.name} keeps the same face, hair and clothes as in the start frame"))
        else:
            parts.append(_sentence(_character_phrase(c)))
    for p in ctx["props"]:
        desc = f"{p.name}, {p.description}" if p.description else p.name
        parts.append(_sentence(f"The {desc} is clearly visible" if not motion_only else f"The {p.name} stays as it was"))
    if ctx["carry"]:
        parts.append(_sentence(f"Continuing from the previous shot: {ctx['carry']}"))
    for fact in ctx["facts"]:
        parts.append(_sentence(fact))
    if not motion_only:
        place = ", ".join(x for x in (ctx["location"], ctx["time"], ctx["weather"]) if x)
        if place:
            parts.append(_sentence(f"The setting is {place}"))
        if ctx["world"] or ctx["era"]:
            parts.append(_sentence(", ".join(x for x in (ctx["world"], ctx["era"]) if x)))
    parts.append(_sentence(f"The camera is a {cam}{move}" if not ctx["camera_language"] else f"The camera is a {cam}{move}, {ctx['camera_language']}"))
    look = ", ".join(x for x in (ctx["lighting"], ctx["palette"], ctx["style"]) if x)
    if look:
        parts.append(_sentence(f"Lighting and look: {look}"))
    if ctx["mood"]:
        parts.append(_sentence(f"The mood is {ctx['mood']}"))
    if ctx["motifs"] and not motion_only:
        parts.append(_sentence(f"Recurring motif: {ctx['motifs']}"))
    if PROFILES[family]["audio"]:
        if ctx["dialogue"]:
            speaker = cast[0].name if cast else "A voice"
            parts.append(f'{speaker} says: "{ctx["dialogue"]}"')
        if ctx["sound"]:
            parts.append(_sentence(f"Audio: {ctx['sound']}"))
    return " ".join(p for p in parts if p)


def _prose_image(ctx: dict[str, Any]) -> str:
    cast = ctx["cast"]
    parts = [_sentence(f"{ctx['camera']}: {ctx['action']}" if ctx["action"] else ctx["camera"])]
    for c in cast:
        parts.append(_sentence(_character_phrase(c)))
    for p in ctx["props"]:
        parts.append(_sentence(f"The {p.name}{', ' + p.description if p.description else ''} is visible"))
    place = ", ".join(x for x in (ctx["location"], ctx["time"], ctx["weather"]) if x)
    if place:
        parts.append(_sentence(f"Setting: {place}"))
    look = ", ".join(x for x in (ctx["lighting"], ctx["palette"], ctx["style"], ctx["mood"]) if x)
    if look:
        parts.append(_sentence(look))
    if ctx["carry"]:
        parts.append(_sentence(ctx["carry"]))
    for fact in ctx["facts"]:
        parts.append(_sentence(fact))
    return " ".join(p for p in parts if p)


def _tags(ctx: dict[str, Any], family: str) -> tuple[str, list[str]]:
    """Comma tags in priority order, trimmed to the CLIP budget."""
    limit = int(PROFILES[family].get("token_limit") or 75)
    short_action = " ".join(ctx["action"].split()[:14])
    groups: list[tuple[int, str]] = []  # (priority, tag) — lower = keep first
    groups.append((0, ctx["camera"]))
    for c in ctx["cast"]:
        groups.append((0, _character_phrase(c, short=True)))
    groups.append((1, short_action))
    if PROFILES[family].get("quality"):
        groups.append((1, PROFILES[family]["quality"]))
    for c in ctx["cast"]:
        if c.wardrobe:
            groups.append((2, f"{c.name} wearing {_clean(c.wardrobe)}"))
    for p in ctx["props"]:
        groups.append((2, p.name))
    for x in (ctx["location"], ctx["time"], ctx["weather"]):
        if x:
            groups.append((3, x))
    for x in (ctx["lighting"], ctx["style"], ctx["palette"], ctx["mood"]):
        if x:
            groups.append((4, x))
    if ctx["carry"]:
        groups.append((5, ctx["carry"]))
    for fact in ctx["facts"]:
        groups.append((6, fact))
    tags = [t for _, t in groups if t]
    dropped: list[str] = []
    ordered = sorted(enumerate(groups), key=lambda item: (item[1][0], item[0]))
    kept = list(ordered)
    while kept and count_tokens(", ".join(t for _, (_, t) in sorted(kept))) > limit:
        idx = max(range(len(kept)), key=lambda i: (kept[i][1][0], kept[i][0]))
        dropped.append(kept[idx][1][1])
        kept.pop(idx)
    tags = [t for _, (_, t) in sorted(kept)]
    return ", ".join(tags), dropped


def _audio(ctx: dict[str, Any]) -> str:
    bits = [x for x in (ctx["sound"], ctx["mood"]) if x]
    if not bits:
        bits = ["cinematic underscore"]
    return ", ".join(bits) + ", high quality, clear mix"


def compile_shot(
    project: Project,
    shot: Shot,
    model: dict[str, Any] | None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Prompt + negative tuned for one model, with budget and warnings."""
    family = model_family(model)
    profile = PROFILES[family]
    ctx = _shot_context(project, shot)
    motion_only = mode in ("i2v", "ref2v") and profile["kind"] == "video"
    warnings: list[str] = []
    dropped: list[str] = []

    if shot.prompt_locked and (shot.prompt or "").strip():
        prompt = shot.prompt.strip()
        source = "locked"
    elif profile["format"] == "tags":
        prompt, dropped = _tags(ctx, family)
        source = "compiled"
    elif profile["format"] == "audio":
        prompt = _audio(ctx)
        source = "compiled"
    elif profile["kind"] == "video":
        prompt = _prose_video(ctx, family, motion_only)
        source = "compiled"
    else:
        prompt = _prose_image(ctx)
        source = "compiled"

    negative = ""
    if profile["negative"]:
        base = {"wan": WAN_NEGATIVE, "sdxl": SD_NEGATIVE, "sd15": SD_NEGATIVE}.get(
            family, VIDEO_NEGATIVE if profile["kind"] == "video" else SD_NEGATIVE
        )
        extra = ", ".join(x for x in (_clean(shot.negative_prompt), ctx["avoid"]) if x)
        negative = f"{extra}, {base}" if extra else base
    elif (ctx["avoid"] or shot.negative_prompt) and profile["kind"] != "audio":
        warnings.append(f"{profile['label']} ignores negative prompts — “avoid” notes are not sent.")

    tokens = count_tokens(prompt)
    words = len(prompt.split())
    if profile.get("token_limit"):
        budget = int(profile["token_limit"])
        over = tokens > budget
        if over:
            warnings.append(f"Prompt is {tokens} tokens; {profile['label']} reads only ~{budget}.")
        if dropped:
            warnings.append("Trimmed to fit: " + "; ".join(dropped[:4]))
    else:
        budget = int(profile.get("budget") or 200)
        over = words > budget
        if over:
            warnings.append(f"Prompt is {words} words; {profile['label']} works best under ~{budget}.")
    if not ctx["action"]:
        warnings.append("This shot has no action — describe what happens.")
    for c in ctx["cast"]:
        if not (c.character_lock or c.look):
            warnings.append(f"{c.name} has no look yet — add one in Film memory so they stay consistent.")
    if profile["kind"] == "image" and (shot.movement or "").strip():
        warnings.append("Image models ignore camera movement.")

    return {
        "shot_id": shot.id,
        "family": family,
        "label": profile["label"],
        "format": profile["format"],
        "prompt": prompt,
        "negative": negative,
        "source": source,
        "tokens": tokens,
        "words": words,
        "budget": budget,
        "budget_unit": "tokens" if profile.get("token_limit") else "words",
        "over_budget": over,
        "warnings": warnings,
        "tips": profile["tips"],
        "motion_only": motion_only,
    }
