"""Drive Wan2GP's real generate path (mmgp + kernels) from StudioNels.

Stock Diffusers is a fallback. When a Wan2GP install is linked in Settings,
Generate submits a settings JSON to `wgp.py --process` so jobs use the same
engine that finishes in ~1 minute locally.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from ..storage import load_settings


ProgressCb = Callable[[str, float], None]

# StudioNels catalog id → Wan2GP model_type / architecture id
_MODEL_MAP: dict[str, str] = {
    "wan21-t2v-1.3b": "t2v_1.3B",
    "wan21-t2v-14b": "t2v",
    "wan21-i2v-14b-480p": "i2v",
    "wan21-i2v-14b-720p": "i2v_720p",
    "wan21-flf2v-14b-720p": "flf2v_720p",
    "wan22-t2v-a14b": "t2v_2_2",
    "wan22-i2v-a14b": "i2v_2_2",
    "wan22-ti2v-5b": "ti2v_2_2",
    "ltx2.3-22b-distilled-diffusers": "ltx2_22B_distilled",
    "ltx2.3-22b-distilled-v11-diffusers": "ltx2_22B_distilled_1_1",
    "ltx2.5-diffusers": "ltx2_25_22B",
    "wan2gp-ltx2.3-22b-distilled": "ltx2_22B_distilled",
    "wan2gp-ltx2.3-22b-distilled-1.1": "ltx2_22B_distilled_1_1",
}


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
    # Env override for Pinokio layouts
    env = (os.environ.get("STUDIONELS_WAN2GP_ROOT") or "").strip()
    if env:
        candidates.insert(0, Path(env).expanduser())

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
        if (root / "ckpts").is_dir() and (root / "wgp.py").is_file():
            return root
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
    ):
        cand = root / rel
        if cand.is_file():
            return str(cand)
    # Pinokio often nests env one level up from the app folder
    for rel in (
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
    return {"available": True, "root": str(root), "python": py}


def map_model_type(job: dict[str, Any], model: dict[str, Any] | None) -> str | None:
    mid = str(job.get("model_id") or (model or {}).get("id") or "")
    if model and model.get("wan2gp_model_type"):
        return str(model["wan2gp_model_type"])
    if mid in _MODEL_MAP:
        return _MODEL_MAP[mid]
    # Wan2GP-imported packs often carry architecture in notes/id
    if mid.startswith("wan2gp-"):
        # wan2gp-ltx2.3-22b-distilled-1.1 → try map
        if mid in _MODEL_MAP:
            return _MODEL_MAP[mid]
        if "ltx2.3" in mid and "1.1" in mid:
            return "ltx2_22B_distilled_1_1"
        if "ltx2.3" in mid:
            return "ltx2_22B_distilled"
        if "ltx2.5" in mid or "ltx25" in mid:
            return "ltx2_25_22B"
    # Heuristic from label / pipeline
    label = f"{mid} {(model or {}).get('label') or ''} {(model or {}).get('pipeline') or ''}".lower()
    if "1.3b" in label and "t2v" in label:
        return "t2v_1.3B"
    if "ti2v" in label:
        return "ti2v_2_2"
    if "wan2.2" in label or "wan22" in label:
        return "i2v_2_2" if ("i2v" in label or job.get("mode") in ("i2v", "ref2v")) else "t2v_2_2"
    if "flf2v" in label:
        return "flf2v_720p"
    if "i2v" in label and "720" in label:
        return "i2v_720p"
    if "i2v" in label:
        return "i2v"
    if "t2v" in label or "wan" in label:
        return "t2v"
    if "ltx" in label and "distill" in label:
        return "ltx2_22B_distilled_1_1" if "1.1" in label else "ltx2_22B_distilled"
    return None


def _profile_for_vram(vram_gb: float | None) -> str:
    if vram_gb is None:
        return "3"
    if vram_gb >= 24:
        return "1"  # HighRAM_HighVRAM — fastest on R9700-class
    if vram_gb >= 16:
        return "3"
    if vram_gb >= 10:
        return "2"
    return "4"


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
    settings: dict[str, Any] = {
        "model_type": model_type,
        "prompt": job.get("prompt") or "",
        "negative_prompt": job.get("negative_prompt") or "",
        "resolution": f"{width}x{height}",
        "video_length": frames,
        "num_inference_steps": steps,
        "repeat_generation": 1,
        "prompt_enhancer": "",
    }
    if guidance is not None:
        settings["guidance_scale"] = float(guidance)
    if fps:
        settings["force_fps"] = str(int(fps))
    if seed is not None and str(seed) != "":
        try:
            settings["seed"] = int(seed)
        except Exception:
            settings["seed"] = -1
    else:
        settings["seed"] = -1

    # Image conditioning
    image_path = job.get("image_path") or job.get("reference_path")
    mode = str(job.get("mode") or "")
    if image_path and Path(str(image_path)).exists() and mode in ("i2v", "ref2v", "ref2i", "ti2v"):
        settings["image_start"] = str(Path(image_path).resolve())
        settings["image_prompt_type"] = "S"  # start image
    return settings


def _parse_progress_line(line: str) -> tuple[str, float, int | None, int | None] | None:
    """Return (message, frac, step, total) from Wan2GP CLI stdout."""
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
    if "video saved" in low or "task" in low and "completed" in low:
        return (text[:180], 0.98, None, None)
    if "denois" in low or "generat" in low:
        return (text[:180], 0.25, None, None)
    return None


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
    # Skip pure upsample / audio-only for now (Wan2GP path is video/image gen)
    mode = str(job.get("mode") or "")
    if mode.startswith("upsample") or mode == "t2a":
        return None

    model_type = map_model_type(job, model)
    if not model_type:
        return None

    root = Path(str(info["root"]))
    py = str(info["python"])
    wgp = root / "wgp.py"
    if not wgp.is_file():
        return None

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
    # Same ROCm / BLAS defaults Wan2GP sets in wgp.py
    env.setdefault("TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", str(min(8, os.cpu_count() or 8)))
    env.setdefault("TRITON_DEFAULT_FP_FUSION", "1")
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
        "--offline",
    ]

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
                    eta = f" · ~{left // 60}m{left % 60:02d}s left" if left >= 60 else f" · ~{left}s left"
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

    # Pick newest media from output_dir
    media_files = sorted(
        [
            *output_dir.rglob("*.mp4"),
            *output_dir.rglob("*.webm"),
            *output_dir.rglob("*.png"),
            *output_dir.rglob("*.jpg"),
            *output_dir.rglob("*.jpeg"),
            *output_dir.rglob("*.wav"),
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
        # Prefer a sibling png if Wan2GP wrote one
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
