"""Run the StudioNels gateway and refuse console CTRL+C from Pinokio/Node on Windows."""
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

port = int(os.environ.get("STUDIONELS_API_PORT") or os.environ.get("PORT") or "8788")
host = os.environ.get("STUDIONELS_API_HOST") or "127.0.0.1"


def _ignore_windows_ctrl() -> None:
    """Pinokio/Node console CTRL events were shutting uvicorn down right after ready."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        def _handler(ctrl_type: int) -> bool:
            # 0 CTRL_C, 1 CTRL_BREAK, 2 CLOSE, 5 LOGOFF, 6 SHUTDOWN
            print(f"boot-api: ignoring Windows console ctrl={ctrl_type}", flush=True)
            return True

        # Keep a reference so it is not GC'd
        global _CTRL_HANDLER  # noqa: PLW0601
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
        access_log=True,
        use_colors=False,
    )
    server = uvicorn.Server(config)
    # Do not install SIGINT/SIGTERM handlers — Pinokio job control was triggering them.
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    await server.serve()
    print("boot-api: uvicorn.serve returned (server stopped)", flush=True)


def main() -> None:
    _ignore_windows_ctrl()
    try:
        print("boot-api: importing uvicorn …", flush=True)
        asyncio.run(_serve())
    except SystemExit as exc:
        print(f"boot-api: SystemExit {exc}", flush=True)
        traceback.print_exc()
        time.sleep(15)
        raise
    except Exception:
        print("boot-api: FATAL", flush=True)
        traceback.print_exc()
        time.sleep(20)
        raise


if __name__ == "__main__":
    main()
