from __future__ import annotations

"""Import existing user clips into Director as shot + take + timeline clip."""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .models import Project, Shot, Take, TimelineClip, new_id
from .paths import OUTPUTS_DIR, UPLOADS_DIR, ensure_dirs
from .storage import save_project


def _probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 3.0
    try:
        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return max(0.2, float((out.stdout or "").strip() or 3.0))
    except Exception:
        return 3.0


def _extract_thumb(path: Path, dest: Path) -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [ffmpeg, "-y", "-i", str(path), "-ss", "0.1", "-vframes", "1", str(dest)],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return str(dest) if dest.exists() else None
    except Exception:
        return None


def import_video_clip(
    project: Project,
    source_path: str,
    *,
    title: str | None = None,
    insert_at: int | None = None,
) -> dict[str, Any]:
    """
    Copy (or use) a video file into the project outputs and append a Director clip.

    Creates: Shot (imported) + Take (real media) + TimelineClip pinned.
    """
    ensure_dirs()
    src = Path(source_path).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError("Video file not found")

    suffix = src.suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif", ".m4v"}:
        raise ValueError(f"Unsupported video type: {suffix}")

    dest_dir = OUTPUTS_DIR / project.id / "imports"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{new_id('imp')}{suffix}"
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)

    duration = _probe_duration(dest)
    thumb = _extract_thumb(dest, dest_dir / f"{dest.stem}_thumb.jpg")

    index = len(project.shots)
    label = (title or src.stem or "Imported clip").strip()[:80] or "Imported clip"
    shot = Shot(
        index=index,
        title=label,
        action=f"Imported clip: {src.name}",
        duration_sec=round(duration, 2),
        status="ready",
        director_notes="Uploaded in Director",
    )
    take = Take(
        shot_id=shot.id,
        label=f"Import · {label}",
        media_path=str(dest),
        thumb_path=thumb,
        is_placeholder=False,
        score_note="Imported existing clip",
        prompt_used="",
    )
    shot.pinned_take_id = take.id

    clip = TimelineClip(
        shot_id=shot.id,
        take_id=take.id,
        start_sec=0.0,
        end_sec=duration,
        trim_in=0.0,
        trim_out=duration,
        pinned=True,
        order=len(project.timeline),
        caption="",
        filter_id=project.default_filter_id or "none",
    )

    project.shots.append(shot)
    project.takes.append(take)

    # Normalize existing timeline order, then insert
    clips = sorted(project.timeline, key=lambda c: c.order) if project.timeline else []
    if insert_at is None or insert_at < 0 or insert_at > len(clips):
        clips.append(clip)
    else:
        clips.insert(insert_at, clip)
    for i, c in enumerate(clips):
        c.order = i
    project.timeline = clips

    # Keep shot indices tidy
    for i, s in enumerate(sorted(project.shots, key=lambda x: x.index)):
        s.index = i

    saved = save_project(project)
    return {
        "ok": True,
        "project": saved,
        "shot_id": shot.id,
        "take_id": take.id,
        "clip_id": clip.id,
        "duration_sec": duration,
        "media_path": str(dest),
        "message": f"Added “{label}” ({round(duration, 1)}s) to the Director timeline.",
    }


def store_upload_bytes(filename: str, data: bytes) -> Path:
    ensure_dirs()
    suffix = Path(filename or "clip.mp4").suffix or ".mp4"
    dest = UPLOADS_DIR / f"{new_id('clip')}{suffix}"
    dest.write_bytes(data)
    return dest
