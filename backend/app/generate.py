from __future__ import annotations

import asyncio
import colorsys
import hashlib
from pathlib import Path

import httpx

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = ImageDraw = ImageFont = None  # type: ignore

from .models import Project, Take, new_id, utc_now
from .paths import MEDIA_DIR, ensure_dirs
from .storage import get_preset, load_settings, save_project


def _seed_for(shot_id: str, n: int) -> int:
    h = hashlib.sha256(f"{shot_id}:{n}".encode()).hexdigest()
    return int(h[:8], 16)


def _color_from_seed(seed: int) -> tuple[int, int, int]:
    hue = (seed % 1000) / 1000
    r, g, b = colorsys.hsv_to_rgb(hue, 0.35, 0.72)
    return int(r * 255), int(g * 255), int(b * 255)


def _draw_placeholder(
    path: Path,
    title: str,
    subtitle: str,
    seed: int,
    size: tuple[int, int] = (768, 432),
) -> None:
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    if Image is None:
        # Tiny valid 1x1 fallback if Pillow missing — still creates a path.
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return
    img = Image.new("RGB", size, _color_from_seed(seed))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size[0], 36], fill=(18, 22, 28))
    draw.rectangle([0, size[1] - 36, size[0], size[1]], fill=(18, 22, 28))
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((28, size[1] // 2 - 20), title[:48], fill=(250, 246, 238), font=font)
    draw.text((28, size[1] // 2 + 8), subtitle[:64], fill=(230, 220, 200), font=font)
    draw.text(
        (28, size[1] - 28),
        f"local preview · seed {seed}",
        fill=(160, 170, 180),
        font=font,
    )
    img.save(path, format="PNG")


async def probe_ollama() -> bool:
    settings = load_settings()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def probe_comfyui() -> bool:
    settings = load_settings()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.comfyui_url.rstrip('/')}/system_stats")
            return r.status_code == 200
    except Exception:
        return False


async def _try_comfy_queue(prompt_graph: dict) -> str | None:
    """Best-effort ComfyUI queue. Returns prompt_id or None."""
    settings = load_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.comfyui_url.rstrip('/')}/prompt",
                json={"prompt": prompt_graph},
            )
            if r.status_code == 200:
                return r.json().get("prompt_id")
    except Exception:
        return None
    return None


def _minimal_comfy_stub(prompt_text: str) -> dict:
    """
    Not a full production graph — presence lets advanced users replace this
    with their ROCm ComfyUI workflow JSON while Framewright still orchestrates jobs.
    """
    return {
        "framewright_note": {
            "class_type": "Note",
            "inputs": {"text": prompt_text[:500]},
        }
    }


async def generate_takes(
    project: Project,
    shot_ids: list[str] | None = None,
    kind: str = "video",
) -> Project:
    preset = get_preset(project.preset_id)
    gen = preset.get("generation", {})
    width = int(gen.get("default_width", 768))
    height = int(gen.get("default_height", 432))
    targets = [
        s
        for s in project.shots
        if shot_ids is None or s.id in shot_ids
    ]
    if not targets and kind != "video":
        # Character / scene stills without shots
        targets = []

    comfy_up = await probe_comfyui()

    if kind in ("character_still", "scene_still"):
        # Generate reference stills for profiles lacking media
        items = (
            project.characters if kind == "character_still" else project.scenes
        )
        for item in items:
            if item.reference_path:
                continue
            seed = _seed_for(item.id, 1)
            out = MEDIA_DIR / project.id / f"{item.id}.png"
            label = getattr(item, "name", "ref")
            _draw_placeholder(
                out,
                label,
                "local character/scene reference",
                seed,
                (width, height),
            )
            item.reference_path = str(out)
            await asyncio.sleep(0.05)
        return save_project(project)

    for shot in targets:
        shot.status = "generating"
        save_project(project)
        # Attempt real queue if Comfy is up; still write local preview for UX.
        if comfy_up and gen.get("backend") == "comfyui":
            await _try_comfy_queue(_minimal_comfy_stub(shot.prompt or shot.action))

        existing = [t for t in project.takes if t.shot_id == shot.id]
        take_n = len(existing) + 1
        seed = _seed_for(shot.id, take_n)
        out = MEDIA_DIR / project.id / f"{shot.id}_take{take_n}.png"
        _draw_placeholder(
            out,
            shot.title,
            shot.action or shot.prompt or kind,
            seed,
            (width, height),
        )
        take = Take(
            id=new_id("take"),
            shot_id=shot.id,
            label=f"Take {chr(64 + take_n)}",
            media_path=str(out),
            thumb_path=str(out),
            seed=seed,
            created_at=utc_now(),
            is_placeholder=not comfy_up,
            score_note="Pin in Sampling if you like this direction.",
        )
        project.takes.append(take)
        if not shot.pinned_take_id:
            shot.pinned_take_id = take.id
        shot.status = "ready"
        save_project(project)
        # Sequential by default to keep VRAM calm
        await asyncio.sleep(0.08)

    return save_project(project)
