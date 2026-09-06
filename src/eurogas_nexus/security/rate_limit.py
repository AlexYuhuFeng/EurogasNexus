"""Small in-memory abuse protection for sensitive auth/admin endpoints.

This is a deployment-appropriate fixed-window throttle for login callback and
identity-administration paths. It is deliberately process-local: multi-process
production deployments should front these endpoints with a deployment rate
limiter as well. No user identifiers are used as keys.
"""

from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request

_WINDOW_SECONDS = 60.0
_WINDOWS: dict[str, tuple[float, int]] = {}
_LOCK = threading.Lock()


def rate_limit(key: str, *, limit: int, window_seconds: float = _WINDOW_SECONDS) -> bool:
    now = time.monotonic()
    with _LOCK:
        started, count = _WINDOWS.get(key, (now, 0))
        if now - started >= window_seconds:
            started, count = now, 0
        if count >= limit:
            return False
        _WINDOWS[key] = (started, count + 1)
        return True


async def require_auth_rate_limit(request: Request) -> None:
    key = f"auth:{request.client.host if request.client else 'unknown'}"
    if not rate_limit(key, limit=30):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many authentication attempts."},
        )


async def require_admin_rate_limit(request: Request) -> None:
    key = f"admin:{request.client.host if request.client else 'unknown'}"
    if not rate_limit(key, limit=120):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many administration requests."},
        )
