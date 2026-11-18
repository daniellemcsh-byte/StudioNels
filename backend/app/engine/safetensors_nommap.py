"""Read safetensors without a Windows memory map.

WinError 1455 ("The paging file is too small for this operation to complete")
is raised when Windows tries to map a multi-gigabyte shard. LTX-2.3's text
encoder is a float32 Gemma (~49 GB on disk). Mapping those shards charges the
paging file for the whole file even when the bytes are only read once.

This reader copies each tensor out of a normal file read. On Windows, shards
of 1.5 GB and up skip the map. Everywhere else, the map is still tried first
and this reader is the fallback when error 1455 shows up.
"""

from __future__ import annotations

import json
import os
import struct
import sys
from typing import Any

# The LTX VAE is about 1.5 GB. Windows still charges that against the paging
# file when it is memory-mapped, and the old cutoff skipped it.
# Gemma stores its 12B text encoder in float32. Downcast the big matrices only.
_DOWNCAST_MIN_NUMEL = 1_000_000

_DTYPE_NAMES = {
    "BOOL": "bool",
    "U8": "uint8",
    "I8": "int8",
    "I16": "int16",
    "U16": "uint16",
    "I32": "int32",
    "U32": "uint32",
    "I64": "int64",
    "U64": "uint64",
    "F16": "float16",
    "BF16": "bfloat16",
    "F32": "float32",
    "F64": "float64",
}

_LOAD_CAST: Any = None


def set_load_cast_dtype(dtype: Any) -> None:
    """Floating weights larger than the threshold are stored in this dtype."""
    global _LOAD_CAST
    _LOAD_CAST = dtype


def reset_load_cast_dtype() -> None:
    global _LOAD_CAST
    _LOAD_CAST = None


def _is_alloc_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "not enough memory" in msg or "out of memory" in msg or "cannot allocate" in msg or "paging file" in msg


def is_pagefile_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        winerror = getattr(current, "winerror", None)
        if winerror == 1455:
            return True
        msg = str(current).lower()
        if (
            "paging file" in msg
            or "os error 1455" in msg
            or "[winerror 1455]" in msg
            or "error 1455" in msg
        ):
            return True
        nxt = current.__cause__ or current.__context__
        current = nxt if isinstance(nxt, BaseException) else None
    return False


def _error_text(exc: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current))
        nxt = current.__cause__ or current.__context__
        current = nxt if isinstance(nxt, BaseException) else None
    return " ".join(parts)


def explain_weight_load_error(source: str, exc: BaseException) -> str:
    text = _error_text(exc)
    low = text.lower()
    if is_pagefile_error(exc) or "paging file" in low or "1455" in low:
        return (
            "Windows paging file is too small to open this model "
            f"({source}). The download is already on disk. "
            "Update StudioNels and retry — checkpoints are read without a page-file mapping. "
            "If it still fails, set a custom paging file of at least 64 GB "
            "(System → Advanced system settings → Performance → Advanced → Virtual memory) and reboot."
        )
    if "not enough memory" in low or "out of memory" in low or "cannot allocate" in low:
        return (
            "This model does not fit in RAM plus the Windows paging file "
            f"({source}). LTX-2.3 keeps a 12B text encoder and a 22B transformer. "
            "Set a custom paging file of at least 64 GB and reboot, then retry. "
            "The weights do not need to be downloaded again."
        )
    if "git-lfs" in low or "git lfs" in low or low.strip().startswith("version https://git-lfs"):
        return (
            f"A weight file under {source} is still a Git LFS pointer, not the real checkpoint. "
            "In Models, download this model again."
        )
    return (
        f"Could not load local weights from {source}: {text}. "
        "The folder is already on disk. Pinokio → Update, then retry."
    )


def prefer_nommap(filename: str, *, platform: str | None = None) -> bool:
    """Windows maps even a 1.5 GB VAE into the paging file. Read the file instead."""
    plat = platform if platform is not None else sys.platform
    if plat != "win32":
        return False
    try:
        return os.path.isfile(filename)
    except OSError:
        return False


def _filename(args: tuple, kwargs: dict) -> str | None:
    raw = args[0] if args else kwargs.get("filename", kwargs.get("file", kwargs.get("path")))
    if raw is None:
        return None
    try:
        return os.fspath(raw)
    except TypeError:
        return None


def _framework(args: tuple, kwargs: dict) -> str:
    if len(args) >= 2:
        return str(args[1])
    return str(kwargs.get("framework") or "pt")


def _device(args: tuple, kwargs: dict):
    if "device" in kwargs:
        return kwargs["device"]
    if len(args) >= 3:
        return args[2]
    return "cpu"


def _framework_is_torch(framework: str) -> bool:
    return framework.lower() in {"pt", "torch", "pytorch"}


def _read_at(path: str, offset: int, nbytes: int) -> bytes:
    """Read nbytes at offset. Each call uses its own file position.

    Transformers materializes weights on a thread pool and slices them with
    ``tensor[...]``. One shared file handle cannot do that: a second seek
    lands the first read at the end of the file, which comes back as 0 bytes.
    """
    if nbytes <= 0:
        return b""
    flags = os.O_RDONLY
    binary = getattr(os, "O_BINARY", 0)
    if binary:
        flags |= binary
    fd = os.open(path, flags)
    try:
        pread = getattr(os, "pread", None)
        out = bytearray()
        if pread is not None:
            while len(out) < nbytes:
                part = pread(fd, nbytes - len(out), offset + len(out))
                if not part:
                    break
                out += part
            return bytes(out)
        os.lseek(fd, offset, os.SEEK_SET)
        while len(out) < nbytes:
            part = os.read(fd, nbytes - len(out))
            if not part:
                break
            out += part
        return bytes(out)
    finally:
        os.close(fd)


class _Slice:
    def __init__(self, owner: "NoMmapSafetensors", name: str):
        self._owner = owner
        self._name = name

    def get_shape(self) -> list[int]:
        return list(self._owner._header[self._name]["shape"])

    def __getitem__(self, index: Any) -> Any:
        return self._owner.get_tensor(self._name)[index]


class NoMmapSafetensors:
    """Context manager with the safe_open surface diffusers and transformers use."""

    def __init__(self, filename: str, framework: str = "pt", device: Any = "cpu"):
        if not _framework_is_torch(framework):
            raise RuntimeError(
                f"Page-file fallback can read PyTorch safetensors, not framework {framework!r}."
            )
        self.filename = filename
        self.framework = framework
        self.device = device
        self._file = open(filename, "rb")
        try:
            self._header, self._data_base, self._metadata = _read_header(self._file)
        except Exception:
            self._file.close()
            raise

    def __enter__(self) -> "NoMmapSafetensors":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self._file.close()
        except Exception:
            pass
        return False

    def keys(self) -> list[str]:
        return list(self._header.keys())

    def metadata(self) -> dict | None:
        return self._metadata

    def get_slice(self, name: str) -> _Slice:
        if name not in self._header:
            raise KeyError(name)
        return _Slice(self, name)

    def get_tensor(self, name: str) -> Any:
        info = self._header[name]
        start, end = info["data_offsets"]
        nbytes = int(end) - int(start)
        try:
            raw = _read_at(self.filename, self._data_base + int(start), nbytes)
            tensor = _tensor_from_bytes(raw, str(info["dtype"]), list(info["shape"]))
            del raw
            tensor = _maybe_cast(tensor)
            if not _is_cpu(self.device):
                tensor = tensor.to(self.device)
            return tensor
        except (OSError, MemoryError, RuntimeError) as exc:
            alloc = isinstance(exc, MemoryError) or _is_alloc_error(exc) or (
                isinstance(exc, OSError) and is_pagefile_error(exc)
            )
            if not alloc:
                raise
            if sys.platform == "win32" or is_pagefile_error(exc):
                raise RuntimeError(
                    "Windows ran out of RAM and paging-file space while reading "
                    f"{self.filename}. The download is already there. "
                    "Set a custom paging file of at least 64 GB "
                    "(System → Advanced system settings → Performance → Advanced → Virtual memory) "
                    "and reboot."
                ) from exc
            raise


def _read_header(handle) -> tuple[dict[str, dict], int, dict | None]:
    prefix = handle.read(8)
    if prefix.startswith(b"version"):
        raise RuntimeError(
            "This file is a Git LFS pointer, not the weight data. Download the model again in Models."
        )
    if len(prefix) != 8:
        raise RuntimeError("Safetensors file is missing its header length.")
    (header_len,) = struct.unpack("<Q", prefix)
    if header_len <= 0 or header_len > 512 * 1024 * 1024:
        raise RuntimeError(f"Safetensors header length looks wrong ({header_len}).")
    payload = handle.read(header_len)
    if len(payload) != header_len:
        raise RuntimeError("Safetensors header was cut off.")
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError("Safetensors header is not a JSON object.")
    metadata = parsed.pop("__metadata__", None)
    if metadata is not None and not isinstance(metadata, dict):
        metadata = None
    header: dict[str, dict] = {}
    for name, info in parsed.items():
        if not isinstance(info, dict) or "data_offsets" not in info:
            continue
        header[str(name)] = info
    return header, 8 + header_len, metadata


def _is_cpu(device: Any) -> bool:
    if device is None:
        return True
    text = str(device).lower().replace(" ", "")
    return text in {"cpu", "meta"} or text.startswith("cpu:")


def _torch_dtype(name: str):
    import torch

    attr = _DTYPE_NAMES.get(name)
    if attr is None or not hasattr(torch, attr):
        raise RuntimeError(f"Safetensors dtype {name} is not supported by this loader.")
    return getattr(torch, attr)


def _tensor_from_bytes(raw: bytes, dtype_name: str, shape: list[int]):
    import torch

    dtype = _torch_dtype(dtype_name)
    dims = [int(dim) for dim in shape]
    numel = 1
    for dim in dims:
        numel *= dim
    if numel == 0:
        return torch.empty(dims, dtype=dtype)
    itemsize = torch.empty((), dtype=dtype).element_size()
    expect = numel * itemsize
    if len(raw) != expect:
        raise RuntimeError(
            f"Safetensors tensor has {len(raw)} bytes, expected {expect} for dtype {dtype_name}."
        )
    storage = torch.frombuffer(bytearray(raw), dtype=torch.uint8)
    out = torch.empty(numel, dtype=dtype)
    out.view(torch.uint8).copy_(storage)
    return out.reshape(dims)


def _maybe_cast(tensor):
    target = _LOAD_CAST
    if target is None or not tensor.is_floating_point():
        return tensor
    if tensor.dtype == target or tensor.numel() < _DOWNCAST_MIN_NUMEL:
        return tensor
    import torch

    # float32 Gemma is the paging-file blow-up. bf16 shards match the fp16 pipeline.
    if tensor.dtype == torch.float32 or (
        tensor.dtype == torch.bfloat16 and target == torch.float16
    ):
        return tensor.to(dtype=target)
    return tensor


def open_safetensors(orig, args: tuple, kwargs: dict):
    """Call the native opener, and switch to the file reader on error 1455.

    On Windows, multi-gigabyte shards skip the native map entirely.
    """
    cleaned = dict(kwargs)
    filename = _filename(args, cleaned)
    framework = _framework(args, cleaned)
    device = _device(args, cleaned)

    def fallback():
        if not filename or not _framework_is_torch(framework):
            return None
        return NoMmapSafetensors(filename, framework=framework, device=device)

    if filename and _framework_is_torch(framework) and prefer_nommap(filename):
        opened = fallback()
        if opened is not None:
            return opened

    attempts = [cleaned]
    if "backend" in cleaned:
        attempts.append({key: value for key, value in cleaned.items() if key != "backend"})

    last_typeerror: TypeError | None = None
    for attempt in attempts:
        try:
            opened = orig(*args, **attempt)
        except TypeError as exc:
            if "backend" in attempt and "backend" in str(exc):
                last_typeerror = exc
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            # Diffusers hides the real safetensors error behind "Unable to load
            # weights". Any failed native open is retried without a memory map.
            try:
                alt = fallback()
            except Exception as reader_exc:
                raise reader_exc from exc
            if alt is not None:
                return alt
            raise
        if filename and hasattr(opened, "__enter__"):
            return _EnterFallback(opened, filename, framework, device)
        return opened
    if last_typeerror is not None:
        raise last_typeerror
    raise RuntimeError("safetensors open failed")


class _EnterFallback:
    """Native open() succeeded, but entering the map can still raise 1455."""

    def __init__(self, native, filename: str, framework: str, device: Any):
        self._native = native
        self._filename = filename
        self._framework = framework
        self._device = device
        self._active = None

    def __enter__(self):
        try:
            self._active = self._native.__enter__()
            return self._active
        except Exception as exc:
            if _framework_is_torch(self._framework):
                self._active = NoMmapSafetensors(
                    self._filename, framework=self._framework, device=self._device
                )
                return self._active.__enter__()
            raise exc

    def __exit__(self, exc_type, exc, tb):
        if self._active is None:
            return False
        return self._active.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str):
        return getattr(self._native, name)
