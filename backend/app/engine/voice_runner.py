"""VoxCPM2 (Apache 2.0) dialogue: design a voice from a description, or clone
one from a short clip, in 30 languages. 48 kHz mono.

Prompt format (VoxCPM's own): "(young woman, calm, warm)The line to say."
A reference audio clip (reference_path) clones that voice; the brackets then
only steer delivery ("slightly faster, cheerful").
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from .queue_store import models_dir

ProgressCb = Callable[[str, float], None] | None

WEIGHTS = "openbmb__VoxCPM2"
_LOCK = threading.Lock()
_MODEL: dict[str, Any] = {}
AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a")


def is_ready() -> bool:
    return (models_dir() / WEIGHTS / "model.safetensors").is_file()


def _model(cb: ProgressCb):
    if "m" in _MODEL:
        return _MODEL["m"]
    from .rocm_compat import patch_missing_distributed

    patch_missing_distributed()
    from voxcpm import VoxCPM

    if cb:
        cb("Loading VoxCPM2 (voices)…", 0.1)
    # optimize=False: torch.compile needs Triton, which Windows ROCm lacks
    _MODEL["m"] = VoxCPM.from_pretrained(str(models_dir() / WEIGHTS), load_denoiser=False, optimize=False)
    return _MODEL["m"]


def speak(text: str, out_path: Path, *, reference: str | None = None, seed: Any = None, cb: ProgressCb = None) -> str:
    import soundfile as sf
    import torch

    line = (text or "").strip()
    if not line:
        raise ValueError("Write the line to say, e.g. (old man, gravelly, tired)We close at nine.")
    ref = reference if reference and str(reference).lower().endswith(AUDIO_EXT) and Path(reference).is_file() else None
    with _LOCK:
        m = _model(cb)
        if seed is not None:
            torch.manual_seed(int(seed))
        if cb:
            cb("Cloning voice from your clip…" if ref else "Speaking (voice from the description)…", 0.35)
        kwargs: dict[str, Any] = {"text": line, "cfg_value": 2.0, "inference_timesteps": 10}
        if ref:
            kwargs["reference_wav_path"] = ref
        wav = m.generate(**kwargs)
        dest = out_path.with_suffix(".wav")
        dest.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(dest), wav, m.tts_model.sample_rate)
    return str(dest)
