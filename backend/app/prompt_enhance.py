"""Expand a short generation prompt into a richer cinematic description."""

from __future__ import annotations

import re
from typing import Any

from .llm_providers import chat_json
from .storage import load_settings

_SYSTEM = """You enhance prompts for local AI image/video generation (Diffusers).
Return ONLY JSON with keys:
  prompt (string) — expanded positive prompt, one paragraph, concrete visual details
  negative_prompt (string) — useful negatives for the mode
  notes (string) — one short tip for the user

Rules:
- Keep the user's intent and subject; do not invent a different story.
- Add camera, lighting, motion, texture, and atmosphere when helpful.
- No markdown, no quotes wrapping the whole prompt.
- For video modes, include gentle motion cues (camera move, subject motion).
- For image modes, emphasize composition and still detail.
- Stay under ~80 words for prompt unless the user already wrote more.
"""


def _builtin_enhance(prompt: str, mode: str, style: str | None) -> dict[str, Any]:
    base = re.sub(r"\s+", " ", (prompt or "").strip())
    if not base:
        return {
            "prompt": "",
            "negative_prompt": "",
            "notes": "Type a short idea first, then Enhance.",
            "source": "builtin",
        }

    style_bit = f", {style} look" if style else ""
    if mode in ("t2v", "i2v", "ref2v"):
        enriched = (
            f"{base}{style_bit}, cinematic lighting, natural motion, "
            f"subtle camera move, coherent frames, film grain, high detail"
        )
        negative = (
            "cut, hard edit, flash, jump cut, flicker, morphing face, "
            "extra limbs, watermark, text overlay, lowres, blurry"
        )
        tip = "Draft video tip: keep one clear action; Enhance adds motion/camera cues."
    elif mode == "t2a":
        enriched = (
            f"{base}{style_bit}, rich stereo bed, clear mix, "
            f"no clipping, evolving texture, studio quality"
        )
        negative = "harsh noise, clipping, muffled, telephone quality, silence gaps"
        tip = "Audio tip: name instruments / mood; Enhance fills mix language."
    else:
        enriched = (
            f"{base}{style_bit}, sharp focus, detailed texture, "
            f"balanced composition, cinematic lighting, high detail"
        )
        negative = (
            "blurry, lowres, deformed hands, extra fingers, watermark, "
            "text, logo, oversaturated, ugly"
        )
        tip = "Still tip: subject + place + light; Enhance fills camera/look words."

    return {
        "prompt": enriched,
        "negative_prompt": negative,
        "notes": tip + " (offline enhance — connect Ollama/Agent for smarter rewrites)",
        "source": "builtin",
    }


async def enhance_prompt(
    prompt: str,
    *,
    mode: str = "t2v",
    negative_prompt: str = "",
    style: str | None = None,
    force_builtin: bool = False,
) -> dict[str, Any]:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Prompt is empty")

    settings = load_settings()
    fallback = _builtin_enhance(prompt, mode, style)

    if force_builtin or (settings.agent_provider or "").lower() == "builtin":
        if negative_prompt and not fallback.get("negative_prompt"):
            fallback["negative_prompt"] = negative_prompt
        elif negative_prompt:
            # Keep user negatives merged lightly
            fallback["negative_prompt"] = f"{negative_prompt}, {fallback['negative_prompt']}"
        return fallback

    user = (
        f"Mode: {mode}\n"
        f"Style hint: {style or 'none'}\n"
        f"Current prompt:\n{prompt}\n"
        f"Current negative (optional):\n{negative_prompt or '(none)'}\n"
    )
    data = await chat_json(settings, _SYSTEM, user, max_tokens=700)
    if not data or not isinstance(data, dict):
        return fallback

    out_prompt = str(data.get("prompt") or "").strip() or prompt
    out_neg = str(data.get("negative_prompt") or "").strip()
    if not out_neg:
        out_neg = negative_prompt or fallback["negative_prompt"]
    notes = str(data.get("notes") or "").strip() or "Enhanced with your Agent LLM."
    return {
        "prompt": out_prompt,
        "negative_prompt": out_neg,
        "notes": notes,
        "source": settings.agent_provider or "agent",
    }
