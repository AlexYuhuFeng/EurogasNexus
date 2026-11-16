"""Serve the built web client from the API process (opt-in, single-origin hosting).

The customer runtime serves the API alone: its web client is delivered separately and
its gateway (Caddy) only proxies to the API. A hosted test/demo server on a container
platform has one container and one port, so ``EUROGAS_NEXUS_WEB_CLIENT_DIR`` lets the API
process also serve a built client (``clients/web/dist``) from the same origin. Unset, as
in every customer deployment, nothing here is installed and the application is unchanged.

Rules, chosen so the client can never stand in for an API answer:

* ``/api`` and everything under it always reaches the API: this middleware never answers
  for it, so an unknown API path keeps its JSON 404, a wrong method its 405, and an
  unauthenticated call its 401;
* only GET and HEAD are answered; other methods on a client path get 405;
* a path naming a file inside the build directory serves that file (no traversal outside
  it, no directory listing). Hashed files under ``/assets/`` are cached for a year, every
  other file is revalidated;
* a path whose last segment looks like a file name but does not exist is a 404, so a
  missing script never comes back as HTML;
* any other path is a client route and serves ``index.html`` (SPA fallback).

:class:`SecurityHeadersMiddleware` adds the browser hardening headers a page served this
way needs (no gateway in front adds them): CSP, frame denial, no MIME sniffing, a strict
referrer policy, a restrictive permissions policy, and HSTS when the request arrived over
HTTPS.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from starlette.responses import FileResponse, JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

WEB_CLIENT_DIR_ENV = "EUROGAS_NEXUS_WEB_CLIENT_DIR"

#: Paths FastAPI itself serves outside ``/api`` (only when a profile exposes docs).
_FRAMEWORK_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})

#: Map tiles and the basemap style come from the configured HTTPS tile service; MapLibre
#: runs its workers from blob URLs; React and MapLibre set inline style attributes.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https:",
        "font-src 'self' data: https:",
        "connect-src 'self' https:",
        "worker-src 'self' blob:",
        "child-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)

SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", CONTENT_SECURITY_POLICY.encode("ascii")),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
)
HSTS_HEADER = (b"strict-transport-security", b"max-age=31536000")


def resolve_web_client_dir(environ: dict[str, str] | None = None) -> Path | None:
    """Return the configured build directory, or ``None`` when serving is off.

    Raises:
        RuntimeError: when the variable is set but names no directory with an
            ``index.html``: a deployment that asked for the client must not start
            without it and answer every page with a 404.
    """

    source = os.environ if environ is None else environ
    raw = (source.get(WEB_CLIENT_DIR_ENV) or "").strip()
    if not raw:
        return None
    directory = Path(raw).resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError(
            f"{WEB_CLIENT_DIR_ENV}={raw!r} has no index.html; build the web client "
            "(npm run build in clients/web) or unset the variable"
        )
    return directory


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class WebClientMiddleware:
    """Answer browser GETs for the built client; pass ``/api`` through untouched."""

    def __init__(self, app: ASGIApp, *, directory: Path) -> None:
        self.app = app
        self.directory = directory.resolve()
        self.index = self.directory / "index.html"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", "")) if scope["type"] == "http" else ""
        if scope["type"] != "http" or _is_api_path(path) or path in _FRAMEWORK_PATHS:
            await self.app(scope, receive, send)
            return
        response = self.response_for(str(scope.get("method", "GET")).upper(), path)
        await response(scope, receive, send)

    def response_for(self, method: str, path: str) -> Response:
        """Return the response for one client path (exposed for unit tests)."""

        if method not in {"GET", "HEAD"}:
            return JSONResponse(
                {"detail": {"error": "method_not_allowed", "message": "Method not allowed."}},
                status_code=405,
                headers={"Allow": "GET, HEAD"},
            )
        relative = path.lstrip("/")
        try:
            candidate = (self.directory / relative).resolve() if relative else self.index
        except (OSError, ValueError):
            return JSONResponse(
                {"detail": {"error": "not_found", "message": "Not found."}}, status_code=404
            )
        inside = candidate == self.directory or self.directory in candidate.parents
        if inside and candidate.is_file():
            cache = (
                "public, max-age=31536000, immutable"
                if relative.startswith("assets/")
                else "no-cache"
            )
            return FileResponse(candidate, headers={"Cache-Control": cache})
        last_segment = relative.rsplit("/", 1)[-1]
        if not inside or "." in last_segment:
            return JSONResponse(
                {"detail": {"error": "not_found", "message": "Not found."}}, status_code=404
            )
        return FileResponse(self.index, headers={"Cache-Control": "no-cache"})


class SecurityHeadersMiddleware:
    """Add browser hardening headers to every HTTP response that lacks them."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        https = scope.get("scheme") == "https" or any(
            key == b"x-forwarded-proto" and value.strip().lower() == b"https"
            for key, value in scope.get("headers", [])
        )

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {key.lower() for key, _ in headers}
                extra = [*SECURITY_HEADERS, *((HSTS_HEADER,) if https else ())]
                headers.extend(item for item in extra if item[0] not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
