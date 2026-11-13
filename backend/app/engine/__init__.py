"""Built-in local generation engine (Wan2GP-style — no ComfyUI)."""

from .catalog import GENERATION_MODES, list_models_for_mode
from .device import detect_device
from .runner import EngineStatus, enqueue_job, get_job, list_jobs, engine_status

__all__ = [
    "GENERATION_MODES",
    "list_models_for_mode",
    "detect_device",
    "EngineStatus",
    "enqueue_job",
    "get_job",
    "list_jobs",
    "engine_status",
]
