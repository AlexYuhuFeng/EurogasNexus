"""Minimal governed DeepSeek API adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

DEEPSEEK_API_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"


@dataclass(frozen=True)
class DeepSeekCallResult:
    """Provider result that never contains the submitted credential."""

    status: str
    content: str | None = None
    error_code: str | None = None


def invoke_deepseek(
    *,
    api_key: str,
    messages: list[dict[str, str]],
    model: str = DEEPSEEK_DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 1600,
    timeout_seconds: float = 45.0,
) -> DeepSeekCallResult:
    """Call the live DeepSeek chat-completions API with bounded output."""

    if not api_key.strip():
        return DeepSeekCallResult(status="credential_missing", error_code="credential_missing")
    try:
        response = httpx.post(
            f"{DEEPSEEK_API_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        content = payload["choices"][0]["message"]["content"]
        return DeepSeekCallResult(status="success", content=str(content))
    except httpx.HTTPStatusError as exc:
        return DeepSeekCallResult(
            status="provider_http_error",
            error_code=f"http_{exc.response.status_code}",
        )
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        return DeepSeekCallResult(
            status="provider_call_failed",
            error_code=exc.__class__.__name__,
        )


def test_deepseek_connection(
    *,
    api_key: str,
    timeout_seconds: float = 15.0,
) -> DeepSeekCallResult:
    """Validate a live DeepSeek credential without generating a completion."""

    if not api_key.strip():
        return DeepSeekCallResult(status="credential_missing", error_code="credential_missing")
    try:
        response = httpx.get(
            f"{DEEPSEEK_API_BASE_URL}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        models = payload.get("data", [])
        return DeepSeekCallResult(
            status="success",
            content=f"models_available:{len(models) if isinstance(models, list) else 0}",
        )
    except httpx.HTTPStatusError as exc:
        return DeepSeekCallResult(
            status="provider_http_error",
            error_code=f"http_{exc.response.status_code}",
        )
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        return DeepSeekCallResult(
            status="provider_call_failed",
            error_code=exc.__class__.__name__,
        )
