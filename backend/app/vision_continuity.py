from __future__ import annotations

"""Offline vision-ish continuity: compare take frames to locks / previous last frame.

Uses PIL histogram + simple palette distance — no cloud vision API. When OpenCV
or a future vision model is present, plug in here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .continue_video import extract_last_frame
from .models import Project, Shot, Take


def _load_rgb(path: str | None):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        from PIL import Image

        return Image.open(p).convert("RGB").resize((64, 64))
    except Exception:
        return None


def _hist(img) -> list[float]:
    # Flattened normalized RGB histogram
    h = img.histogram()
    total = sum(h) or 1
    return [c / total for c in h]


def _hist_distance(a: list[float], b: list[float]) -> float:
    # Bhattacharyya-ish similarity → distance 0..1
    import math

    n = min(len(a), len(b))
    s = sum(math.sqrt(max(a[i], 0) * max(b[i], 0)) for i in range(n))
    # s near 1 = similar
    return max(0.0, min(1.0, 1.0 - s))


def _mean_color(img) -> tuple[float, float, float]:
    pixels = list(img.getdata())
    n = len(pixels) or 1
    r = sum(p[0] for p in pixels) / n
    g = sum(p[1] for p in pixels) / n
    b = sum(p[2] for p in pixels) / n
    return r, g, b


def _color_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return min(1.0, (((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5) / 255.0)


def score_frame_pair(ref_path: str | None, cand_path: str | None) -> dict[str, Any]:
    ref = _load_rgb(ref_path)
    cand = _load_rgb(cand_path)
    if ref is None or cand is None:
        return {"ok": False, "vision_score": None, "detail": "missing frame"}
    hd = _hist_distance(_hist(ref), _hist(cand))
    cd = _color_distance(_mean_color(ref), _mean_color(cand))
    # Lower distance = better match
    dist = 0.65 * hd + 0.35 * cd
    score = round(max(0.0, min(1.0, 1.0 - dist)), 3)
    return {
        "ok": True,
        "vision_score": score,
        "hist_distance": round(hd, 3),
        "color_distance": round(cd, 3),
        "detail": "histogram+palette match",
    }


def reference_for_shot(project: Project, shot: Shot) -> str | None:
    """Prefer character reference still, else previous take last frame."""
    for cid in shot.character_ids or []:
        char = next((c for c in project.characters if c.id == cid), None)
        if char and char.reference_path:
            return char.reference_path
    # previous shot pinned take
    ordered = sorted(project.shots, key=lambda s: s.index)
    prev = None
    for s in ordered:
        if s.id == shot.id:
            break
        prev = s
    if prev and prev.pinned_take_id:
        take = next((t for t in project.takes if t.id == prev.pinned_take_id), None)
        if take and take.media_path:
            return extract_last_frame(take.media_path) or take.thumb_path
    return None


def vision_score_take(project: Project, shot: Shot, take: Take) -> dict[str, Any]:
    cand = take.thumb_path or extract_last_frame(take.media_path) or take.media_path
    ref = reference_for_shot(project, shot)
    result = score_frame_pair(ref, cand)
    flags: list[str] = []
    if not result.get("ok"):
        return {
            "vision_score": None,
            "vision_flags": ["No reference frame for vision check"],
            "ref_path": ref,
            "cand_path": cand,
        }
    score = float(result["vision_score"])
    if score < 0.45:
        flags.append(f"Vision drift vs lock/previous ({int(score * 100)}% similar)")
    elif score < 0.6:
        flags.append(f"Vision soft match ({int(score * 100)}%) — watch wardrobe/palette")
    return {
        "vision_score": score,
        "vision_flags": flags,
        "ref_path": ref,
        "cand_path": cand,
        **{k: result[k] for k in ("hist_distance", "color_distance", "detail") if k in result},
    }


def blend_scores(prompt_score: float, vision_score: float | None, vision_weight: float = 0.45) -> float:
    if vision_score is None:
        return prompt_score
    w = max(0.0, min(0.8, vision_weight))
    return round((1 - w) * prompt_score + w * vision_score, 3)
