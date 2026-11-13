from __future__ import annotations

"""Project packs — zip a project (JSON + media refs) for sharing offline."""

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .models import Project, ProjectSummary, new_id, utc_now
from .paths import OUTPUTS_DIR, PROJECTS_DIR, ensure_dirs
from .storage import list_projects, load_project, save_project


def export_project_pack(project: Project) -> dict[str, Any]:
    ensure_dirs()
    out_dir = OUTPUTS_DIR / project.id / "packs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace(":", "").replace("-", "")[:15]
    zip_path = out_dir / f"{project.id}_{stamp}.studionels.zip"

    media_paths: list[Path] = []
    for take in project.takes:
        for attr in ("media_path", "thumb_path", "last_frame_path"):
            p = getattr(take, attr, None)
            if p and Path(p).exists():
                media_paths.append(Path(p))
    for clip in project.audio_timeline or []:
        if clip.media_path and Path(clip.media_path).exists():
            media_paths.append(Path(clip.media_path))
    for char in project.characters:
        if char.reference_path and Path(char.reference_path).exists():
            media_paths.append(Path(char.reference_path))
    for scene in project.scenes:
        if scene.reference_path and Path(scene.reference_path).exists():
            media_paths.append(Path(scene.reference_path))

    look_bible = {
        "visual_style": project.visual_style,
        "frame_size_id": getattr(project, "frame_size_id", None),
        "aspect_ratio": getattr(project, "aspect_ratio", None),
        "width": getattr(project, "width", None),
        "height": getattr(project, "height", None),
        "continuity_rules": project.continuity_rules,
        "world_bible": project.world_bible,
        "auto_reject_below": project.auto_reject_below,
        "continue_from_previous": project.continue_from_previous,
        "preset_id": project.preset_id,
        "characters": [
            {
                "name": c.name,
                "lock": c.character_lock,
                "look": c.look,
                "has_ref": bool(c.reference_path),
                "has_identity": bool(c.identity_fingerprint),
            }
            for c in project.characters
        ],
        "recipe": (project.meta or {}).get("recipe"),
    }

    manifest = {
        "format": "studionels-pack-v1",
        "kind": "look_bible_project_pack",
        "exported_at": utc_now(),
        "creator": "StudioNels",
        "project_id": project.id,
        "title": project.title,
        "media_count": len(media_paths),
        "look_bible": look_bible,
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("look_bible.json", json.dumps(look_bible, indent=2))
        zf.writestr("project.json", project.model_dump_json(indent=2))
        for i, path in enumerate(media_paths):
            arc = f"media/{i:04d}_{path.name}"
            zf.write(path, arcname=arc)

    return {
        "zip_path": str(zip_path),
        "download_url": f"/api/file?path={zip_path}",
        "media_count": len(media_paths),
        "title": project.title,
        "message": f"Pack ready · {len(media_paths)} media file(s).",
    }


def import_project_pack(zip_path: Path) -> Project:
    ensure_dirs()
    if not zip_path.exists():
        raise FileNotFoundError("Pack zip not found")

    extract = OUTPUTS_DIR / "_pack_import" / new_id("imp")
    extract.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract)
        project_file = extract / "project.json"
        if not project_file.exists():
            raise ValueError("Not a StudioNels pack (missing project.json)")
        data = json.loads(project_file.read_text(encoding="utf-8"))
        old_id = data.get("id") or "imported"
        new_project_id = new_id("prj")
        data["id"] = new_project_id
        data["title"] = f"{data.get('title') or 'Imported'} (pack)"
        data["updated_at"] = utc_now()

        media_root = OUTPUTS_DIR / new_project_id / "imported"
        media_root.mkdir(parents=True, exist_ok=True)
        media_dir = extract / "media"
        path_map: dict[str, str] = {}
        if media_dir.exists():
            for src in sorted(media_dir.iterdir()):
                if not src.is_file():
                    continue
                dest = media_root / src.name
                shutil.copy2(src, dest)
                # remap by basename match in project JSON paths
                path_map[src.name.split("_", 1)[-1] if "_" in src.name else src.name] = str(dest)

        def _remap(path: str | None) -> str | None:
            if not path:
                return path
            name = Path(path).name
            return path_map.get(name, path)

        for take in data.get("takes") or []:
            take["media_path"] = _remap(take.get("media_path"))
            take["thumb_path"] = _remap(take.get("thumb_path"))
            if "last_frame_path" in take:
                take["last_frame_path"] = _remap(take.get("last_frame_path"))
        for clip in data.get("audio_timeline") or []:
            clip["media_path"] = _remap(clip.get("media_path"))

        project = Project.model_validate(data)
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        saved = save_project(project)
        # keep old id in meta for debugging
        saved.meta = dict(saved.meta or {})
        saved.meta["imported_from_pack"] = old_id
        return save_project(saved)
    finally:
        shutil.rmtree(extract, ignore_errors=True)


def list_packs() -> list[dict[str, Any]]:
    ensure_dirs()
    packs: list[dict[str, Any]] = []
    if not OUTPUTS_DIR.exists():
        return packs
    for zip_path in list(OUTPUTS_DIR.rglob("*.studionels.zip")) + list(
        OUTPUTS_DIR.rglob("*.nellpack.zip")
    ):
        packs.append(
            {
                "path": str(zip_path),
                "name": zip_path.name,
                "size_mb": round(zip_path.stat().st_size / (1024 * 1024), 2),
                "download_url": f"/api/file?path={zip_path}",
            }
        )
    return sorted(packs, key=lambda p: p["name"], reverse=True)


def project_summaries() -> list[ProjectSummary]:
    return list_projects()
