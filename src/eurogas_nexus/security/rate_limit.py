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


# --- per-principal quotas on writes and heavy computations (security review M7) -----------

import os  # noqa: E402
import weakref  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402

HEAVY_LIMIT_ENV = "EUROGAS_NEXUS_RATE_LIMIT_HEAVY_PER_MINUTE"
WRITE_LIMIT_ENV = "EUROGAS_NEXUS_RATE_LIMIT_WRITES_PER_MINUTE"
STREAM_LIMIT_ENV = "EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL"
#: Computations that hold the single API process for seconds (solvers, backtests, reports,
#: model calls, PDF reading).
HEAVY_PREFIXES = (
    "/api/optimization/",
    "/api/research/",
    "/api/route-cost/calculate",
    "/api/route-cost/recommend",
    "/api/route-cost/resource-pool/",
    "/api/route-cost/lng-regas/",
    "/api/analysis/",
    "/api/reports/",
    "/api/strategy-lab/",
    "/api/functional-runs",
    "/api/functional-models/",
    "/api/agent/",
    "/api/contracts/intake",
    "/api/lng/cargo-economics",
    "/api/news/",
    "/api/opportunities/evaluations",
)
_STREAMS: dict[str, weakref.WeakSet] = {}


def _production() -> bool:
    from eurogas_nexus.core.config import runtime_environment

    return runtime_environment() in {"trial", "release"}


def _limit(raw: str | None, production_default: int) -> int:
    """A per-minute limit; 0 means none. Defaults apply in trial and release only."""

    raw = (raw or "").strip()
    if raw.isdigit():
        return int(raw)
    return production_default if _production() else 0


def _principal_key(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    principal = getattr(identity, "principal_id", None)
    return principal or f"address:{request.client.host if request.client else 'unknown'}"


async def require_principal_quota(request: Request) -> None:
    """Per-principal fixed-window quotas on writes and on heavy computations.

    ``EUROGAS_NEXUS_RATE_LIMIT_HEAVY_PER_MINUTE`` (default 30 in trial and release) and
    ``EUROGAS_NEXUS_RATE_LIMIT_WRITES_PER_MINUTE`` (default 300). Process-local, like the
    sign-in throttle: a multi-process deployment fronts the API with its own limiter as well.
    """

    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    key = _principal_key(request)
    path = request.url.path
    heavy = _limit(os.environ.get(HEAVY_LIMIT_ENV), 30)
    if heavy and path.startswith(HEAVY_PREFIXES) and not rate_limit(f"heavy:{key}", limit=heavy):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many heavy requests; wait a minute."},
            headers={"Retry-After": "60"},
        )
    writes = _limit(os.environ.get(WRITE_LIMIT_ENV), 300)
    if writes and not rate_limit(f"write:{key}", limit=writes):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many changes; wait a minute."},
            headers={"Retry-After": "60"},
        )


def stream_limit() -> int:
    raw = (os.environ.get(STREAM_LIMIT_ENV) or "").strip()
    return int(raw) if raw.isdigit() else 5


class _CountedStream:
    """An event stream that counts against its principal's cap while it is alive."""

    def __init__(self, principal_id: str, stream: AsyncIterator[str]) -> None:
        self.principal_id = principal_id
        self.stream = stream

    def __aiter__(self) -> _CountedStream:
        return self

    async def __anext__(self) -> str:
        try:
            return await self.stream.__anext__()
        except BaseException:
            self.release()
            raise

    async def aclose(self) -> None:
        self.release()
        closer = getattr(self.stream, "aclose", None)
        if closer is not None:
            await closer()

    def release(self) -> None:
        with _LOCK:
            live = _STREAMS.get(self.principal_id)
            if live is not None:
                live.discard(self)


def open_counted_stream(principal_id: str, stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """``stream`` as a counted stream of ``principal_id``, or 429 past the cap (review M7).

    Open streams are held weakly: a stream whose response never started (the client left
    first) is dropped by the garbage collector and stops counting; one that ran is released
    when it ends or is closed.
    """

    limit = stream_limit()
    counted = _CountedStream(principal_id, stream)
    with _LOCK:
        live = _STREAMS.setdefault(principal_id, weakref.WeakSet())
        if limit and len(live) >= limit:
            raise HTTPException(
                status_code=429,
                detail={"code": "too_many_streams",
                        "message": f"At most {limit} live streams per person at once."},
            )
        live.add(counted)
    return counted


async def read_body_limited(request: Request, limit: int) -> bytes:
    """The request body, refused with 413 once it passes ``limit`` bytes (chunked too)."""

    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > limit:
            raise HTTPException(status_code=413, detail={"code": "body_too_large"})
    return bytes(received)
