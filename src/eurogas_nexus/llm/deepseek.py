"""Governed chat-completions adapter (OpenAI-compatible; DeepSeek by default).

The function names keep their historical ``deepseek`` prefix for the callers; the endpoint
comes from :func:`eurogas_nexus.llm.provider.configured_endpoint`.

This is the one place a request leaves for a model, so three rules hold here whatever the
caller checked before:

* **AI off means no request.** The installation switch
  (``EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED``) and the administrator's organisation
  switch (``ai_enabled``, ``application/ai_controls.ai_enabled``) are both read before any
  connection is opened; either off returns ``provider_disabled`` / ``ai_off``.
* **A hard time limit.** The call runs on a small worker pool and the caller waits at most
  ``timeout_seconds`` in total (connect, send, model time and reply together); after it the
  caller gets ``status="timeout"`` and carries on without the model. The abandoned request is
  bounded by the same limit per network phase and ends on its own.
* **A key only where one is needed**: a model on the firm's own network may run without one
  (``provider.key_required``).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

import httpx

from eurogas_nexus.core.config import get_settings
from eurogas_nexus.llm.provider import (
    DEEPSEEK_BASE_URL,
    DEFAULT_MODEL,
    LlmEndpointError,
    call_timeout_seconds,
    configured_endpoint,
    key_required,
)

#: Calls in flight at once; a call that waits for a worker still ends at its own deadline.
MAX_CONCURRENT_CALLS = 8
_POOL = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS, thread_name_prefix="ai-call")

DEEPSEEK_API_BASE_URL = DEEPSEEK_BASE_URL
DEEPSEEK_DEFAULT_MODEL = DEFAULT_MODEL


@dataclass(frozen=True)
class DeepSeekCallResult:
    """Provider result that never contains the submitted credential."""

    status: str
    content: str | None = None
    error_code: str | None = None


def _blocked(api_key: str | None) -> DeepSeekCallResult | None:
    """Why no request may leave now, or ``None`` (checked before every connection)."""

    if not get_settings().llm_external_provider_enabled:
        return DeepSeekCallResult(
            status="provider_disabled", error_code="LLM_PROVIDER_DISABLED_IN_PROFILE"
        )
    from eurogas_nexus.application.ai_controls import ai_enabled

    if not ai_enabled():
        return DeepSeekCallResult(status="ai_off", error_code="AI_SWITCHED_OFF")
    if not (api_key or "").strip() and key_required():
        return DeepSeekCallResult(status="credential_missing", error_code="credential_missing")
    return None


def _headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if (api_key or "").strip():
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def invoke_deepseek(
    *,
    api_key: str | None,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1600,
    timeout_seconds: float | None = None,
) -> DeepSeekCallResult:
    """Call the configured chat-completions endpoint with bounded output and a hard deadline.

    ``model`` defaults to the configured model; a caller-supplied model that differs from
    the configured one is replaced by it, so the installation decides which model runs.
    ``timeout_seconds`` is the whole call's limit; by default the interactive one
    (``provider.call_timeout_seconds``). A ``None`` or empty key is allowed only for a model on
    the firm's own network.
    """

    blocked = _blocked(api_key)
    if blocked is not None:
        return blocked
    try:
        endpoint = configured_endpoint()
    except LlmEndpointError:
        return DeepSeekCallResult(
            status="provider_misconfigured", error_code="llm_endpoint_invalid"
        )
    deadline = timeout_seconds if timeout_seconds is not None else call_timeout_seconds()
    body = {
        "model": endpoint.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    def post() -> httpx.Response:
        return httpx.post(
            f"{endpoint.base_url}/chat/completions",
            headers=_headers(api_key),
            json=body,
            timeout=deadline,
        )

    future = _POOL.submit(post)
    try:
        response = future.result(timeout=deadline)
    except FutureTimeout:
        # The caller carries on now; the request ends by its own per-phase timeout.
        future.cancel()
        return DeepSeekCallResult(status="timeout", error_code="ai_deadline_exceeded")
    except httpx.TimeoutException:
        return DeepSeekCallResult(status="timeout", error_code="ai_deadline_exceeded")
    except httpx.HTTPError as exc:
        return DeepSeekCallResult(
            status="provider_call_failed",
            error_code=exc.__class__.__name__,
        )
    try:
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
    api_key: str | None,
    timeout_seconds: float = 15.0,
) -> DeepSeekCallResult:
    """Validate a live credential (or a keyless self-hosted endpoint) without a completion."""

    blocked = _blocked(api_key)
    if blocked is not None:
        return blocked
    try:
        endpoint = configured_endpoint()
    except LlmEndpointError:
        return DeepSeekCallResult(
            status="provider_misconfigured", error_code="llm_endpoint_invalid"
        )
    try:
        response = httpx.get(
            f"{endpoint.base_url}/models",
            headers=_headers(api_key),
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
