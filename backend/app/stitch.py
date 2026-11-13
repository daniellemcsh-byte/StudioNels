from __future__ import annotations

"""Local full-cut stitch: playlist preview + optional ffmpeg concat."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .captions import _clip_duration
from .models import Project, utc_now
from .paths import OUTPUTS_DIR, ensure_dirs


def build_playlist(project: Project) -> dict[str, Any]:
    """Ordered media playlist for in-app preview player (no re-encode)."""
    clips = sorted(project.timeline, key=lambda c: c.order) if project.timeline else []
    if not clips:
        for shot in sorted(project.shots, key=lambda s: s.index):
            if shot.pinned_take_id:
                from .models import TimelineClip

                clips.append(
                    TimelineClip(
                        shot_id=shot.id,
                        take_id=shot.pinned_take_id,
                        end_sec=shot.duration_sec,
                        trim_out=shot.duration_sec,
                        order=len(clips),
                        pinned=True,
                    )
                )

    entries = []
    cursor = 0.0
    for clip in clips:
        shot = next((s for s in project.shots if s.id == clip.shot_id), None)
        take = next((t for t in project.takes if t.id == clip.take_id), None)
        dur = _clip_duration(clip, shot.duration_sec if shot else 3.0)
        entries.append(
            {
                "clip_id": clip.id,
                "shot_id": clip.shot_id,
                "title": shot.title if shot else clip.id,
                "media_path": take.media_path if take else None,
                "thumb_path": take.thumb_path if take else None,
                "start": cursor,
                "duration": dur,
                "end": cursor + dur,
                "caption": clip.caption,
                "caption_style": clip.caption_style,
                "caption_x": getattr(clip, "caption_x", 0),
                "caption_y": getattr(clip, "caption_y", 0),
                "filter_id": clip.filter_id,
                "filter_intensity": clip.filter_intensity,
                "transition": getattr(clip, "transition", "none"),
                "transition_dur": getattr(clip, "transition_dur", 0.35),
                "scale": getattr(clip, "scale", 1.0),
                "pan_x": getattr(clip, "pan_x", 0.0),
                "pan_y": getattr(clip, "pan_y", 0.0),
                "trim_in": clip.trim_in,
                "speed": clip.speed or 1.0,
            }
        )
        cursor += dur

    audio = [
        {
            "id": a.id,
            "label": a.label,
            "kind": a.kind,
            "media_path": a.media_path,
            "timeline_start": a.timeline_start,
            "duration_sec": a.duration_sec,
            "volume": a.volume,
            "muted": a.muted,
            "track": a.track,
        }
        for a in (project.audio_timeline or [])
    ]

    return {
        "project_id": project.id,
        "title": project.title,
        "total_sec": cursor,
        "built_at": utc_now(),
        "entries": entries,
        "audio": audio,
        "captions_enabled": getattr(project, "captions_enabled", True),
    }


def stitch_preview(project: Project) -> dict[str, Any]:
    """Write playlist JSON and try ffmpeg concat into a preview mp4 when possible."""
    ensure_dirs()
    out_dir = OUTPUTS_DIR / project.id / "stitch"
    out_dir.mkdir(parents=True, exist_ok=True)
    playlist = build_playlist(project)
    playlist_path = out_dir / "playlist.json"
    playlist_path.write_text(json.dumps(playlist, indent=2), encoding="utf-8")

    result: dict[str, Any] = {
        "playlist": playlist,
        "playlist_path": str(playlist_path),
        "preview_path": None,
        "preview_url": None,
        "method": "playlist",
        "message": "In-app playlist ready — play the cut in Director.",
    }

    media_files = [e["media_path"] for e in playlist["entries"] if e.get("media_path")]
    if len(media_files) < 1:
        result["message"] = "No media on timeline yet — pin takes first."
        return result

    # ffmpeg concat demuxer (copy when all mp4; otherwise re-encode lightly)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        result["message"] = "Playlist ready. Install ffmpeg for a single preview.mp4 file."
        return result

    list_file = out_dir / "concat.txt"
    lines = []
    for path in media_files:
        p = Path(path)
        if p.exists():
            # escape single quotes for concat demuxer
            esc = str(p.resolve()).replace("'", "'\\''")
            lines.append(f"file '{esc}'")
    if not lines:
        return result
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    preview = out_dir / "preview.mp4"
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(preview),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
        if preview.exists() and preview.stat().st_size > 0:
            result["preview_path"] = str(preview)
            result["preview_url"] = f"/api/file?path={preview}"
            result["method"] = "ffmpeg-copy"
            result["message"] = "Stitched preview.mp4 ready."
            return result
    except Exception:
        pass

    # re-encode fallback
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(preview),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        if preview.exists():
            result["preview_path"] = str(preview)
            result["preview_url"] = f"/api/file?path={preview}"
            result["method"] = "ffmpeg-reencode"
            result["message"] = "Stitched preview.mp4 ready (re-encoded)."
    except Exception as exc:
        result["message"] = f"Playlist ready; ffmpeg stitch skipped ({exc.__class__.__name__})."

    return result
