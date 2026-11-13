from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRESETS_DIR = ROOT / "presets"
DATA_DIR = Path.home() / ".framewright"
PROJECTS_DIR = DATA_DIR / "projects"
SETTINGS_PATH = DATA_DIR / "settings.json"
MEDIA_DIR = DATA_DIR / "media"


def ensure_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
