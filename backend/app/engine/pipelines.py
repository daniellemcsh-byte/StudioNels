from __future__ import annotations

import math
import struct
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable

import shutil
import subprocess

from .catalog import get_model, get_text_encoder_preset
from .device import detect_device
from .queue_store import models_dir


ProgressCb = Callable[[str, float], None]


def snap_dim(value: int, multiple: int = 32, minimum: int = 64) -> int:
    """Round size to nearest multiple (LTX / Wan need ÷32). Prefer round-up when mid."""
    value = max(int(value or minimum), minimum)
    if multiple <= 1:
        return value
    down = (value // multiple) * multiple
    up = down + multiple
    if value - down < up - value and down >= minimum:
        return down
    return max(up, minimum)


def snap_frame_size(width: int, height: int, *, multiple: int = 32) -> tuple[int, int]:
    return snap_dim(width, multiple), snap_dim(height, multiple)


def _progress(cb: ProgressCb | None, message: str, frac: float) -> None:
    if cb:
        cb(message, max(0.0, min(1.0, frac)))


def _call_pipe_with_progress(
    pipe: Any,
    kwargs: dict[str, Any],
    cb: ProgressCb | None,
    *,
    steps: int,
    label: str = "Generating",
) -> Any:
    """Run pipe(**kwargs) with step callbacks + heartbeat so UI doesn't sit at 20%."""
    total = max(1, int(steps or 1))
    state = {"step": 0, "done": False}
    stop = threading.Event()
    started = time.time()

    def _report(i: int) -> None:
        i = max(0, min(int(i), total))
        state["step"] = i
        frac = 0.22 + 0.68 * min(1.0, i / total)
        elapsed = int(time.time() - started)
        eta = ""
        if i >= 1:
            per = elapsed / i
            left = max(0, int(per * (total - i)))
            if left >= 60:
                eta = f" · ~{left // 60}m{left % 60:02d}s left"
            else:
                eta = f" · ~{left}s left"
        _progress(
            cb,
            f"{label} · step {i}/{total} · {elapsed}s elapsed{eta}",
            frac,
        )

    def on_step_end(pipe_self=None, step_index=None, timestep=None, callback_kwargs=None, **_kw):
        # Diffusers callback_on_step_end — step_index is 0-based
        idx = step_index
        if idx is None and isinstance(callback_kwargs, dict):
            idx = callback_kwargs.get("i", callback_kwargs.get("step_index"))
        try:
            i = int(idx) + 1 if idx is not None else state["step"] + 1
        except Exception:
            i = state["step"] + 1
        _report(i)
        return callback_kwargs if isinstance(callback_kwargs, dict) else {}

    def on_step_legacy(step: int, timestep, latents):
        try:
            _report(int(step) + 1)
        except Exception:
            _report(state["step"] + 1)
        return latents

    call_kwargs = dict(kwargs)
    # Try modern callback first; fall back inside TypeError handler
    call_kwargs["callback_on_step_end"] = on_step_end

    def beat() -> None:
        while not stop.wait(2.5):
            if state["done"]:
                return
            i = int(state["step"] or 0)
            elapsed = int(time.time() - started)
            if i > 0:
                _report(i)
                continue
            # Soft crawl before first callback fires (ROCm can sit quiet a while)
            soft = 0.22 + min(0.45, elapsed / 180.0)
            hint = ""
            if elapsed >= 90:
                hint = " · still no step — check Memory=GPU VRAM; Diffusers ≠ Wan2GP speed"
            _progress(
                cb,
                f"{label} · step 0/{total} · starting denoise · {elapsed}s{hint}",
                min(0.65, soft),
            )

    if cb:
        t = threading.Thread(target=beat, name="gen-beat", daemon=True)
        t.start()
    try:
        try:
            return pipe(**call_kwargs)
        except TypeError:
            # Older pipes: callback + callback_steps
            legacy = {
                k: v
                for k, v in kwargs.items()
                if k not in {"callback_on_step_end", "callback", "callback_steps"}
            }
            legacy["callback"] = on_step_legacy
            legacy["callback_steps"] = 1
            try:
                return pipe(**legacy)
            except TypeError:
                clean = {
                    k: v
                    for k, v in kwargs.items()
                    if k not in {"callback_on_step_end", "callback", "callback_steps"}
                }
                return pipe(**clean)
    finally:
        state["done"] = True
        stop.set()
        if state["step"] < total:
            _report(total)


def _heartbeat_while(
    cb: ProgressCb | None,
    label: str,
    start_frac: float,
    end_frac: float,
    fn: Callable[[], Any],
    *,
    max_sec: int = 360,
) -> Any:
    """Keep job progress moving while a long blocking load runs (ROCm first load).

    Raises RuntimeError if fn has not returned within max_sec — otherwise a stuck
    from_pretrained can sit at ~18% forever while the heartbeat keeps the UI alive.
    """
    if not cb:
        box: dict[str, Any] = {}

        def _run() -> None:
            try:
                box["value"] = fn()
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        t0 = threading.Thread(target=_run, name="studionels-load", daemon=True)
        t0.start()
        t0.join(timeout=max_sec)
        if t0.is_alive():
            raise RuntimeError(
                f"{label} timed out after {max_sec // 60} min. "
                "Weights never finished loading — Stop, pick Wan 1.3B / LTX Distilled "
                "(or finish the model Download in Models), then retry."
            )
        if "error" in box:
            raise box["error"]
        return box.get("value")

    stop = threading.Event()
    started = time.time()
    box: dict[str, Any] = {}

    def beat() -> None:
        frac = start_frac
        while not stop.wait(2.0):
            elapsed = int(time.time() - started)
            frac = min(end_frac, frac + (end_frac - start_frac) / 50.0)
            hint = " · still in RAM (VRAM fills after this step)"
            if elapsed >= 90:
                hint = " · if this passes 5–6 min, Stop and use a smaller Ready model (or link Wan2GP)"
            _progress(
                cb,
                f"{label} ({elapsed}s — first AMD load){hint}…",
                frac,
            )

    def _run() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    beat_t = threading.Thread(target=beat, name="studionels-load-beat", daemon=True)
    work_t = threading.Thread(target=_run, name="studionels-load", daemon=True)
    beat_t.start()
    work_t.start()
    work_t.join(timeout=max_sec)
    stop.set()
    beat_t.join(timeout=0.2)
    if work_t.is_alive():
        raise RuntimeError(
            f"{label} timed out after {max_sec // 60} min. "
            "Diffusers never finished reading weights (often a huge HF download or incomplete "
            "local folder). Stop → Models → ensure the model shows Ready, prefer Wan 1.3B / "
            "LTX Distilled, then Generate again."
        )
    if "error" in box:
        raise box["error"]
    return box.get("value")


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
    # Always write last frame sidecar for video continuation (i2v chain)
    if frames:
        try:
            frames[-1].save(path.with_name(path.stem + "_last.png"))
        except Exception:
            pass
    try:
        import imageio.v2 as imageio
        import numpy as np

        arrs = [np.asarray(f.convert("RGB")) for f in frames]
        imageio.mimsave(path.with_suffix(".mp4"), arrs, fps=fps)
        frames[0].save(path.with_suffix(".png"))
        return str(path.with_suffix(".mp4"))
    except Exception:
        frames[0].save(path.with_suffix(".png"))
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
    scale = float(job.get("lora_scale") if job.get("lora_scale") is not None else 0.8)
    scale = max(0.0, min(2.0, scale))
    if scale <= 0.001:
        _progress(cb, "LoRA strength 0 — skipped", 0.12)
        return
    _progress(cb, f"Loading LoRA (strength {scale:.2f})…", 0.12)
    try:
        pipe.load_lora_weights(lora)
        applied = False
        if hasattr(pipe, "set_adapters"):
            try:
                pipe.set_adapters(["default"], adapter_weights=[scale])
                applied = True
            except Exception:
                pass
        if not applied and hasattr(pipe, "fuse_lora"):
            try:
                pipe.fuse_lora(lora_scale=scale)
                applied = True
            except TypeError:
                pipe.fuse_lora()
                applied = True
        # Stash for callers that honor cross_attention_kwargs at inference time
        job["_lora_scale"] = scale
        _progress(cb, f"LoRA ready · strength {scale:.2f}", 0.15)
    except Exception as exc:  # noqa: BLE001
        _progress(cb, f"LoRA skipped: {exc}", 0.15)


def mux_audio_onto_video(
    video_path: str,
    audio_path: str,
    out_path: Path | None = None,
    cb: ProgressCb | None = None,
) -> str:
    """Combine a silent/generated video with an audio bed via ffmpeg."""
    video = Path(video_path)
    audio = Path(audio_path)
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video}")
    if not audio.exists():
        raise FileNotFoundError(f"Audio not found: {audio}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — install ffmpeg to add audio to video.")

    dest = out_path or video.with_name(f"{video.stem}_with_audio.mp4")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _progress(cb, "Muxing audio onto video…", 0.85)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        # Re-encode fallback when stream copy fails
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not dest.exists():
            err = (proc.stderr or proc.stdout or "ffmpeg failed")[-800:]
            raise RuntimeError(f"Could not mux audio: {err}")
    _progress(cb, "Audio attached", 0.95)
    return str(dest)


def _apply_text_encoder(pipe, job: dict[str, Any], device: str, dtype, cb: ProgressCb | None) -> None:
    choice = (job.get("text_encoder") or "auto").strip()
    preset = get_text_encoder_preset(choice)
    if not preset or not preset.get("hf_id"):
        return
    hf_id = str(preset["hf_id"])
    slot = str(preset.get("slot") or "text_encoder")
    _progress(cb, f"Loading text encoder ({preset.get('label') or hf_id})…", 0.08)
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer, CLIPTextModel, T5EncoderModel

        # Prefer known encoder classes; fall back to AutoModel.
        encoder = None
        last_err: Exception | None = None
        for loader in (CLIPTextModel, T5EncoderModel, AutoModel):
            try:
                encoder = loader.from_pretrained(hf_id, torch_dtype=dtype)
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        if encoder is None:
            raise RuntimeError(str(last_err or "encoder load failed"))

        tokenizer = None
        try:
            tokenizer = AutoTokenizer.from_pretrained(hf_id)
        except Exception:
            tokenizer = None

        moved = encoder.to(device if not str(device).startswith("cuda") or not job.get("cpu_offload") else "cpu")
        if hasattr(pipe, slot):
            setattr(pipe, slot, moved)
        elif hasattr(pipe, "text_encoder"):
            pipe.text_encoder = moved
        else:
            _progress(cb, "Pipeline has no text_encoder slot — left as model default.", 0.1)
            return

        # Match tokenizer slot when present
        tok_slot = "tokenizer_2" if slot.endswith("_2") else "tokenizer"
        if tokenizer is not None and hasattr(pipe, tok_slot):
            setattr(pipe, tok_slot, tokenizer)
        elif tokenizer is not None and hasattr(pipe, "tokenizer"):
            pipe.tokenizer = tokenizer
        _progress(cb, f"Text encoder → {preset.get('label') or hf_id}", 0.11)
    except Exception as exc:  # noqa: BLE001
        _progress(cb, f"Text encoder swap skipped: {exc}", 0.11)


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

    from .memory import resolve_memory_for_job

    device_info = detect_device()
    device = device_info["device"] if device_info["ready_for_inference"] else "cpu"
    mem = resolve_memory_for_job(job)
    dtype_name = str(mem.get("dtype") or "bfloat16")
    if not device.startswith("cuda"):
        dtype = torch.float32
        mem["placement"] = "cpu"
    elif dtype_name in ("float16", "fp16"):
        dtype = torch.float16
    elif dtype_name in ("float32", "fp32"):
        dtype = torch.float32
    else:
        dtype = torch.bfloat16

    prompt = job.get("prompt") or ""
    negative = job.get("negative_prompt") or ""
    raw_w = int(job.get("width") or 768)
    raw_h = int(job.get("height") or 448)
    # LTX-2 / Wan / most DiT video pipes require ÷32 (and often ÷64 for latents)
    multiple = 32
    pipe_name = str(model.get("pipeline") or "").lower()
    if "ltx" in pipe_name or "wan" in pipe_name or model.get("kind") == "video":
        multiple = 32
    width, height = snap_frame_size(raw_w, raw_h, multiple=multiple)
    if (width, height) != (raw_w, raw_h):
        _progress(
            cb,
            f"Snapped size {raw_w}×{raw_h} → {width}×{height} (must be ÷{multiple})",
            0.04,
        )
        job["width"] = width
        job["height"] = height
    steps = int(job.get("steps") or model.get("default_steps") or 20)
    guidance = float(
        job.get("guidance")
        if job.get("guidance") is not None
        else (model.get("default_guidance") if model.get("default_guidance") is not None else 5.0)
    )
    # Distilled LTX-2 family: keep fast defaults unless user overrode steps/guidance
    if model.get("distilled") and job.get("steps") is None:
        steps = int(model.get("default_steps") or 8)
    if model.get("distilled") and job.get("guidance") is None:
        guidance = float(model.get("default_guidance") if model.get("default_guidance") is not None else 1.0)
    seed = job.get("seed")
    frames_n = int(job.get("frames") or model.get("default_frames") or 49)
    fps = int(job.get("fps") or model.get("fps") or 16)
    duration_sec = float(job.get("duration_sec") or model.get("default_duration_sec") or 8)
    cpu_offload = bool(mem.get("cpu_offload", job.get("cpu_offload", True)))
    generator = None
    if seed is not None:
        generator = torch.Generator(device=device if device != "cpu" else "cpu").manual_seed(int(seed))

    kind = model["kind"]
    # Big AMD cards often keep the Low-VRAM preset by mistake — sequential offload
    # can sit at 20% for tens of minutes while Wan2GP finishes in ~1 min.
    vram = device_info.get("vram_gb")
    placement = str(mem.get("placement") or "")
    # Large cards: Low-VRAM sequential offload can look "stuck at 20%" for 40+ min
    # while Wan2GP finishes in ~1 min. Prefer resident GPU unless already on GPU/CPU.
    if (
        isinstance(vram, (int, float))
        and float(vram) >= 20
        and placement in {"sequential_cpu_offload", "model_cpu_offload"}
    ):
        mem = dict(mem)
        mem["placement"] = "gpu"
        mem["placement_label"] = "GPU VRAM (auto — large card)"
        mem["cpu_offload"] = False
        mem["attention_slicing"] = False
        mem["vae_slicing"] = False
        mem["vae_tiling"] = False
        mem["text_encoder_on_cpu"] = False
        cpu_offload = False
        _progress(
            cb,
            f"Auto memory → GPU VRAM ({vram} GB detected; offload was stalling Wan/LTX)",
            0.03,
        )
    _progress(
        cb,
        f"Memory: {mem.get('placement_label') or mem.get('placement')} · {dtype_name}",
        0.03,
    )

    if kind == "audio" or mode == "t2a":
        _progress(cb, "Loading audio model…", 0.05)
        # Stable Audio / AudioGen APIs vary — try Diffusers StableAudio first.
        try:
            from diffusers import StableAudioPipeline
            from .memory import apply_memory_to_pipeline

            pipe = StableAudioPipeline.from_pretrained(model["hf_id"], torch_dtype=dtype)
            apply_memory_to_pipeline(pipe, device, mem)
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

    # Warm cache (engine daemon): skip multi-minute reload when model matches
    pipe = None
    if job.get("warm_cache"):
        try:
            from .pipe_cache import cache_key, get as cache_get

            dtype_name = str(getattr(dtype, "__name__", None) or dtype)
            key = cache_key(str(model.get("id") or job.get("model_id") or ""), mem, dtype_name)
            pipe = cache_get(key)
            if pipe is not None:
                _progress(cb, "Warm model ready (skipped reload)…", 0.18)
        except Exception:
            pipe = None
    if pipe is None:
        _progress(cb, "Loading pipeline weights…", 0.05)
        pipe = _heartbeat_while(
            cb,
            "Loading pipeline weights",
            0.05,
            0.18,
            lambda: _build_pipeline(model, device, dtype, cpu_offload, mem, cb=cb),
            max_sec=6 * 60,
        )
        if job.get("warm_cache") and pipe is not None:
            try:
                from .pipe_cache import cache_key, put as cache_put

                dtype_name = str(getattr(dtype, "__name__", None) or dtype)
                key = cache_key(str(model.get("id") or job.get("model_id") or ""), mem, dtype_name)
                cache_put(key, pipe, label=str(model.get("label") or model.get("id") or key))
            except Exception:
                pass
    # When TE should stay on CPU for VRAM savings
    te_job = dict(job)
    if mem.get("text_encoder_on_cpu"):
        te_job["cpu_offload"] = True
    _apply_text_encoder(pipe, te_job, device, dtype, cb)
    _apply_lora(pipe, job, cb)
    place = (mem or {}).get("placement") or "unknown"
    _progress(
        cb,
        f"Generating… {width}×{height} · {frames_n}f · {steps} steps · VRAM busy is normal ({place})",
        0.2,
    )

    image_in = _load_image(job.get("image_path"))
    ref_in = _load_image(job.get("reference_path"))
    conditioning = image_in or ref_in

    lora_kw = None
    if job.get("_lora_scale") is not None:
        lora_kw = {"scale": float(job["_lora_scale"])}

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
        if lora_kw is not None:
            kwargs["cross_attention_kwargs"] = lora_kw
        if mode in ("ref2i",) and conditioning is not None:
            try:
                result = _call_pipe_with_progress(
                    pipe,
                    {
                        "prompt": prompt,
                        "image": conditioning.resize((width, height)),
                        "strength": float(job.get("strength") or 0.65),
                        "num_inference_steps": steps,
                        "guidance_scale": max(guidance, 1.0),
                        "generator": generator,
                    },
                    cb,
                    steps=steps,
                    label="Generating image",
                )
            except TypeError:
                result = _call_pipe_with_progress(
                    pipe, kwargs, cb, steps=steps, label="Generating image"
                )
        else:
            result = _call_pipe_with_progress(
                pipe, kwargs, cb, steps=steps, label="Generating image"
            )
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
    if lora_kw is not None:
        kwargs["cross_attention_kwargs"] = lora_kw

    tried_errors: list[str] = []
    result = None
    attempts = []
    # Wan first (no frame_rate) — LTX may accept frame_rate but Wan can hang/mis-route on it
    wan_like = "wan" in pipe_name or "wan" in str(model.get("id") or "").lower()
    sized = {
        **kwargs,
        "num_frames": frames_n,
        "height": height,
        "width": width,
    }
    ltx_video = {**sized, "frame_rate": float(fps)}
    if mode in ("i2v", "ref2v") and conditioning is not None:
        if wan_like:
            attempts.append({**sized, "image": conditioning})
            attempts.append({**kwargs, "image": conditioning, "num_frames": frames_n})
        else:
            attempts.append({**ltx_video, "image": conditioning})
            attempts.append({**sized, "image": conditioning})
            attempts.append({**kwargs, "image": conditioning, "num_frames": frames_n})
        attempts.append({**kwargs, "image": conditioning})
    if wan_like:
        attempts.append(sized)
        attempts.append(ltx_video)
    else:
        attempts.append(ltx_video)
        attempts.append(sized)
    attempts.append({**kwargs, "num_frames": frames_n, "height": height, "width": width})
    attempts.append(kwargs)

    for attempt in attempts:
        try:
            result = _call_pipe_with_progress(
                pipe,
                attempt,
                cb,
                steps=steps,
                label="Generating video",
            )
            break
        except TypeError as exc:
            tried_errors.append(str(exc))
            continue
        except Exception as exc:  # noqa: BLE001
            tried_errors.append(str(exc))
            # Keep trying lighter kwargs only for TypeError-like mismatches
            if "unexpected keyword" not in str(exc).lower() and "got an unexpected" not in str(exc).lower():
                raise
            continue
    if result is None:
        raise RuntimeError("Pipeline call failed: " + " | ".join(tried_errors[:3]))

    # LTX-2 may return (video, audio) tuple / list
    if isinstance(result, (tuple, list)) and result and not hasattr(result, "frames"):
        result = result[0]

    video_frames = getattr(result, "frames", None) or getattr(result, "images", None)
    if video_frames is None and hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
        # numpy / tensor batch already
        video_frames = result
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


def _resolve_model_source(model: dict[str, Any]) -> tuple[str, bool]:
    """Prefer local StudioNels models/ mirror so loads don't re-hit Hugging Face."""
    hf_id = str(model.get("hf_id") or "")
    if not hf_id:
        return hf_id, False

    candidates: list[Path] = []
    if model.get("local_path"):
        candidates.append(Path(str(model["local_path"])))
    candidates.append(models_dir() / hf_id.replace("/", "__"))
    # Common alternate folder names people already have on disk
    leaf = hf_id.split("/")[-1]
    for alt in (
        leaf,
        leaf.replace(".", "-"),
        f"Lightricks__{leaf}",
        "LTX-2-19b-distilled",
        "LTX-2",
        "LTX-2.5-Diffusers",
    ):
        candidates.append(models_dir() / alt)

    seen: set[str] = set()
    for mirror in candidates:
        key = str(mirror)
        if key in seen:
            continue
        seen.add(key)
        if not mirror.exists():
            continue
        if (mirror / "model_index.json").exists() or any(mirror.glob("*.safetensors")) or any(
            mirror.glob("**/*.safetensors")
        ):
            return str(mirror), True

    try:
        from .models_manager import list_models_with_status

        for row in list_models_with_status():
            if row.get("id") == model.get("id") and row.get("local_path"):
                p = Path(str(row["local_path"]))
                if p.exists():
                    return str(p), True
    except Exception:
        pass
    return hf_id, False


def _build_pipeline(
    model: dict[str, Any],
    device: str,
    dtype,
    cpu_offload: bool,
    memory: dict[str, Any] | None = None,
    cb: ProgressCb | None = None,
):
    # mmgp redirects safetensors — import early when present
    try:
        from .mmgp_accel import apply_runtime_env, mmgp_available

        apply_runtime_env()
        if mmgp_available():
            from mmgp import offload as _mmgp_offload  # noqa: F401
    except Exception:
        pass

    from diffusers import DiffusionPipeline

    from .memory import apply_memory_to_pipeline, memory_from_preset

    source, is_local = _resolve_model_source(model)
    where = "local disk" if is_local else "Hugging Face (download if missing)"
    short = source if len(str(source)) < 80 else ("…" + str(source)[-60:])
    _progress(cb, f"Reading weights from {where}: {short}", 0.06)

    load_kwargs: dict[str, Any] = {"torch_dtype": dtype}
    if is_local:
        load_kwargs["local_files_only"] = True
        # Incomplete local packs used to silently fall through to a multi-GB HF download
        # and look "stuck at 18%" for ages — fail fast instead.
        local_path = Path(str(source))
        if local_path.exists() and not (
            (local_path / "model_index.json").exists()
            or any(local_path.glob("*.safetensors"))
            or any(local_path.glob("**/*.safetensors"))
        ):
            raise RuntimeError(
                f"Local model folder looks empty: {source}. "
                "Open Models → Download until status is Ready, then retry."
            )

    # Always materialize on CPU first so mmgp can own device placement
    try:
        pipe = DiffusionPipeline.from_pretrained(source, **load_kwargs)
    except Exception as first_exc:
        if is_local:
            raise RuntimeError(
                f"Could not load local weights from {source}: {first_exc}. "
                "Re-download the model in Models (do not wait on a silent HF fetch)."
            ) from first_exc
        import torch

        _progress(cb, f"Retrying load (float32)… {first_exc}", 0.08)
        retry_kwargs: dict[str, Any] = {"torch_dtype": torch.float32}
        try:
            pipe = DiffusionPipeline.from_pretrained(source, **retry_kwargs)
        except Exception as second_exc:
            hf = model.get("hf_id")
            if not hf:
                raise RuntimeError(f"Pipeline load failed: {second_exc}") from second_exc
            _progress(cb, f"Fetching from Hugging Face: {hf}", 0.09)
            pipe = DiffusionPipeline.from_pretrained(hf, torch_dtype=torch.float32)

    _progress(cb, "Weights in RAM — applying StudioNels mmgp / device placement…", 0.14)
    try:
        pipe.to("cpu")
    except Exception:
        pass

    mem = dict(memory or {})
    if not mem:
        # Legacy flag → placement
        mem = memory_from_preset(
            {
                "target_vram_gb": 8 if cpu_offload else 24,
                "generation": {"cpu_offload": cpu_offload, "attention_slicing": True},
            }
        )
    placement = apply_memory_to_pipeline(pipe, device, mem)
    _progress(cb, f"Device ready ({placement})", 0.17)
    # Prefer SDPA when available — faster than sliced attention on big AMD cards
    try:
        if hasattr(pipe, "set_attention_backend"):
            pipe.set_attention_backend("sdpa")
        elif hasattr(pipe, "enable_xformers_memory_efficient_attention"):
            pass
    except Exception:
        pass
    try:
        pipe.set_progress_bar_config(disable=True)
    except Exception:
        pass
    try:
        pipe._studionels_placement = placement  # type: ignore[attr-defined]
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
        draw.text((20, 12), f"StudioNels · {mode.upper()} · {q}", fill=(57, 255, 199), font=font)
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
