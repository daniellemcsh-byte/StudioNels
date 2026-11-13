from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Project, ProjectSummary, Settings, utc_now
from .paths import PRESETS_DIR, PROJECTS_DIR, SETTINGS_PATH, ensure_dirs


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_settings() -> Settings:
    ensure_dirs()
    raw = _read_json(SETTINGS_PATH, {})
    return Settings(**raw) if raw else Settings()


def save_settings(settings: Settings) -> Settings:
    ensure_dirs()
    # Keep existing API key when client sends blank / masked placeholder
    existing = load_settings()
    key = (settings.agent_api_key or "").strip()
    if not key or key in ("••••••••", "***", "(unchanged)"):
        settings.agent_api_key = existing.agent_api_key or ""
    _write_json(SETTINGS_PATH, settings.model_dump())
    return settings


def settings_public(settings: Settings | None = None) -> dict:
    """Settings for the UI — never send the raw API key back."""
    s = settings or load_settings()
    data = s.model_dump()
    key = (data.get("agent_api_key") or "").strip()
    data["agent_api_key"] = ""
    data["agent_api_key_set"] = bool(key)
    return data


def list_presets() -> list[dict[str, Any]]:
    presets = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        presets.append(_read_json(path, {}))
    return presets


def get_preset(preset_id: str) -> dict[str, Any]:
    path = PRESETS_DIR / f"{preset_id}.json"
    if not path.exists():
        path = PRESETS_DIR / "amd-low-vram.json"
    return _read_json(path, {})


def project_path(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.json"


def list_projects() -> list[ProjectSummary]:
    ensure_dirs()
    items: list[ProjectSummary] = []
    for path in PROJECTS_DIR.glob("*.json"):
        try:
            data = _read_json(path, {})
            project = Project(**data)
            items.append(
                ProjectSummary(
                    id=project.id,
                    title=project.title,
                    mode=project.mode,
                    updated_at=project.updated_at,
                    shot_count=len(project.shots),
                    preset_id=project.preset_id,
                )
            )
        except Exception:
            continue
    items.sort(key=lambda p: p.updated_at, reverse=True)
    return items


def load_project(project_id: str) -> Project:
    path = project_path(project_id)
    if not path.exists():
        raise FileNotFoundError(project_id)
    return Project(**_read_json(path, {}))


def save_project(project: Project) -> Project:
    ensure_dirs()
    project.updated_at = utc_now()
    _write_json(project_path(project.id), project.model_dump())
    return project


def delete_project(project_id: str) -> None:
    path = project_path(project_id)
    if path.exists():
        path.unlink()
