"""Small shims for the Windows ROCm PyTorch build, which ships without
torch.distributed. Some audio libraries import it at module level even though
a single-GPU run never calls it (vector_quantize_pytorch, used by ACE-Step)."""
from __future__ import annotations

import sys
import types


def patch_fsq_meta_init() -> None:
    """Transformers 5 builds models on the 'meta' device. vector_quantize_pytorch's
    FSQ reads tensor values (.item()) while it is constructed, which meta tensors
    cannot do. Build those small quantizers on the CPU instead; their buffers are
    computed, not loaded, so nothing is lost."""
    import functools

    import torch
    import vector_quantize_pytorch as vq

    for cls_name in ("FSQ", "ResidualFSQ"):
        cls = getattr(vq, cls_name, None)
        if cls is None or getattr(cls.__init__, "_studionels_cpu", False):
            continue
        original = cls.__init__

        @functools.wraps(original)
        def init(self, *args, __original=original, **kwargs):
            with torch.device("cpu"):
                __original(self, *args, **kwargs)

        init._studionels_cpu = True
        cls.__init__ = init
    # The FSQ inside ResidualFSQ is imported by name in its own module
    try:
        from vector_quantize_pytorch import residual_fsq

        residual_fsq.FSQ = vq.FSQ
    except Exception:
        pass


def patch_missing_distributed() -> None:
    import torch.distributed as dist

    if dist.is_available():
        return
    if "torch.distributed.nn" not in sys.modules:
        stub = types.ModuleType("torch.distributed.nn")

        def _all_reduce(tensor, *args, **kwargs):  # single process: nothing to reduce
            return tensor

        stub.all_reduce = _all_reduce
        sys.modules["torch.distributed.nn"] = stub
        dist.nn = stub
    for name, value in (("is_initialized", lambda: False), ("get_world_size", lambda *a, **k: 1), ("get_rank", lambda *a, **k: 0)):
        if not hasattr(dist, name):
            setattr(dist, name, value)
