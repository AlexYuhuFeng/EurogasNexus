"""SDK HTTP helpers that attach release-profile auth headers.

Release deployments require the deployment token on every request and an
explicit operator principal (``EUROGAS_NEXUS_PRINCIPAL``) for OPERATOR routes.
Both are read from the environment so SDK/CLI operators can configure them
without code changes; when unset (development/trial against the local API), no
auth headers are sent and behavior is unchanged.

The deployment token is resolved from ``EUROGAS_NEXUS_PUBLIC_API_TOKEN`` -- the
name the server reads -- falling back to the older client-side
``EUROGAS_NEXUS_API_TOKEN``. Reading only the old name meant an operator who set
the server's variable (or read the deployment template) left the SDK sending no
credential at all.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

API_TOKEN_ENV = "EUROGAS_NEXUS_PUBLIC_API_TOKEN"
LEGACY_API_TOKEN_ENV = "EUROGAS_NEXUS_API_TOKEN"
PRINCIPAL_ENV = "EUROGAS_NEXUS_PRINCIPAL"
IDENTITY_ENV = "EUROGAS_NEXUS_IDENTITY_BEARER"
PRINCIPAL_HEADER = "X-Eurogas-Principal"
IDENTITY_HEADER = "X-Eurogas-Identity"

_UNSET = object()


def resolve_api_token(environ: dict[str, str] | None = None) -> str:
    """Return the configured deployment token, preferring the canonical name.

    ``EUROGAS_NEXUS_PUBLIC_API_TOKEN`` is the name the server reads and the one
    the shipped template documents. ``EUROGAS_NEXUS_API_TOKEN`` is accepted as a
    fallback so an existing SDK environment keeps working.
    """

    source = os.environ if environ is None else environ
    # Iterate the variable *names*, not the constant names: this tuple must hold
    # the environment keys themselves.
    for env_name in (API_TOKEN_ENV, LEGACY_API_TOKEN_ENV):
        value = (source.get(env_name) or "").strip()
        if value:
            return value
    return ""


def auth_headers() -> dict[str, str]:
    """Return release-profile auth headers from the environment."""

    headers: dict[str, str] = {}
    token = resolve_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    principal = os.environ.get(PRINCIPAL_ENV, "").strip()
    if principal:
        headers[PRINCIPAL_HEADER] = principal
    identity = os.environ.get(IDENTITY_ENV, "").strip()
    if identity:
        headers[IDENTITY_HEADER] = identity
    return headers


def put(
    url: str,
    *,
    json: Any = None,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """PUT with configured auth headers merged in."""

    merged = {**auth_headers(), **(headers or {})}
    call_kwargs = dict(kwargs)
    if merged:
        call_kwargs["headers"] = merged
    return httpx.put(url, json=json, timeout=timeout, **call_kwargs)


def patch(
    url: str,
    *,
    json: Any = None,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """PATCH with configured auth headers merged in."""

    merged = {**auth_headers(), **(headers or {})}
    call_kwargs = dict(kwargs)
    if merged:
        call_kwargs["headers"] = merged
    return httpx.patch(url, json=json, timeout=timeout, **call_kwargs)


def get(
    url: str,
    *,
    params: dict[str, Any] | None | object = _UNSET,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """GET with configured auth headers merged in.

    ``params`` uses a sentinel so callers that never passed it keep not
    passing it (preserving transport call shapes); the ``headers`` kwarg is
    only added when auth is configured.
    """

    merged = {**auth_headers(), **(headers or {})}
    call_kwargs = dict(kwargs)
    if merged:
        call_kwargs["headers"] = merged
    if params is not _UNSET:
        call_kwargs["params"] = params
    return httpx.get(url, timeout=timeout, **call_kwargs)


def post(
    url: str,
    *,
    json: Any = None,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """POST with configured auth headers merged in."""

    merged = {**auth_headers(), **(headers or {})}
    call_kwargs = dict(kwargs)
    if merged:
        call_kwargs["headers"] = merged
    return httpx.post(url, json=json, timeout=timeout, **call_kwargs)
