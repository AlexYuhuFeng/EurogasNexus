"""One live-update poller per API process, fanning out to every open stream.

Before this, each open server-sent-event connection polled PostgreSQL itself, synchronously,
inside the event loop, every 1.5 seconds: with a few dozen tabs open the loop spent most of its
time waiting on the database and every other request waited behind it (the demo measured 4 to
6 seconds per page and 502 errors). Now:

* one thread per process (:class:`StreamHub`) runs one poll per interval for every stream the
  process holds, in one database session, off the event loop;
* each source is read once per poll from the oldest cursor any stream holds
  (``application.live_topics.Reads``), and each stream takes the rows after its own cursor;
* each stream keeps its own caller's entitlement: rows and notices pass that caller's rule in
  memory, and the caller's books are read once per poll per distinct caller;
* the finished events go to each connection through an in-memory queue owned by that
  connection's event loop; the connection only awaits its queue.

A stream's state (its cursors and its guard) is touched only by the poller thread. A new stream
wakes the poller at once so it gets its first events without waiting for the next interval;
such an early wake polls only the new streams.

每个 API 进程只有一个实时更新轮询线程：每个周期读一次数据库，按每个连接的权限在内存中过滤后分发。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from eurogas_nexus.application import process_metrics

logger = logging.getLogger(__name__)

#: Batches a connection may have waiting before it is ended as too slow (it resumes from its
#: last event id when it reconnects, so nothing is lost).
MAX_PENDING_BATCHES = 200
#: The least time between two polls woken early by new streams (a burst of reconnects after a
#: restart is served by one poll, not one per connection).
EARLY_WAKE_GAP_SECONDS = 0.05
#: While the store stays unreachable, a failed poll is logged at most this often.
FAILURE_LOG_INTERVAL_SECONDS = 60.0
#: Open streams per caller and process at most (``EUROGAS_NEXUS_STREAMS_PER_PRINCIPAL``).
DEFAULT_STREAMS_PER_PRINCIPAL = 8


class StreamState(Protocol):
    """One open stream's cursors and rules; called by the poller thread only."""

    started: bool

    def want(self, reads: Any) -> None: ...

    def poll(self, reads: Any) -> tuple[list[str], bool]: ...


@dataclass(eq=False)
class Subscription:
    state: StreamState
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue
    principal_id: str | None = None
    closed: bool = False


@dataclass
class HubStats:
    polls: int = 0
    last_poll_seconds: float = 0.0
    last_poll_queries: int = 0
    max_poll_seconds: float = 0.0
    failed_polls: int = 0
    slow_consumers_ended: int = 0
    refused_over_cap: int = 0
    poll_seconds_total: float = 0.0
    by_principal: dict[str, int] = field(default_factory=dict)


class StreamLimitReached(Exception):
    """The caller already holds the most streams one process allows."""


def streams_per_principal(environ: dict[str, str] | None = None) -> int:
    if environ is None:
        raw = os.environ.get("EUROGAS_NEXUS_STREAMS_PER_PRINCIPAL", "")
    else:
        raw = environ.get("EUROGAS_NEXUS_STREAMS_PER_PRINCIPAL", "")
    try:
        value = int(str(raw).strip())
    except ValueError:
        return DEFAULT_STREAMS_PER_PRINCIPAL
    return value if value > 0 else DEFAULT_STREAMS_PER_PRINCIPAL


class StreamHub:
    """The process's live-update poller and its subscribers."""

    def __init__(
        self,
        interval: Callable[[], float],
        session_factory: Callable[[], Callable[[], Any]],
        warning: Callable[[], str],
        refused: Callable[[], str] = lambda: "",
        *,
        autostart: bool = True,
    ) -> None:
        self._interval = interval
        self._session_factory = session_factory
        self._warning = warning
        self._refused = refused
        self._autostart = autostart  # off: the caller runs :meth:`poll` itself (tests)
        self._subs: set[Subscription] = set()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._pid = os.getpid()
        self.stats = HubStats()
        self._failing_since: float | None = None
        self._failures_at_start = 0
        self._failure_logged_at = 0.0

    # Subscribers (event-loop side) ----------------------------------------------------------

    def subscribe(self, state: StreamState, principal_id: str | None = None) -> Subscription:
        loop = asyncio.get_running_loop()
        sub = Subscription(state, loop, asyncio.Queue(), principal_id)
        with self._lock:
            if principal_id:
                held = self.stats.by_principal.get(principal_id, 0)
                if held >= streams_per_principal():
                    self.stats.refused_over_cap += 1
                    process_metrics.stream_refused()
                    raise StreamLimitReached(principal_id)
                self.stats.by_principal[principal_id] = held + 1
            self._subs.add(sub)
        if self._autostart:
            self._ensure_thread()
            self._wake.set()
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.discard(sub)
                if sub.principal_id:
                    left = self.stats.by_principal.get(sub.principal_id, 1) - 1
                    if left > 0:
                        self.stats.by_principal[sub.principal_id] = left
                    else:
                        self.stats.by_principal.pop(sub.principal_id, None)
            sub.closed = True

    def open_streams(self) -> int:
        with self._lock:
            return len(self._subs)

    def streams_of(self, principal_id: str) -> int:
        with self._lock:
            return self.stats.by_principal.get(principal_id, 0)

    async def stream(
        self, state: StreamState, principal_id: str | None = None
    ) -> AsyncGenerator[str, None]:
        """The connection's events, as the poller hands them over."""

        try:
            sub = self.subscribe(state, principal_id)
        except StreamLimitReached:  # opened past the route's check (a race): say so and end
            yield self._refused()
            return
        try:
            while True:
                chunks, done = await sub.queue.get()
                for chunk in chunks:
                    yield chunk
                if done:
                    return
        finally:
            self.unsubscribe(sub)

    # The poller (its own thread) ------------------------------------------------------------

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._pid != os.getpid():  # a forked worker: the parent's thread is not here
                self._pid = os.getpid()
                self._thread = None
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run, name="nexus-stream-poller", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:
        next_full = 0.0
        last_poll = 0.0
        while True:
            with self._lock:
                subs = [sub for sub in self._subs if not sub.closed]
            if not subs:
                self._wake.wait()
                self._wake.clear()
                continue
            now = time.monotonic()
            if now >= next_full:
                due = subs
                next_full = now + max(0.0, float(self._interval()))
            else:
                due = [sub for sub in subs if not sub.state.started]
            if due:
                gap = EARLY_WAKE_GAP_SECONDS - (now - last_poll)
                if due is not subs and gap > 0:
                    time.sleep(gap)
                last_poll = time.monotonic()
                try:
                    self.poll(due)
                except Exception:  # never let the poller die
                    logger.exception("live-update poll failed")
            wait = max(0.0, next_full - time.monotonic())
            if self._wake.wait(timeout=wait):
                self._wake.clear()

    def poll(self, subs: list[Subscription]) -> None:
        """One poll for ``subs``: one session, shared reads, each stream's own events."""

        from eurogas_nexus.application.live_topics import Reads

        started = time.monotonic()
        delivered: set[int] = set()
        queries = 0
        failed = False
        try:
            with self._session_factory()() as session:
                reads = Reads(session)
                for sub in subs:
                    with contextlib.suppress(Exception):
                        sub.state.want(reads)
                for sub in subs:
                    try:
                        chunks, done = sub.state.poll(reads)
                    except Exception:
                        logger.exception("live-update stream poll failed")
                        _rollback(session)
                        chunks, done = [self._warning()], False
                    self._deliver(sub, chunks, done)
                    delivered.add(id(sub))
                queries = reads.queries
                # A stream that could not read answers with a warning event and goes on; the
                # poll still failed to reach the store for it: log and count it once.
                if reads.failure is not None:
                    failed = True
                    self.stats.failed_polls += 1
                    self._log_failed_poll(reads.failure)
        except Exception:
            if not failed:  # counted once per poll
                failed = True
                self.stats.failed_polls += 1
                self._log_failed_poll()
            for sub in subs:
                if id(sub) not in delivered:
                    sub.state.started = True
                    self._deliver(sub, [self._warning()], False)
        elapsed = time.monotonic() - started
        self.stats.polls += 1
        self.stats.last_poll_seconds = elapsed
        self.stats.poll_seconds_total += elapsed
        self.stats.max_poll_seconds = max(self.stats.max_poll_seconds, elapsed)
        self.stats.last_poll_queries = queries
        if not failed and self._failing_since is not None:
            logger.info(
                "live-update poller reached the store again after %d failed polls",
                self.stats.failed_polls - self._failures_at_start,
            )
            self._failing_since = None
        # Every worker's own counter file: the scrape sums the processes' pollers.
        process_metrics.stream_poll(elapsed, failed=failed)
        # The poller checks out connections between requests: publish the pool counts too.
        process_metrics.observe_pools()

    def _log_failed_poll(self, exc_info: Any = True) -> None:
        """Log the first failed poll with its error, then at most once a minute while the
        store stays unreachable (a poll runs every 1.5 s)."""

        now = time.monotonic()
        if self._failing_since is None:
            self._failing_since = now
            self._failures_at_start = self.stats.failed_polls - 1
            self._failure_logged_at = now
            logger.error("live-update poll could not reach the store", exc_info=exc_info)
        elif now - self._failure_logged_at >= FAILURE_LOG_INTERVAL_SECONDS:
            self._failure_logged_at = now
            logger.error(
                "live-update poll still cannot reach the store (%d failed polls)",
                self.stats.failed_polls - self._failures_at_start,
                exc_info=exc_info,
            )

    def _deliver(self, sub: Subscription, chunks: list[str], done: bool) -> None:
        if sub.closed or (not chunks and not done):
            return
        if sub.queue.qsize() >= MAX_PENDING_BATCHES:
            self.stats.slow_consumers_ended += 1
            chunks, done = [], True
        try:
            sub.loop.call_soon_threadsafe(sub.queue.put_nowait, (chunks, done))
        except RuntimeError:  # the connection's loop is gone
            done = True
        if done:
            self.unsubscribe(sub)


def _rollback(session) -> None:
    with contextlib.suppress(Exception):
        session.rollback()


_HUB: StreamHub | None = None
_HUB_LOCK = threading.Lock()


def get_hub() -> StreamHub:
    """The process's hub (created on first use; a forked worker makes its own thread)."""

    global _HUB
    with _HUB_LOCK:
        if _HUB is None:
            from eurogas_nexus.api.routes.public import streaming

            def session_factory():
                from eurogas_nexus.db import session as db_session

                return db_session.get_session_factory()

            _HUB = StreamHub(
                interval=lambda: streaming.POLL_SECONDS,
                session_factory=session_factory,
                warning=streaming.warning_event,
                refused=streaming.refused_event,
            )
        return _HUB


__all__ = [
    "DEFAULT_STREAMS_PER_PRINCIPAL",
    "HubStats",
    "StreamHub",
    "StreamLimitReached",
    "get_hub",
    "streams_per_principal",
]
