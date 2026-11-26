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
# Reentrant: a stream released by the garbage collector may run while this thread holds it.
_LOCK = threading.RLock()


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
_STREAMS: dict[str, set[object]] = {}


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
    ``EUROGAS_NEXUS_RATE_LIMIT_WRITES_PER_MINUTE`` (default 300). Counted in the shared cache
    like the sign-in throttle (:func:`rate_limit`): with several API processes and a shared
    cache the quota holds across all of them; without one, or while it cannot be reached,
    each process counts for itself.
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


#: The default cap. The web client holds ONE live stream per browser tab (its topics multiplexed
#: on ``/api/stream/live``), so this is eight tabs or windows of one person at once: a trader's
#: screens across several monitors plus the desktop app, with room for a reconnect that overlaps
#: its predecessor for a moment. Still a small fixed bound on one account's connections.
DEFAULT_STREAM_LIMIT = 8


def stream_limit() -> int:
    """Open live-update streams per person at most (``EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL``,
    default :data:`DEFAULT_STREAM_LIMIT`; 0 means no cap)."""

    raw = (os.environ.get(STREAM_LIMIT_ENV) or "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_STREAM_LIMIT


#: A stream's slot in the shared cache is a lease: refreshed while the stream sends, gone this
#: long after a process died without releasing it.
STREAM_SLOT_TTL_SECONDS = 90.0
STREAM_SLOT_REFRESH_SECONDS = 30.0


class _SharedSlot:
    """One stream's slot ``stream:<owner digest>:<n>`` in the shared cache (n < the cap)."""

    def __init__(self, cache, key: str, token: bytes) -> None:
        self.cache = cache
        self.key = key
        self.token = token
        self.refreshed = time.monotonic()

    def refresh(self) -> None:
        now = time.monotonic()
        if now - self.refreshed < STREAM_SLOT_REFRESH_SECONDS:
            return
        self.refreshed = now
        from eurogas_nexus.core.shared_cache import SharedCacheUnavailable

        try:
            if self.cache.get(self.key) in (None, self.token):
                self.cache.set(self.key, self.token, ttl_seconds=STREAM_SLOT_TTL_SECONDS)
        except SharedCacheUnavailable:
            pass  # the lease runs out; the stream itself goes on

    def release(self) -> None:
        from eurogas_nexus.core.shared_cache import SharedCacheUnavailable

        try:
            if self.cache.get(self.key) == self.token:
                self.cache.delete(self.key)
        except SharedCacheUnavailable:
            pass  # the lease expires on its own


def _release(owner: str, slot: _SharedSlot | None, ref) -> None:
    """Free a stream's place (idempotent; also run when the stream is garbage collected)."""

    with _LOCK:
        live = _STREAMS.get(owner)
        if live is not None:
            live.discard(ref)
            if not live:
                _STREAMS.pop(owner, None)
    if slot is not None:
        slot.release()


#: The longest a counted stream stays silent: past this it sends a comment line, so a connection
#: the client has closed is noticed at that send (a server that reports a disconnect only when
#: a write fails) and its slot freed, and no proxy times out a quiet but healthy stream.
STREAM_KEEPALIVE_SECONDS = 10.0
KEEPALIVE_COMMENT = ": keepalive\n\n"


def _retrieve(task) -> None:
    """Done callback of an abandoned read: take its outcome so none is reported as lost."""

    if not task.cancelled():
        task.exception()


class _CountedStream:
    """An event stream that counts against its principal's cap while it is alive.

    Its place is released, exactly once, the moment it ends, fails, is cancelled (the server
    cancels the response when the client disconnects) or is closed; failing all of those, when
    it is garbage collected. The wrapped stream is read in a task of its own so that a quiet
    stream still sends :data:`KEEPALIVE_COMMENT` every :data:`STREAM_KEEPALIVE_SECONDS`.
    """

    def __init__(self, principal_id: str, stream: AsyncIterator[str]) -> None:
        self.principal_id = principal_id
        self.stream = stream
        self.slot: _SharedSlot | None = None
        self._ref = object()
        self._finalizer = None
        self._pending = None  # the read of the wrapped stream in flight, if any
        self._done = False

    def __aiter__(self) -> _CountedStream:
        return self

    async def __anext__(self) -> str:
        import asyncio

        if self._done:
            raise StopAsyncIteration
        try:
            if self._pending is None:
                self._pending = asyncio.ensure_future(self.stream.__anext__())
            done, _ = await asyncio.wait({self._pending}, timeout=STREAM_KEEPALIVE_SECONDS)
            if done:
                task, self._pending = self._pending, None
                chunk = task.result()
            else:
                chunk = KEEPALIVE_COMMENT  # the read stays pending for the next call
        except BaseException:
            # Ended, failed or cancelled: free the place now, without awaiting anything (a
            # cancelled response may not await again).
            self._abandon()
            raise
        if self.slot is not None:
            self.slot.refresh()
        return chunk

    def _abandon(self) -> None:
        self._done = True
        pending, self._pending = self._pending, None
        if pending is not None and not pending.done():
            pending.add_done_callback(_retrieve)
            pending.cancel()  # runs the wrapped stream's own clean-up (it leaves the poller)
        self.release()

    async def aclose(self) -> None:
        import asyncio
        import contextlib

        pending = self._pending
        self._abandon()
        if pending is not None:
            await asyncio.wait({pending})  # its clean-up has run; its outcome is not ours
        closer = getattr(self.stream, "aclose", None)
        if closer is not None:
            with contextlib.suppress(RuntimeError, StopAsyncIteration):
                await closer()

    def release(self) -> None:
        if self._finalizer is not None:
            self._finalizer()  # runs _release once


def _claim_shared(cache, owner: str, limit: int) -> _SharedSlot | None:
    """A free slot of ``owner`` in the shared cache, or None when all ``limit`` are held."""

    import secrets

    digest = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:32]
    token = secrets.token_hex(8).encode()
    for index in range(limit):
        key = f"stream:{digest}:{index}"
        if cache.add(key, token, ttl_seconds=STREAM_SLOT_TTL_SECONDS):
            return _SharedSlot(cache, key, token)
    return None


def _refuse_stream(limit: int) -> HTTPException:
    from eurogas_nexus.application import process_metrics

    process_metrics.stream_refused()
    return HTTPException(
        status_code=429,
        detail={
            # The catalogued code (the client explains it), with the reason.
            "code": "rate_limited",
            "reason": "stream_limit_reached",
            "message": f"At most {limit} live streams per person at once.",
        },
        headers={"Retry-After": "30"},
    )


def open_counted_stream(principal_id: str, stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """``stream`` as a counted stream of ``principal_id``, or 429 past the cap (review M7).

    One cap, ``EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL``. With a shared cache configured
    (several API processes) each open stream holds a slot there, an expiring lease refreshed
    while the stream sends, so the cap holds across every process and a process that dies
    frees its slots within :data:`STREAM_SLOT_TTL_SECONDS`. Without one, or while it cannot be
    reached, this process counts its own streams.

    A stream is released the moment it ends, fails, is cancelled or is closed (serve it with
    :class:`CountedStreamingResponse`, which closes it however the response ends); one whose
    response never started (the client left first) is released when it is garbage collected.
    """

    from eurogas_nexus.core.shared_cache import SharedCacheUnavailable, shared_cache

    limit = stream_limit()
    counted = _CountedStream(principal_id, stream)
    slot: _SharedSlot | None = None
    cache = shared_cache()
    shared = False
    if limit and cache.shared:
        try:
            slot = _claim_shared(cache, principal_id, limit)
            shared = True
        except SharedCacheUnavailable:
            shared = False  # this process's own count below
        if shared and slot is None:
            raise _refuse_stream(limit)
    with _LOCK:
        live = _STREAMS.setdefault(principal_id, set())
        if limit and not shared and len(live) >= limit:
            raise _refuse_stream(limit)
        live.add(counted._ref)
    counted.slot = slot
    counted._finalizer = weakref.finalize(counted, _release, principal_id, slot, counted._ref)
    return counted


def open_streams(principal_id: str) -> int:
    """This process's open streams of ``principal_id`` (tests, diagnostics)."""

    with _LOCK:
        return len(_STREAMS.get(principal_id, ()))


from fastapi.responses import StreamingResponse  # noqa: E402


class CountedStreamingResponse(StreamingResponse):
    """A server-sent-event response that frees its stream's place however it ends.

    The client disconnecting (the server cancels the response, or, on a server that reports a
    disconnect only through a failed write, the next send fails: at the latest the keepalive
    after :data:`STREAM_KEEPALIVE_SECONDS`), the stream ending, or any error: the counted
    stream is closed in ``finally``, so a slot never outlives its connection.
    """

    def __init__(self, content: AsyncIterator[str], **kwargs) -> None:
        kwargs.setdefault("media_type", "text/event-stream")
        headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        headers.update(kwargs.pop("headers", None) or {})
        super().__init__(content, headers=headers, **kwargs)

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            closer = getattr(self.body_iterator, "aclose", None)
            if closer is not None:
                await closer()


async def read_body_limited(request: Request, limit: int) -> bytes:
    """The request body, refused with 413 once it passes ``limit`` bytes (chunked too)."""

    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > limit:
            raise HTTPException(status_code=413, detail={"code": "body_too_large"})
    return bytes(received)
