"""Run the StudioNels gateway on 127.0.0.1:8787 and stay there.

Windows/Pinokio console events were stopping uvicorn right after it became
ready. This process ignores those events and starts the server again if it
ever returns.
"""
from __future__ import annotations

import asyncio
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

port = int(os.environ.get("STUDIONELS_API_PORT") or "8787")
host = os.environ.get("STUDIONELS_API_HOST") or "127.0.0.1"


def _ignore_windows_ctrl() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        def _handler(ctrl_type: int) -> bool:
            print(f"boot-api: ignoring Windows console ctrl={ctrl_type}", flush=True)
            return True

        global _CTRL_HANDLER  # noqa: PLW0603
        _CTRL_HANDLER = HandlerRoutine(_handler)
        ok = ctypes.windll.kernel32.SetConsoleCtrlHandler(_CTRL_HANDLER, True)
        print(f"boot-api: SetConsoleCtrlHandler ok={bool(ok)}", flush=True)
    except Exception as exc:
        print(f"boot-api: ctrl handler setup failed: {exc}", flush=True)


async def _serve() -> None:
    import uvicorn

    print("boot-api: importing app.gateway …", flush=True)
    from app.gateway import app  # noqa: E402

    print(f"boot-api: starting uvicorn on {host}:{port} …", flush=True)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        lifespan="on",
        access_log=False,
        use_colors=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    await server.serve()
    print("boot-api: uvicorn.serve returned (server stopped)", flush=True)


def main() -> None:
    _ignore_windows_ctrl()
    print("boot-api: importing uvicorn …", flush=True)
    while True:
        try:
            asyncio.run(_serve())
        except SystemExit as exc:
            print(f"boot-api: SystemExit {exc}", flush=True)
            traceback.print_exc()
        except Exception:
            print("boot-api: FATAL", flush=True)
            traceback.print_exc()
        print("boot-api: restarting server in 2s …", flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
