from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import Project, Shot, Take
from .paths import MEDIA_DIR, ensure_dirs


def extract_last_frame(media_path: str | None, out_path: Path | None = None) -> str | None:
    """Pull the final frame from a video (or pass through an image) for i2v continuation."""
    if not media_path:
        return None
    src = Path(media_path)
    if not src.exists():
        return None

    # Prefer already-written companion last frame
    companion = src.with_name(src.stem + "_last.png")
    if companion.exists():
        return str(companion)
    if src.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return str(src)

    ensure_dirs()
    dest = out_path or src.with_name(src.stem + "_last.png")
    dest.parent.mkdir(parents=True, exist_ok=True)

    # imageio first
    try:
        import imageio.v2 as imageio
        from PIL import Image

        reader = imageio.get_reader(str(src))
        last = None
        for frame in reader:
            last = frame
        reader.close()
        if last is not None:
            Image.fromarray(last).convert("RGB").save(dest)
            return str(dest)
    except Exception:
        pass

    # ffmpeg fallback
    try:
        import subprocess

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-sseof",
                "-0.1",
                "-i",
                str(src),
                "-frames:v",
                "1",
                str(dest),
            ],
            check=True,
            capture_output=True,
        )
        if dest.exists():
            return str(dest)
    except Exception:
        pass
    return None


def previous_shot(project: Project, shot: Shot) -> Shot | None:
    ordered = sorted(project.shots, key=lambda s: s.index)
    for i, s in enumerate(ordered):
        if s.id == shot.id and i > 0:
            return ordered[i - 1]
    return None


def best_take_for_shot(project: Project, shot: Shot) -> Take | None:
    if shot.pinned_take_id:
        pinned = next((t for t in project.takes if t.id == shot.pinned_take_id), None)
        if pinned and pinned.media_path and not pinned.rejected:
            return pinned
    candidates = [
        t
        for t in project.takes
        if t.shot_id == shot.id and t.media_path and not t.rejected
    ]
    if not candidates:
        return None
    # Prefer finals over rehearsals, then higher continuity
    candidates.sort(
        key=lambda t: (
            0 if t.is_rehearsal else 1,
            float(t.continuity_score or 0),
            t.created_at,
        ),
        reverse=True,
    )
    return candidates[0]


def continuation_source(
    project: Project, shot: Shot, from_take_id: str | None = None
) -> dict[str, Any] | None:
    """Resolve the media + last-frame path to continue this shot from."""
    if from_take_id:
        take = next((t for t in project.takes if t.id == from_take_id), None)
    else:
        prev = previous_shot(project, shot)
        if not prev:
            return None
        take = best_take_for_shot(project, prev)
    if not take or not take.media_path:
        return None

    out_dir = MEDIA_DIR / project.id / "continue"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = extract_last_frame(
        take.media_path, out_dir / f"{take.id}_last.png"
    )
    if not frame:
        return None
    prev_shot = next((s for s in project.shots if s.id == take.shot_id), None)
    return {
        "from_take_id": take.id,
        "from_shot_id": take.shot_id,
        "from_shot_title": prev_shot.title if prev_shot else take.shot_id,
        "media_path": take.media_path,
        "image_path": frame,
        "thumb_path": take.thumb_path or frame,
    }


def ensure_last_frame_sidecar(media_path: str | None) -> str | None:
    """After a job finishes, guarantee a *_last.png next to the clip."""
    if not media_path:
        return None
    return extract_last_frame(media_path)
