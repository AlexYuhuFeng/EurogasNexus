"""SDK HTTP helpers that attach release-profile auth headers.

Release deployments require the public API token (``EUROGAS_NEXUS_API_TOKEN``)
on every request and an explicit operator principal
(``EUROGAS_NEXUS_PRINCIPAL``) for OPERATOR routes. Both are read from the
environment so SDK/CLI operators can configure them without code changes;
when unset (development/trial against the local API), no auth headers are
sent and behavior is unchanged.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

API_TOKEN_ENV = "EUROGAS_NEXUS_API_TOKEN"
PRINCIPAL_ENV = "EUROGAS_NEXUS_PRINCIPAL"
IDENTITY_ENV = "EUROGAS_NEXUS_IDENTITY_BEARER"
PRINCIPAL_HEADER = "X-Eurogas-Principal"
IDENTITY_HEADER = "X-Eurogas-Identity"

_UNSET = object()


def auth_headers() -> dict[str, str]:
    """Return release-profile auth headers from the environment."""

    headers: dict[str, str] = {}
    token = os.environ.get(API_TOKEN_ENV, "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    principal = os.environ.get(PRINCIPAL_ENV, "").strip()
    if principal:
        headers[PRINCIPAL_HEADER] = principal
    identity = os.environ.get(IDENTITY_ENV, "").strip()
    if identity:
        headers[IDENTITY_HEADER] = identity
    return headers


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
