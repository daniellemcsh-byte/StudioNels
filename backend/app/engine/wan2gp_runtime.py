"""Optional Wan2GP bridge (legacy / opt-in only).

StudioNels Generate uses Diffusers + native mmgp and Models → Download by default.
This module is only used when STUDIONELS_PREFER_WAN2GP=1 (or job.prefer_wan2gp).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from ..storage import load_settings


ProgressCb = Callable[[str, float], None]

# StudioNels catalog id → Wan2GP model_type / architecture id
_MODEL_MAP: dict[str, str] = {
    # Wan video
    "wan21-t2v-1.3b": "t2v_1.3B",
    "wan21-t2v-14b": "t2v",
    "wan21-i2v-14b-480p": "i2v",
    "wan21-i2v-14b-720p": "i2v_720p",
    "wan21-flf2v-14b-720p": "flf2v_720p",
    "wan22-t2v-a14b": "t2v_2_2",
    "wan22-i2v-a14b": "i2v_2_2",
    "wan22-ti2v-5b": "ti2v_2_2",
    # LTX
    "ltx-video-0.9.7": "ltxv_13B",
    "ltx2-19b-distilled": "ltx2_19B",
    "ltx2-official": "ltx2_22B",
    "ltx2.5-diffusers": "ltx2_25_22B",
    "ltx2.3-22b-distilled-diffusers": "ltx2_22B_distilled",
    "ltx2.3-22b-distilled-v11-diffusers": "ltx2_22B_distilled_1_1",
    "wan2gp-ltx2.3-22b-distilled": "ltx2_22B_distilled",
    "wan2gp-ltx2.3-22b-distilled-1.1": "ltx2_22B_distilled_1_1",
    # MiniMax / Hunyuan / others
    "minimax-h3": "minimax_h3_ref2va",
    "hunyuan-video": "hunyuan",
    "hunyuan-video-i2v": "hunyuan_i2v",
    "skyreels-v2-i2v-14b-720p": "sky_df_720p_14B",
    "skyreels-v2-t2v-14b-720p": "sky_df_14B",
    # Image
    "flux-schnell": "flux_schnell",
    "flux-dev": "flux",
    "qwen-image": "qwen_image_20B",
    # Audio
    "stable-audio-open": "stable_audio3_medium",
    "stable-audio-song": "stable_audio3_medium",
}

# Loose keyword → preferred Wan2GP architecture (checked against live catalog)
_KEYWORD_PREFER: list[tuple[tuple[str, ...], str]] = [
    (("ltx2.3", "1.1", "distill"), "ltx2_22B_distilled_1_1"),
    (("ltx2.3", "distill"), "ltx2_22B_distilled"),
    (("ltx2.5", "distill"), "ltx2_25_22B_distilled"),
    (("ltx2.5",), "ltx2_25_22B"),
    (("ltx2", "19"), "ltx2_19B"),
    (("ltx-video",), "ltxv_13B"),
    (("ltxv",), "ltxv_13B"),
    (("ti2v",), "ti2v_2_2"),
    (("flf2v",), "flf2v_720p"),
    (("wan2.2", "i2v"), "i2v_2_2"),
    (("wan22", "i2v"), "i2v_2_2"),
    (("wan2.2", "t2v"), "t2v_2_2"),
    (("wan22", "t2v"), "t2v_2_2"),
    (("1.3b", "t2v"), "t2v_1.3B"),
    (("i2v", "720"), "i2v_720p"),
    (("flux", "schnell"), "flux_schnell"),
    (("flux", "dev"), "flux"),
    (("flux",), "flux_schnell"),
    (("hunyuan", "i2v"), "hunyuan_i2v"),
    (("hunyuan",), "hunyuan"),
    (("minimax", "music"), "minimax_music3"),
    (("minimax", "image"), "minimax_h3_image"),
    (("minimax", "h3"), "minimax_h3_ref2va"),
    (("ace", "step"), "ace_step_v1_5"),
    (("chatterbox",), "chatterbox"),
    (("stable", "audio"), "stable_audio3_medium"),
    (("qwen", "image"), "qwen_image_20B"),
    (("skyreels", "i2v"), "sky_df_720p_14B"),
    (("skyreels", "t2v"), "sky_df_14B"),
    (("vace", "1.3"), "vace_1.3B"),
    (("vace",), "vace_14B"),
]


def _pinokio_sibling_wan2gp_roots() -> list[Path]:
    """Find Wan2GP next to StudioNels under Pinokio (…/pinokio/api/*/wgp.py)."""
    found: list[Path] = []
    try:
        # backend/app/engine/this.py → repo root is parents[3]
        repo = Path(__file__).resolve().parents[3]
        api_dir = repo.parent
        if not api_dir.is_dir():
            return found
        for child in sorted(api_dir.iterdir()):
            if not child.is_dir():
                continue
            name = child.name.lower()
            if "studio" in name and "nel" in name:
                continue
            if (child / "wgp.py").is_file():
                found.append(child)
                continue
            # Pinokio sometimes nests the clone one level deeper
            for nested in child.glob("*/wgp.py"):
                found.append(nested.parent)
            for nested in child.glob("*/*/wgp.py"):
                found.append(nested.parent)
    except Exception:
        return found
    return found


def wan2gp_root() -> Path | None:
    settings = load_settings()
    candidates: list[Path] = []
    for key in ("wan2gp_assets_path", "wan2gp_ckpts_path"):
        raw = (getattr(settings, key, None) or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser()
        candidates.append(p)
        if p.name.lower() == "ckpts":
            candidates.append(p.parent)
        if (p / "ckpts").is_dir():
            candidates.append(p)
    env = (os.environ.get("STUDIONELS_WAN2GP_ROOT") or "").strip()
    if env:
        candidates.insert(0, Path(env).expanduser())
    # Prefer an explicit link, then auto-discover a sibling Pinokio Wan2GP install
    candidates.extend(_pinokio_sibling_wan2gp_roots())

    seen: set[str] = set()
    for c in candidates:
        key = str(c.resolve()) if c.exists() else str(c)
        if key in seen:
            continue
        seen.add(key)
        root = c.resolve() if c.exists() else c
        if not root.exists():
            continue
        if (root / "wgp.py").is_file():
            return root
        if root.name.lower() == "ckpts" and (root.parent / "wgp.py").is_file():
            return root.parent
    return None


def wan2gp_python(root: Path) -> str | None:
    env_py = (os.environ.get("STUDIONELS_WAN2GP_PYTHON") or "").strip()
    if env_py and Path(env_py).exists():
        return env_py
    for rel in (
        "venv/bin/python",
        "venv/bin/python3",
        "venv/Scripts/python.exe",
        ".venv/bin/python",
        ".venv/Scripts/python.exe",
        "env/bin/python",
        "env/Scripts/python.exe",
        "../venv/bin/python",
        "../env/bin/python",
        "../venv/Scripts/python.exe",
        "../env/Scripts/python.exe",
    ):
        cand = (root / rel).resolve()
        if cand.is_file():
            return str(cand)
    return None


def wan2gp_available() -> dict[str, Any]:
    root = wan2gp_root()
    if not root:
        return {"available": False, "reason": "Import Wan2GP folder in Models / Settings first."}
    py = wan2gp_python(root)
    if not py:
        return {
            "available": False,
            "root": str(root),
            "reason": "Found Wan2GP but no venv python — set STUDIONELS_WAN2GP_PYTHON.",
        }
    archs = list_architectures(root)
    return {
        "available": True,
        "root": str(root),
        "python": py,
        "model_count": len(archs),
    }


@lru_cache(maxsize=4)
def list_architectures(root_str: str | Path) -> tuple[str, ...]:
    """All Wan2GP model_type ids present under defaults/ + finetunes/."""
    root = Path(root_str)
    found: set[str] = set()
    for sub in ("defaults", "finetunes"):
        d = root / sub
        if not d.is_dir():
            continue
        for path in d.glob("*.json"):
            found.add(path.stem)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                model = data.get("model") if isinstance(data, dict) else None
                if isinstance(model, dict) and model.get("architecture"):
                    found.add(str(model["architecture"]))
            except Exception:
                pass
    return tuple(sorted(found))


def clear_architecture_cache() -> None:
    list_architectures.cache_clear()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _pick_from_catalog(preferred: str, catalog: set[str]) -> str | None:
    if preferred in catalog:
        return preferred
    # Soft match ignoring case / punctuation
    pref_n = _norm(preferred)
    for arch in catalog:
        if _norm(arch) == pref_n:
            return arch
    # Prefix / contains
    for arch in catalog:
        an = _norm(arch)
        if pref_n and (pref_n in an or an in pref_n):
            return arch
    return None


def map_model_type(job: dict[str, Any], model: dict[str, Any] | None) -> str | None:
    mid = str(job.get("model_id") or (model or {}).get("id") or "")
    root = wan2gp_root()
    catalog = set(list_architectures(root)) if root else set()

    def accept(candidate: str | None) -> str | None:
        if not candidate:
            return None
        if not catalog:
            return candidate
        return _pick_from_catalog(candidate, catalog)

    # Explicit field on catalog / imported packs
    if model and model.get("wan2gp_model_type"):
        hit = accept(str(model["wan2gp_model_type"]))
        if hit:
            return hit

    # Direct id is already a Wan2GP architecture (engine-scanned models)
    if mid.startswith("wgp-"):
        hit = accept(mid[4:])
        if hit:
            return hit
    hit = accept(mid)
    if hit and mid in catalog:
        return hit

    if mid in _MODEL_MAP:
        hit = accept(_MODEL_MAP[mid])
        if hit:
            return hit

    blob = " ".join(
        [
            mid,
            str((model or {}).get("label") or ""),
            str((model or {}).get("pipeline") or ""),
            str((model or {}).get("hf_id") or ""),
            str((model or {}).get("notes") or ""),
        ]
    ).lower()

    for keys, preferred in _KEYWORD_PREFER:
        if all(k in blob for k in keys):
            hit = accept(preferred)
            if hit:
                return hit

    # Fuzzy: match catalog stem against model id/label tokens
    if catalog:
        tokens = [t for t in re.split(r"[^a-z0-9]+", blob) if len(t) >= 3]
        best: tuple[int, str] | None = None
        for arch in catalog:
            an = _norm(arch)
            score = sum(1 for t in tokens if t in an)
            if "i2v" in blob and "i2v" in an:
                score += 2
            if "t2v" in blob and "t2v" in an:
                score += 2
            if score > 0 and (best is None or score > best[0]):
                best = (score, arch)
        if best and best[0] >= 2:
            return best[1]

    # Only invent a default when this is already a Wan2GP-sourced entry
    if model and (model.get("wan2gp") or str(model.get("format") or "").startswith("wan2gp")):
        mode = str(job.get("mode") or "")
        if mode == "t2a":
            return accept("ace_step_v1_5") or accept("stable_audio3_medium")
        if mode in ("t2i", "ref2i"):
            return accept("flux_schnell") or accept("flux")
        if mode in ("t2v",):
            return accept("t2v_1.3B") or accept("t2v")
        if mode in ("i2v", "ref2v"):
            return accept("i2v") or accept("i2v_2_2")
    return None


def _profile_for_vram(vram_gb: float | None) -> str:
    from .mmgp_accel import wan2gp_profile_number

    return str(wan2gp_profile_number(vram_gb))


def _infer_image_mode(job: dict[str, Any], model: dict[str, Any], model_type: str) -> int:
    kind = str(model.get("kind") or "").lower()
    mode = str(job.get("mode") or "")
    mt = model_type.lower()
    if mode == "t2a" or kind == "audio" or any(
        x in mt for x in ("audio", "ace_step", "chatterbox", "music", "tts", "speech")
    ):
        return 0  # audio-centric; Wan2GP still uses image_mode flags per model
    if mode in ("t2i", "ref2i") or kind == "image" or mt.startswith("flux") or "qwen_image" in mt:
        return 1
    return 0


def build_settings(job: dict[str, Any], model: dict[str, Any], model_type: str) -> dict[str, Any]:
    width = int(job.get("width") or 832)
    height = int(job.get("height") or 480)
    frames = int(job.get("frames") or model.get("default_frames") or 81)
    steps = int(job.get("steps") or model.get("default_steps") or 20)
    guidance = job.get("guidance")
    if guidance is None:
        guidance = model.get("default_guidance")
    fps = job.get("fps") or model.get("fps") or ""
    seed = job.get("seed")
    image_mode = _infer_image_mode(job, model, model_type)
    kind = str(model.get("kind") or "").lower()
    mode = str(job.get("mode") or "")

    settings: dict[str, Any] = {
        "model_type": model_type,
        "prompt": job.get("prompt") or "",
        "negative_prompt": job.get("negative_prompt") or "",
        "resolution": f"{width}x{height}",
        "num_inference_steps": steps,
        "repeat_generation": 1,
        "prompt_enhancer": "",
        "image_mode": image_mode,
    }

    if kind == "audio" or mode == "t2a":
        settings["video_length"] = 0
        settings["duration_seconds"] = float(
            job.get("duration_sec") or model.get("default_duration_sec") or 8
        )
    else:
        settings["video_length"] = frames if image_mode == 0 and kind != "image" else frames

    if guidance is not None:
        settings["guidance_scale"] = float(guidance)
    if fps and kind == "video":
        settings["force_fps"] = str(int(fps))
    if seed is not None and str(seed) != "":
        try:
            settings["seed"] = int(seed)
        except Exception:
            settings["seed"] = -1
    else:
        settings["seed"] = -1

    image_path = job.get("image_path") or job.get("reference_path")
    if image_path and Path(str(image_path)).exists():
        resolved = str(Path(image_path).resolve())
        if mode in ("i2v", "ref2v") or "i2v" in model_type.lower():
            settings["image_start"] = resolved
            settings["image_prompt_type"] = "S"
        elif mode in ("ref2i", "ref2v") or "ref" in model_type.lower():
            settings["image_refs"] = [resolved]
            settings["video_prompt_type"] = settings.get("video_prompt_type") or "KI"
        elif mode in ("t2i", "ref2i") and image_mode == 1:
            # Optional init / reference for image models that accept it
            settings["image_refs"] = [resolved]

    return settings


def _parse_progress_line(line: str) -> tuple[str, float, int | None, int | None] | None:
    text = line.strip()
    if not text:
        return None
    m = re.search(r"\[(\d+)\s*/\s*(\d+)\]", text)
    if m:
        step, total = int(m.group(1)), max(1, int(m.group(2)))
        frac = 0.15 + 0.75 * (step / total)
        return (text[:180], min(0.95, frac), step, total)
    low = text.lower()
    if "loading" in low or "preload" in low:
        return (text[:180], 0.08, None, None)
    if "vae" in low and ("decod" in low or "encod" in low):
        return (text[:180], 0.92, None, None)
    if "video saved" in low or "image saved" in low or ("task" in low and "completed" in low):
        return (text[:180], 0.98, None, None)
    if "denois" in low or "generat" in low:
        return (text[:180], 0.25, None, None)
    return None


def _modes_for_architecture(arch: str, meta: dict[str, Any] | None = None) -> list[str]:
    a = arch.lower()
    name = f"{arch} {(meta or {}).get('name') or ''}".lower()
    if any(x in a for x in ("audio", "ace_step", "chatterbox", "music", "tts", "speech")):
        return ["t2a"]
    if a.startswith("flux") or "qwen_image" in a or "image" in a and "i2v" not in a and "t2v" not in a:
        modes = ["t2i"]
        if "edit" in a or "kontext" in a or "ref" in a:
            modes.append("ref2i")
        return modes
    if "upsampler" in a or "upsample" in a:
        return ["upsample_video", "upsample_image"]
    modes = ["t2v"]
    if "i2v" in a or "ti2v" in a or "flf2v" in a or "ref2" in a or "hunyuan_i2v" in a:
        modes = ["i2v", "ref2v", "t2v"] if "t2v" in a or "ti2v" in a else ["i2v", "ref2v"]
    if "ti2v" in a:
        modes = ["t2v", "i2v", "ref2v"]
    if "ltx" in a or "wan" in name or a in {"t2v", "t2v_1.3b", "t2v_2_2", "hunyuan"}:
        if "t2v" not in modes:
            modes.insert(0, "t2v")
        if "i2v" not in modes:
            modes.extend(["i2v", "ref2v"])
    return modes or ["t2v"]


def scan_engine_models() -> list[dict[str, Any]]:
    """Expose every Wan2GP architecture as a StudioNels Generate model when linked."""
    root = wan2gp_root()
    if not root or not (root / "wgp.py").is_file():
        return []
    out: list[dict[str, Any]] = []
    for arch in list_architectures(root):
        meta: dict[str, Any] = {}
        for sub in ("defaults", "finetunes"):
            path = root / sub / f"{arch}.json"
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data.get("model"), dict):
                        meta = data["model"]
                except Exception:
                    pass
                break
        modes = _modes_for_architecture(arch, meta)
        kind = (
            "audio"
            if modes == ["t2a"]
            else "image"
            if "t2i" in modes and "t2v" not in modes and "i2v" not in modes
            else "upsample"
            if any(m.startswith("upsample") for m in modes)
            else "video"
        )
        label = str(meta.get("name") or arch.replace("_", " "))
        out.append(
            {
                "id": f"wgp-{arch}",
                "label": f"{label} (Wan2GP)",
                "modes": modes,
                "hf_id": None,
                "pipeline": "Wan2GP",
                "wan2gp_model_type": arch,
                "wan2gp": True,
                "format": "wan2gp-engine",
                "min_vram_gb": 8,
                "default_steps": 20,
                "default_guidance": 5.0,
                "kind": kind,
                "default_frames": 81,
                "fps": 16,
                "supports_lora": True,
                "tier": "wan2gp",
                "notes": f"Runs on Wan2GP mmgp engine ({arch}).",
            }
        )
    return out


def run_wan2gp_job(
    job: dict[str, Any],
    out_path: Path,
    cb: ProgressCb | None = None,
    *,
    cancel_check: Callable[[], bool] | None = None,
    proc_holder: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run via Wan2GP. Returns result dict, or None if Wan2GP cannot handle this job."""
    from .catalog import get_model
    from .device import detect_device

    info = wan2gp_available()
    if not info.get("available"):
        return None

    model = get_model(job.get("model_id") or "") or {}
    mode = str(job.get("mode") or "")
    # Keep pure local Lanczos in StudioNels
    if str(model.get("pipeline") or "") == "lanczos" or (
        mode.startswith("upsample") and str(model.get("pipeline") or "") == "lanczos"
    ):
        return None

    model_type = map_model_type(job, model)
    if not model_type:
        return None

    root = Path(str(info["root"]))
    py = str(info["python"])
    wgp = root / "wgp.py"
    if not wgp.is_file():
        return None

    # Refresh catalog cache after import
    clear_architecture_cache()

    work = out_path.parent / f"{out_path.name}_wan2gp"
    work.mkdir(parents=True, exist_ok=True)
    settings_path = work / "settings.json"
    output_dir = work / "out"
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = build_settings(job, model, model_type)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    device = detect_device()
    vram = device.get("vram_gb")
    profile = _profile_for_vram(float(vram) if isinstance(vram, (int, float)) else None)
    attention = (os.environ.get("STUDIONELS_WAN2GP_ATTENTION") or "sdpa").strip() or "sdpa"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", str(min(8, os.cpu_count() or 8)))
    env.setdefault("TRITON_DEFAULT_FP_FUSION", "1")
    # Allow first-time weight fetch inside Wan2GP when offline would fail
    if os.environ.get("STUDIONELS_WAN2GP_ONLINE", "").strip() in {"1", "true", "yes"}:
        env.pop("HF_HUB_OFFLINE", None)
    else:
        env.setdefault("HF_HUB_OFFLINE", "1")

    cmd = [
        py,
        str(wgp),
        "--process",
        str(settings_path),
        "--output-dir",
        str(output_dir),
        "--profile",
        profile,
        "--attention",
        attention,
        "--verbose",
        "1",
    ]
    if env.get("HF_HUB_OFFLINE") == "1":
        cmd.append("--offline")

    if cb:
        cb(
            f"Wan2GP engine · {model_type} · profile {profile} · {attention}",
            0.05,
        )

    proc = subprocess.Popen(
        cmd,
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if proc_holder is not None:
        proc_holder["proc"] = proc

    started = time.time()
    last_step = 0
    last_total = max(1, int(settings.get("num_inference_steps") or 20))
    log_tail: list[str] = []

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel_check and cancel_check():
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except Exception:
                    proc.kill()
                raise RuntimeError("Stopped by user")
            line = line.rstrip("\n")
            if line:
                log_tail.append(line)
                if len(log_tail) > 40:
                    log_tail = log_tail[-40:]
            parsed = _parse_progress_line(line)
            if parsed and cb:
                msg, frac, step, total = parsed
                if step is not None:
                    last_step = step
                if total is not None:
                    last_total = total
                elapsed = int(time.time() - started)
                eta = ""
                if last_step >= 1:
                    per = elapsed / last_step
                    left = max(0, int(per * (last_total - last_step)))
                    eta = (
                        f" · ~{left // 60}m{left % 60:02d}s left"
                        if left >= 60
                        else f" · ~{left}s left"
                    )
                cb(
                    f"Wan2GP · step {last_step}/{last_total} · {elapsed}s{eta} · {msg[:100]}",
                    frac,
                )
        code = proc.wait()
    finally:
        if proc_holder is not None:
            proc_holder.pop("proc", None)

    if code != 0:
        detail = "\n".join(log_tail[-12:]) or f"exit {code}"
        raise RuntimeError(f"Wan2GP failed (exit {code}): {detail}")

    media_files = sorted(
        [
            *output_dir.rglob("*.mp4"),
            *output_dir.rglob("*.webm"),
            *output_dir.rglob("*.png"),
            *output_dir.rglob("*.jpg"),
            *output_dir.rglob("*.jpeg"),
            *output_dir.rglob("*.wav"),
            *output_dir.rglob("*.flac"),
            *output_dir.rglob("*.mp3"),
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not media_files:
        raise RuntimeError(
            "Wan2GP finished but no media was written. "
            f"Check model_type={model_type} is installed in Wan2GP. Log:\n"
            + "\n".join(log_tail[-12:])
        )

    src = media_files[0]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dest = out_path.with_suffix(src.suffix)
    shutil.copy2(src, dest)
    thumb = None
    if dest.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        thumb = str(dest)
    else:
        for cand in media_files:
            if cand.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                thumb_dest = dest.with_suffix(".png")
                shutil.copy2(cand, thumb_dest)
                thumb = str(thumb_dest)
                break

    if cb:
        cb("Wan2GP complete", 1.0)
    return {
        "media_path": str(dest),
        "thumb_path": thumb or str(dest),
        "frames": int(settings.get("video_length") or 0),
        "engine": "wan2gp",
        "wan2gp_model_type": model_type,
    }
