"""Keep Wan video decode from hanging after the last denoise step."""
from __future__ import annotations

from typing import Any, Callable

ProgressCb = Callable[[str, float], None]


def plan_wan_chunks(num_latent_frames: int, chunk: int = 4):
    total = int(num_latent_frames)
    size = max(1, int(chunk))
    if total <= 0:
        return []
    if total <= size:
        return [(0, total, 0)]
    planned = []
    start = 0
    while start < total:
        end = min(total, start + size)
        planned.append((0, end, 0) if start == 0 else (max(0, start - 1), end, 1))
        if end >= total:
            break
        start = end
    return planned


def _is_wan_vae(vae):
    name = type(vae).__name__.lower()
    cfg = getattr(vae, "config", None)
    cls = str(getattr(cfg, "_class_name", "") or "").lower() if cfg is not None else ""
    return "wan" in name or "wan" in cls


def _disable_tiling(pipe, vae):
    for obj in (vae, pipe):
        if obj is None:
            continue
        for method in ("disable_tiling", "disable_vae_tiling"):
            fn = getattr(obj, method, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        if hasattr(obj, "use_tiling"):
            try:
                obj.use_tiling = False
            except Exception:
                pass


def _reset_causal_cache(vae):
    modules = getattr(vae, "modules", None)
    if not callable(modules):
        return
    for mod in modules():
        if hasattr(mod, "feat_cache"):
            try:
                mod.feat_cache = None
            except Exception:
                pass


def _as_tensor(out):
    if isinstance(out, tuple):
        return out[0]
    if hasattr(out, "sample"):
        return out.sample
    return out


def _drop_front(tensor, n):
    if n <= 0 or not hasattr(tensor, "dim") or tensor.dim() < 3:
        return tensor
    # Wan decode output often (B,C,T,H,W) with C in 1/3/4 → time on axis 2
    axis = 2 if tensor.dim() == 5 and int(tensor.shape[1]) in (1, 3, 4) else (1 if tensor.dim() == 5 else 2)
    length = int(tensor.shape[axis])
    if n >= length:
        return tensor
    return tensor.narrow(axis, n, length - n)


def _decode_latents(vae, original, latents, progress, *, chunk):
    def once(piece):
        _reset_causal_cache(vae)
        return _as_tensor(original(piece, return_dict=False))

    if progress:
        progress("Denoise finished — decoding frames (VAE, not another sample step)…", 0.91)
    is_5d = hasattr(latents, "dim") and callable(latents.dim) and latents.dim() == 5
    if not is_5d or not _is_wan_vae(vae) or getattr(vae, "use_tiling", False):
        return once(latents)
    # Diffusers Wan layout (B,C,T,H,W)
    if int(latents.shape[1]) <= 4 and int(latents.shape[2]) > 4:
        return once(latents)  # unexpected layout
    count = int(latents.shape[2])
    slices = plan_wan_chunks(count, chunk)
    if len(slices) <= 1:
        return once(latents)
    import torch

    pieces = []
    for index, (ctx, end, drop) in enumerate(slices):
        if progress:
            progress(
                f"Denoise finished — decoding frames {index + 1}/{len(slices)} (VAE). "
                "The sample steps are already done.",
                0.90 + 0.06 * ((index + 1) / len(slices)),
            )
        decoded = once(latents[:, :, ctx:end])
        pieces.append(_drop_front(decoded, drop))
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    axis = 2 if pieces[0].dim() == 5 and int(pieces[0].shape[1]) in (1, 3, 4) else 1
    return torch.cat(pieces, dim=axis)


def install_safe_video_decode(pipe, progress=None, *, chunk=4):
    vae = getattr(pipe, "vae", None)
    if vae is None:
        return
    wan_tiled = False
    if _is_wan_vae(vae) and callable(getattr(vae, "enable_tiling", None)):
        # Wan 2.1 VAE, 33 frames at 832x480 on an R9700: 251 s in one pass,
        # 17 s tiled (and 2.2 GB instead of 6.9 GB). The old "tiling hangs on
        # AMD" note no longer reproduces; chunked decode stays as the fallback.
        try:
            vae.enable_tiling()
            wan_tiled = True
        except Exception:
            wan_tiled = False
    if not wan_tiled:
        _disable_tiling(pipe, vae)
    # LTX(-2) VAEs: decode in overlapping 16-frame chunks. One big 3D conv over
    # all frames falls onto MIOpen's slow fallback on RDNA4: 73 frames at
    # 768x448 took 70 s in one pass and 6 s framewise (17 frames alone: 0.8 s).
    if not _is_wan_vae(vae) and hasattr(vae, "use_framewise_decoding"):
        try:
            vae.use_framewise_decoding = True
        except Exception:
            pass
    vae._studionels_decode_progress = progress
    if getattr(vae, "_studionels_decode_wrapped", False):
        return
    original = vae.decode

    def wrapped(z, *args, **kwargs):
        prog = getattr(vae, "_studionels_decode_progress", None)
        return_dict = kwargs.get("return_dict", True)
        if args or any(k != "return_dict" for k in kwargs):
            return original(z, *args, **kwargs)
        try:
            sample = _decode_latents(vae, original, z, prog, chunk=chunk)
        except Exception:
            return original(z, return_dict=return_dict)
        if not return_dict:
            return (sample,)

        class _Decoded:
            def __init__(self, tensor):
                self.sample = tensor

        for path in (
            "diffusers.models.autoencoders.vae",
            "diffusers.models.autoencoders.autoencoder_kl",
            "diffusers.models.vae",
        ):
            try:
                module = __import__(path, fromlist=["DecoderOutput"])
                return module.DecoderOutput(sample=sample)
            except Exception:
                continue
        return _Decoded(sample)

    vae.decode = wrapped
    vae._studionels_decode_wrapped = True
