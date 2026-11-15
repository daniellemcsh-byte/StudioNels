"""Print immediately, then run the StudioNels gateway on STUDIONELS_API_PORT."""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

print("boot-api: python alive", flush=True)
print(f"boot-api: exe={sys.executable}", flush=True)
print(f"boot-api: version={sys.version}", flush=True)

backend = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend))
print(f"boot-api: sys.path[0]={backend}", flush=True)

port = int(os.environ.get("STUDIONELS_API_PORT") or os.environ.get("PORT") or "8788")
host = os.environ.get("STUDIONELS_API_HOST") or "127.0.0.1"

try:
    print("boot-api: importing uvicorn …", flush=True)
    import uvicorn

    print("boot-api: importing app.gateway …", flush=True)
    from app.gateway import app  # noqa: E402

    print(f"boot-api: starting uvicorn on {host}:{port} …", flush=True)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        lifespan="on",
        access_log=True,
        # Avoid stdin-watch quirks under Node on Windows.
        use_colors=False,
    )
    print("boot-api: uvicorn.run returned (server stopped)", flush=True)
except SystemExit as exc:
    print(f"boot-api: SystemExit {exc}", flush=True)
    traceback.print_exc()
    time.sleep(15)
    raise
except Exception:
    print("boot-api: FATAL", flush=True)
    traceback.print_exc()
    # Stay alive briefly so Pinokio Terminal keeps the traceback visible.
    time.sleep(20)
    raise
