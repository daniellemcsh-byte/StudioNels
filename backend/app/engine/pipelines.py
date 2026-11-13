from __future__ import annotations

import math
import struct
import wave
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
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import imageio.v2 as imageio
        import numpy as np

        arrs = [np.asarray(f.convert("RGB")) for f in frames]
        imageio.mimsave(path.with_suffix(".mp4"), arrs, fps=fps)
        frames[0].save(path.with_suffix(".png"))
        return str(path.with_suffix(".mp4"))
    except Exception:
        frames[0].save(path.with_suffix(".png"))
        if len(frames) > 1:
            frames[-1].save(path.with_name(path.stem + "_last.png"))
        return str(path.with_suffix(".png"))


def _write_preview_wav(path: Path, duration_sec: float, seed: int) -> str:
    """Simple synthetic tone bed so audio mode works without weights."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    n = int(rate * max(0.5, duration_sec))
    freq = 110 + (seed % 400)
    with wave.open(str(path.with_suffix(".wav")), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        for i in range(n):
            t = i / rate
            # soft plucky envelope
            env = min(1.0, t * 4) * max(0.0, 1.0 - t / max(duration_sec, 0.01))
            val = int(12000 * env * math.sin(2 * math.pi * freq * t))
            wf.writeframes(struct.pack("<h", val))
    return str(path.with_suffix(".wav"))


def _apply_lora(pipe, job: dict[str, Any], cb: ProgressCb | None) -> None:
    lora = job.get("lora_path")
    if not lora:
        return
    scale = float(job.get("lora_scale") or 0.8)
    _progress(cb, f"Loading LoRA ({scale})…", 0.12)
    try:
        pipe.load_lora_weights(lora)
        if hasattr(pipe, "fuse_lora"):
            pipe.fuse_lora(lora_scale=scale)
        elif hasattr(pipe, "set_adapters"):
            pipe.set_adapters(["default"], adapter_weights=[scale])
    except Exception as exc:  # noqa: BLE001
        _progress(cb, f"LoRA skipped: {exc}", 0.15)


def _upsample_image_file(src: str, out_path: Path, scale: int, cb: ProgressCb | None) -> dict[str, Any]:
    from PIL import Image

    _progress(cb, f"Upsampling image ×{scale}…", 0.2)
    img = Image.open(src).convert("RGB")
    w, h = img.size
    up = img.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    media = _save_image(up, out_path.with_suffix(".png"))
    _progress(cb, "Done", 1.0)
    return {"media_path": media, "thumb_path": media, "frames": 1}


def _upsample_video_file(src: str, out_path: Path, scale: int, fps: int, cb: ProgressCb | None) -> dict[str, Any]:
    from PIL import Image

    _progress(cb, f"Upsampling video ×{scale}…", 0.15)
    # If src is a still/preview strip, treat as image sequence of one.
    if src.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        img = Image.open(src).convert("RGB")
        w, h = img.size
        up = img.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
        media = _save_image(up, out_path.with_suffix(".png"))
        return {"media_path": media, "thumb_path": media, "frames": 1}

    try:
        import imageio.v2 as imageio
        import numpy as np

        reader = imageio.get_reader(src)
        frames = []
        for i, frame in enumerate(reader):
            img = Image.fromarray(frame).convert("RGB")
            w, h = img.size
            frames.append(img.resize((w * scale, h * scale), Image.Resampling.LANCZOS))
            if i % 5 == 0:
                _progress(cb, f"Frame {i}", min(0.9, 0.2 + i * 0.02))
        media = _export_video_frames(frames, out_path, fps=fps)
        thumb = str(Path(media).with_suffix(".png"))
        if frames and not Path(thumb).exists():
            _save_image(frames[0], Path(thumb))
        _progress(cb, "Done", 1.0)
        return {"media_path": media, "thumb_path": thumb if Path(thumb).exists() else media, "frames": len(frames)}
    except Exception:
        # Fallback: write note frame
        img = Image.new("RGB", (768 * scale // 2, 432 * scale // 2), (10, 14, 22))
        media = _save_image(img, out_path.with_suffix(".png"))
        return {"media_path": media, "thumb_path": media, "frames": 1}


def run_diffusers_job(job: dict[str, Any], out_path: Path, cb: ProgressCb | None = None) -> dict[str, Any]:
    """Run a real in-process Diffusers / upsample / audio pipeline."""
    model = get_model(job["model_id"])
    if not model:
        raise ValueError(f"Unknown model {job['model_id']}")

    mode = job["mode"]
    scale = int(model.get("scale") or 2)

    if mode == "upsample_image":
        src = job.get("image_path")
        if not src:
            raise ValueError("upsample_image needs image_path")
        return _upsample_image_file(src, out_path, scale, cb)

    if mode == "upsample_video":
        src = job.get("video_path") or job.get("image_path")
        if not src:
            raise ValueError("upsample_video needs video_path")
        return _upsample_video_file(src, out_path, scale, int(job.get("fps") or 16), cb)

    if model.get("pipeline") == "lanczos":
        # Safety: lanczos models without mode still upsample
        src = job.get("image_path") or job.get("video_path")
        if not src:
            raise ValueError("Upsample needs an input file")
        if mode.endswith("video") or (src and src.lower().endswith((".mp4", ".webm", ".mov"))):
            return _upsample_video_file(src, out_path, scale, int(job.get("fps") or 16), cb)
        return _upsample_image_file(src, out_path, scale, cb)

    import torch

    device_info = detect_device()
    device = device_info["device"] if device_info["ready_for_inference"] else "cpu"
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32

    prompt = job.get("prompt") or ""
    negative = job.get("negative_prompt") or ""
    width = int(job.get("width") or 768)
    height = int(job.get("height") or 432)
    steps = int(job.get("steps") or model.get("default_steps") or 20)
    guidance = float(job.get("guidance") or model.get("default_guidance") or 5.0)
    seed = job.get("seed")
    frames_n = int(job.get("frames") or model.get("default_frames") or 49)
    fps = int(job.get("fps") or model.get("fps") or 16)
    duration_sec = float(job.get("duration_sec") or model.get("default_duration_sec") or 8)
    cpu_offload = bool(job.get("cpu_offload", True))
    generator = None
    if seed is not None:
        generator = torch.Generator(device=device if device != "cpu" else "cpu").manual_seed(int(seed))

    kind = model["kind"]

    if kind == "audio" or mode == "t2a":
        _progress(cb, "Loading audio model…", 0.05)
        # Stable Audio / AudioGen APIs vary — try Diffusers StableAudio first.
        try:
            from diffusers import StableAudioPipeline

            pipe = StableAudioPipeline.from_pretrained(model["hf_id"], torch_dtype=dtype)
            if cpu_offload and device.startswith("cuda"):
                pipe.enable_model_cpu_offload()
            else:
                pipe.to(device)
            _progress(cb, "Generating audio…", 0.25)
            result = pipe(
                prompt,
                negative_prompt=negative or None,
                num_inference_steps=steps,
                audio_end_in_s=duration_sec,
                num_waveforms_per_prompt=1,
                generator=generator,
            )
            audio = result.audios[0]
            import numpy as np
            import soundfile as sf

            out = out_path.with_suffix(".wav")
            out.parent.mkdir(parents=True, exist_ok=True)
            # audios may be torch tensor
            arr = audio.T.float().cpu().numpy() if hasattr(audio, "T") else np.asarray(audio)
            sf.write(str(out), arr, result.sr if hasattr(result, "sr") else 44100)
            _progress(cb, "Done", 1.0)
            return {"media_path": str(out), "thumb_path": None, "frames": 0}
        except Exception:
            # Fall through to preview tone if model API mismatches
            media = _write_preview_wav(out_path, duration_sec, int(seed or 1))
            return {"media_path": media, "thumb_path": None, "frames": 0, "preview": True}

    _progress(cb, "Loading pipeline weights…", 0.05)
    pipe = _build_pipeline(model, device, dtype, cpu_offload)
    _apply_lora(pipe, job, cb)
    _progress(cb, "Generating…", 0.2)

    image_in = _load_image(job.get("image_path"))
    ref_in = _load_image(job.get("reference_path"))
    conditioning = image_in or ref_in

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

    kwargs = {
        "prompt": prompt,
        "num_inference_steps": steps,
        "guidance_scale": guidance if guidance else 1.0,
        "generator": generator,
    }
    if negative:
        kwargs["negative_prompt"] = negative

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
    try:
        pipe = DiffusionPipeline.from_pretrained(hf_id, torch_dtype=dtype)
    except Exception:
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
    """Mode-aware preview when weights/torch aren't ready."""
    from PIL import Image, ImageDraw, ImageFont
    import colorsys
    import hashlib

    mode = job["mode"]
    model = get_model(job["model_id"]) or {}
    scale = int(model.get("scale") or 2)
    seed = int(job.get("seed") or int(hashlib.sha256(job["id"].encode()).hexdigest()[:8], 16))

    if mode == "t2a":
        _progress(cb, "Preview audio…", 0.2)
        dur = float(job.get("duration_sec") or 6)
        media = _write_preview_wav(out_path, dur, seed)
        _progress(cb, "Done", 1.0)
        return {"media_path": media, "thumb_path": None, "frames": 0, "preview": True}

    if mode == "upsample_image" and job.get("image_path"):
        return _upsample_image_file(job["image_path"], out_path, scale, cb)

    if mode == "upsample_video" and (job.get("video_path") or job.get("image_path")):
        return _upsample_video_file(
            job.get("video_path") or job["image_path"],
            out_path,
            scale,
            int(job.get("fps") or 12),
            cb,
        )

    _progress(cb, "Preview engine (install ROCm PyTorch + model for real gen)…", 0.1)
    hue = (seed % 1000) / 1000
    rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.55, 0.55))
    width = int(job.get("width") or 768)
    height = int(job.get("height") or 432)
    prompt = (job.get("prompt") or "")[:60]
    image_modes = ("t2i", "ref2i", "upsample_image")
    frames_n = 1 if mode in image_modes else min(int(job.get("frames") or 16), 24)

    font = ImageFont.load_default()
    pil_frames = []
    for i in range(frames_n):
        img = Image.new("RGB", (width, height), rgb)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, width, 40], fill=(5, 8, 14))
        draw.rectangle([0, height - 40, width, height], fill=(5, 8, 14))
        if frames_n > 1:
            bar_w = int((i + 1) / frames_n * (width - 40))
            draw.rectangle([20, height // 2 - 6, 20 + bar_w, height // 2 + 6], fill=(57, 255, 199))
        if job.get("image_path") or job.get("reference_path") or job.get("lora_path"):
            draw.ellipse([width - 70, 50, width - 30, 90], outline=(255, 61, 206), width=3)
        q = job.get("quality") or "balanced"
        draw.text((20, 12), f"Framewright · {mode.upper()} · {q}", fill=(57, 255, 199), font=font)
        draw.text((20, height // 2 + 20), prompt or job.get("model_id", ""), fill=(242, 247, 255), font=font)
        draw.text((20, height - 28), f"preview · seed {seed}", fill=(154, 168, 199), font=font)
        pulse = int(20 + 10 * math.sin(i / max(frames_n - 1, 1) * math.pi))
        draw.rectangle([20, 50, 20 + pulse, 54], fill=(255, 61, 206))
        pil_frames.append(img)
        _progress(cb, f"Preview frame {i + 1}/{frames_n}", 0.1 + 0.8 * (i + 1) / frames_n)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if mode in image_modes:
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
