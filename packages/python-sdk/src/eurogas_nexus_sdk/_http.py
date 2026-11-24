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


class NexusAPIError(httpx.HTTPStatusError):
    """A refusal or failure from the Eurogas Nexus API, with the server's stable fields.

    Every SDK call raises this from ``response.raise_for_status()``. It is an
    ``httpx.HTTPStatusError``, so existing ``except httpx.HTTPStatusError`` handlers keep
    working; new code can read the fields instead of parsing the body:

    * ``status_code``: the HTTP status;
    * ``code``: the endpoint's own stable code (``permission_denied``, ``cargo_not_found``,
      ...) when it gave one, else the envelope's ``error``; ``None`` when the body carried
      neither (a proxy page, for example);
    * ``error`` and ``family``: the envelope's catalogue code and family (``not_found``,
      ``VALIDATION``), the same for every endpoint;
    * ``message``: what the server said, in words;
    * ``recoverability``: the server's hint (``retry``, ``fix_request``, ...) when given;
    * ``correlation_id``: quote it to an administrator to find the request in the logs;
    * ``detail``: the full ``detail`` object as sent.
    """

    def __init__(self, response: httpx.Response) -> None:
        body: Any = None
        try:
            body = response.json()
        except ValueError:
            body = None
        detail = body.get("detail") if isinstance(body, dict) else None
        self.status_code = response.status_code
        self.detail = detail
        self.code: str | None = None
        self.message = ""
        if isinstance(detail, dict):
            self.code = detail.get("code")
            self.message = str(detail.get("message") or "")
        elif isinstance(detail, list):  # request validation: one entry per field
            self.code = "validation_failed"
            self.message = "; ".join(
                f"{'.'.join(str(part) for part in item.get('loc', ()))}: {item.get('msg')}"
                for item in detail
                if isinstance(item, dict)
            )
        elif isinstance(detail, str):
            self.message = detail
        envelope = body if isinstance(body, dict) else {}
        self.error = envelope.get("error")
        self.family = envelope.get("family")
        if self.code is None and isinstance(self.error, str):
            self.code = self.error
        self.recoverability = envelope.get("recoverability")
        self.correlation_id = envelope.get("correlation_id") or response.headers.get(
            "x-request-id"
        )
        text = f"{response.status_code} {self.code or response.reason_phrase}"
        if self.message:
            text += f": {self.message}"
        if self.correlation_id:
            text += f" (correlation id {self.correlation_id})"
        super().__init__(text, request=response.request, response=response)


def _raise_typed(response: httpx.Response) -> httpx.Response:
    if response.is_success:
        return response
    raise NexusAPIError(response)


def _clean(url: str) -> str:
    """Collapse doubled slashes in the path, so ``base_url`` may end with ``/`` everywhere."""

    scheme, separator, rest = url.partition("://")
    if not separator:
        return url
    path, query_mark, query = rest.partition("?")
    while "//" in path:
        path = path.replace("//", "/")
    return f"{scheme}://{path}{query_mark}{query}"


def _typed(response: httpx.Response) -> httpx.Response:
    """Make ``response.raise_for_status()`` raise :class:`NexusAPIError`."""

    response.raise_for_status = lambda: _raise_typed(response)  # type: ignore[method-assign]
    return response


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
    return _typed(httpx.put(_clean(url), json=json, timeout=timeout, **call_kwargs))


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
    return _typed(httpx.patch(_clean(url), json=json, timeout=timeout, **call_kwargs))


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
    return _typed(httpx.get(_clean(url), timeout=timeout, **call_kwargs))


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
    return _typed(httpx.post(_clean(url), json=json, timeout=timeout, **call_kwargs))
