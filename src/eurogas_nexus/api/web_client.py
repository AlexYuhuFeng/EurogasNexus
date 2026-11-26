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

import mimetypes
import os
from pathlib import Path
from typing import Any

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

WEB_CLIENT_DIR_ENV = "EUROGAS_NEXUS_WEB_CLIENT_DIR"

# The client ships its interface font (clients/web/src/styles/fonts.css). A slim image has no
# /etc/mime.types and Python's own table may lack the font types, which would serve the face as
# application/octet-stream; name them here so the file arrives as what it is.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")

#: Built files served compressed when the browser accepts it (text: the bundle, the network and
#: basemap geometry, glyph ranges).
_COMPRESSED_SUFFIXES = (".js", ".css", ".html", ".json", ".geojson", ".svg", ".pbf", "/")

#: Paths FastAPI itself serves outside ``/api`` (only when a profile exposes docs).
_FRAMEWORK_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})

#: Map tiles and the basemap style come from the configured HTTPS tile service; MapLibre
#: runs its workers from blob URLs; React and MapLibre set inline style attributes.
#: Security review M5: ``connect-src``/``img-src`` named any HTTPS host, so injected script
#: could send data anywhere. They now name the tile service the client uses, plus the hosts
#: in ``EUROGAS_NEXUS_CSP_EXTRA_HOSTS`` (a firm's own tile server or API origin).
TILE_HOSTS = "https://tiles.openfreemap.org"
CSP_EXTRA_HOSTS_ENV = "EUROGAS_NEXUS_CSP_EXTRA_HOSTS"


def _extra_hosts() -> str:
    hosts = [
        item.strip()
        for item in (os.environ.get(CSP_EXTRA_HOSTS_ENV) or "").split(",")
        if item.strip().startswith("https://") and ";" not in item and " " not in item.strip()
    ]
    return " ".join([TILE_HOSTS, *hosts])


CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        f"img-src 'self' data: blob: {_extra_hosts()}",
        f"font-src 'self' data: {_extra_hosts()}",
        f"connect-src 'self' {_extra_hosts()}",
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
HSTS_HEADER = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")

#: The API's own answers (JSON, files): nothing in them is a page, so nothing may load.
API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
API_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", API_CONTENT_SECURITY_POLICY.encode("ascii")),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-site"),
)


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
        response = self.response_for(
            str(scope.get("method", "GET")).upper(),
            path,
            if_none_match=Headers(scope=scope).get("if-none-match"),
        )
        if path.endswith(_COMPRESSED_SUFFIXES):
            # Text files (the bundle, the network and basemap geometry) travel compressed.
            await GZipMiddleware(response, minimum_size=1024, compresslevel=6)(scope, receive, send)
            return
        await response(scope, receive, send)

    def response_for(self, method: str, path: str, if_none_match: str | None = None) -> Response:
        """Return the response for one client path (exposed for unit tests).

        A file revalidated with the ETag it was last sent (``If-None-Match``) is answered
        ``304 Not Modified`` with no body: geometry and glyphs are read once and then only
        checked.
        """

        if method not in {"GET", "HEAD"}:
            return _refusal(
                405, "method_not_allowed", "Method not allowed.", {"Allow": "GET, HEAD"}
            )
        relative = path.lstrip("/")
        try:
            candidate = (self.directory / relative).resolve() if relative else self.index
        except (OSError, ValueError):
            return _refusal(404, "not_found", "Not found.")
        inside = candidate == self.directory or self.directory in candidate.parents
        if inside and candidate.is_file():
            cache = (
                "public, max-age=31536000, immutable"
                if relative.startswith("assets/")
                # Reference geometry (the bundled basemap, glyphs, context pipelines): read
                # once in a session, then revalidated by its ETag.
                else "public, max-age=3600"
                if relative.startswith(("basemaps/", "map/"))
                else "no-cache"
            )
            served = FileResponse(
                candidate, headers={"Cache-Control": cache}, stat_result=candidate.stat()
            )
            etag = served.headers.get("etag")
            if (
                etag
                and if_none_match
                and etag in {item.strip() for item in if_none_match.split(",")}
            ):
                return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache})
            return served
        last_segment = relative.rsplit("/", 1)[-1]
        if not inside or "." in last_segment:
            return _refusal(404, "not_found", "Not found.")
        return FileResponse(self.index, headers={"Cache-Control": "no-cache"})


def _refusal(status: int, code: str, message: str, headers: dict | None = None) -> Response:
    """The API's one error body (``error_handlers.error_body``) for a static-path refusal."""

    from uuid import uuid4

    from eurogas_nexus.api.error_handlers import error_body

    correlation_id = uuid4().hex
    body = error_body(
        status, {"error": code, "message": message}, correlation_id=correlation_id
    )
    return JSONResponse(
        body, status_code=status, headers={**(headers or {}), "X-Request-Id": correlation_id}
    )


class SecurityHeadersMiddleware:
    """Add browser hardening headers to every HTTP response that lacks them.

    Installed in every deployment (security review M5), not only where the API serves the web
    client: ``/api`` answers get the API set (no content may load, no framing, no sniffing,
    no referrer), pages the client set, and HTTPS answers HSTS.
    """

    def __init__(self, app: ASGIApp, *, serves_pages: bool = True) -> None:
        self.app = app
        self.serves_pages = serves_pages

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
                page = self.serves_pages and not str(scope.get("path", "")).startswith("/api/")
                base = SECURITY_HEADERS if page else API_SECURITY_HEADERS
                extra = [*base, *((HSTS_HEADER,) if https else ())]
                headers.extend(item for item in extra if item[0] not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
