from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .models import Settings

# Local-first film planner can use free Ollama, built-in offline, or a paid API.


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
    base = settings.agent_api_base or settings.ollama_url or "http://127.0.0.1:11434"
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
        async with httpx.AsyncClient(timeout=90.0) as client:
            res = await client.post(f"{base.rstrip('/')}/api/chat", json=payload)
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
    status: dict[str, Any] = {
        "provider": provider,
        "label": meta["label"],
        "model": settings.agent_model
        or settings.ollama_model
        or meta.get("default_model")
        or "",
        "needs_key": bool(meta.get("needs_key")),
        "key_set": bool((settings.agent_api_key or "").strip()),
        "reachable": False,
        "detail": "",
    }
    if provider == "builtin":
        status["reachable"] = True
        status["detail"] = "Offline planner ready"
        return status
    if provider == "ollama":
        base = settings.agent_api_base or settings.ollama_url or "http://127.0.0.1:11434"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{base.rstrip('/')}/api/tags")
                status["reachable"] = r.status_code == 200
                status["detail"] = "Ollama connected" if status["reachable"] else "Ollama offline"
        except Exception:
            status["detail"] = "Ollama offline"
        return status
    if not status["key_set"]:
        status["detail"] = "API key missing"
        return status
    status["reachable"] = True
    status["detail"] = f"{meta['label']} key saved — will call on plan"
    return status
