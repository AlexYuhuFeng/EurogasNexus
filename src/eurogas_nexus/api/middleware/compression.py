"""Compress large read responses (GET /api/...), never anything carrying a secret.

A desk page loads some 28 reads at once; several are 0.6-1.4 MB of JSON (market context,
TSO access, normalized markets), which on a small demo host or a slow link pushed reads past
the client's 10 s timeout. JSON compresses roughly tenfold. Responses that can carry a
session secret (``/api/me``: the CSRF token; ``/api/auth/*``, ``/api/dev/*``: sign-in) and
event streams are never compressed (no BREACH-style oracle, no buffered stream).
"""

from __future__ import annotations

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

#: Paths never compressed: they carry session secrets, or are streams.
_EXCLUDED_PREFIXES = ("/api/me", "/api/auth", "/api/dev", "/api/stream", "/api/credentials")


class ApiReadCompressionMiddleware:
    """gzip for GET reads under ``/api/`` above ``minimum_size`` bytes (client must accept it)."""

    def __init__(self, app: ASGIApp, minimum_size: int = 2048) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size, compresslevel=5)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if (
            scope["type"] == "http"
            and scope.get("method") == "GET"
            and path.startswith("/api/")
            and not path.startswith(_EXCLUDED_PREFIXES)
        ):
            await self.gzip(scope, receive, send)
            return
        await self.app(scope, receive, send)
