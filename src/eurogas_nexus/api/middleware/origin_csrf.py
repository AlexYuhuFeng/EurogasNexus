"""Origin/CSRF guard for cookie-authenticated browser requests.

API-key/bearer clients have no ambient cookie authority and are not subject to
this guard. Cookie-authenticated mutations require:

1. an Origin header;
2. origin allowed for the deployment (same-origin or explicit CORS list);
3. ``X-Eurogas-CSRF`` matching the session-bound token returned by /api/me.

GET/HEAD/OPTIONS and the OIDC callback/login paths are exempt from the CSRF
header but not from authentication and entitlement checks.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Awaitable, Callable
from typing import Any

SESSION_COOKIE = "eurogas_session"
CSRF_HEADER = "x-eurogas-csrf"
ALLOWED_ORIGINS_ENV = "EUROGAS_NEXUS_CORS_ORIGINS"

_ALWAYS_ALLOWED = {
    "http://localhost",
    "http://127.0.0.1",
    "http://tauri.localhost",
    "tauri://localhost",
}


def _allowed_origins() -> set[str]:
    configured = {
        value.strip().rstrip("/")
        for value in os.environ.get(ALLOWED_ORIGINS_ENV, "").split(",")
        if value.strip()
    }
    return configured | _ALWAYS_ALLOWED


def _csrf_for_session(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


class OriginCsrfGuardMiddleware:
    """ASGI middleware enforcing origin+CSRF for cookie sessions."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
            if isinstance(key, bytes)
        }
        cookies = headers.get(b"cookie", b"").decode("latin-1", errors="ignore")
        session_token = _cookie_value(cookies, SESSION_COOKIE)
        is_safe = method in {"GET", "HEAD", "OPTIONS"} or path.startswith("/api/auth/oidc/")
        if not session_token or is_safe:
            await self.app(scope, receive, send)
            return

        origin = headers.get(b"origin", b"").decode("latin-1", errors="ignore")
        if not origin or not _origin_allowed(origin, headers):
            await _reject(send, status=403, code="origin_not_allowed")
            return
        csrf = headers.get(CSRF_HEADER.encode(), b"").decode("latin-1", errors="ignore")
        if csrf != _csrf_for_session(session_token):
            await _reject(send, status=403, code="csrf_invalid")
            return
        await self.app(scope, receive, send)


def _origin_allowed(origin: str, headers: dict[bytes, bytes]) -> bool:
    normalized = origin.rstrip("/")
    if normalized in _allowed_origins():
        return True
    host = headers.get(b"host", b"").decode("latin-1", errors="ignore")
    forwarded_proto = headers.get(b"x-forwarded-proto", b"http").decode(
        "latin-1", errors="ignore"
    )
    scheme = "https" if forwarded_proto == "https" else "http"
    expected = f"{scheme}://{host}"
    return normalized == expected


def _cookie_value(cookies: str, name: str) -> str:
    for part in cookies.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


async def _reject(send: Any, *, status: int, code: str) -> None:
    body = (
        '{"error":"' + code + '","message":"Cookie-authenticated request blocked."}'
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
