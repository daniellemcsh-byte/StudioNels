"""On-disk int8 copies of big pipeline components (the Wan2GP trick).

The first load of a model that is bigger than RAM shrinks its transformer and
text encoder to int8 while reading (quanto). For LTX-2.3 that means reading
81 GB (the Gemma encoder is float32 on disk) and quantizing on the CPU, every
time StudioNels starts. Here the result is written once, next to the model,
and later loads read the ~29 GB int8 files straight into an empty model.

Everything is best-effort: any mismatch or error means "no cache", and the
caller falls back to the normal load. Turn off with STUDIONELS_INT8_CACHE=0.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import time
from pathlib import Path
from typing import Any, Callable

FORMAT = 1
CACHE_DIRNAME = "_studionels_int8"

_DTYPE_CODES = {
    "torch.int8": "I8",
    "torch.uint8": "U8",
    "torch.int16": "I16",
    "torch.int32": "I32",
    "torch.int64": "I64",
    "torch.bool": "BOOL",
    "torch.float16": "F16",
    "torch.bfloat16": "BF16",
    "torch.float32": "F32",
    "torch.float64": "F64",
}

ProgressCb = Callable[[str, float], None]


def enabled() -> bool:
    return os.environ.get("STUDIONELS_INT8_CACHE", "1").strip().lower() not in {"0", "off", "false", "no"}


def _versions() -> dict[str, str]:
    import importlib.metadata as md

    out = {}
    for pkg in ("torch", "diffusers", "transformers", "optimum-quanto"):
        try:
            out[pkg] = md.version(pkg)
        except Exception:
            out[pkg] = "?"
    return out


def _fingerprint(component_dir: Path) -> list[list[Any]]:
    files = []
    for f in sorted(component_dir.glob("*.safetensors")) + sorted(component_dir.glob("*.json")):
        st = f.stat()
        files.append([f.name, st.st_size, int(st.st_mtime)])
    return files


def _cache_dir(source: Path, dtype_name: str, component: str) -> Path:
    return source / CACHE_DIRNAME / dtype_name / component


def _expected_meta(source: Path, component: str, library: str, class_name: str, dtype_name: str) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "component": component,
        "library": library,
        "class_name": class_name,
        "dtype": dtype_name,
        "source": _fingerprint(source / component),
        "versions": _versions(),
    }


def _index(source: Path) -> dict[str, list[str]]:
    spec = json.loads((source / "model_index.json").read_text(encoding="utf-8"))
    return {k: v for k, v in spec.items() if isinstance(v, list) and len(v) == 2}


def _matches(meta_path: Path, expected: dict[str, Any]) -> bool:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    keys = ("format", "component", "library", "class_name", "dtype", "source", "versions")
    return all(meta.get(k) == expected.get(k) for k in keys)


# --------------------------------------------------------------------------- save


def _write_safetensors(path: Path, tensors: list[tuple[str, Any]]) -> None:
    """Stream tensors to a .safetensors file without building it in memory."""
    import torch

    header: dict[str, Any] = {"__metadata__": {"format": "pt"}}
    offset = 0
    for name, t in tensors:
        code = _DTYPE_CODES.get(str(t.dtype))
        if code is None:
            raise RuntimeError(f"int8 cache: unsupported dtype {t.dtype} for {name}")
        nbytes = t.numel() * t.element_size()
        header[name] = {"dtype": code, "shape": list(t.shape), "data_offsets": [offset, offset + nbytes]}
        offset += nbytes
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    raw += b" " * ((8 - len(raw) % 8) % 8)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", len(raw)))
        fh.write(raw)
        for _name, t in tensors:
            if t.numel() == 0:
                continue
            flat = t.detach().cpu().contiguous().reshape(-1)
            if flat.dtype == torch.bool:
                flat = flat.to(torch.uint8)
            fh.write(memoryview(flat.view(torch.uint8).numpy()))


def _plain(t: Any) -> bool:
    import torch

    return type(t) is torch.Tensor or type(t) is torch.nn.Parameter


def save_component(source: Path, component: str, module: Any, dtype_name: str, cb: ProgressCb | None = None) -> bool:
    """Write one already-quantized component. Returns True when written."""
    from optimum.quanto import quantization_map
    from optimum.quanto.nn import QModuleMixin
    from optimum.quanto.tensor import QTensor

    library, class_name = _index(source)[component]
    # Only frozen int8 weights are worth caching (and safe to restore).
    for m in module.modules():
        if isinstance(m, QModuleMixin) and not isinstance(m.weight, QTensor):
            return False
    qmap = quantization_map(module)
    if not qmap:
        return False

    state = module.state_dict(keep_vars=False)
    tensors: list[tuple[str, Any]] = []
    aliases: dict[str, str] = {}
    seen: dict[tuple[int, int, tuple, str], str] = {}
    total = 0
    for name, t in state.items():
        if not _plain(t):
            return False  # unexpected subclass in the state dict: do not guess
        key = (t.untyped_storage().data_ptr(), t.storage_offset(), tuple(t.shape), str(t.dtype))
        if t.numel() and key in seen:
            aliases[name] = seen[key]  # tied weight (e.g. lm_head = embed_tokens)
            continue
        seen[key] = name
        tensors.append((name, t))
        total += t.numel() * t.element_size()

    target = _cache_dir(source, dtype_name, component)
    free = shutil.disk_usage(str(source)).free
    if free < total + 4 * 1024**3:
        if cb:
            cb(f"Skipping int8 cache for {component}: not enough free disk space", 0.14)
        return False

    tmp = target.with_name(target.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    if cb:
        cb(f"Saving 8-bit copy of {component} ({total / 1024**3:.1f} GB) so the next start loads faster…", 0.14)
    _write_safetensors(tmp / "model.safetensors", tensors)
    buffers = {name: str(b.dtype) for name, b in module.named_buffers()}
    (tmp / "quant.json").write_text(
        json.dumps({"quantization_map": qmap, "aliases": aliases, "buffer_dtypes": buffers}), encoding="utf-8"
    )
    meta = _expected_meta(source, component, library, class_name, dtype_name)
    meta["saved_at"] = time.time()
    meta["bytes"] = total
    # meta.json last: its presence marks a complete cache.
    (tmp / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    return True


def save_pipeline(source: str, pipe: Any, components: list[str], dtype_name: str, cb: ProgressCb | None = None) -> list[str]:
    if not enabled():
        return []
    root = Path(source)
    saved = []
    for name in components:
        module = getattr(pipe, name, None)
        if module is None:
            continue
        try:
            if save_component(root, name, module, dtype_name, cb):
                saved.append(name)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(_cache_dir(root, dtype_name, name).with_name(name + ".tmp"), ignore_errors=True)
            if cb:
                cb(f"Could not save 8-bit copy of {name} ({exc}); next start loads normally", 0.14)
    return saved


# --------------------------------------------------------------------------- load


def _empty_module(source: Path, component: str, library: str, class_name: str):
    from accelerate import init_empty_weights

    folder = source / component
    if library == "diffusers":
        import diffusers

        cls = getattr(diffusers, class_name)
        config = cls.load_config(str(folder))
        with init_empty_weights():
            return cls.from_config(config)
    if library == "transformers":
        import transformers

        cls = getattr(transformers, class_name)
        config = transformers.AutoConfig.from_pretrained(str(folder), local_files_only=True)
        with init_empty_weights():
            return cls._from_config(config)
    raise RuntimeError(f"int8 cache: unsupported library {library}")


def load_component(source: Path, component: str, dtype_name: str):
    """Rebuild one int8 component from the cache, or return None."""
    import torch
    from optimum.quanto.quantize import _quantize_submodule

    from .safetensors_nommap import NoMmapSafetensors

    library, class_name = _index(source)[component]
    target = _cache_dir(source, dtype_name, component)
    if not _matches(target / "meta.json", _expected_meta(source, component, library, class_name, dtype_name)):
        return None
    info = json.loads((target / "quant.json").read_text(encoding="utf-8"))

    module = _empty_module(source, component, library, class_name)
    for name, sub in list(module.named_modules()):
        q = info["quantization_map"].get(name)
        if q is None:
            continue
        weights = None if q["weights"] == "none" else q["weights"]
        activations = None if q["activations"] == "none" else q["activations"]
        _quantize_submodule(module, name, sub, weights=weights, activations=activations)

    state: dict[str, Any] = {}
    with NoMmapSafetensors(str(target / "model.safetensors")) as reader:
        for key in reader.keys():
            state[key] = reader.get_tensor(key)
    for alias, original in (info.get("aliases") or {}).items():
        state[alias] = state[original]

    module.load_state_dict(state, strict=False, assign=True)
    del state

    # Anything still on meta was missing from the cache: refuse to use it.
    for name, p in list(module.named_parameters()) + list(module.named_buffers()):
        if p.device.type == "meta":
            raise RuntimeError(f"int8 cache for {component} is missing {name}")
    # Non-persistent buffers (rotary tables etc.) were built by __init__ in the
    # default dtype; give them the dtype they had in the original load.
    want = info.get("buffer_dtypes") or {}
    for mod_name, mod in module.named_modules():
        for buf_name, buf in list(mod.named_buffers(recurse=False)):
            full = f"{mod_name}.{buf_name}" if mod_name else buf_name
            dt = want.get(full)
            if dt and str(buf.dtype) != dt and buf.is_floating_point():
                mod._buffers[buf_name] = buf.to(getattr(torch, dt.split(".")[-1]))
    if hasattr(module, "tie_weights"):
        try:
            module.tie_weights()
        except Exception:
            pass
    module.eval()
    return module


def load_pipeline_components(source: str, components: list[str], dtype_name: str, cb: ProgressCb | None = None) -> dict[str, Any] | None:
    """All requested components from the cache, or None (load normally)."""
    if not enabled():
        return None
    root = Path(source)
    out: dict[str, Any] = {}
    for name in components:
        started = time.time()
        if cb:
            cb(f"Loading saved 8-bit {name} (fast path)…", 0.08)
        try:
            module = load_component(root, name, dtype_name)
        except Exception as exc:  # noqa: BLE001
            if cb:
                cb(f"Saved 8-bit {name} unusable ({exc}); loading normally", 0.08)
            return None
        if module is None:
            return None
        out[name] = module
        if cb:
            cb(f"Loaded saved 8-bit {name} in {time.time() - started:.0f}s", 0.1)
    return out
