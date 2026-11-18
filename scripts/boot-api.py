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


def _stop_orphan_gpu() -> None:
    """Kill a warm-engine python left behind by a previous Start. That process
    holds the GPU at full load even after Pinokio Stop."""
    pid_file = Path(__file__).resolve().parent.parent / "outputs" / "_engine_daemon" / "daemon.pid"
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        return
    if pid <= 0:
        return
    print(f"boot-api: stopping leftover GPU worker pid={pid}", flush=True)
    try:
        if sys.platform == "win32":
            import subprocess

            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
        else:
            import os

            os.kill(pid, 9)
    except Exception as exc:
        print(f"boot-api: leftover worker kill failed: {exc}", flush=True)
    try:
        pid_file.unlink()
    except Exception:
        pass


def main() -> None:
    _ignore_windows_ctrl()
    _stop_orphan_gpu()
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
