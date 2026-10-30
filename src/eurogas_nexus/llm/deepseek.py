"""Governed chat-completions adapter (OpenAI-compatible; DeepSeek by default).

The function names keep their historical ``deepseek`` prefix for the callers; the endpoint
comes from :func:`eurogas_nexus.llm.provider.configured_endpoint`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from eurogas_nexus.core.config import get_settings
from eurogas_nexus.llm.provider import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    LlmEndpointError,
    configured_endpoint,
)

DEEPSEEK_API_BASE_URL = DEFAULT_BASE_URL
DEEPSEEK_DEFAULT_MODEL = DEFAULT_MODEL


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
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1600,
    timeout_seconds: float = 45.0,
) -> DeepSeekCallResult:
    """Call the configured chat-completions endpoint with bounded output.

    ``model`` defaults to the configured model; a caller-supplied model that differs from
    the configured one is replaced by it, so the installation decides which model runs.
    """

    if not get_settings().llm_external_provider_enabled:
        return DeepSeekCallResult(
            status="provider_disabled", error_code="LLM_PROVIDER_DISABLED_IN_PROFILE"
        )
    if not api_key.strip():
        return DeepSeekCallResult(status="credential_missing", error_code="credential_missing")
    try:
        endpoint = configured_endpoint()
    except LlmEndpointError:
        return DeepSeekCallResult(
            status="provider_misconfigured", error_code="llm_endpoint_invalid"
        )
    model = endpoint.model
    try:
        response = httpx.post(
            f"{endpoint.base_url}/chat/completions",
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

    if not get_settings().llm_external_provider_enabled:
        return DeepSeekCallResult(
            status="provider_disabled", error_code="LLM_PROVIDER_DISABLED_IN_PROFILE"
        )
    if not api_key.strip():
        return DeepSeekCallResult(status="credential_missing", error_code="credential_missing")
    try:
        endpoint = configured_endpoint()
    except LlmEndpointError:
        return DeepSeekCallResult(
            status="provider_misconfigured", error_code="llm_endpoint_invalid"
        )
    try:
        response = httpx.get(
            f"{endpoint.base_url}/models",
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
