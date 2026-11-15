"""Light ASGI entry: bind quickly, load app.main in a background thread."""

from __future__ import annotations

import json
import threading
import traceback
from typing import Any, Callable

_real_app: Any = None
_load_error: str | None = None
_status = "booting"
_lock = threading.Lock()
_load_started = False


def _set_status(value: str) -> None:
    global _status
    _status = value
    print(f"gateway: {_status}", flush=True)


def _run_startup_handlers(real: Any) -> None:
    handlers: list[Callable[..., Any]] = []
    try:
        handlers.extend(list(getattr(real.router, "on_startup", []) or []))
    except Exception:
        pass
    for handler in handlers:
        try:
            handler()
        except Exception as exc:
            print(f"gateway: startup handler error: {exc}", flush=True)


def _load_main() -> None:
    global _real_app, _load_error
    try:
        _set_status("loading_main")
        print("gateway: importing app.main …", flush=True)
        from app.main import app as real

        _set_status("running_startup")
        _run_startup_handlers(real)
        with _lock:
            _real_app = real
            _load_error = None
        _set_status("ready")
        print("gateway: app.main ready — full API online", flush=True)
    except Exception:
        err = traceback.format_exc()
        with _lock:
            _load_error = err
        _set_status("error")
        print("gateway: app.main FAILED\n", err, flush=True)


def _ensure_load() -> None:
    global _load_started
    with _lock:
        if _load_started:
            return
        _load_started = True
    threading.Thread(target=_load_main, name="studionels-load-main", daemon=True).start()


async def _send_json(send: Any, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class Gateway:
    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    try:
                        print("gateway: lifespan startup", flush=True)
                        _ensure_load()
                        await send({"type": "lifespan.startup.complete"})
                        print("gateway: lifespan startup complete", flush=True)
                    except Exception:
                        err = traceback.format_exc()
                        print("gateway: lifespan startup FAILED\n", err, flush=True)
                        await send({"type": "lifespan.startup.failed", "message": err})
                        return
                elif message["type"] == "lifespan.shutdown":
                    print("gateway: lifespan shutdown", flush=True)
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return

        if scope["type"] != "http":
            return

        path = scope.get("path") or ""
        if path in ("/api/ready", "/api/ready/"):
            with _lock:
                ready = _real_app is not None
                err = _load_error
                st = _status
            await _send_json(
                send,
                200,
                {
                    "ok": True,
                    "ready": ready,
                    "booting": not ready and not err,
                    "status": st,
                    "error": (err[:500] if err else None),
                },
            )
            return

        with _lock:
            real = _real_app
            err = _load_error

        if err:
            await _send_json(
                send,
                503,
                {
                    "ok": False,
                    "booting": False,
                    "status": "error",
                    "detail": "API failed to load — see run-api terminal / cache/api.log",
                    "error": err[:2000],
                },
            )
            return

        if real is None:
            await _send_json(
                send,
                503,
                {
                    "ok": False,
                    "booting": True,
                    "status": _status,
                    "detail": "StudioNels API is still loading — try again in a few seconds.",
                },
            )
            return

        await real(scope, receive, send)


app = Gateway()
