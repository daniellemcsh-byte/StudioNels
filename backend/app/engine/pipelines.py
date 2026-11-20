from __future__ import annotations

import os

import contextlib
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


def snap_video_frames(frames: int, family: str = "") -> int:
    """Wan wants 4n+1 frames, LTX/CogVideo 8n+1. Wrong counts raise and abort the job."""
    frames = max(9, int(frames or 49))
    fam = (family or "").lower()
    if any(k in fam for k in ("ltx", "cogvideo", "mochi")):
        n = max(1, round((frames - 1) / 8))
        return int(n * 8 + 1)
    if any(k in fam for k in ("wan", "hunyuan", "skyreel")):
        n = max(1, round((frames - 1) / 4))
        return int(n * 4 + 1)
    # Unknown video family: still snap to 4n+1 (safe for most DiT video pipes)
    n = max(1, round((frames - 1) / 4))
    return int(n * 4 + 1)


def _progress(cb: ProgressCb | None, message: str, frac: float) -> None:
    if cb:
        cb(message, max(0.0, min(1.0, frac)))


def check_frames_look_real(arr: Any) -> None:
    """Fail loudly on NaN or blank output instead of saving a black video.

    arr: float frames (any layout), values 0..1 or 0..255. A fp16 overflow used
    to come out as an all-black MP4 that looked like a successful job.
    """
    import numpy as np

    a = np.asarray(arr)
    if a.size == 0 or a.dtype == np.uint8:
        return
    sample = a[::4] if a.ndim >= 4 and a.shape[0] > 8 else a
    sample = sample.astype(np.float32, copy=False)
    bad = float(np.mean(~np.isfinite(sample)))
    if bad > 0.001:
        raise RuntimeError(
            f"The model produced invalid pixel values ({bad:.0%} NaN/inf), so the result would be "
            "black. This is usually a precision problem (float16 overflow) for this model."
        )
    scale = 255.0 if float(np.nanmax(sample)) > 1.5 else 1.0
    std = float(np.nanstd(sample)) / scale
    mean = float(np.nanmean(sample)) / scale
    if std < 2.0 / 255.0:
        what = "black" if mean < 0.03 else "a single flat colour"
        raise RuntimeError(
            f"The result came out {what} (no picture detail), so it was not saved as a take. "
            "Try again; if it repeats, report it with this job's settings."
        )


def _sync_gpu() -> None:
    """Wait for queued GPU work. Step callbacks otherwise fire when work is
    queued, not done: "step 8/8" showed while the GPU still had a minute left."""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass


class _LivePreview:
    """Write a small JPEG of where the clip is heading, every step (LTX-2).

    Flow-matching Euler steps are x_next = x + (s_next - s) * v, so two
    consecutive latents give v and the clean estimate x0 = x_next - s_next * v.
    One middle latent frame of x0 is decoded with the VAE (~0.1 s).
    """

    def __init__(self, pipe: Any, path: Path, *, frames: int, height: int, width: int):
        self.pipe = pipe
        self.path = Path(path)
        self.prev = None
        self.off = False
        t_ratio = int(getattr(pipe, "vae_temporal_compression_ratio", 8) or 8)
        s_ratio = int(getattr(pipe, "vae_spatial_compression_ratio", 32) or 32)
        self.lf = (int(frames) - 1) // t_ratio + 1
        self.lh = int(height) // s_ratio
        self.lw = int(width) // s_ratio
        self.timings: list[float] = []

    @staticmethod
    def supported(pipe: Any) -> bool:
        return all(hasattr(pipe, a) for a in ("_unpack_latents", "_denormalize_latents", "vae", "scheduler"))

    def update(self, step_index: int, latents: Any) -> None:
        if self.off or latents is None:
            return
        import torch

        prev, self.prev = self.prev, latents.detach().clone()
        if prev is None:
            return
        started = time.time()
        try:
            sigmas = self.pipe.scheduler.sigmas
            s_prev = float(sigmas[step_index])
            s_next = float(sigmas[step_index + 1])
            if abs(s_next - s_prev) < 1e-6:
                return
            with torch.no_grad():
                x = latents.float()
                v = (x - prev.float()) / (s_next - s_prev)
                x0 = (x - s_next * v).to(latents.dtype)
                pipe = self.pipe
                z = pipe._unpack_latents(
                    x0,
                    self.lf,
                    self.lh,
                    self.lw,
                    getattr(pipe, "transformer_spatial_patch_size", 1),
                    getattr(pipe, "transformer_temporal_patch_size", 1),
                )
                vae = pipe.vae
                z = pipe._denormalize_latents(
                    z, vae.latents_mean, vae.latents_std, vae.config.scaling_factor
                )
                mid = max(0, int(z.shape[2]) // 2)
                zf = z[:, :, mid : mid + 1].to(dtype=vae.dtype)
                # temb= routes past vae_decode's wrapper, which would announce
                # "Denoise finished — decoding frames" in the middle of denoising.
                img = vae.decode(zf, temb=None, return_dict=False)[0]
                frame = (img[0, :, 0].float() / 2 + 0.5).clamp(0, 1)
                arr = (frame.permute(1, 2, 0).cpu().numpy() * 255).astype("uint8")
            from PIL import Image

            pic = Image.fromarray(arr)
            pic.thumbnail((480, 480))
            tmp = self.path.with_name(self.path.name + ".tmp")
            pic.save(tmp, format="JPEG", quality=80)
            os.replace(tmp, self.path)
            self.timings.append(time.time() - started)
        except Exception as exc:  # noqa: BLE001
            # A preview must never cost the generation: switch it off for this job.
            self.off = True
            print(f"[studionels] live preview disabled: {exc}", flush=True)


def _call_pipe_with_progress(
    pipe: Any,
    kwargs: dict[str, Any],
    cb: ProgressCb | None,
    *,
    steps: int,
    label: str = "Generating",
    live: "_LivePreview | None" = None,
) -> Any:
    """Run pipe(**kwargs) with step callbacks + heartbeat so UI doesn't sit at 20%."""
    total = max(1, int(steps or 1))
    state = {"step": 0, "done": False, "last_step_at": time.time()}
    stop = threading.Event()
    started = time.time()

    def _report(i: int) -> None:
        i = max(0, min(int(i), total))
        prev = int(state["step"] or 0)
        state["step"] = i
        if i > prev:
            state["last_step_at"] = time.time()
        frac = 0.22 + 0.68 * min(1.0, i / total)
        elapsed = int(time.time() - started)
        # After the last denoise step, Diffusers still runs VAE decode (often the long AMD hang)
        if i >= total:
            _progress(
                cb,
                f"{label} · step {total}/{total} · denoise done — decoding frames "
                f"(VAE, can take several minutes on AMD)… {elapsed}s",
                0.90,
            )
            return
        eta = ""
        if i >= 1:
            # Average of finished steps, minus time already spent on the current
            # one, so the countdown falls between steps instead of growing.
            done_at = float(state.get("last_step_at") or time.time())
            per = max(0.1, (done_at - started) / i)
            left = max(0, int(per * (total - i) - (time.time() - done_at)))
            if left >= 60:
                eta = f" · ~{left // 60}m{left % 60:02d}s left"
            else:
                eta = f" · ~{left}s left"
        _progress(
            cb,
            f"{label} · step {i}/{total} · {elapsed}s elapsed{eta}",
            frac,
        )

    def on_step_end(*args, **kwargs):
        # Diffusers calls (pipe, step, t, callback_kwargs). Some LTX builds
        # omit the pipe. Always return the same dict — an empty one drops
        # latents and the next step never leaves the GPU.
        callback_kwargs = kwargs.get("callback_kwargs")
        step_index = kwargs.get("step_index", kwargs.get("i"))
        for arg in args:
            if isinstance(arg, dict):
                callback_kwargs = arg
            elif isinstance(arg, int) and not isinstance(arg, bool):
                step_index = arg
        if not isinstance(callback_kwargs, dict):
            callback_kwargs = {}
        idx = step_index
        if idx is None:
            idx = callback_kwargs.get("i", callback_kwargs.get("step_index"))
        try:
            i = int(idx) + 1 if idx is not None else state["step"] + 1
        except Exception:
            i = state["step"] + 1
        _sync_gpu()
        if live is not None and i < total:
            live.update(i - 1, callback_kwargs.get("latents"))
        _report(i)
        return callback_kwargs

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
            if i >= total:
                # Still inside pipe() after last step → VAE decode / post-process
                since = int(time.time() - float(state.get("last_step_at") or started))
                soft = min(0.96, 0.90 + since / 600.0)
                _progress(
                    cb,
                    f"{label} · decoding / assembling frames… {since}s after step {total}/{total} "
                    f"(VAE on AMD is often slower than denoise)",
                    soft,
                )
                continue
            if i > 0:
                _report(i)
                continue
            # Soft crawl before first callback fires (ROCm can sit quiet a while)
            soft = 0.22 + min(0.45, elapsed / 180.0)
            hint = ""
            if elapsed >= 90:
                hint = " · first step on a large model streams from RAM and can take a few minutes"
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
    is_local: bool | None = None,
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
                "Weights never finished loading. Stop, confirm this model is Ready in Models, then retry."
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
            # Real, live progress instead of a guessed label: what step we are on
            # and how much of the model is already in RAM.
            note = _LOAD_NOTE.get("text") or (
                "reading this model from disk into RAM" if is_local is not False
                else "reading the cached weights into RAM"
            )
            mem = _ram_in_use_note()
            _progress(
                cb,
                f"{label} ({elapsed}s — first load) · {note}{mem}…",
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
            "local folder). Stop → Models → wait until this model shows Ready, then Generate again."
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
    # Never truth-test numpy/torch arrays (ambiguous .any()/.all() crash).
    if frames is not None and len(frames) > 0:
        try:
            frames[-1].save(path.with_name(path.stem + "_last.png"))
        except Exception:
            pass
    import numpy as np

    arrs = [np.asarray(f.convert("RGB")) for f in frames]
    mp4 = path.with_suffix(".mp4")
    errors: list[str] = []
    try:
        import imageio.v2 as imageio

        imageio.mimsave(
            mp4,
            arrs,
            fps=max(1, int(fps or 16)),
            codec="libx264",
            quality=8,
            macro_block_size=1,
        )
        if mp4.exists() and mp4.stat().st_size > 256:
            frames[0].save(path.with_suffix(".png"))
            return str(mp4)
        errors.append("imageio wrote an empty file")
    except Exception as exc:
        errors.append(f"imageio: {exc}")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            errors.append(f"ffmpeg missing: {exc}")
            ffmpeg = None
    if ffmpeg:
        h, w = arrs[0].shape[0], arrs[0].shape[1]
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(max(1, int(fps or 16))),
            "-i",
            "-",
            "-an",
            "-vcodec",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "16",
            "-preset",
            "veryfast",
            str(mp4),
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            assert proc.stdin is not None
            for frame in arrs:
                proc.stdin.write(np.ascontiguousarray(frame).tobytes())
            proc.stdin.close()
            err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            code = proc.wait(timeout=180)
            if code == 0 and mp4.exists() and mp4.stat().st_size > 256:
                frames[0].save(path.with_suffix(".png"))
                return str(mp4)
            errors.append(f"ffmpeg exit {code}: {err[-400:]}")
        except Exception as exc:
            errors.append(f"ffmpeg: {exc}")

    try:
        frames[0].save(path.with_suffix(".png"))
    except Exception:
        pass
    raise RuntimeError(
        "Video denoise finished but MP4 export failed. "
        + " | ".join(errors[:3])
        + " Install ffmpeg (or pip install imageio-ffmpeg) and retry."
    )


def _write_audio_array(audio, path: Path, sample_rate: int) -> str:
    """Write generated audio (torch or numpy, several layouts) to a 16-bit wav.

    Uses the stdlib wave module: soundfile is not in the venv, so every audio
    job used to fail at "No module named 'soundfile'" after generating.
    """
    import numpy as np

    arr = audio.detach().float().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[0]
    # (channels, samples) → (samples, channels)
    if arr.ndim == 2 and arr.shape[0] <= 8 and arr.shape[0] < arr.shape[1]:
        arr = arr.T
    if arr.ndim == 1:
        arr = arr[:, None]
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 1.0:  # some models return slightly hot samples
        arr = arr / peak
    pcm = (np.clip(np.nan_to_num(arr), -1.0, 1.0) * 32767.0).astype("<i2")
    out = path.with_suffix(".wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(int(pcm.shape[1]))
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate or 44100))
        wf.writeframes(pcm.tobytes())
    return str(out)


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
    """Load / switch / remove the job's LoRA on a (possibly warm, reused) pipe.

    The warm cache is not keyed on LoRA, so a LoRA used once stayed on every
    later job, and a second LoRA stacked onto the first. Track what is loaded
    and unload it when the job wants something else (or nothing).
    """
    lora = job.get("lora_path") or None
    scale = float(job.get("lora_scale") if job.get("lora_scale") is not None else 0.8)
    scale = max(0.0, min(2.0, scale))
    if scale <= 0.001:
        lora = None
    loaded = getattr(pipe, "_studionels_lora", None)
    if loaded and loaded != lora:
        try:
            pipe.unload_lora_weights()
            _progress(cb, "Previous LoRA removed", 0.11)
        except Exception as exc:  # noqa: BLE001
            _progress(cb, f"Could not remove previous LoRA ({exc}) — restart StudioNels to clear it", 0.11)
        pipe._studionels_lora = None
    if not lora:
        return
    _progress(cb, f"Loading LoRA (strength {scale:.2f})…", 0.12)
    try:
        if getattr(pipe, "_studionels_lora", None) != lora:
            pipe.load_lora_weights(lora, adapter_name="studionels")
            pipe._studionels_lora = lora
        applied = False
        if hasattr(pipe, "set_adapters"):
            try:
                pipe.set_adapters(["studionels"], adapter_weights=[scale])
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
    # The warm engine keeps pipes between jobs, so a swapped encoder would stick.
    # Put the model's own encoder back before doing anything else.
    originals = getattr(pipe, "_studionels_te_orig", None) or {}
    want_key = f"{preset.get('hf_id')}|{preset.get('slot')}" if preset and preset.get("hf_id") else None
    if originals and getattr(pipe, "_studionels_te_key", None) != want_key:
        for s, (enc, tok_slot, tok) in originals.items():
            setattr(pipe, s, enc)
            if tok_slot and tok is not None:
                setattr(pipe, tok_slot, tok)
        pipe._studionels_te_orig = {}
        pipe._studionels_te_key = None
        _progress(cb, "Text encoder → model default", 0.08)
    if not preset or not preset.get("hf_id"):
        return
    if getattr(pipe, "_studionels_te_key", None) == want_key:
        return
    # CLIP / T5 presets only fit Stable Diffusion-style pipelines. LTX (Gemma),
    # Wan (UMT5) and FLUX expect their own encoder shapes and break otherwise.
    if not type(pipe).__name__.startswith("StableDiffusion"):
        _progress(cb, f"Text encoder '{preset.get('label')}' doesn't fit this model — using its own.", 0.08)
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
        if not hasattr(pipe, slot):
            slot = "text_encoder"
        if not hasattr(pipe, slot):
            _progress(cb, "Pipeline has no text_encoder slot — left as model default.", 0.1)
            return
        tok_slot = "tokenizer_2" if slot.endswith("_2") else "tokenizer"
        if not hasattr(pipe, tok_slot):
            tok_slot = ""
        pipe._studionels_te_orig = {
            slot: (getattr(pipe, slot), tok_slot, getattr(pipe, tok_slot) if tok_slot else None)
        }
        setattr(pipe, slot, moved)
        if tokenizer is not None and tok_slot:
            setattr(pipe, tok_slot, tokenizer)
        pipe._studionels_te_key = want_key
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


def _accepts(pipe: Any, arg: str, *, strict: bool = False) -> bool:
    """Does pipe(...) take this keyword? strict=True ignores **kwargs: SDXL's
    text-to-image call has **kwargs and silently drops an `image` passed to it."""
    try:
        import inspect

        params = inspect.signature(pipe.__call__).parameters
        if arg in params:
            return True
        return not strict and any(p.kind == p.VAR_KEYWORD for p in params.values())
    except Exception:
        return False


def _audio_family(model: dict[str, Any]) -> str:
    """Which loader a Text → Audio model needs. Everything used to go through
    StableAudioPipeline, so MusicGen (Transformers) failed with a 404 on
    model_index.json."""
    key = f"{model.get('id') or ''} {model.get('hf_id') or ''} {model.get('pipeline') or ''}".lower()
    if "audiogen" in key:
        return "audiogen"
    if "musicgen" in key:
        return "musicgen"
    if "audioldm2" in key or "audioldm-2" in key:
        return "audioldm2"
    return "stable_audio"


def _run_audio_family(
    family: str,
    source: str,
    *,
    prompt: str,
    negative: str,
    steps: int,
    duration_sec: float,
    guidance: float | None,
    seed: Any,
    device: str,
    out_path: Path,
    cb: ProgressCb | None,
) -> str:
    import numpy as np
    import torch

    seconds = max(1.0, min(30.0, float(duration_sec or 5.0)))
    if seed is not None:
        try:
            torch.manual_seed(int(seed))
        except Exception:
            pass
    if family == "musicgen":
        from transformers import AutoProcessor

        try:
            from transformers import MusicgenMelodyForConditionalGeneration, MusicgenForConditionalGeneration
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("MusicGen needs a newer transformers. Pinokio → Update, then retry.") from exc
        cls = MusicgenMelodyForConditionalGeneration if "melody" in str(source).lower() else MusicgenForConditionalGeneration
        processor = AutoProcessor.from_pretrained(source)
        # float32: MusicGen is small, and half precision risks the same NaN/silence
        # overflow as LTX-2 in fp16 on ROCm.
        model = cls.from_pretrained(source, torch_dtype=torch.float32).to(device)
        model.eval()
        inputs = processor(text=[prompt or "ambient music"], padding=True, return_tensors="pt").to(device)
        frame_rate = int(getattr(model.config.audio_encoder, "frame_rate", 50) or 50)
        _progress(cb, f"Generating music · {seconds:.1f}s…", 0.3)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                do_sample=True,
                guidance_scale=float(guidance) if guidance and guidance > 0 else 3.0,
                max_new_tokens=int(seconds * frame_rate) + 4,
            )
        audio = out[0, 0].float().cpu().numpy()
        sr = int(model.config.audio_encoder.sampling_rate)
        del model
    else:  # audioldm2
        from diffusers import AudioLDM2Pipeline

        pipe = AudioLDM2Pipeline.from_pretrained(source, torch_dtype=torch.float32).to(device)
        _progress(cb, f"Generating audio · {max(10, int(steps))} steps · {seconds:.1f}s…", 0.3)
        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "num_inference_steps": max(10, int(steps)),
            "audio_length_in_s": seconds,
        }
        if negative:
            kwargs["negative_prompt"] = negative
        if guidance and guidance > 0:
            kwargs["guidance_scale"] = guidance
        audio = np.asarray(pipe(**kwargs).audios[0])
        sr = 16000
        del pipe
    _release_gpu_cache()
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0 or not np.isfinite(audio).all() or float(np.max(np.abs(audio))) < 1e-4:
        raise RuntimeError("The audio model returned silence or invalid samples, so nothing was saved. Try again.")
    return _write_audio_array(audio, out_path, sr)


_LTX_UPSAMPLER: dict[str, Any] = {}


def _ltx_latent_upsampler(device: str):
    """LTX-2.3 2x spatial latent upsampler (models/ltx-2.3-latent-upsampler), or None.

    Lightricks ships it as one file; it loads into diffusers' LTX2LatentUpsamplerModel
    with the LTX-2 config and use_rational_resampler=False (plain conv + pixel shuffle).
    """
    if "model" in _LTX_UPSAMPLER:
        return _LTX_UPSAMPLER["model"]
    folder = models_dir() / "ltx-2.3-latent-upsampler"
    weights = folder / "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
    cfg_path = folder / "config.json"
    if not (weights.is_file() and cfg_path.is_file()):
        return None
    import json as _json

    import torch
    from safetensors.torch import load_file

    try:
        from diffusers.models.latent_upscaler import LTX2LatentUpsamplerModel
    except ImportError:
        return None
    cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["use_rational_resampler"] = False
    model = LTX2LatentUpsamplerModel.from_config(cfg)
    model.load_state_dict(load_file(str(weights)), strict=True)
    model = model.to(device=device, dtype=torch.bfloat16).eval()
    _LTX_UPSAMPLER["model"] = model
    return model


def _adain(x: Any, ref: Any) -> Any:
    """Match per-channel mean/std of the upsampled latents to the originals."""
    dims = (2, 3, 4)
    mx, sx = x.mean(dim=dims, keepdim=True), x.std(dim=dims, keepdim=True) + 1e-6
    mr, sr = ref.mean(dim=dims, keepdim=True), ref.std(dim=dims, keepdim=True)
    return (x - mx) / sx * sr + mr


def _ltx_two_stage(
    pipe: Any,
    attempt: dict[str, Any],
    cb: ProgressCb | None,
    *,
    steps: int,
    live: Any,
    width: int,
    height: int,
    device: str,
) -> Any:
    """LTX's own recipe for sharper, steadier faces: generate, upsample the
    latents 2x, then refine 3 steps at 2x resolution before decoding."""
    import torch

    from diffusers.pipelines.ltx2.utils import STAGE_2_DISTILLED_SIGMA_VALUES

    upsampler = _ltx_latent_upsampler(device)
    if upsampler is None:
        raise RuntimeError("latent upsampler not installed")
    first = {**attempt, "output_type": "latent", "return_dict": False}
    out = _call_pipe_with_progress(pipe, first, cb, steps=steps, label="Generating video · stage 1 of 2", live=live)
    video_lat, audio_lat = out[0], (out[1] if len(out) > 1 else None)
    _progress(cb, "Upscaling latents 2× (LTX-2.3 spatial upsampler)…", 0.84)
    with torch.no_grad():
        up = upsampler(video_lat.to(device=device, dtype=torch.bfloat16))
        up = _adain(up.float(), video_lat.float())
    sigmas = list(STAGE_2_DISTILLED_SIGMA_VALUES)
    second = {
        **attempt,
        "latents": up,
        "width": width * 2,
        "height": height * 2,
        "sigmas": sigmas,
        "num_inference_steps": len(sigmas),
        "noise_scale": float(sigmas[0]),
        "guidance_scale": 1.0,
    }
    if audio_lat is not None:
        second["audio_latents"] = audio_lat
    with _ltx_tiled_decode(pipe):
        return _call_pipe_with_progress(pipe, second, cb, steps=len(sigmas), label="Refining at 2× · stage 2 of 2")


def _ltx_video_upscale(
    pipe: Any,
    src: str,
    cb: ProgressCb | None,
    *,
    device: str,
    prompt: str,
    negative: str,
    fps: int,
    generator: Any,
) -> Any:
    """AI video upscale: encode the clip with LTX's VAE, upsample the latents 2x
    and refine 3 steps at 2x. Adds real detail (Lanczos only stretches pixels)."""
    import torch
    from diffusers.utils import load_video

    upsampler = _ltx_latent_upsampler(device)
    if upsampler is None:
        raise RuntimeError("The LTX-2.3 latent upsampler is not installed (models/ltx-2.3-latent-upsampler).")
    _progress(cb, "AI upscale · reading the clip…", 0.06)
    frames = load_video(src)
    if len(frames) < 9:
        raise RuntimeError("The clip is too short to upscale (needs at least 9 frames).")
    n = ((len(frames) - 1) // 8) * 8 + 1
    frames = frames[: min(n, 241)]
    n = ((len(frames) - 1) // 8) * 8 + 1
    frames = frames[:n]
    w0, h0 = frames[0].size
    shrink = min(1.0, 960 / max(w0, h0))  # stage-2 output is 2x this
    w, h = max(256, int(w0 * shrink) // 32 * 32), max(256, int(h0 * shrink) // 32 * 32)
    vae = pipe.vae
    if hasattr(vae, "use_framewise_encoding"):
        vae.use_framewise_encoding = True
    video = pipe.video_processor.preprocess_video(frames, height=h, width=w)
    vae_dtype = next(vae.parameters()).dtype
    _progress(cb, f"AI upscale · encoding {n} frames at {w}×{h}…", 0.12)
    with torch.no_grad():
        raw = vae.encode(video.to(device=device, dtype=vae_dtype)).latent_dist.mode()
        _progress(cb, "AI upscale · upsampling latents 2×…", 0.2)
        up = upsampler(raw.to(dtype=torch.bfloat16))
        up = _adain(up.float(), raw.float())
    # Gentler than generation's stage 2 (starts at 0.91, which repaints faces
    # and props). Upscaling should keep who and what is in the clip and only
    # add detail, so start from far less noise.
    sigmas = [0.5, 0.33, 0.16]
    kwargs: dict[str, Any] = {
        "prompt": prompt or "high detail, sharp focus, natural skin and fabric texture, coherent faces",
        "latents": up,
        "width": w * 2,
        "height": h * 2,
        "num_frames": n,
        "frame_rate": float(fps or 24),
        "sigmas": sigmas,
        "num_inference_steps": len(sigmas),
        "noise_scale": float(sigmas[0]),
        "guidance_scale": 1.0,
        "generator": generator,
    }
    if negative:
        kwargs["negative_prompt"] = negative
    with _ltx_tiled_decode(pipe):
        return _call_pipe_with_progress(pipe, kwargs, cb, steps=len(sigmas), label="AI upscale · refining at 2×")


@contextlib.contextmanager
def _ltx_tiled_decode(pipe: Any):
    """At 2x (1536x896) the framewise LTX decode alone took ~9 min on the R9700.
    Spatial tiles keep each conv small. Only for the 2x passes; base-size decode
    is already fast framewise."""
    vae = getattr(pipe, "vae", None)
    was = bool(getattr(vae, "use_tiling", False))
    on = False
    if vae is not None and not was and callable(getattr(vae, "enable_tiling", None)):
        try:
            vae.enable_tiling()
            on = True
        except Exception:
            on = False
    try:
        yield
    finally:
        if on:
            try:
                vae.disable_tiling()
            except Exception:
                pass


def _model_safe_dtype(model: dict[str, Any] | None, device: str, dtype: Any, dtype_name: str, mem: dict[str, Any]):
    """LTX-2 overflows in float16 (NaN -> all-black frames). Its weights are
    bfloat16 and the R9700 runs bfloat16 natively, so never run it in fp16."""
    import torch

    pipe_name = str((model or {}).get("pipeline") or "")
    if str(device).startswith("cuda") and "LTX2" in pipe_name and dtype == torch.float16:
        mem["dtype"] = "bfloat16"
        return torch.bfloat16, "bfloat16"
    return dtype, dtype_name


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

    if mode == "upsample_video" and not job.get("ai_upscale"):
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
    from .mmgp_accel import tune_amd_inference

    tune_amd_inference()

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
    elif device_info.get("rocm"):
        # Windows ROCm VAE often errors on bfloat16. fp16 is faster and stable on R9700.
        dtype = torch.float16
        dtype_name = "float16"
    else:
        dtype = torch.bfloat16
    dtype, dtype_name = _model_safe_dtype(model, device, dtype, dtype_name, mem)

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
    kind = model["kind"]
    is_video = kind == "video" or mode in {"t2v", "i2v", "ref2v"}
    raw_frames = int(job.get("frames") or model.get("default_frames") or 49)
    family = f"{model.get('pipeline') or ''} {model.get('id') or ''} {kind or ''}"
    frames_n = snap_video_frames(raw_frames, family) if is_video else raw_frames
    if frames_n != raw_frames:
        job["frames"] = frames_n
        _progress(
            cb,
            f"Snapped frames {raw_frames} → {frames_n} (model requires 4n+1 or 8n+1)",
            0.04,
        )
    fps = int(job.get("fps") or model.get("fps") or 16)
    duration_sec = float(job.get("duration_sec") or model.get("default_duration_sec") or 8)
    cpu_offload = bool(mem.get("cpu_offload", job.get("cpu_offload", True)))
    # CPU generator is reliable on Windows ROCm (cuda Generator often errors or desyncs).
    generator = None
    if seed is not None:
        generator = torch.Generator(device="cpu").manual_seed(int(seed))
    from .memory import tune_memory_for_model

    mem = tune_memory_for_model(mem, model)
    _release_gpu_cache()
    _progress(
        cb,
        f"Memory: {mem.get('placement_label') or mem.get('placement')} · {dtype_name}",
        0.03,
    )

    if kind == "audio" or mode == "t2a":
        _progress(cb, "Loading audio model…", 0.05)
        family = _audio_family(model)
        if family == "audiogen":
            raise RuntimeError(
                f"{model.get('label') or 'AudioGen'} only ships for Meta's audiocraft library, which "
                "StudioNels does not run. Pick MusicGen, Stable Audio Open or AudioLDM 2 for Text → Audio."
            )
        if family in ("musicgen", "audioldm2"):
            source, _is_local = _resolve_model_source(model)
            media = _run_audio_family(
                family,
                source,
                prompt=prompt,
                negative=negative,
                steps=steps,
                duration_sec=float(duration_sec),
                guidance=guidance,
                seed=job.get("seed"),
                device=device,
                out_path=out_path,
                cb=cb,
            )
            _progress(cb, "Done", 1.0)
            return {"media_path": media, "thumb_path": None, "frames": 0}
        try:
            from diffusers import StableAudioPipeline
            from .memory import apply_memory_to_pipeline
        except Exception as exc:
            raise RuntimeError(
                "Stable Audio needs Diffusers in the venv. Pinokio → Update, then retry."
            ) from exc

        source, _is_local = _resolve_model_source(model)
        try:
            pipe = StableAudioPipeline.from_pretrained(source, torch_dtype=dtype)
        except TypeError:
            pipe = StableAudioPipeline.from_pretrained(source, dtype=dtype)
        apply_memory_to_pipeline(pipe, device, mem)
        _progress(cb, f"Generating audio · {steps} steps · {duration_sec:.1f}s…", 0.25)
        audio_kwargs: dict[str, Any] = {
            "prompt": prompt,
            "num_inference_steps": max(8, int(steps)),
            "audio_end_in_s": max(1.0, float(duration_sec)),
            "num_waveforms_per_prompt": 1,
            "generator": generator,
        }
        if guidance and guidance > 0:
            audio_kwargs["guidance_scale"] = guidance
        if negative:
            audio_kwargs["negative_prompt"] = negative
        try:
            result = pipe(**audio_kwargs)
        except TypeError:
            audio_kwargs.pop("negative_prompt", None)
            audio_kwargs.pop("guidance_scale", None)
            result = pipe(**audio_kwargs)
        audio = result.audios[0]
        sr = getattr(result, "sample_rate", None) or getattr(result, "sr", None) or 44100
        media = _write_audio_array(audio, out_path, int(sr))
        _progress(cb, "Done", 1.0)
        return {"media_path": media, "thumb_path": None, "frames": 0}

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
        _, is_local_src = _resolve_model_source(model)
        if is_local_src:
            start_msg = "Loading from local disk (no HF download)…"
            load_label = "Loading from local disk (no HF download)"
        else:
            start_msg = "Loading from Hugging Face cache / download…"
            load_label = "Loading from Hugging Face cache / download"
        _progress(cb, start_msg, 0.05)
        pipe = _heartbeat_while(
            cb,
            load_label,
            0.05,
            0.18,
            lambda: _build_pipeline(model, device, dtype, cpu_offload, mem, cb=cb),
            max_sec=_load_timeout_sec(model),
            is_local=is_local_src,
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
    # Wan VAE tiling hangs on AMD after the last denoise step — chunked decode instead.
    if kind == "video":
        try:
            from .vae_decode import install_safe_video_decode

            install_safe_video_decode(pipe, cb)
            _progress(
                cb,
                "Video decode set to small frame groups (VAE tiling off — it hangs Wan on AMD)",
                0.19,
            )
        except Exception:
            pass
    _progress(
        cb,
        f"Generating… {width}×{height} · {frames_n}f · {steps} steps · VRAM busy is normal ({place})",
        0.2,
    )

    image_in = _load_image(job.get("image_path"))
    ref_in = _load_image(job.get("reference_path"))
    conditioning = image_in or ref_in

    lora_kw = None
    # Only pipelines that take cross_attention_kwargs get the LoRA scale there;
    # LTX-2 does not, and passing it made every LoRA video job fail.
    if job.get("_lora_scale") is not None and _accepts(pipe, "cross_attention_kwargs", strict=True):
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
            img_pipe = pipe
            if not _accepts(pipe, "image", strict=True):
                # Text-to-image pipes (SDXL, SD) take no image: build the
                # image-to-image twin from the same loaded parts (no reload).
                try:
                    from diffusers import AutoPipelineForImage2Image

                    img_pipe = AutoPipelineForImage2Image.from_pipe(pipe)
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"{model.get('label') or 'This model'} has no image-to-image version ({exc})."
                    ) from exc
            try:
                ref_kwargs: dict[str, Any] = {
                    "prompt": prompt,
                    "image": conditioning.resize((width, height)),
                    "strength": float(job.get("strength") or 0.65),
                    "num_inference_steps": steps,
                    "guidance_scale": max(guidance, 1.0),
                    "generator": generator,
                }
                if negative:
                    ref_kwargs["negative_prompt"] = negative
                result = _call_pipe_with_progress(
                    img_pipe,
                    ref_kwargs,
                    cb,
                    steps=steps,
                    label="Generating image",
                )
            except TypeError as exc:
                # Used to retry without the reference and return a plain
                # text-to-image result as if the photo had been used.
                raise RuntimeError(
                    f"{model.get('label') or 'This model'} can't take a reference photo ({exc}). "
                    "Pick an image-to-image capable model for Reference → Image."
                ) from exc
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

    # Distilled LTX-2 family: use official sigma schedule when Diffusers provides it
    pipe_cls_name = str(model.get("pipeline") or "")
    if model.get("distilled") and "LTX2" in pipe_cls_name:
        try:
            from diffusers.pipelines.ltx2.utils import DISTILLED_SIGMA_VALUES

            kwargs["sigmas"] = DISTILLED_SIGMA_VALUES
            kwargs["guidance_scale"] = 1.0
            # The distilled schedule fixes the step count; keep the progress bar honest.
            if steps != len(DISTILLED_SIGMA_VALUES):
                _progress(
                    cb,
                    f"{model.get('label') or 'This model'} is distilled: it always runs "
                    f"{len(DISTILLED_SIGMA_VALUES)} steps (your {steps} is ignored)",
                    0.19,
                )
            steps = len(DISTILLED_SIGMA_VALUES)
            kwargs["num_inference_steps"] = steps
        except ImportError:
            pass

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

    # LTX2Pipeline has no `image` argument: every image attempt raised
    # TypeError, the loop fell through to a text-only attempt, and Image/Reference
    # → Video silently ignored the photo. Use the image-to-video pipeline built
    # from the same loaded components (no reload).
    call_pipe = pipe
    needs_image = mode in ("i2v", "ref2v") and conditioning is not None
    if needs_image and type(pipe).__name__ == "LTX2Pipeline":
        try:
            try:
                from diffusers import LTX2ImageToVideoPipeline
            except ImportError:
                from diffusers.pipelines.ltx2.pipeline_ltx2_image2video import LTX2ImageToVideoPipeline
            # Construct from the live components rather than from_pipe(): from_pipe
            # calls .to(dtype) and int8 (quanto) weights refuse a dtype change.
            import inspect as _inspect

            wanted = list(_inspect.signature(LTX2ImageToVideoPipeline.__init__).parameters)[1:]
            parts = {k: v for k, v in pipe.components.items() if k in wanted}
            call_pipe = LTX2ImageToVideoPipeline(**parts)
            for attr in ("_studionels_mmgp", "_studionels_placement", "_studionels_prequantized"):
                if hasattr(pipe, attr):
                    setattr(call_pipe, attr, getattr(pipe, attr))
            # The start image is H.264-recompressed to match training data, which
            # needs PyAV (not in the venv). crf=0 skips that step instead of failing.
            try:
                import av  # noqa: F401
            except ImportError:
                if "image_crf" in _inspect.signature(LTX2ImageToVideoPipeline.__call__).parameters:
                    attempts = [{**a, "image_crf": 0} if "image" in a else a for a in attempts]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Could not switch LTX-2 to its image-to-video pipeline ({exc}). Pinokio → Update, then retry."
            ) from exc

    live = None
    if _LivePreview.supported(call_pipe):
        try:
            live_path = Path(str(out_path) + ".live.jpg")
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live = _LivePreview(call_pipe, live_path, frames=frames_n, height=height, width=width)
        except Exception:
            live = None
    used_attempt: dict[str, Any] | None = None
    # High / Max on LTX-2: two-stage generate → 2x latent upsample → refine.
    two_stage = (
        "LTX2" in pipe_cls_name
        and str(job.get("quality") or "").lower() in ("high", "max")
        and os.environ.get("STUDIONELS_TWO_STAGE", "1").lower() not in ("0", "off", "false")
        and width * 2 <= 1920
        and height * 2 <= 1920
    )
    if job.get("ai_upscale") and mode == "upsample_video":
        src = job.get("video_path") or job.get("image_path")
        if not src:
            raise ValueError("upsample_video needs video_path")
        result = _ltx_video_upscale(
            call_pipe,
            src,
            cb,
            device=device,
            prompt=prompt,
            negative=negative,
            fps=int(job.get("fps") or 24),
            generator=generator,
        )
        used_attempt = {"ai_upscale": True}
    if two_stage and attempts and result is None:
        try:
            result = _ltx_two_stage(
                call_pipe, attempts[0], cb, steps=steps, live=live, width=width, height=height, device=device
            )
            used_attempt = attempts[0]
            width, height = width * 2, height * 2
        except Exception as exc:  # noqa: BLE001
            result = None
            print(f"[studionels] two-stage upscale skipped: {exc}", flush=True)
            _progress(cb, f"2× upscale unavailable ({str(exc)[:80]}) — generating at normal size", 0.2)
    for attempt in attempts if result is None else []:
        try:
            result = _call_pipe_with_progress(
                call_pipe,
                attempt,
                cb,
                steps=steps,
                label="Generating video",
                live=live,
            )
            used_attempt = attempt
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
    if needs_image and used_attempt is not None and "image" not in used_attempt:
        raise RuntimeError(
            f"{model.get('label') or 'This model'} could not use your "
            f"{'start photo' if mode == 'i2v' else 'reference photo'} ({tried_errors[0] if tried_errors else 'no image input'}), "
            "so the result was not saved. Pick a model that supports Image → Video."
        )

    _progress(cb, "Denoise finished — collecting frames…", 0.96)

    # LTX-2 may return (video, audio) tuple / list — never truth-test arrays
    if (
        isinstance(result, (tuple, list))
        and len(result) > 0
        and not hasattr(result, "frames")
    ):
        result = result[0]

    _frames = getattr(result, "frames", None)
    _images = getattr(result, "images", None)
    if _frames is not None:
        video_frames = _frames
    elif _images is not None:
        video_frames = _images
    elif hasattr(result, "shape"):
        video_frames = result
    elif isinstance(result, (list, tuple)) and len(result) > 0:
        video_frames = result
    else:
        video_frames = None
    if video_frames is None:
        raise RuntimeError("Pipeline returned no frames")
    if isinstance(video_frames, list) and len(video_frames) > 0 and isinstance(video_frames[0], list):
        video_frames = video_frames[0]

    # Torch / numpy batches → PIL list for export
    try:
        import numpy as np
        from PIL import Image

        if hasattr(video_frames, "detach"):
            video_frames = video_frames.detach().float().cpu().numpy()
        if isinstance(video_frames, np.ndarray):
            arr = video_frames
            if arr.ndim == 5:
                arr = arr[0]
            if arr.ndim == 4 and arr.shape[1] in (1, 3, 4) and arr.shape[1] < arr.shape[-1]:
                arr = np.transpose(arr, (0, 2, 3, 1))
            check_frames_look_real(arr)
            pil_list = []
            for frame in arr:
                f = frame
                if f.dtype != np.uint8:
                    peak = float(np.nanmax(f)) if getattr(f, "size", 0) else 0.0
                    if peak <= 1.5:
                        f = (np.clip(f, 0, 1) * 255).astype(np.uint8)
                    else:
                        f = np.clip(f, 0, 255).astype(np.uint8)
                if getattr(f, "ndim", 0) == 2:
                    f = np.stack([f, f, f], axis=-1)
                pil_list.append(Image.fromarray(f[..., :3] if f.shape[-1] >= 3 else f))
            video_frames = pil_list
    except RuntimeError:
        raise
    except Exception as _frames_exc:
        raise RuntimeError(f"Could not convert decoded frames for export: {_frames_exc}") from _frames_exc

    # Pipelines that hand back PIL frames skip the array path above.
    try:
        import numpy as np

        if isinstance(video_frames, list) and video_frames and hasattr(video_frames[0], "size"):
            check_frames_look_real(
                np.stack([np.asarray(f, dtype=np.float32) for f in video_frames[::4]])
            )
    except RuntimeError:
        raise
    except Exception:
        pass

    n_frames = len(video_frames) if hasattr(video_frames, "__len__") else 0
    _progress(cb, f"Exporting MP4 ({n_frames} frames)…", 0.97)
    media = _heartbeat_while(
        cb,
        f"Exporting MP4 ({n_frames} frames)",
        0.97,
        0.99,
        lambda: _export_video_frames(video_frames, out_path, fps=fps),
        max_sec=5 * 60,
    )
    thumb = str(Path(media).with_suffix(".png"))
    if not Path(thumb).exists() and video_frames is not None and len(video_frames) > 0:
        try:
            _save_image(video_frames[0], Path(thumb))
        except Exception:
            pass
    _release_gpu_cache()
    if live is not None and live.timings:
        print(
            f"[studionels] live preview: {len(live.timings)} frames, "
            f"avg {sum(live.timings) / len(live.timings):.2f}s each",
            flush=True,
        )
    _progress(cb, "Done", 1.0)
    return {
        "media_path": media,
        "thumb_path": thumb if Path(thumb).exists() else media,
        "frames": n_frames,
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


def _release_gpu_cache() -> None:
    """Drop PyTorch's cached blocks so the next load does not see a full card."""
    try:
        import gc

        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _park_text_encoders(pipe) -> None:
    """Keep UMT5 / CLIP in RAM. That is the piece that asks for ~29 GB."""
    try:
        import torch
    except Exception:
        return
    for name in ("text_encoder", "text_encoder_2", "text_encoder_3"):
        mod = getattr(pipe, name, None)
        if mod is None:
            continue
        try:
            mod.to(device="cpu", dtype=torch.float16)
        except Exception:
            try:
                mod.to("cpu")
            except Exception:
                pass
    _release_gpu_cache()


_LTX2_UPGRADE_MSG = (
    "LTX-2 needs Diffusers 0.38+. In Pinokio: Update "
    "(or pip install -U 'diffusers>=0.38.0' in backend/.venv). "
    "Or pick Wan 1.3B / LTX-Video 0.9.7."
)


def _is_ltx2_attr_error(exc: BaseException) -> bool:
    msg = str(exc)
    return "LTX2TextConnectors" in msg or "ltx2" in msg.lower()


def _resolve_pipeline_cls(model: dict[str, Any]):
    """Pick the concrete Diffusers pipeline class from the catalog entry."""
    name = str(model.get("pipeline") or "").strip()
    wants_ltx2 = name == "LTX2Pipeline" or "LTX2" in name

    if wants_ltx2:
        pipe_cls = None
        try:
            from diffusers.pipelines.ltx2 import LTX2Pipeline as pipe_cls  # type: ignore
        except Exception:
            try:
                from diffusers import LTX2Pipeline as pipe_cls  # type: ignore
            except Exception:
                pipe_cls = None
        if pipe_cls is None:
            raise RuntimeError(_LTX2_UPGRADE_MSG)
        return pipe_cls

    if name == "LTXPipeline":
        try:
            from diffusers import LTXPipeline

            return LTXPipeline
        except Exception:
            try:
                from diffusers.pipelines.ltx import LTXPipeline  # type: ignore

                return LTXPipeline
            except Exception:
                pass

    if name == "StableAudioPipeline":
        try:
            from diffusers import StableAudioPipeline

            return StableAudioPipeline
        except Exception:
            pass

    from diffusers import DiffusionPipeline

    return DiffusionPipeline


def _load_timeout_sec(model: dict[str, Any]) -> int:
    """LTX-2.3 is ~90 GB of shards. Give a cold disk read time to finish."""
    ident = f"{model.get('id') or ''} {model.get('pipeline') or ''}".lower()
    if "ltx" in ident:
        return 15 * 60
    return 8 * 60


def _release_resident_model(cb: ProgressCb | None) -> None:
    """Free the warm pipeline before a new checkpoint is read.

    The cache used to keep the previous model until the new one finished
    loading, so both were committed at once. LTX-2.3 then hits Windows
    error 1455 even when the new weights would have fit on their own.
    """
    try:
        from .pipe_cache import clear as cache_clear
        from .pipe_cache import status as cache_status

        if int((cache_status() or {}).get("count") or 0) <= 0:
            return
        _progress(cb, "Releasing the previous model so this one can load…", 0.05)
        cache_clear()
    except Exception:
        return
    try:
        import gc

        gc.collect()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _build_pipeline(
    model: dict[str, Any],
    device: str,
    dtype,
    cpu_offload: bool,
    memory: dict[str, Any] | None = None,
    cb: ProgressCb | None = None,
):
    # mmgp redirects safetensors — import early when present, then re-patch backend=
    try:
        from .mmgp_accel import apply_runtime_env, mmgp_available
        from .safetensors_compat import apply_safetensors_backend_compat

        apply_runtime_env()
        if mmgp_available():
            from mmgp import offload as _mmgp_offload  # noqa: F401
        apply_safetensors_backend_compat(force=True)
    except Exception:
        pass

    from .memory import apply_memory_to_pipeline, memory_from_preset

    pipe_cls = _resolve_pipeline_cls(model)
    wants_ltx2 = "LTX2" in str(model.get("pipeline") or "")

    source, is_local = _resolve_model_source(model)
    short = source if len(str(source)) < 80 else ("…" + str(source)[-60:])
    if is_local:
        _progress(cb, f"Loading from local disk (no HF download)… {short}", 0.06)
    else:
        _progress(cb, f"Loading from Hugging Face cache / download… {short}", 0.06)

    def _dtype_kwargs(dt) -> dict[str, Any]:
        # Newer diffusers prefer dtype=; older want torch_dtype=
        return {"dtype": dt}

    load_kwargs: dict[str, Any] = _dtype_kwargs(dtype)
    # Stream shards into RAM. A 22B file must not be allocated in one block.
    load_kwargs["low_cpu_mem_usage"] = True
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

    def _from_pretrained(src: str, **kwargs: Any):
        try:
            return pipe_cls.from_pretrained(src, **kwargs)
        except TypeError as exc:
            # Older diffusers: dtype= unknown, or low_cpu_mem_usage not accepted.
            msg = str(exc)
            if "dtype" in kwargs and ("dtype" in msg or "unexpected" in msg.lower()):
                alt = dict(kwargs)
                dt = alt.pop("dtype", None)
                if dt is not None:
                    alt["torch_dtype"] = dt
                return pipe_cls.from_pretrained(src, **alt)
            if "low_cpu_mem_usage" in kwargs and "low_cpu_mem_usage" in msg:
                alt = dict(kwargs)
                alt.pop("low_cpu_mem_usage", None)
                return pipe_cls.from_pretrained(src, **alt)
            raise
        except AttributeError as exc:
            if wants_ltx2 and _is_ltx2_attr_error(exc):
                raise RuntimeError(_LTX2_UPGRADE_MSG) from exc
            raise

    # Always materialize on CPU first so mmgp can own device placement.
    # Drop the previous resident model first — LTX-2.3 will not fit beside it.
    _release_resident_model(cb)
    from .safetensors_nommap import (
        explain_weight_load_error,
        reset_load_cast_dtype,
        set_load_cast_dtype,
    )

    quant_plan = None
    if is_local:
        try:
            from .mmgp_accel import system_ram_gb

            quant_plan = ram_safe_quant_plan(str(source), system_ram_gb())
        except Exception:
            quant_plan = None
    _set_load_note("")
    # Saved int8 copies (written after the first load) skip reading the 16/32-bit
    # weights and quantizing them on the CPU again — the Wan2GP fast-start trick.
    dtype_label = str(dtype).replace("torch.", "")
    cached_parts = None
    if quant_plan:
        try:
            from .int8_cache import load_pipeline_components

            _set_load_note("reading saved 8-bit copies")
            cached_parts = load_pipeline_components(
                str(source), list(quant_plan["components"]), dtype_label, cb
            )
        except Exception:
            cached_parts = None
    if cached_parts:
        load_kwargs.update(cached_parts)
        _set_load_note("saved 8-bit transformer + text encoder loaded — reading the small parts")
    elif quant_plan:
        try:
            load_kwargs["quantization_config"] = _quanto_mapping(quant_plan["components"])
            _set_load_note(
                f"reading + shrinking {' & '.join(quant_plan['components'])} to 8-bit "
                f"(target ~{quant_plan['after_gb']:.0f} GB of {quant_plan['gb16']:.0f} GB) — "
                "first load only, takes a few minutes"
            )
            _progress(
                cb,
                f"Model is {quant_plan['gb16']} GB at 16-bit — bigger than RAM allows. "
                f"Shrinking {', '.join(quant_plan['components'])} to 8-bit while reading "
                f"(~{quant_plan['after_gb']} GB). First load only; it stays loaded after.",
                0.07,
            )
        except Exception as exc:  # noqa: BLE001
            quant_plan = None
            _progress(cb, f"8-bit load not available ({exc}); loading at 16-bit", 0.07)

    # Large float32 matrices (the Gemma text encoder) are stored as float16
    # while they are read, so a 49 GB shard does not have to sit in RAM twice.
    set_load_cast_dtype(dtype)
    try:
        pipe = _from_pretrained(source, **load_kwargs)
    except TypeError as first_exc:
        # safetensors/mmgp rejected backend= — patch and retry once
        if "backend" in str(first_exc):
            try:
                from .safetensors_compat import apply_safetensors_backend_compat

                apply_safetensors_backend_compat(force=True)
            except Exception:
                pass
            pipe = _from_pretrained(source, **load_kwargs)
        elif is_local:
            raise RuntimeError(explain_weight_load_error(str(source), first_exc)) from first_exc
        else:
            raise
    except AttributeError as first_exc:
        if wants_ltx2 and _is_ltx2_attr_error(first_exc):
            raise RuntimeError(_LTX2_UPGRADE_MSG) from first_exc
        raise
    except RuntimeError:
        raise
    except Exception as first_exc:
        if wants_ltx2 and _is_ltx2_attr_error(first_exc):
            raise RuntimeError(_LTX2_UPGRADE_MSG) from first_exc
        if "backend" in str(first_exc):
            try:
                from .safetensors_compat import apply_safetensors_backend_compat

                apply_safetensors_backend_compat(force=True)
                pipe = _from_pretrained(source, **load_kwargs)
            except Exception as retry_exc:
                if wants_ltx2 and _is_ltx2_attr_error(retry_exc):
                    raise RuntimeError(_LTX2_UPGRADE_MSG) from retry_exc
                raise RuntimeError(
                    f"Weight load failed (safetensors/transformers mismatch): {retry_exc}. "
                    "Pinokio → Update, or: pip install -U 'safetensors>=0.5.3'"
                ) from retry_exc
        elif is_local:
            raise RuntimeError(explain_weight_load_error(str(source), first_exc)) from first_exc
        else:
            raise RuntimeError(
                f"Could not load weights in float16: {first_exc}. "
                "A float32 retry would ask the GPU for about 29 GB."
            ) from first_exc
    finally:
        reset_load_cast_dtype()

    if quant_plan:
        try:
            pipe._studionels_prequantized = list(quant_plan["components"])  # type: ignore[attr-defined]
        except Exception:
            pass
        if not cached_parts:
            try:
                from .int8_cache import save_pipeline

                _set_load_note("saving 8-bit copies for faster starts (one time)")
                save_pipeline(str(source), pipe, list(quant_plan["components"]), dtype_label, cb)
            except Exception:
                pass
    _set_load_note("weights in RAM — mmgp is placing them on the GPU")
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
    # Wan2GP attention mode is sdpa, with AOTriton enabled for AMD.
    try:
        import torch

        torch.backends.cuda.enable_flash_sdp(True)
        torch.backends.cuda.enable_mem_efficient_sdp(True)
        torch.backends.cuda.enable_math_sdp(True)
        if hasattr(pipe, "set_attention_backend"):
            pipe.set_attention_backend("sdpa")
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
    if mem.get("text_encoder_on_cpu"):
        _park_text_encoders(pipe)
    return pipe



# ---------------------------------------------------------------------------
# RAM-safe loading for models bigger than system RAM (LTX-2.3 22B on 64 GB).
#
# from_pretrained used to read every component at 16-bit before mmgp shrank
# it: ~38 GB transformer + ~24 GB Gemma encoder = more than 61.6 GB usable, so
# Windows swapped and the load froze ("mmgp is placing this model" for 6+ min).
# When the 16-bit size would not fit comfortably, the big components are
# quantized to int8 *while they are read* (quanto), so RAM peaks at ~half.
# ---------------------------------------------------------------------------


# What the loader is doing right now (shown by the load heartbeat).
_LOAD_NOTE: dict[str, str] = {"text": ""}


def _set_load_note(text: str) -> None:
    _LOAD_NOTE["text"] = text


def _ram_in_use_note() -> str:
    try:
        import psutil

        rss = psutil.Process().memory_info().rss / 1024**3
        vm = psutil.virtual_memory()
        return f" · {rss:.1f} GB loaded · PC RAM {vm.percent:.0f}% used"
    except Exception:
        return ""

_DTYPE_BYTES = {"F64": 8, "F32": 4, "BF16": 2, "F16": 2, "F8_E4M3": 1, "F8_E5M2": 1, "I8": 1, "U8": 1}


def _component_gb16(folder: Path) -> float:
    """Size of one component folder once loaded at 16-bit (reads only shard headers)."""
    import json as _json
    import struct as _struct

    total = 0.0
    for f in folder.glob("*.safetensors"):
        try:
            with open(f, "rb") as fh:
                n = _struct.unpack("<Q", fh.read(8))[0]
                header = _json.loads(fh.read(min(n, 50_000_000)))
            # Count each tensor at its own width. A shard is not all-float32 just
            # because it holds a few small float32 tensors (LTX-2.3's bf16
            # transformer has 0.02 GB of them, which used to halve all 35 GB).
            shard = 0.0
            for k, v in header.items():
                if k == "__metadata__" or not isinstance(v, dict):
                    continue
                start, end = v["data_offsets"]
                width = _DTYPE_BYTES.get(str(v.get("dtype") or ""), 2)
                nbytes = float(end) - float(start)
                shard += nbytes * (2.0 / width) if width > 2 else nbytes
            total += shard
        except Exception:
            try:
                total += f.stat().st_size
            except Exception:
                pass
    return total / 1024**3


def ram_safe_quant_plan(source: str, ram_gb: float | None) -> dict[str, Any] | None:
    """Return {components:{name: library}, gb16, after_gb} if int8-at-load is needed, else None."""
    import json as _json

    root = Path(str(source))
    index = root / "model_index.json"
    if not ram_gb or not index.exists():
        return None
    if os.environ.get("STUDIONELS_LOAD_QUANT", "auto").lower() in ("0", "off", "false"):
        return None
    try:
        spec = _json.loads(index.read_text(encoding="utf-8"))
    except Exception:
        return None
    sizes: dict[str, float] = {}
    libs: dict[str, str] = {}
    for name, val in spec.items():
        if name.startswith("_") or not isinstance(val, list) or len(val) != 2:
            continue
        folder = root / name
        if folder.is_dir():
            sizes[name] = _component_gb16(folder)
            libs[name] = str(val[0])
    gb16 = sum(sizes.values())
    budget = float(ram_gb) * 0.7  # leave Windows + the app ~30%
    forced = os.environ.get("STUDIONELS_LOAD_QUANT", "auto").lower() in ("1", "on", "true", "always")
    if gb16 <= budget and not forced:
        return None
    picks = {
        n: libs[n]
        for n, g in sorted(sizes.items(), key=lambda kv: -kv[1])
        if g >= 4.0 and libs.get(n) in ("diffusers", "transformers")
    }
    if not picks:
        return None
    after = gb16 - sum(sizes[n] / 2 for n in picks)
    return {"components": picks, "gb16": round(gb16, 1), "after_gb": round(after, 1)}


def _quanto_mapping(components: dict[str, str]):
    """PipelineQuantizationConfig with int8 quanto per component (diffusers vs transformers class)."""
    from diffusers import PipelineQuantizationConfig
    from diffusers import QuantoConfig as DiffusersQuanto

    mapping: dict[str, Any] = {}
    for name, lib in components.items():
        if lib == "transformers":
            from transformers import QuantoConfig as TransformersQuanto

            mapping[name] = TransformersQuanto(weights="int8")
        else:
            mapping[name] = DiffusersQuanto(weights_dtype="int8")
    return PipelineQuantizationConfig(quant_mapping=mapping)

def preload_diffusers_model(
    model_id: str,
    *,
    preset_id: str | None = None,
    cb: ProgressCb | None = None,
) -> dict[str, Any]:
    """Load one Diffusers pipeline into pipe_cache without generating.

    Same build path as Generate's warm_cache branch — keeps one resident model
    so the next Generate skips the multi-minute weight reload.
    """
    import torch

    from .memory import resolve_memory_for_job
    from .pipe_cache import cache_key, get as cache_get, put as cache_put, status as cache_status

    model = get_model(model_id)
    if not model:
        raise ValueError(f"Unknown model {model_id}")
    if model.get("pipeline") == "lanczos" or model.get("kind") == "upsample":
        raise RuntimeError(f"{model.get('label') or model_id} does not use a Diffusers weight cache.")

    modes = list(model.get("modes") or [])
    mode = str(modes[0] if modes else ("t2v" if model.get("kind") == "video" else "t2i"))
    job: dict[str, Any] = {
        "model_id": model_id,
        "mode": mode,
        "preset_id": preset_id,
        "warm_cache": True,
    }

    label = str(model.get("label") or model_id)
    _progress(cb, f"Preloading {label} into RAM/VRAM…", 0.05)

    device_info = detect_device()
    device = device_info["device"] if device_info["ready_for_inference"] else "cpu"
    if not device_info.get("diffusers_available"):
        raise RuntimeError(
            "Diffusers is not available yet. In Pinokio run Update / Install AMD engine, then Stop → Start."
        )
    mem = resolve_memory_for_job(job)
    dtype_name = str(mem.get("dtype") or "bfloat16")
    if not device.startswith("cuda"):
        dtype = torch.float32
        mem["placement"] = "cpu"
    elif dtype_name in ("float16", "fp16"):
        dtype = torch.float16
    elif dtype_name in ("float32", "fp32"):
        dtype = torch.float32
    elif device_info.get("rocm"):
        # Windows ROCm VAE often errors on bfloat16. fp16 is faster and stable on R9700.
        dtype = torch.float16
        dtype_name = "float16"
    else:
        dtype = torch.bfloat16
    dtype, dtype_name = _model_safe_dtype(model, device, dtype, dtype_name, mem)

    from .memory import tune_memory_for_model

    mem = tune_memory_for_model(mem, model)
    cpu_offload = bool(mem.get("cpu_offload", True))
    dtype_key = str(getattr(dtype, "__name__", None) or dtype)
    key = cache_key(str(model.get("id") or model_id), mem, dtype_key)
    pipe = cache_get(key)
    if pipe is not None:
        cached = cache_status().get("cached") or [label]
        _progress(cb, f"Model ready: {label}", 1.0)
        return {"ok": True, "label": label, "cached": list(cached), "already_loaded": True}

    _, is_local_src = _resolve_model_source(model)
    load_label = (
        "Loading from local disk (no HF download)"
        if is_local_src
        else "Loading from Hugging Face cache / download"
    )
    _progress(cb, f"Preloading {label} into RAM/VRAM…", 0.08)
    pipe = _heartbeat_while(
        cb,
        f"Preloading {label} · {load_label}",
        0.08,
        0.9,
        lambda: _build_pipeline(model, device, dtype, cpu_offload, mem, cb=cb),
        max_sec=_load_timeout_sec(model),
        is_local=is_local_src,
    )
    if pipe is None:
        raise RuntimeError(f"Failed to preload {label}")
    cache_put(key, pipe, label=label)
    cached = cache_status().get("cached") or [label]
    _progress(cb, f"Model ready: {label}", 1.0)
    return {"ok": True, "label": label, "cached": list(cached), "already_loaded": False}


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
