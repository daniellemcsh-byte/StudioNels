from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from .models import Settings, new_id, utc_now
from .paths import ADDONS_DIR, LORAS_DIR, MODELS_DIR, ensure_dirs
from .storage import load_settings, save_settings

Kind = Literal["model", "lora", "addon"]

_IMPORTS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def personal_profile(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or load_settings()
    return {
        "github_url": s.github_url or "",
        "huggingface_url": s.huggingface_url or "",
        "huggingface_token_set": bool((s.huggingface_token or "").strip()),
        "display_name": s.creator_display_name or "",
        "imports": list_imports(12),
        "hints": {
            "github": "https://github.com/your-username or https://github.com/you/framewright-pack",
            "huggingface": "https://huggingface.co/your-username",
            "import_model": "owner/repo or https://huggingface.co/owner/repo",
            "import_lora": "HF file URL, GitHub raw URL, or local-style owner/repo/file.safetensors",
            "import_addon": "GitHub raw JSON/MD URL into addons/",
        },
    }


def save_personal_links(
    *,
    github_url: str | None = None,
    huggingface_url: str | None = None,
    huggingface_token: str | None = None,
    creator_display_name: str | None = None,
) -> dict[str, Any]:
    s = load_settings()
    if github_url is not None:
        s.github_url = _clean_url(github_url)
    if huggingface_url is not None:
        s.huggingface_url = _clean_url(huggingface_url)
    if creator_display_name is not None:
        s.creator_display_name = creator_display_name.strip()[:80]
    if huggingface_token is not None:
        tok = huggingface_token.strip()
        if tok and tok not in ("••••••••", "***", "(unchanged)"):
            s.huggingface_token = tok
        elif not tok:
            # blank = keep existing
            pass
    save_settings(s)
    return personal_profile(s)


def list_imports(limit: int = 20) -> list[dict[str, Any]]:
    with _LOCK:
        items = sorted(_IMPORTS.values(), key=lambda x: x.get("updated_at") or "", reverse=True)
    return items[:limit]


def get_import(job_id: str) -> dict[str, Any] | None:
    return _IMPORTS.get(job_id)


def start_import(kind: Kind, source: str, name: str | None = None) -> dict[str, Any]:
    source = (source or "").strip()
    if not source:
        raise ValueError("Paste a Hugging Face or GitHub URL (or owner/repo).")
    kind = kind if kind in ("model", "lora", "addon") else "model"
    job = {
        "id": new_id("imp"),
        "kind": kind,
        "source": source,
        "name": name or "",
        "status": "queued",
        "progress": 0.0,
        "message": "Queued",
        "local_path": None,
        "error": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    with _LOCK:
        _IMPORTS[job["id"]] = job

    def worker() -> None:
        try:
            _run_import(job)
        except Exception as exc:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = str(exc)
            job["message"] = str(exc)
            job["updated_at"] = utc_now()

    threading.Thread(target=worker, name=f"import-{job['id']}", daemon=True).start()
    return job


def _run_import(job: dict[str, Any]) -> None:
    ensure_dirs()
    job["status"] = "running"
    job["message"] = "Starting import…"
    job["progress"] = 0.05
    job["updated_at"] = utc_now()

    kind: Kind = job["kind"]
    source = job["source"]
    settings = load_settings()

    if kind == "model":
        path = _import_hf_model(source, settings, job)
    elif kind == "lora":
        path = _import_file(source, LORAS_DIR, settings, job, default_name="lora.safetensors")
    else:
        dest_root = ADDONS_DIR / "plugins" if source.endswith(".json") else ADDONS_DIR / "skills"
        path = _import_file(source, dest_root, settings, job, default_name="addon.json")

    job["local_path"] = str(path)
    job["status"] = "done"
    job["progress"] = 1.0
    job["message"] = f"Saved to {path}"
    job["updated_at"] = utc_now()


def _import_hf_model(source: str, settings: Settings, job: dict[str, Any]) -> Path:
    repo = _parse_hf_repo(source)
    if not repo:
        raise ValueError("Need a Hugging Face repo like owner/name or huggingface.co/owner/name")
    job["message"] = f"Downloading {repo}…"
    job["progress"] = 0.15
    job["updated_at"] = utc_now()
    token = (settings.huggingface_token or "").strip() or None
    local_dir = MODELS_DIR / repo.replace("/", "__")
    local_dir.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=repo,
            local_dir=str(local_dir),
            local_dir_use_symlinks=False,
            token=token,
        )
    except ImportError as exc:
        raise ValueError(
            "huggingface_hub not installed. pip install huggingface_hub — or copy the model folder into models/ manually."
        ) from exc
    job["progress"] = 0.9
    job["name"] = repo
    return local_dir


def _import_file(
    source: str,
    dest_dir: Path,
    settings: Settings,
    job: dict[str, Any],
    default_name: str,
) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    url, filename = _resolve_download_url(source, settings)
    if job.get("name"):
        filename = Path(job["name"]).name
    dest = dest_dir / filename
    job["message"] = f"Downloading {filename}…"
    job["progress"] = 0.2
    job["updated_at"] = utc_now()

    headers = {}
    token = (settings.huggingface_token or "").strip()
    if token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=120.0) as res:
        if res.status_code >= 400:
            raise ValueError(f"Download failed ({res.status_code}) for {url}")
        total = int(res.headers.get("content-length") or 0)
        done = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as f:
            for chunk in res.iter_bytes():
                f.write(chunk)
                done += len(chunk)
                if total:
                    job["progress"] = 0.2 + 0.7 * (done / total)
                    job["updated_at"] = utc_now()
        tmp.replace(dest)
    job["name"] = filename
    return dest


def _parse_hf_repo(source: str) -> str | None:
    s = source.strip().rstrip("/")
    if re.fullmatch(r"[\w.-]+/[\w.-]+", s):
        return s
    m = re.search(r"huggingface\.co/([\w.-]+/[\w.-]+)", s)
    return m.group(1) if m else None


def _resolve_download_url(source: str, settings: Settings) -> tuple[str, str]:
    s = source.strip()
    # Already a direct URL
    if s.startswith("http://") or s.startswith("https://"):
        parsed = urlparse(s)
        name = Path(parsed.path).name or "download.bin"
        # HF blob page → resolve
        if "huggingface.co" in parsed.netloc and "/blob/" in parsed.path:
            s = s.replace("/blob/", "/resolve/")
            name = Path(urlparse(s).path).name
        # GitHub blob → raw
        if "github.com" in parsed.netloc and "/blob/" in parsed.path:
            s = s.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            name = Path(urlparse(s).path).name
        return s, name

    # owner/repo/path/file.safetensors on HF
    if "/" in s and not s.startswith("http"):
        parts = s.split("/")
        if len(parts) >= 3:
            repo = f"{parts[0]}/{parts[1]}"
            rel = "/".join(parts[2:])
            url = f"https://huggingface.co/{repo}/resolve/main/{rel}"
            return url, parts[-1]
        if len(parts) == 2 and settings.huggingface_url:
            # treat as repo under user? skip
            pass
    raise ValueError(
        "Use a full https URL (HF resolve / GitHub raw) or owner/repo/file.safetensors"
    )


def _clean_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith("http"):
        if "huggingface.co" in u or u.startswith("hf.co"):
            u = "https://" + u.lstrip("/")
        elif "github.com" in u:
            u = "https://" + u.lstrip("/")
        else:
            # bare username → guess
            if "/" not in u:
                return u  # store username-ish; UI can prefix
            u = "https://" + u
    return u[:300]
