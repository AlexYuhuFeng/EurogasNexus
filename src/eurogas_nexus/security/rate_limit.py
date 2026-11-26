"""Small abuse protection for sensitive auth/admin endpoints.

A fixed-window throttle for sign-in and identity-administration paths, counted in the shared
cache (``core/shared_cache.py``): with several API processes and a shared backend configured,
the limit holds across all of them; without one, each process counts for itself. When the
shared backend cannot be reached, this process's own count applies (a limit never disappears,
and sign-in is not refused because the cache is down). Keys are a digest of the client
address and the limit's name; no user identifier is used.
"""

from __future__ import annotations

import hashlib
import threading
import time

from fastapi import HTTPException, Request

_WINDOW_SECONDS = 60.0
_WINDOWS: dict[str, tuple[float, int]] = {}
_LOCK = threading.Lock()


def rate_limit(key: str, *, limit: int, window_seconds: float = _WINDOW_SECONDS) -> bool:
    """Count one request against ``key``; False once ``limit`` is reached in the window."""

    from eurogas_nexus.core.shared_cache import SharedCacheUnavailable, shared_cache

    cache = shared_cache()
    if cache.shared:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        try:
            return cache.incr(f"rl:{digest}", ttl_seconds=window_seconds) <= limit
        except SharedCacheUnavailable:
            pass  # this process's own count below
    return _local_rate_limit(key, limit=limit, window_seconds=window_seconds)


def _local_rate_limit(key: str, *, limit: int, window_seconds: float) -> bool:
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
