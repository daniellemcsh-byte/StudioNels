"""Print immediately, then run the StudioNels gateway.

Port defaults to 8788 when fronted by run-api's Node proxy on 8787.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

print("boot-api: python alive", flush=True)
print(f"boot-api: exe={sys.executable}", flush=True)

backend = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend))

port = int(os.environ.get("STUDIONELS_API_PORT") or os.environ.get("PORT") or "8788")
host = os.environ.get("STUDIONELS_API_HOST") or "127.0.0.1"

print("boot-api: importing uvicorn …", flush=True)
import uvicorn

print("boot-api: importing app.gateway …", flush=True)
from app.gateway import app  # noqa: E402

print(f"boot-api: starting uvicorn on {host}:{port} …", flush=True)
uvicorn.run(app, host=host, port=port, log_level="info")
