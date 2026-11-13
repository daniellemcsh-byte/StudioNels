from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .models import Settings

# Local-first film planner can use free Ollama, built-in offline, or a paid API.

# Never honour HTTP(S)_PROXY for local Ollama — Pinokio/Windows proxies often
# break 127.0.0.1 and make a running Ollama look "offline".
_OLLAMA_TIMEOUT = httpx.Timeout(8.0, connect=3.0)


def _ollama_client(timeout: httpx.Timeout | float | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout if timeout is not None else _OLLAMA_TIMEOUT,
        trust_env=False,
    )


def _ollama_base_candidates(settings: Settings) -> list[str]:
    raw = (
        (settings.agent_api_base or "").strip()
        or (settings.ollama_url or "").strip()
        or "http://127.0.0.1:11434"
    )
    bases = [raw.rstrip("/")]
    # Common Windows / Pinokio variants
    for alt in (
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://[::1]:11434",
    ):
        if alt.rstrip("/") not in bases:
            bases.append(alt.rstrip("/"))
    return bases


async def _ollama_get_tags(settings: Settings) -> tuple[str | None, dict[str, Any] | None, str]:
    """Try candidate bases; return (base, json, error_detail)."""
    errors: list[str] = []
    async with _ollama_client() as client:
        for base in _ollama_base_candidates(settings):
            try:
                r = await client.get(f"{base}/api/tags")
                if r.status_code == 200:
                    return base, r.json(), ""
                errors.append(f"{base} → HTTP {r.status_code}")
            except Exception as exc:
                errors.append(f"{base} → {exc.__class__.__name__}")
    return None, None, "; ".join(errors) or "no response"


PROVIDERS = [
    {
        "id": "builtin",
        "label": "Built-in (offline)",
        "blurb": "No network — deterministic shot list. Always free.",
        "needs_key": False,
        "default_model": "",
        "default_base": "",
    },
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "blurb": "Free local models via Ollama on this machine.",
        "needs_key": False,
        "default_model": "llama3.2:3b",
        "default_base": "http://127.0.0.1:11434",
    },
    {
        "id": "openai",
        "label": "OpenAI (paid)",
        "blurb": "GPT models via OpenAI Chat Completions API.",
        "needs_key": True,
        "default_model": "gpt-4o-mini",
        "default_base": "https://api.openai.com/v1",
    },
    {
        "id": "anthropic",
        "label": "Anthropic (paid)",
        "blurb": "Claude models via Anthropic Messages API.",
        "needs_key": True,
        "default_model": "claude-sonnet-4-20250514",
        "default_base": "https://api.anthropic.com",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter (paid)",
        "blurb": "One key for many hosted models (OpenAI-compatible).",
        "needs_key": True,
        "default_model": "openai/gpt-4o-mini",
        "default_base": "https://openrouter.ai/api/v1",
    },
    {
        "id": "custom",
        "label": "Custom OpenAI-compatible",
        "blurb": "Any paid/self-hosted endpoint that speaks Chat Completions.",
        "needs_key": True,
        "default_model": "gpt-4o-mini",
        "default_base": "https://api.example.com/v1",
    },
]


def list_providers() -> list[dict[str, Any]]:
    return PROVIDERS


def provider_meta(provider_id: str) -> dict[str, Any]:
    return next((p for p in PROVIDERS if p["id"] == provider_id), PROVIDERS[0])


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except Exception:
            pass
    # First object
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


async def chat_json(
    settings: Settings,
    system: str,
    user: str,
    max_tokens: int = 1200,
) -> dict[str, Any] | None:
    """Call the configured agent LLM and parse a JSON object reply."""
    provider = (settings.agent_provider or "ollama").lower()
    if provider == "builtin":
        return None

    if provider == "ollama":
        return await _ollama_chat(settings, system, user, max_tokens)

    if provider == "anthropic":
        return await _anthropic_chat(settings, system, user, max_tokens)

    # openai / openrouter / custom — Chat Completions
    return await _openai_compatible_chat(settings, system, user, max_tokens)


async def _ollama_chat(
    settings: Settings, system: str, user: str, max_tokens: int
) -> dict[str, Any] | None:
    model = settings.agent_model or settings.ollama_model or "llama3.2:3b"
    base, _, _ = await _ollama_get_tags(settings)
    if not base:
        base = (settings.agent_api_base or settings.ollama_url or "http://127.0.0.1:11434").rstrip(
            "/"
        )
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"num_predict": max_tokens},
    }
    try:
        async with _ollama_client(timeout=90.0) as client:
            res = await client.post(f"{base}/api/chat", json=payload)
            if res.status_code != 200:
                return None
            content = res.json().get("message", {}).get("content", "")
            return _extract_json(content)
    except Exception:
        return None


async def _openai_compatible_chat(
    settings: Settings, system: str, user: str, max_tokens: int
) -> dict[str, Any] | None:
    meta = provider_meta(settings.agent_provider)
    key = (settings.agent_api_key or "").strip()
    if not key:
        return None
    base = (settings.agent_api_base or meta.get("default_base") or "").rstrip("/")
    model = settings.agent_model or meta.get("default_model") or "gpt-4o-mini"
    if not base:
        return None
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if settings.agent_provider == "openrouter":
        headers["HTTP-Referer"] = "https://studionels.local"
        headers["X-Title"] = "StudioNels"
    payload = {
        "model": model,
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
            if res.status_code == 400:
                # Some gateways reject response_format — retry without
                payload.pop("response_format", None)
                res = await client.post(
                    f"{base}/chat/completions", json=payload, headers=headers
                )
            if res.status_code != 200:
                return None
            content = (
                res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            return _extract_json(content)
    except Exception:
        return None


async def _anthropic_chat(
    settings: Settings, system: str, user: str, max_tokens: int
) -> dict[str, Any] | None:
    key = (settings.agent_api_key or "").strip()
    if not key:
        return None
    meta = provider_meta("anthropic")
    base = (settings.agent_api_base or meta["default_base"]).rstrip("/")
    model = settings.agent_model or meta["default_model"]
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system + "\nRespond with ONLY valid JSON.",
        "messages": [{"role": "user", "content": user}],
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(f"{base}/v1/messages", json=payload, headers=headers)
            if res.status_code != 200:
                return None
            blocks = res.json().get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return _extract_json(text)
    except Exception:
        return None


async def probe_agent(settings: Settings) -> dict[str, Any]:
    """Lightweight status for health / settings UI."""
    provider = (settings.agent_provider or "ollama").lower()
    meta = provider_meta(provider)
    model = (
        settings.agent_model
        or settings.ollama_model
        or meta.get("default_model")
        or ""
    )
    status: dict[str, Any] = {
        "provider": provider,
        "label": meta["label"],
        "model": model,
        "needs_key": bool(meta.get("needs_key")),
        "key_set": bool((settings.agent_api_key or "").strip()),
        "reachable": False,
        "detail": "",
        "models": [],
        "model_ready": False,
        "ok": False,
    }
    if provider == "builtin":
        status["reachable"] = True
        status["ok"] = True
        status["model_ready"] = True
        status["detail"] = "Built-in offline planner ready (no Ollama needed)"
        return status
    if provider == "ollama":
        base, payload, err = await _ollama_get_tags(settings)
        if not base or payload is None:
            status["detail"] = (
                "Cannot reach Ollama. Open the Ollama app from the Start menu "
                "(tray icon), then in a browser open http://127.0.0.1:11434/api/tags — "
                f"you should see JSON with your models. Tried: {err}"
            )
            return status
        status["reachable"] = True
        status["base"] = base
        names = []
        for m in (payload.get("models") or []):
            name = m.get("name") or m.get("model") or ""
            if name:
                names.append(name)
        status["models"] = names
        want = (model or "").strip()
        ready = False
        if want:
            ready = any(
                n == want or n.startswith(want + ":") or want.startswith(n.split(":")[0])
                for n in names
            )
            if not ready and ":" not in want:
                ready = any(n.split(":")[0] == want for n in names)
            if not ready:
                ready = any(want in n or n in want for n in names)
        status["model_ready"] = bool(ready) if want else bool(names)
        if not names:
            status["detail"] = (
                "Ollama is running, but no models are installed. "
                "In PowerShell: & \"$env:LOCALAPPDATA\\Programs\\Ollama\\ollama.exe\" pull llama3.2:3b"
            )
        elif want and not status["model_ready"]:
            status["detail"] = (
                f"Ollama connected at {base} · model “{want}” not found. "
                f"Installed: {', '.join(names[:8]) or '(none)'}. "
                f"Pick one of those in Settings."
            )
        else:
            status["ok"] = True
            status["detail"] = (
                f"Ollama connected at {base} · using {want or names[0]} "
                f"({len(names)} model{'s' if len(names) != 1 else ''} installed)"
            )
        return status
    if not status["key_set"]:
        status["detail"] = "API key missing — paste a key and Save"
        return status
    status["reachable"] = True
    status["ok"] = True
    status["model_ready"] = True
    status["detail"] = f"{meta['label']} key saved — will call on chat/plan"
    return status


async def test_agent_ping(settings: Settings) -> dict[str, Any]:
    """Probe + optional tiny generation to prove the agent path works."""
    status = await probe_agent(settings)
    status["ping_ok"] = False
    status["ping_detail"] = ""
    if not status.get("reachable"):
        return status
    provider = (settings.agent_provider or "ollama").lower()
    if provider == "builtin":
        status["ping_ok"] = True
        status["ping_detail"] = "Built-in planner OK"
        status["ok"] = True
        return status
    if provider == "ollama" and status.get("model_ready"):
        # Tiny JSON ping so we know chat works
        try:
            result = await chat_json(
                settings,
                'Reply with ONLY JSON: {"ok": true, "hi": "short hello"}',
                "ping",
                max_tokens=64,
            )
            if result and (result.get("ok") is True or "hi" in result):
                status["ping_ok"] = True
                status["ping_detail"] = f"Chat works — model answered: {result.get('hi') or 'ok'}"
                status["ok"] = True
                status["detail"] = status["ping_detail"]
            else:
                status["ping_detail"] = (
                    "Ollama is up and the model is installed, but chat returned nothing useful. "
                    "Try another model or restart Ollama."
                )
        except Exception as exc:
            status["ping_detail"] = f"Chat ping failed: {exc.__class__.__name__}"
    elif provider == "ollama":
        status["ping_detail"] = status.get("detail") or "Pull a model first"
    else:
        status["ping_ok"] = bool(status.get("key_set"))
        status["ping_detail"] = "Key saved — will be used on the next Agent message"
        status["ok"] = status["ping_ok"]
    return status
