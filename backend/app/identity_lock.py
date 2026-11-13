from __future__ import annotations

"""Character identity lock from a reference still — offline palette fingerprint.

When a heavier face/IP-Adapter model is present later, plug it in here.
Until then: dominant-color + histogram signature + prompt lock injection.
"""

from pathlib import Path
from typing import Any

from .models import CharacterProfile, Project, Take


def fingerprint_image(path: str | None) -> list[float] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        from PIL import Image

        img = Image.open(p).convert("RGB").resize((48, 48))
        hist = img.histogram()  # 768 bins
        # downsample to 64 floats
        step = max(1, len(hist) // 64)
        sig = []
        for i in range(0, len(hist), step):
            chunk = hist[i : i + step]
            sig.append(sum(chunk) / max(1, len(chunk)))
            if len(sig) >= 64:
                break
        total = sum(sig) or 1.0
        return [round(v / total, 6) for v in sig]
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def refresh_character_identity(character: CharacterProfile) -> CharacterProfile:
    """Compute / refresh fingerprint from reference_path."""
    fp = fingerprint_image(character.reference_path)
    character.identity_fingerprint = fp
    if fp and not (character.character_lock or "").strip():
        # nudge empty lock so prompts still carry identity intent
        character.character_lock = (
            f"same person as reference still of {character.name}, "
            "consistent face structure, hair, and wardrobe across every shot"
        )
    elif fp:
        # ensure lock mentions reference identity
        lock = character.character_lock or ""
        if "same person" not in lock.lower() and "identical" not in lock.lower():
            character.character_lock = (
                f"{lock.rstrip('. ')}. Same person as the locked reference still — "
                "do not change face, hair, or signature features."
            ).strip()
    return character


def identity_score_take(project: Project, take: Take) -> dict[str, Any]:
    """Compare take thumb/frame fingerprint to cast reference fingerprints."""
    frame = take.thumb_path or take.media_path
    take_fp = fingerprint_image(frame)
    if take_fp is None:
        return {"identity_score": None, "identity_flags": [], "detail": "no take frame"}

    shot = next((s for s in project.shots if s.id == take.shot_id), None)
    chars = []
    if shot and shot.character_ids:
        chars = [c for c in project.characters if c.id in shot.character_ids]
    if not chars:
        chars = [c for c in project.characters if c.identity_fingerprint or c.reference_path][:1]
    if not chars:
        return {"identity_score": None, "identity_flags": [], "detail": "no cast refs"}

    scores = []
    flags: list[str] = []
    for c in chars:
        fp = c.identity_fingerprint or fingerprint_image(c.reference_path)
        if not fp:
            flags.append(f"No identity fingerprint for {c.name} — upload a lock still.")
            continue
        sim = _cosine(take_fp, fp)
        scores.append(sim)
        if sim < 0.55:
            flags.append(f"Identity drift vs {c.name} ({int(sim * 100)}% match)")
        elif sim < 0.72:
            flags.append(f"Soft identity match for {c.name} ({int(sim * 100)}%)")

    if not scores:
        return {"identity_score": None, "identity_flags": flags, "detail": "no comparable refs"}

    score = sum(scores) / len(scores)
    return {
        "identity_score": round(score, 3),
        "identity_flags": flags[:8],
        "detail": f"identity {int(score * 100)}%",
    }


def identity_prompt_suffix(project: Project, character_ids: list[str] | None) -> str:
    bits = []
    chars = (
        [c for c in project.characters if c.id in (character_ids or [])]
        if character_ids
        else project.characters[:2]
    )
    for c in chars:
        if c.character_lock:
            bits.append(f"{c.name}: {c.character_lock}")
        elif c.reference_path:
            bits.append(f"{c.name}: match locked reference still exactly")
    if not bits:
        return ""
    return "IDENTITY LOCK — " + " | ".join(bits)
