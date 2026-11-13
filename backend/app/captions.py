from __future__ import annotations

import re
from typing import Any

from .models import Project, TimelineClip, new_id
from .storage import save_project


def _clean_line(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t[:180]


def caption_for_shot(project: Project, shot_id: str) -> str:
    shot = next((s for s in project.shots if s.id == shot_id), None)
    if not shot:
        return ""
    if shot.dialogue and shot.dialogue.strip():
        # Prefer spoken line as subtitle
        who = ""
        chars = [c for c in project.characters if c.id in (shot.character_ids or [])]
        if chars:
            who = chars[0].name
        line = _clean_line(shot.dialogue)
        return f"{who}: {line}" if who and not line.lower().startswith(who.lower()) else line
    if shot.action:
        return _clean_line(shot.action)
    return _clean_line(shot.title)


def generate_captions(project: Project, overwrite: bool = False) -> Project:
    """Fill timeline clip captions from dialogue/action. Creates timeline from pins if empty."""
    if not project.timeline:
        clips: list[TimelineClip] = []
        for i, shot in enumerate(sorted(project.shots, key=lambda s: s.index)):
            if not shot.pinned_take_id:
                continue
            clips.append(
                TimelineClip(
                    id=new_id("clip"),
                    shot_id=shot.id,
                    take_id=shot.pinned_take_id,
                    start_sec=0.0,
                    end_sec=float(shot.duration_sec or 3.0),
                    trim_out=float(shot.duration_sec or 3.0),
                    pinned=True,
                    order=i,
                    filter_id=project.default_filter_id or "none",
                )
            )
        project.timeline = clips

    for clip in project.timeline:
        if clip.caption and not overwrite:
            continue
        clip.caption = caption_for_shot(project, clip.shot_id)
        if not clip.caption_style:
            clip.caption_style = "bottom"
    project.captions_enabled = True
    return save_project(project)


def captions_srt(project: Project) -> str:
    """Export timeline captions as SRT."""
    lines: list[str] = []
    cursor = 0.0
    idx = 1
    for clip in sorted(project.timeline, key=lambda c: c.order):
        shot = next((s for s in project.shots if s.id == clip.shot_id), None)
        dur = _clip_duration(clip, shot.duration_sec if shot else 3.0)
        text = (clip.caption or "").strip()
        if text:
            lines.append(str(idx))
            lines.append(f"{_srt_ts(cursor)} --> {_srt_ts(cursor + dur)}")
            lines.append(text)
            lines.append("")
            idx += 1
        cursor += dur
    return "\n".join(lines) if lines else ""


def _clip_duration(clip: TimelineClip, fallback: float) -> float:
    if clip.trim_out is not None:
        dur = max(0.2, float(clip.trim_out) - float(clip.trim_in or 0.0))
    elif clip.end_sec is not None:
        dur = max(0.2, float(clip.end_sec) - float(clip.start_sec or 0.0))
    else:
        dur = float(fallback or 3.0)
    speed = float(clip.speed or 1.0) or 1.0
    return dur / speed


def _srt_ts(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def timeline_progress(project: Project) -> dict[str, Any]:
    ordered = sorted(project.timeline, key=lambda c: c.order)
    segments = []
    cursor = 0.0
    for clip in ordered:
        shot = next((s for s in project.shots if s.id == clip.shot_id), None)
        dur = _clip_duration(clip, shot.duration_sec if shot else 3.0)
        segments.append(
            {
                "clip_id": clip.id,
                "shot_id": clip.shot_id,
                "title": shot.title if shot else clip.id,
                "start": cursor,
                "end": cursor + dur,
                "duration": dur,
                "caption": clip.caption,
                "filter_id": clip.filter_id,
                "has_take": bool(clip.take_id),
            }
        )
        cursor += dur
    done = sum(1 for s in segments if s["has_take"])
    return {
        "total_sec": cursor,
        "clip_count": len(segments),
        "with_media": done,
        "pct_ready": round(100 * done / len(segments), 1) if segments else 0.0,
        "segments": segments,
    }
