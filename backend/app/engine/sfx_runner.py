"""Stable Audio 3 Small SFX (Stability AI Community licence: commercial use
free under $1M a year): sound effects and ambience from text, stereo 44.1 kHz.

Loads from models/stabilityai__stable-audio-3-small-sfx instead of the HF
cache, so nothing is fetched at generate time.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

from .queue_store import models_dir

ProgressCb = Callable[[str, float], None] | None

WEIGHTS = "stabilityai__stable-audio-3-small-sfx"
_LOCK = threading.Lock()
_MODEL: dict[str, Any] = {}


def is_ready() -> bool:
    return (models_dir() / WEIGHTS / "model.safetensors").is_file()


def _model(cb: ProgressCb):
    if "m" in _MODEL:
        return _MODEL["m"]
    import torch
    from stable_audio_3.loading_utils import load_diffusion_cond
    from stable_audio_3.model import StableAudioModel

    folder = models_dir() / WEIGHTS
    config = json.loads((folder / "model_config.json").read_text(encoding="utf-8"))
    # Point the text encoder at the local copy (the config names the HF repo)
    for cond in config.get("model", {}).get("conditioning", {}).get("configs", []):
        c = cond.get("config") or {}
        if c.get("repo_id") and c.get("subfolder"):
            c["model_path"] = str(folder / c.pop("subfolder"))
            c.pop("repo_id", None)
    if cb:
        cb("Loading Stable Audio 3 (sound effects)…", 0.1)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    half = device == "cuda"
    model = load_diffusion_cond(config, str(folder / "model.safetensors"), device=device, model_half=half)
    model.use_lora = False
    model.lora_names = []
    _MODEL["m"] = StableAudioModel(model, config, device, half)
    return _MODEL["m"]


def make_sound(prompt: str, out_path: Path, *, duration_sec: float, seed: Any = None, negative: str = "", cb: ProgressCb = None) -> str:
    import soundfile as sf

    text = (prompt or "").strip() or "ambient room tone"
    seconds = max(1.0, min(120.0, float(duration_sec or 7)))
    with _LOCK:
        sa = _model(cb)
        if cb:
            cb(f"Making sound · {seconds:.0f}s…", 0.4)
        audio = sa.generate(
            prompt=text,
            negative_prompt=negative or None,
            duration=seconds,
            steps=8,
            cfg_scale=1.0,
            seed=int(seed) if seed is not None else -1,
        )
        rate = int(sa.model_config.get("sample_rate") or 44100)
    wav = audio[0] if getattr(audio, "dim", lambda: 0)() == 3 else audio
    arr = wav.float().cpu().clamp(-1, 1).numpy().T  # (samples, channels)
    dest = out_path.with_suffix(".wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dest), arr, rate)
    return str(dest)
