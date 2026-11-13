from __future__ import annotations

"""Character identity lock — multi-region embedding + optional face detector.

Offline by default (PIL grid + center “face” crop). If insightface / face_recognition
is installed, uses a real face embedding and stores it in the same fingerprint slot.
"""

from pathlib import Path
from typing import Any

from .models import CharacterProfile, Project, Take

EMBED_DIM = 128
METHOD_HIST = "hist_v2"
METHOD_FACE = "face_v1"


def _load_rgb(path: str | None, size: tuple[int, int] | None = None):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        from PIL import Image

        img = Image.open(p).convert("RGB")
        if size:
            img = img.resize(size)
        return img
    except Exception:
        return None


def _hist_block(img, bins: int = 16) -> list[float]:
    """Per-channel coarse histogram normalized."""
    from PIL import Image

    small = img.resize((64, 64)) if img.size[0] > 64 else img
    # quantize via resize + getdata average in tiles is heavier; use histogram
    h = small.histogram()
    # 256*3 → collapse to bins*3
    out: list[float] = []
    for ch in range(3):
        base = ch * 256
        step = 256 // bins
        for i in range(bins):
            chunk = h[base + i * step : base + (i + 1) * step]
            out.append(float(sum(chunk)))
    total = sum(out) or 1.0
    return [v / total for v in out]


def _edge_energy(img) -> list[float]:
    """Simple luma edge magnitude in 4x4 grid — structure, not just color."""
    from PIL import ImageFilter, ImageOps

    g = ImageOps.grayscale(img.resize((32, 32)))
    e = g.filter(ImageFilter.FIND_EDGES)
    pix = list(e.getdata())
    cells: list[float] = []
    for gy in range(4):
        for gx in range(4):
            vals = []
            for y in range(gy * 8, (gy + 1) * 8):
                for x in range(gx * 8, (gx + 1) * 8):
                    vals.append(pix[y * 32 + x])
            cells.append(sum(vals) / max(1, len(vals)) / 255.0)
    return cells


def _face_crop(img):
    """Upper-center crop — where faces usually sit in character refs."""
    w, h = img.size
    cw, ch = int(w * 0.55), int(h * 0.55)
    left = max(0, (w - cw) // 2)
    top = max(0, int(h * 0.08))
    return img.crop((left, top, left + cw, min(h, top + ch)))


def _try_face_embedding(path: str) -> list[float] | None:
    """Optional heavy path — only if a face lib is installed."""
    # insightface
    try:
        from insightface.app import FaceAnalysis  # type: ignore

        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(320, 320))
        import cv2  # type: ignore
        import numpy as np

        bgr = cv2.imread(path)
        if bgr is None:
            return None
        faces = app.get(bgr)
        if not faces:
            return None
        emb = faces[0].normed_embedding
        vec = [float(x) for x in emb.tolist()]
        # pad / trim to EMBED_DIM
        if len(vec) >= EMBED_DIM:
            return vec[:EMBED_DIM]
        return vec + [0.0] * (EMBED_DIM - len(vec))
    except Exception:
        pass

    # face_recognition
    try:
        import face_recognition  # type: ignore

        image = face_recognition.load_image_file(path)
        encs = face_recognition.face_encodings(image)
        if not encs:
            return None
        vec = [float(x) for x in encs[0]]
        if len(vec) >= EMBED_DIM:
            return vec[:EMBED_DIM]
        return vec + [0.0] * (EMBED_DIM - len(vec))
    except Exception:
        pass

    return None


def fingerprint_image(path: str | None) -> list[float] | None:
    """Return embedding vector (length EMBED_DIM). Prefer real face embed when available."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None

    face_emb = _try_face_embedding(str(p))
    if face_emb:
        return [round(v, 6) for v in face_emb]

    img = _load_rgb(str(p))
    if img is None:
        return None

    face = _face_crop(img)
    parts: list[float] = []
    parts.extend(_hist_block(face, bins=8))  # 24
    parts.extend(_hist_block(img.resize((96, 96)), bins=8))  # 24
    # 3x3 tile color means
    tw, th = img.size[0] // 3, img.size[1] // 3
    for ty in range(3):
        for tx in range(3):
            tile = img.crop((tx * tw, ty * th, (tx + 1) * tw, (ty + 1) * th)).resize((16, 16))
            pixels = list(tile.getdata())
            n = len(pixels) or 1
            r = sum(p[0] for p in pixels) / n / 255.0
            g = sum(p[1] for p in pixels) / n / 255.0
            b = sum(p[2] for p in pixels) / n / 255.0
            parts.extend([r, g, b])  # +27 → 75
    parts.extend(_edge_energy(face))  # +16 → 91
    parts.extend(_edge_energy(img))  # +16 → 107

    # pad to EMBED_DIM
    if len(parts) < EMBED_DIM:
        parts.extend([0.0] * (EMBED_DIM - len(parts)))
    else:
        parts = parts[:EMBED_DIM]
    # L2 normalize
    norm = sum(v * v for v in parts) ** 0.5 or 1.0
    return [round(v / norm, 6) for v in parts]


def fingerprint_method(path: str | None) -> str:
    if not path or not Path(path).exists():
        return METHOD_HIST
    if _try_face_embedding(path):
        return METHOD_FACE
    return METHOD_HIST


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
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
    method = fingerprint_method(character.reference_path)
    # stash method on tags lightly so UI can show it
    tags = [t for t in (character.tags or []) if not t.startswith("idlock:")]
    if fp:
        tags.append(f"idlock:{method}")
    character.tags = tags

    if fp and not (character.character_lock or "").strip():
        character.character_lock = (
            f"same person as reference still of {character.name}, "
            "identical face geometry, eyes, nose, mouth, hairline, skin tone, and wardrobe — "
            "do not age-shift, gender-swap, or reinvent the face"
        )
    elif fp:
        lock = character.character_lock or ""
        if "same person" not in lock.lower() and "identical" not in lock.lower():
            character.character_lock = (
                f"{lock.rstrip('. ')}. Same person as the locked reference still — "
                "preserve face geometry, hair, and signature features exactly."
            ).strip()
    return character


def identity_score_take(project: Project, take: Take) -> dict[str, Any]:
    """Compare take thumb/frame fingerprint to cast reference fingerprints."""
    frame = take.thumb_path or take.media_path
    # for video paths without thumb, fingerprint may fail — ok
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
        method = next((t.split(":", 1)[1] for t in (c.tags or []) if t.startswith("idlock:")), "hist")
        label = "face" if method.startswith("face") else "look"
        if sim < 0.50:
            flags.append(f"Identity drift vs {c.name} ({int(sim * 100)}% {label} match)")
        elif sim < 0.68:
            flags.append(f"Soft identity match for {c.name} ({int(sim * 100)}% {label})")

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
            bits.append(f"{c.name}: match locked reference still exactly, same face")
    if not bits:
        return ""
    return "IDENTITY LOCK (face must match reference) — " + " | ".join(bits)


def primary_identity_ref(project: Project, character_ids: list[str] | None) -> str | None:
    chars = (
        [c for c in project.characters if c.id in (character_ids or [])]
        if character_ids
        else project.characters
    )
    for c in chars:
        if c.reference_path and Path(c.reference_path).exists():
            return c.reference_path
    return None
