from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .models import new_id, utc_now
from .paths import ADDONS_DIR, ENABLED_ADDONS_PATH, PLUGINS_DIR, SKILLS_DIR, ensure_dirs

# Pinokio-style: everything lives in the downloaded app folder.
BUNDLED = ADDONS_DIR
USER_ADDONS = ADDONS_DIR


def _ensure() -> None:
    ensure_dirs()
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _enabled_map() -> dict[str, bool]:
    if not ENABLED_ADDONS_PATH.exists():
        return {}
    try:
        return json.loads(ENABLED_ADDONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_enabled(data: dict[str, bool]) -> None:
    _ensure()
    ENABLED_ADDONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENABLED_ADDONS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _scan_plugins(folder: Path, source: str) -> list[dict[str, Any]]:
    items = []
    if not folder.exists():
        return items
    for path in sorted(folder.glob("*.json")):
        data = _read_json(path)
        if not data:
            continue
        pid = data.get("id") or path.stem
        items.append(
            {
                "id": pid,
                "name": data.get("name") or pid,
                "version": data.get("version") or "0.1.0",
                "description": data.get("description") or "",
                "kind": "plugin",
                "hooks": data.get("hooks") or [],
                "modes_added": data.get("modes_added") or [],
                "provides": data.get("provides") or [],
                "source": source,
                "path": str(path),
                "enabled": True,
            }
        )
    return items


def _scan_skills(folder: Path, source: str) -> list[dict[str, Any]]:
    items = []
    if not folder.exists():
        return items
    for path in sorted(list(folder.glob("*.json")) + list(folder.glob("*.md"))):
        if path.suffix == ".json":
            data = _read_json(path) or {}
            sid = data.get("id") or path.stem
            items.append(
                {
                    "id": sid,
                    "name": data.get("name") or sid,
                    "version": data.get("version") or "0.1.0",
                    "description": data.get("description") or "",
                    "kind": "skill",
                    "trigger": data.get("trigger") or [],
                    "content": data.get("content") or data.get("instructions") or "",
                    "source": source,
                    "path": str(path),
                    "enabled": True,
                }
            )
        else:
            text = path.read_text(encoding="utf-8")
            title = path.stem.replace("-", " ").replace("_", " ").title()
            first = text.strip().splitlines()[0].lstrip("# ").strip() if text.strip() else title
            items.append(
                {
                    "id": path.stem,
                    "name": first or title,
                    "version": "0.1.0",
                    "description": (text.strip().split("\n\n")[0])[:180],
                    "kind": "skill",
                    "trigger": [],
                    "content": text,
                    "source": source,
                    "path": str(path),
                    "enabled": True,
                }
            )
    return items


def list_addons() -> dict[str, Any]:
    _ensure()
    enabled = _enabled_map()
    plugins = _scan_plugins(PLUGINS_DIR, "app")
    skills = _scan_skills(SKILLS_DIR, "app")

    def apply_enabled(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for item in items:
            if item["id"] in enabled:
                item["enabled"] = bool(enabled[item["id"]])
        return sorted(items, key=lambda x: x["name"].lower())

    return {
        "plugins": apply_enabled(plugins),
        "skills": apply_enabled(skills),
        "paths": {
            "addons": str(ADDONS_DIR),
            "plugins": str(PLUGINS_DIR),
            "skills": str(SKILLS_DIR),
        },
    }


def set_addon_enabled(addon_id: str, enabled: bool) -> dict[str, Any]:
    data = _enabled_map()
    data[addon_id] = enabled
    _save_enabled(data)
    return {"id": addon_id, "enabled": enabled}


def install_skill(name: str, content: str, description: str = "") -> dict[str, Any]:
    _ensure()
    sid = new_id("skill")
    payload = {
        "id": sid,
        "name": name,
        "version": "0.1.0",
        "description": description or name,
        "content": content,
        "trigger": [],
        "created_at": utc_now(),
    }
    path = SKILLS_DIR / f"{sid}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {**payload, "kind": "skill", "source": "app", "path": str(path), "enabled": True}


def install_plugin_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _ensure()
    pid = manifest.get("id") or new_id("plugin")
    manifest = {**manifest, "id": pid, "version": manifest.get("version") or "0.1.0"}
    path = PLUGINS_DIR / f"{pid}.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        **manifest,
        "kind": "plugin",
        "source": "app",
        "path": str(path),
        "enabled": True,
    }


def enabled_skill_texts() -> list[str]:
    pack = list_addons()
    texts = []
    for skill in pack["skills"]:
        if skill.get("enabled") and skill.get("content"):
            texts.append(f"### Skill: {skill['name']}\n{skill['content']}")
    return texts
