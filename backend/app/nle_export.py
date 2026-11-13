from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .models import Project, Take, TimelineClip, utc_now
from .paths import OUTPUTS_DIR, ensure_dirs


def _take_for_clip(project: Project, shot_id: str, take_id: str | None) -> Take | None:
    if take_id:
        t = next((x for x in project.takes if x.id == take_id), None)
        if t:
            return t
    shot = next((s for s in project.shots if s.id == shot_id), None)
    if shot and shot.pinned_take_id:
        return next((x for x in project.takes if x.id == shot.pinned_take_id), None)
    return next((x for x in project.takes if x.shot_id == shot_id and not x.rejected), None)


def _timeline_or_pins(project: Project) -> list[TimelineClip]:
    if project.timeline:
        return sorted(project.timeline, key=lambda c: c.order)
    clips: list[TimelineClip] = []
    for shot in sorted(project.shots, key=lambda s: s.index):
        take = _take_for_clip(project, shot.id, shot.pinned_take_id)
        if take and take.media_path:
            clips.append(
                TimelineClip(
                    shot_id=shot.id,
                    take_id=take.id,
                    pinned=True,
                    order=len(clips),
                    end_sec=shot.duration_sec,
                )
            )
    return clips


def _timecode(seconds: float, fps: float = 24.0) -> str:
    total = max(0, int(round(seconds * fps)))
    f = total % int(fps)
    total //= int(fps)
    s = total % 60
    total //= 60
    m = total % 60
    h = total // 60
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def build_edl(project: Project, fps: float = 24.0) -> str:
    lines = [
        f"TITLE: {project.title}",
        f"FCM: NON-DROP FRAME",
        "",
    ]
    clips = _timeline_or_pins(project)
    cursor = 0.0
    event = 1
    for clip in clips:
        shot = next((s for s in project.shots if s.id == clip.shot_id), None)
        take = _take_for_clip(project, clip.shot_id, clip.take_id)
        if not shot or not take or not take.media_path:
            continue
        dur = float(shot.duration_sec or 3.0)
        src_in = 0.0
        src_out = dur
        rec_in = cursor
        rec_out = cursor + dur
        name = Path(take.media_path).stem.upper()[:32]
        lines.append(
            f"{event:03d}  {name:<32} V     C        "
            f"{_timecode(src_in, fps)} {_timecode(src_out, fps)} "
            f"{_timecode(rec_in, fps)} {_timecode(rec_out, fps)}"
        )
        note = shot.title.replace("\n", " ")
        lines.append(f"* FROM CLIP NAME: {note}")
        if take.continuity_score is not None:
            lines.append(f"* CONTINUITY: {int(take.continuity_score * 100)}%")
        if take.is_rehearsal:
            lines.append("* MARKER: REHEARSAL")
        for flag in (take.continuity_flags or [])[:3]:
            lines.append(f"* FLAG: {flag}")
        lines.append("")
        cursor = rec_out
        event += 1
    return "\n".join(lines)


def build_fcpxml(project: Project, fps: float = 24.0) -> str:
    """Minimal FCPXML 1.9-ish timeline for Premiere/Resolve/Final Cut import."""
    clips = _timeline_or_pins(project)
    assets: list[str] = []
    spine: list[str] = []
    total_frames = 0
    frame_duration = f"100/{int(fps * 100)}s"

    for i, clip in enumerate(clips):
        shot = next((s for s in project.shots if s.id == clip.shot_id), None)
        take = _take_for_clip(project, clip.shot_id, clip.take_id)
        if not shot or not take or not take.media_path:
            continue
        aid = f"r{i + 1}"
        path = Path(take.media_path).resolve().as_uri()
        dur_f = max(1, int(round(float(shot.duration_sec or 3.0) * fps)))
        assets.append(
            f'    <asset id="{aid}" name="{escape(shot.title)}" start="0s" '
            f'duration="{dur_f}/{int(fps)}s" hasVideo="1" hasAudio="0">'
            f'<media-rep kind="original-media" src="{escape(path)}"/></asset>'
        )
        note_bits = []
        if take.continuity_score is not None:
            note_bits.append(f"cont {int(take.continuity_score * 100)}%")
        if take.is_rehearsal:
            note_bits.append("rehearsal")
        note = escape(" · ".join(note_bits)) if note_bits else ""
        spine.append(
            f'      <asset-clip name="{escape(shot.title)}" ref="{aid}" '
            f'offset="{total_frames}/{int(fps)}s" duration="{dur_f}/{int(fps)}s" '
            f'start="0s">{f"<note>{note}</note>" if note else ""}</asset-clip>'
        )
        total_frames += dur_f

    body = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<!DOCTYPE fcpxml>",
            '<fcpxml version="1.9">',
            "  <resources>",
            f'    <format id="r0" name="FFVideoFormat{int(fps)}p" '
            f'frameDuration="{frame_duration}" width="1920" height="1080"/>',
            *assets,
            "  </resources>",
            "  <library>",
            f'    <event name="{escape(project.title)}">',
            f'      <project name="{escape(project.title)}">',
            f'        <sequence format="r0" duration="{total_frames}/{int(fps)}s" tcStart="0s">',
            "          <spine>",
            *spine,
            "          </spine>",
            "        </sequence>",
            "      </project>",
            "    </event>",
            "  </library>",
            "</fcpxml>",
        ]
    )
    return body


def build_markers_json(project: Project) -> dict[str, Any]:
    markers = []
    cursor = 0.0
    for clip in _timeline_or_pins(project):
        shot = next((s for s in project.shots if s.id == clip.shot_id), None)
        take = _take_for_clip(project, clip.shot_id, clip.take_id)
        if not shot:
            continue
        dur = float(shot.duration_sec or 3.0)
        markers.append(
            {
                "shot_id": shot.id,
                "title": shot.title,
                "start_sec": cursor,
                "end_sec": cursor + dur,
                "take_id": take.id if take else None,
                "media_path": take.media_path if take else None,
                "continuity_score": take.continuity_score if take else None,
                "continuity_flags": take.continuity_flags if take else [],
                "is_rehearsal": bool(take.is_rehearsal) if take else False,
                "character_lock": [
                    {"name": c.name, "lock": c.character_lock}
                    for c in project.characters
                    if c.id in (shot.character_ids or [])
                ],
                "dialogue": shot.dialogue,
                "audio_notes": shot.director_notes,
                "caption": getattr(clip, "caption", "") or "",
                "caption_style": getattr(clip, "caption_style", "bottom") or "bottom",
                "caption_x": getattr(clip, "caption_x", 0.0),
                "caption_y": getattr(clip, "caption_y", 0.0),
                "caption_start": getattr(clip, "caption_start", 0.0),
                "caption_end": getattr(clip, "caption_end", None),
                "filter_id": getattr(clip, "filter_id", "none") or "none",
                "filter_intensity": getattr(clip, "filter_intensity", 1.0),
                "trim_in": getattr(clip, "trim_in", 0.0),
                "trim_out": getattr(clip, "trim_out", None),
                "speed": getattr(clip, "speed", 1.0),
                "transition": getattr(clip, "transition", "none") or "none",
                "transition_dur": getattr(clip, "transition_dur", 0.35),
            }
        )
        cursor += dur
    return {
        "project": project.title,
        "exported_at": utc_now(),
        "visual_style": project.visual_style,
        "target_duration_sec": project.target_duration_sec,
        "default_filter_id": getattr(project, "default_filter_id", "none"),
        "captions_enabled": getattr(project, "captions_enabled", True),
        "markers": markers,
        "audio": [
            {
                "id": a.id,
                "label": a.label,
                "kind": a.kind,
                "media_path": a.media_path,
                "timeline_start": a.timeline_start,
                "duration_sec": a.duration_sec,
                "volume": a.volume,
                "track": a.track,
                "muted": a.muted,
            }
            for a in getattr(project, "audio_timeline", []) or []
        ],
    }


def export_nle_package(project: Project, fps: float = 24.0) -> dict[str, Any]:
    ensure_dirs()
    out_root = OUTPUTS_DIR / project.id / "nle_export"
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    media_dir = out_root / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    edl = build_edl(project, fps)
    xml = build_fcpxml(project, fps)
    markers = build_markers_json(project)
    (out_root / f"{_safe(project.title)}.edl").write_text(edl, encoding="utf-8")
    (out_root / f"{_safe(project.title)}.fcpxml").write_text(xml, encoding="utf-8")
    (out_root / "markers.json").write_text(json.dumps(markers, indent=2), encoding="utf-8")
    (out_root / "README.txt").write_text(
        "Framewright NLE export\n"
        "- .edl — CMX3600-style EDL for Premiere / Resolve\n"
        "- .fcpxml — Final Cut / Resolve XML\n"
        "- markers.json — continuity locks, flags, rehearsal markers, dialogue\n"
        "- media/ — copied take files referenced by the cut\n",
        encoding="utf-8",
    )

    copied = 0
    for m in markers["markers"]:
        src = m.get("media_path")
        if not src:
            continue
        p = Path(src)
        if not p.exists():
            continue
        dest = media_dir / p.name
        if not dest.exists():
            shutil.copy2(p, dest)
            copied += 1

    zip_path = OUTPUTS_DIR / project.id / f"{_safe(project.title)}_nle.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_root.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_root).as_posix())

    return {
        "folder": str(out_root),
        "zip_path": str(zip_path),
        "edl": edl[:500],
        "clip_count": len(markers["markers"]),
        "media_copied": copied,
        "download_url": f"/api/file?path={zip_path}",
    }


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:48] or "project"
