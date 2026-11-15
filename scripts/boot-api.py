"""Print immediately, then run the StudioNels gateway on :8787.

Pinokio/run-api use this instead of `python -m uvicorn` so the first log line
appears before importlib spends time resolving packages on Windows.
"""
from __future__ import annotations

import sys
from pathlib import Path

print("boot-api: python alive", flush=True)
print(f"boot-api: exe={sys.executable}", flush=True)

backend = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend))

print("boot-api: importing uvicorn …", flush=True)
import uvicorn

print("boot-api: importing app.gateway …", flush=True)
from app.gateway import app  # noqa: E402

print("boot-api: starting uvicorn on 127.0.0.1:8787 …", flush=True)
uvicorn.run(app, host="127.0.0.1", port=8787, log_level="info")
