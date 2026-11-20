"""ACE-Step 1.5 (MIT) songs and score: text (+ optional lyrics) -> stereo 48 kHz.

The ACE-Step code lives in vendor/ACE-Step-1.5 (cloned by install.js); the
weights in models/ACE-Step__Ace-Step1.5. Handlers stay loaded between jobs in
the warm engine (DiT ~5 GB, planner LM ~4 GB).
"""
from __future__ import annotations

import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from ..paths import ROOT
from .queue_store import models_dir

ProgressCb = Callable[[str, float], None] | None

VENDOR = ROOT / "vendor" / "ACE-Step-1.5"
WEIGHTS = "ACE-Step__Ace-Step1.5"
_LOCK = threading.Lock()
_HANDLERS: dict[str, Any] = {}

# "Lyrics:" header, or song-section tags like [verse] / [chorus]
_LYRICS_SPLIT = re.compile(r"(?is)^(.*?)(?:\n\s*lyrics\s*:\s*\n?|(?=\[(?:verse|chorus|intro|bridge|outro|pre-chorus|hook)[^\]]*\]))(.*)$")


def split_prompt(prompt: str) -> tuple[str, str]:
    """'style text' + optional lyrics. No lyrics -> instrumental."""
    text = (prompt or "").strip()
    m = _LYRICS_SPLIT.match(text)
    if m and m.group(2).strip():
        return m.group(1).strip(" ,.\n") or "song", m.group(2).strip()
    return text or "cinematic instrumental score", ""


def is_ready() -> bool:
    w = models_dir() / WEIGHTS
    return (VENDOR / "acestep" / "inference.py").is_file() and (w / "acestep-v15-turbo" / "model.safetensors").is_file()


def _link_checkpoints() -> None:
    """ACE-Step looks for <repo>/checkpoints; point it at models/ (junction, no copy)."""
    link = VENDOR / "checkpoints"
    target = models_dir() / WEIGHTS
    if link.exists():
        return
    import subprocess

    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def _handlers(cb: ProgressCb) -> tuple[Any, Any]:
    if "dit" in _HANDLERS:
        return _HANDLERS["dit"], _HANDLERS["llm"]
    if not is_ready():
        raise RuntimeError("ACE-Step 1.5 isn't installed (code in vendor/ACE-Step-1.5, weights in models/).")
    from .rocm_compat import patch_fsq_meta_init, patch_missing_distributed

    patch_missing_distributed()
    patch_fsq_meta_init()
    _link_checkpoints()
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler

    if cb:
        cb("Loading ACE-Step 1.5 (music model)…", 0.08)
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=str(VENDOR), config_path="acestep-v15-turbo", device="auto", offload_to_cpu=False)
    if not ok:
        raise RuntimeError(f"ACE-Step music model failed to load: {str(msg)[:300]}")
    if cb:
        cb("Loading ACE-Step song planner…", 0.15)
    llm = LLMHandler()
    msg, ok = llm.initialize(
        checkpoint_dir=str(VENDOR / "checkpoints"),
        lm_model_path="acestep-5Hz-lm-1.7B",
        backend="pt",
        device="auto",
        offload_to_cpu=False,
        dtype=None,
    )
    if not ok:
        raise RuntimeError(f"ACE-Step planner failed to load: {str(msg)[:300]}")
    _HANDLERS.update(dit=dit, llm=llm)
    return dit, llm


def generate_song(
    prompt: str,
    out_path: Path,
    *,
    duration_sec: float,
    seed: Any = None,
    steps: int = 8,
    cb: ProgressCb = None,
) -> str:
    """Write a song/score to out_path (.wav). Returns the file path."""
    caption, lyrics = split_prompt(prompt)
    with _LOCK:
        dit, llm = _handlers(cb)
        from acestep.inference import GenerationConfig, GenerationParams, generate_music

        params = GenerationParams(
            task_type="text2music",
            thinking=True,
            caption=caption[:500],
            lyrics=lyrics[:4000] if lyrics else "[Instrumental]",
            instrumental=not lyrics,
            vocal_language="en" if lyrics else "unknown",
            duration=max(10.0, min(240.0, float(duration_sec or 30))),
            inference_steps=max(4, min(16, int(steps or 8))),
            guidance_scale=1.0,
            seed=int(seed) if seed is not None else -1,
        )
        if cb:
            kind = "song with vocals" if lyrics else "instrumental"
            cb(f"Composing {kind} · {params.duration:.0f}s (planner writes the arrangement first)…", 0.25)
        work = out_path.parent / f"{out_path.stem}_ace"
        work.mkdir(parents=True, exist_ok=True)
        res = generate_music(dit, llm, params=params, config=GenerationConfig(batch_size=1, audio_format="wav"), save_dir=str(work))
    if not res.success or not res.audios:
        raise RuntimeError(f"ACE-Step failed: {str(getattr(res, 'error', '') or 'no audio')[:300]}")
    src = Path(res.audios[0]["path"])
    dest = out_path.with_suffix(".wav")
    shutil.move(str(src), dest)
    shutil.rmtree(work, ignore_errors=True)
    return str(dest)
