from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

from .catalog import get_model
from .device import detect_device


ProgressCb = Callable[[str, float], None]


def _progress(cb: ProgressCb | None, message: str, frac: float) -> None:
    if cb:
        cb(message, max(0.0, min(1.0, frac)))


def _load_image(path: str | None):
    if not path:
        return None
    from PIL import Image

    return Image.open(path).convert("RGB")


def _save_image(img, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return str(path)


def _export_video_frames(frames, path: Path, fps: int = 16) -> str:
    """Save MP4 if imageio/ffmpeg available, else a sprite strip PNG + first frame."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import imageio.v2 as imageio
        import numpy as np

        arrs = [np.asarray(f.convert("RGB")) for f in frames]
        imageio.mimsave(path.with_suffix(".mp4"), arrs, fps=fps)
        frames[0].save(path.with_suffix(".png"))
        return str(path.with_suffix(".mp4"))
    except Exception:
        # Fallback: save first + last frames
        frames[0].save(path.with_suffix(".png"))
        if len(frames) > 1:
            frames[-1].save(path.with_name(path.stem + "_last.png"))
        return str(path.with_suffix(".png"))


def run_diffusers_job(job: dict[str, Any], out_path: Path, cb: ProgressCb | None = None) -> dict[str, Any]:
    """Run a real in-process Diffusers pipeline (Wan / SDXL / LTX family)."""
    import torch

    model = get_model(job["model_id"])
    if not model:
        raise ValueError(f"Unknown model {job['model_id']}")

    device_info = detect_device()
    device = device_info["device"] if device_info["ready_for_inference"] else "cpu"
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32

    mode = job["mode"]
    prompt = job.get("prompt") or ""
    negative = job.get("negative_prompt") or ""
    width = int(job.get("width") or 768)
    height = int(job.get("height") or 432)
    steps = int(job.get("steps") or model.get("default_steps") or 20)
    guidance = float(job.get("guidance") or model.get("default_guidance") or 5.0)
    seed = job.get("seed")
    frames_n = int(job.get("frames") or model.get("default_frames") or 49)
    fps = int(job.get("fps") or model.get("fps") or 16)
    cpu_offload = bool(job.get("cpu_offload", True))
    generator = None
    if seed is not None:
        generator = torch.Generator(device=device if device != "cpu" else "cpu").manual_seed(int(seed))

    _progress(cb, "Loading pipeline weights…", 0.05)
    pipe = _build_pipeline(model, device, dtype, cpu_offload)
    _progress(cb, "Generating…", 0.2)

    image_in = _load_image(job.get("image_path"))
    ref_in = _load_image(job.get("reference_path"))
    conditioning = image_in or ref_in

    kind = model["kind"]
    if kind == "image":
        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "num_inference_steps": steps,
            "width": width,
            "height": height,
            "generator": generator,
        }
        if guidance and guidance > 0:
            kwargs["guidance_scale"] = guidance
        if negative:
            kwargs["negative_prompt"] = negative
        # ref2i: pass image when pipeline supports it (IP-Adapter / img2img style fallback)
        if mode in ("ref2i",) and conditioning is not None:
            try:
                result = pipe(
                    prompt=prompt,
                    image=conditioning.resize((width, height)),
                    strength=float(job.get("strength") or 0.65),
                    num_inference_steps=steps,
                    guidance_scale=max(guidance, 1.0),
                    generator=generator,
                )
            except TypeError:
                result = pipe(**kwargs)
        else:
            result = pipe(**kwargs)
        out = result.images[0]
        media = _save_image(out, out_path.with_suffix(".png"))
        _progress(cb, "Done", 1.0)
        return {"media_path": media, "thumb_path": media, "frames": 1}

    # Video
    kwargs = {
        "prompt": prompt,
        "num_inference_steps": steps,
        "guidance_scale": guidance if guidance else 1.0,
        "generator": generator,
    }
    if negative:
        kwargs["negative_prompt"] = negative

    # Different pipelines accept different arg names — try progressive fallbacks.
    tried_errors: list[str] = []
    result = None
    attempts = []
    if mode in ("i2v", "ref2v") and conditioning is not None:
        attempts.append({**kwargs, "image": conditioning, "num_frames": frames_n})
        attempts.append({**kwargs, "image": conditioning})
    attempts.append({**kwargs, "num_frames": frames_n, "height": height, "width": width})
    attempts.append(kwargs)

    for attempt in attempts:
        try:
            result = pipe(**attempt)
            break
        except TypeError as exc:
            tried_errors.append(str(exc))
            continue
    if result is None:
        raise RuntimeError("Pipeline call failed: " + " | ".join(tried_errors[:3]))

    video_frames = getattr(result, "frames", None) or getattr(result, "images", None)
    if video_frames is None:
        raise RuntimeError("Pipeline returned no frames")
    # Some pipelines return list[list[PIL]]
    if isinstance(video_frames, list) and video_frames and isinstance(video_frames[0], list):
        video_frames = video_frames[0]

    media = _export_video_frames(video_frames, out_path, fps=fps)
    thumb = str(Path(media).with_suffix(".png"))
    if not Path(thumb).exists() and video_frames:
        _save_image(video_frames[0], Path(thumb))
    _progress(cb, "Done", 1.0)
    return {
        "media_path": media,
        "thumb_path": thumb if Path(thumb).exists() else media,
        "frames": len(video_frames),
    }


def _build_pipeline(model: dict[str, Any], device: str, dtype, cpu_offload: bool):
    from diffusers import DiffusionPipeline

    hf_id = model["hf_id"]
    # Prefer Auto / generic load so catalog stays flexible across versions.
    try:
        pipe = DiffusionPipeline.from_pretrained(hf_id, torch_dtype=dtype)
    except Exception:
        # Retry float32 for picky AMD builds
        import torch

        pipe = DiffusionPipeline.from_pretrained(hf_id, torch_dtype=torch.float32)

    if cpu_offload and device.startswith("cuda"):
        try:
            pipe.enable_model_cpu_offload()
        except Exception:
            pipe.to(device)
    else:
        pipe.to(device)

    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass
    try:
        pipe.vae.enable_slicing()
    except Exception:
        pass
    return pipe


def run_preview_job(job: dict[str, Any], out_path: Path, cb: ProgressCb | None = None) -> dict[str, Any]:
    """
    Local preview when weights/torch aren't ready — still mode-aware so the
    studio UI (t2i/t2v/i2v/ref2i/ref2v) is exerciseable without ComfyUI.
    """
    from PIL import Image, ImageDraw, ImageFont
    import colorsys
    import hashlib

    _progress(cb, "Preview engine (install PyTorch+ROCm + model for real gen)…", 0.1)
    seed = int(job.get("seed") or int(hashlib.sha256(job["id"].encode()).hexdigest()[:8], 16))
    hue = (seed % 1000) / 1000
    rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.4, 0.7))
    width = int(job.get("width") or 768)
    height = int(job.get("height") or 432)
    mode = job["mode"]
    prompt = (job.get("prompt") or "")[:60]
    frames_n = 1 if mode in ("t2i", "ref2i") else min(int(job.get("frames") or 16), 24)

    font = ImageFont.load_default()
    pil_frames = []
    for i in range(frames_n):
        img = Image.new("RGB", (width, height), rgb)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, width, 40], fill=(20, 28, 24))
        draw.rectangle([0, height - 40, width, height], fill=(20, 28, 24))
        # Motion bar for video modes
        if frames_n > 1:
            bar_w = int((i + 1) / frames_n * (width - 40))
            draw.rectangle([20, height // 2 - 6, 20 + bar_w, height // 2 + 6], fill=(216, 245, 106))
        # Reference/image badge
        if job.get("image_path") or job.get("reference_path"):
            draw.ellipse([width - 70, 50, width - 30, 90], outline=(216, 245, 106), width=3)
        draw.text((20, 12), f"Framewright · {mode.upper()}", fill=(216, 245, 106), font=font)
        draw.text((20, height // 2 + 20), prompt or job.get("model_id", ""), fill=(250, 246, 238), font=font)
        draw.text((20, height - 28), f"preview · seed {seed}", fill=(180, 190, 185), font=font)
        # Subtle pulse
        pulse = int(20 + 10 * math.sin(i / max(frames_n - 1, 1) * math.pi))
        draw.rectangle([20, 50, 20 + pulse, 54], fill=(126, 208, 182))
        pil_frames.append(img)
        _progress(cb, f"Preview frame {i + 1}/{frames_n}", 0.1 + 0.8 * (i + 1) / frames_n)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if mode in ("t2i", "ref2i"):
        media = _save_image(pil_frames[0], out_path.with_suffix(".png"))
        _progress(cb, "Done", 1.0)
        return {"media_path": media, "thumb_path": media, "frames": 1, "preview": True}

    media = _export_video_frames(pil_frames, out_path, fps=int(job.get("fps") or 12))
    thumb = str(Path(media).with_suffix(".png"))
    if not Path(thumb).exists():
        thumb = _save_image(pil_frames[0], Path(thumb))
    _progress(cb, "Done", 1.0)
    return {
        "media_path": media,
        "thumb_path": thumb,
        "frames": len(pil_frames),
        "preview": True,
    }
