"""Warm views: a heavy read answers from its last good result and refreshes behind it.

The desk's first-screen reads (Today, the forward balance, the spread board, the instrument
catalogue, the report catalogue, the limits) are computed from tens of thousands of stored
rows, 1 to 10 s each, and every open of a tab used to compute them again. A warm view keeps
the last result of each read in this process, per caller, and answers from it at once:

- **Who**: an entry is keyed by the caller's whole authenticated principal (id, role, roles,
  data scopes, ...), the database and the read's own parameters, and the UTC day. A result is
  only ever served to a request whose principal is identical to the one it was computed for,
  so nothing crosses users or entitlements; a changed grant is a new key.
- **When it is fresh**: until something it may read has changed. Three signals: the market
  event outbox moved (its newest ``seq``; every price, outage, fundamentals, ingestion, contract,
  mark, limit or freight change publishes there, ``application/market_events.py``); a write
  through this API (any successful POST/PUT/PATCH/DELETE that is not a computation); or the
  view's ``max_age`` passed (time-dependent figures: late/stale states, the gas day).
- **Stale answers say so**: a stale entry is served at once with ``meta.view.state``
  ``refreshing`` and its ``computed_at_utc``, and is recomputed in the background; the next
  read gets the new result. The figures inside keep their own as-of times. A caller's own
  write is never answered from before it: that caller's entries are recomputed before they
  are served again. An entry older than ``max_stale`` is never served.
- **Kept warm**: entries read in the last ``keep_warm_seconds`` are refreshed in the background
  when a signal moves, so the next open finds the new figures already computed.
- **Per reader inside**: a refresh runs in a copy of the first request's context, so what
  reads the request principal from a context variable (alert visibility,
  ``application/alert_scope.py``; the book scope, ``security/portfolio_scope.py``) reads the
  same reader; per-reader slices (alerts on Today) are never computed for anyone else.
- **Licensed use** (GOV-1): the families a computation noted are kept with its result and
  noted again on every request it answers, so metering counts each served read as before.

Several API processes: each keeps its own results, but the write signal is shared. With the
shared cache configured (``EUROGAS_NEXUS_SHARED_CACHE_URL``, ``core/shared_cache.py``), a write
through any process makes every process's entries due and the writer's own unservable, so a
caller's own write is never answered from before it whichever process answers next. When the
shared cache cannot be read, nothing is answered from memory (each read computes) until it can.
Without a shared cache (one process: the demo, development) the signal is this process's own.
``EUROGAS_NEXUS_WARM_VIEWS=off`` switches it off.

预热视图：重型读取按调用者缓存最近一次结果，立即返回并在后台按变更信号刷新。
"""

from __future__ import annotations

import contextvars
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

#: Most entries kept (least recently used dropped first).
MAX_ENTRIES = 512
#: How often the outbox's newest event is read, at most.
WATERMARK_POLL_SECONDS = 2.0
#: How often the keeper looks for entries to refresh.
KEEPER_INTERVAL_SECONDS = 5.0
#: Background computations at once (each holds a database connection).
REFRESH_WORKERS = 2

FRESH = "fresh"
REFRESHING = "refreshing"

#: Successful non-GET requests that only compute and change nothing stored: they do not
#: invalidate anything (substrings of the path).
COMPUTE_ONLY_PATHS = (
    "/api/auth/",
    "/api/dev/auth/",
    "/evaluate",
    "/ask",
    "/explain",
    "/interpret",
    "/normalise",
    "/price-conversion",
    "/cash-valuation",
    "/query",
    "/plan",
    "/brief",
    "/recommend",
    "/optimize",
    "/optimization/",
    "/preview",
)


@dataclass(frozen=True)
class ViewSpec:
    """How one read is kept: its name and how long a result may stand."""

    name: str
    #: A result older than this is refreshed (served meanwhile, marked ``refreshing``).
    max_age_seconds: float = 60.0
    #: A result older than this is never served; the read computes and waits.
    max_stale_seconds: float = 600.0
    #: Refresh in the background while the entry was read within this long.
    keep_warm_seconds: float = 900.0


@dataclass
class _Entry:
    spec: ViewSpec
    owner: str
    value: dict[str, Any]
    computed_at: datetime
    computed_mono: float
    watermark: int | None
    generation: tuple[int, int]
    owner_generation: tuple[int, int]
    families: frozenset[str]
    compute: Callable[[], Any]
    context: contextvars.Context
    last_access: float
    refreshing: Future | None = None
    error: str | None = None


@dataclass
class WarmViewStats:
    hits: int = 0
    stale_hits: int = 0
    misses: int = 0
    refreshes: int = 0
    refresh_errors: int = 0
    by_view: dict[str, int] = field(default_factory=dict)


def enabled(environ=os.environ) -> bool:
    return (environ.get("EUROGAS_NEXUS_WARM_VIEWS") or "on").strip().lower() not in {
        "0", "off", "false", "no",
    }


#: A generation: the shared count and this process's own (its own writes count even when the
#: shared count could not be raised).
Generation = tuple[int, int]
Signals = tuple[Generation, dict[str, Generation]]
#: The outbox watermark, the generation, the owner's generation, and when (wall, monotonic).
Stamp = tuple[int | None, Generation, Generation, datetime, float]
#: An owner's shared write count is forgotten after this long without a write (it then
#: restarts at zero, which only makes that owner's kept entries unservable once).
OWNER_GENERATION_TTL_SECONDS = 7 * 24 * 3600.0


class Generations:
    """The write signal: a global generation and one per owner (see the module text)."""

    def __init__(self, cache_getter: Callable[[], Any] | None = None) -> None:
        self._cache_getter = cache_getter
        self._lock = threading.Lock()
        self._local = 0
        self._local_owner: dict[str, int] = {}

    def _cache(self):
        if self._cache_getter is not None:
            return self._cache_getter()
        from eurogas_nexus.core.shared_cache import shared_cache

        return shared_cache()

    @staticmethod
    def _owner_key(owner: str) -> str:
        import hashlib

        return "wv:o:" + hashlib.sha256(owner.encode("utf-8")).hexdigest()[:32]

    def bump(self, owner: str | None) -> None:
        with self._lock:
            self._local += 1
            if owner:
                self._local_owner[owner] = self._local_owner.get(owner, 0) + 1
        cache = self._cache()
        if not cache.shared:
            return
        from eurogas_nexus.core.shared_cache import SharedCacheUnavailable

        try:
            cache.incr("wv:g")
            if owner:
                cache.incr(self._owner_key(owner), ttl_seconds=OWNER_GENERATION_TTL_SECONDS)
        except SharedCacheUnavailable:
            # Other processes do not hear of this write; theirs go due at max_age or when the
            # outbox moves. This process's own count above still holds here.
            return

    def read(self, owners: list[str]) -> Signals | None:
        """The generations as they stand, or None when the shared count cannot be read."""

        with self._lock:
            local = self._local
            local_owner = {owner: self._local_owner.get(owner, 0) for owner in owners}
        cache = self._cache()
        if not cache.shared:
            return (0, local), {owner: (0, local_owner[owner]) for owner in owners}
        from eurogas_nexus.core.shared_cache import SharedCacheUnavailable

        try:
            values = cache.get_many(["wv:g", *[self._owner_key(owner) for owner in owners]])
        except SharedCacheUnavailable:
            return None
        shared = [int(value) if value is not None else 0 for value in values]
        return (shared[0], local), {
            owner: (shared[index + 1], local_owner[owner]) for index, owner in enumerate(owners)
        }


def _outbox_watermark() -> int | None:
    """The newest market event's ``seq``, or ``None`` when it cannot be read."""

    from sqlalchemy import func, select
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.models.market_events import MarketEventRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return None
    try:
        with get_session_factory()() as session:
            return session.execute(select(func.max(MarketEventRecord.seq))).scalar()
    except SQLAlchemyError:
        return None


class WarmViews:
    """The warm view store (see the module text). Thread-safe."""

    def __init__(
        self,
        *,
        watermark: Callable[[], int | None] = _outbox_watermark,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        executor: Any | None = None,
        max_entries: int = MAX_ENTRIES,
        watermark_poll_seconds: float = WATERMARK_POLL_SECONDS,
        generations: Generations | None = None,
    ) -> None:
        self._watermark_reader = watermark
        self._clock = clock
        self._wall_clock = wall_clock
        self._executor = executor
        self._max_entries = max_entries
        self._poll = watermark_poll_seconds
        self._lock = threading.RLock()
        self._key_locks: dict[Hashable, threading.Lock] = {}
        self._entries: OrderedDict[Hashable, _Entry] = OrderedDict()
        self._generations = generations or Generations()
        self._watermark: int | None = None
        self._watermark_at: float | None = None
        self._keeper: threading.Thread | None = None
        self.stats = WarmViewStats()

    # ------------------------------------------------------------------ signals

    def watermark(self) -> int | None:
        now = self._clock()
        with self._lock:
            if self._watermark_at is not None and now - self._watermark_at < self._poll:
                return self._watermark
        value = self._watermark_reader()
        with self._lock:
            self._watermark, self._watermark_at = value, self._clock()
        return value

    def note_write(self, owner: str | None) -> None:
        """A write went through this API: everything is due, the writer's own at once."""

        self._generations.bump(owner)
        with self._lock:
            # The next read of the outbox is not deferred by the poll interval.
            self._watermark_at = None

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _signals(self, owners: list[str]) -> Signals | None:
        """The write signal for ``owners``; when it cannot be read, everything kept is dropped:
        writes made through other processes meanwhile are unknown, so after the outage every
        read computes again."""

        signals = self._generations.read(owners)
        if signals is None:
            self.clear()
        return signals

    # ------------------------------------------------------------------ reads

    def serve(
        self,
        spec: ViewSpec,
        owner: str,
        key: Hashable,
        compute: Callable[[], Any],
    ) -> Any:
        """The view's answer for ``key``: kept, kept and refreshing, or computed now."""

        from eurogas_nexus.governance.usage import note_licensed_read

        full_key = (spec.name, key)
        signals = self._signals([owner])
        if signals is None:
            # The write signal cannot be read: a kept answer might predate a write made
            # through another process. Compute, and keep nothing, until it can be read.
            result, families = _metered(compute)
            for family in families:
                note_licensed_read(family)
            return result
        watermark = self.watermark()
        now = self._clock()
        value = None
        with self._lock:
            entry = self._entries.get(full_key)
            if entry is not None and self._servable(entry, now, signals):
                self._entries.move_to_end(full_key)
                entry.last_access = now
                if self._fresh(entry, watermark, now, signals):
                    state = FRESH
                    self.stats.hits += 1
                else:
                    state = REFRESHING
                    self.stats.stale_hits += 1
                    self._schedule(full_key, entry)
                families, value = entry.families, self._decorate(entry, state)
        if value is not None:
            for family in families:
                note_licensed_read(family)
            return value
        return self._compute_now(spec, owner, full_key, compute)

    def _servable(self, entry: _Entry, now: float, signals: Signals) -> bool:
        """Whether the entry may be served at all (fresh, or stale and refreshing)."""

        if now - entry.computed_mono > entry.spec.max_stale_seconds:
            return False
        # The caller's own write: never answer from before it.
        return signals[1].get(entry.owner) == entry.owner_generation

    def _fresh(self, entry: _Entry, watermark: int | None, now: float, signals: Signals) -> bool:
        return (
            entry.generation == signals[0]
            and entry.watermark == watermark
            and now - entry.computed_mono < entry.spec.max_age_seconds
        )

    def _decorate(self, entry: _Entry, state: str) -> dict[str, Any]:
        meta = dict(entry.value.get("meta") or {})
        meta["view"] = {
            "state": state,
            "computed_at_utc": entry.computed_at.isoformat().replace("+00:00", "Z"),
            "max_age_seconds": entry.spec.max_age_seconds,
        }
        return {**entry.value, "meta": meta}

    def _key_lock(self, full_key: Hashable) -> threading.Lock:
        with self._lock:
            lock = self._key_locks.get(full_key)
            if lock is None:
                lock = self._key_locks[full_key] = threading.Lock()
            return lock

    def _compute_now(self, spec: ViewSpec, owner: str, full_key: Hashable, compute) -> Any:
        from eurogas_nexus.governance.usage import note_licensed_read

        with self._key_lock(full_key):
            # Another request computed it while this one waited: serve that.
            signals = self._signals([owner])
            watermark = self.watermark()
            now = self._clock()
            with self._lock:
                entry = self._entries.get(full_key)
                if (
                    entry is not None
                    and signals is not None
                    and self._servable(entry, now, signals)
                    and self._fresh(entry, watermark, now, signals)
                ):
                    entry.last_access = now
                    self.stats.hits += 1
                    families, value = entry.families, self._decorate(entry, FRESH)
                else:
                    value = None
            if value is not None:
                for family in families:
                    note_licensed_read(family)
                return value
            with self._lock:
                self.stats.misses += 1
                self.stats.by_view[spec.name] = self.stats.by_view.get(spec.name, 0) + 1
            stamp = self._stamp(owner)
            # The request's context (its principal for alert visibility, its book scope): a
            # background refresh runs in a copy of it, so it reads as this reader did.
            context = contextvars.copy_context()
            result, families = _metered(compute)
            for family in families:
                note_licensed_read(family)
            if stamp is None or not _cacheable(result):
                return result
            entry = self._store(spec, owner, full_key, result, families, stamp, compute, context)
            return self._decorate(entry, FRESH)

    def _stamp(self, owner: str) -> Stamp | None:
        """The signals as they stand before a computation starts (a change during it wins);
        None when the write signal cannot be read (the result is then not kept)."""

        signals = self._signals([owner])
        if signals is None:
            return None
        watermark = self.watermark()
        return (watermark, signals[0], signals[1][owner], self._wall_clock(), self._clock())

    def _store(self, spec, owner, full_key, result, families, stamp, compute, context) -> _Entry:
        watermark, generation, owner_generation, computed_at, computed_mono = stamp
        entry = _Entry(
            spec=spec, owner=owner, value=result, computed_at=computed_at,
            computed_mono=computed_mono, watermark=watermark, generation=generation,
            owner_generation=owner_generation, families=frozenset(families), compute=compute,
            context=context, last_access=self._clock(),
        )
        with self._lock:
            self._entries[full_key] = entry
            self._entries.move_to_end(full_key)
            while len(self._entries) > self._max_entries:
                dropped, _ = self._entries.popitem(last=False)
                self._key_locks.pop(dropped, None)
        return entry

    # ------------------------------------------------------------------ refreshes

    def _schedule(self, full_key: Hashable, entry: _Entry) -> None:
        """Recompute ``entry`` in the background, once at a time (call with the lock held)."""

        if entry.refreshing is not None and not entry.refreshing.done():
            return
        executor = self._executor_or_default()
        entry.refreshing = executor.submit(self._refresh, full_key, entry)

    def _refresh(self, full_key: Hashable, entry: _Entry) -> None:
        stamp = self._stamp(entry.owner)
        if stamp is None:
            return  # the write signal cannot be read: the next read computes
        try:
            result, families = entry.context.copy().run(_metered, entry.compute)
        except Exception as exc:  # noqa: BLE001 - the last good result stays
            with self._lock:
                entry.error = exc.__class__.__name__
                self.stats.refresh_errors += 1
            return
        with self._lock:
            self.stats.refreshes += 1
            current = self._entries.get(full_key)
        if current is not entry or not _cacheable(result):
            return
        fresh = self._store(entry.spec, entry.owner, full_key, result, families, stamp,
                            entry.compute, entry.context)
        fresh.last_access = entry.last_access

    def refresh_due(self) -> int:
        """Start a refresh of every entry read lately whose signals moved; how many started."""

        with self._lock:
            owners = sorted({entry.owner for entry in self._entries.values()})
        signals = self._signals(owners)
        if signals is None:
            return 0
        watermark = self.watermark()
        now = self._clock()
        started = 0
        with self._lock:
            for full_key, entry in list(self._entries.items()):
                if now - entry.last_access > entry.spec.keep_warm_seconds:
                    continue
                if entry.owner not in signals[1]:
                    continue  # stored after the signals were read: the next round sees it
                if self._fresh(entry, watermark, now, signals):
                    continue
                if entry.refreshing is not None and not entry.refreshing.done():
                    continue
                self._schedule(full_key, entry)
                started += 1
        return started

    def _executor_or_default(self):
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=REFRESH_WORKERS, thread_name_prefix="warm-view"
            )
        return self._executor

    def start_keeper(self, interval: float = KEEPER_INTERVAL_SECONDS) -> None:
        """Refresh read-lately entries in the background as their signals move (idempotent)."""

        with self._lock:
            if self._keeper is not None and self._keeper.is_alive():
                return

            def loop() -> None:
                while True:
                    time.sleep(interval)
                    try:
                        self.refresh_due()
                    except Exception:  # noqa: BLE001, S112 - the keeper outlives a bad round
                        continue

            self._keeper = threading.Thread(target=loop, name="warm-view-keeper", daemon=True)
            self._keeper.start()


def _metered(compute: Callable[[], Any]) -> tuple[Any, set[str]]:
    """Run ``compute`` under a meter of its own: its result and the licensed families read."""

    from eurogas_nexus.governance.usage import metering, not_metered

    with not_metered(), metering() as meter:
        result = compute()
    return result, set(meter.families)


def _cacheable(result: Any) -> bool:
    return isinstance(result, dict) and isinstance(result.get("meta"), dict)


_VIEWS = WarmViews()


def views() -> WarmViews:
    return _VIEWS


def owner_of(request: Any) -> tuple[str, Hashable] | None:
    """The caller's id and the whole principal (the key part), or ``None`` (not kept)."""

    identity = getattr(getattr(request, "state", None), "identity", None)
    principal_id = getattr(identity, "principal_id", None)
    if not principal_id:
        return None
    try:
        hash(identity)
    except TypeError:
        return None
    return principal_id, identity


def serve_view(
    request: Any,
    spec: ViewSpec,
    params: tuple,
    compute: Callable[[], Any],
) -> Any:
    """Answer a route's read through the warm view store (or straight, when off/unkeyed)."""

    if not enabled():
        return compute()
    owner = owner_of(request)
    if owner is None:
        return compute()
    from eurogas_nexus.db.session import resolve_database_url

    principal_id, principal = owner
    day = datetime.now(UTC).date().isoformat()
    store = views()
    store.start_keeper()
    key = (principal, resolve_database_url(), day, params)
    return store.serve(spec, principal_id, key, compute)


def _frozen(value: Any) -> Hashable:
    if isinstance(value, list | tuple | set | frozenset):
        return tuple(_frozen(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((str(k), _frozen(v)) for k, v in value.items()))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def not_json(params: dict[str, Any]) -> bool:
    """``skip`` for a read that can also answer a file (``format=csv|xlsx|pdf``)."""

    return params.get("format", "json") != "json"


def as_of_read(params: dict[str, Any]) -> bool:
    """``skip`` for a read of an earlier instant (``as_of``): computed as asked, not kept."""

    return params.get("as_of") is not None


def warm_view(spec: ViewSpec, *, skip: Callable[[dict[str, Any]], bool] | None = None):
    """Route decorator: the read answers through the warm view store (see the module text).

    The route's query parameters are the key (with the caller); ``skip`` names calls that are
    answered directly (a CSV file, an ``as_of`` read). FastAPI reads the route's own signature
    through ``functools.wraps``, so its parameters and OpenAPI description are unchanged.
    """

    import functools

    def decorate(fn):
        @functools.wraps(fn)
        def route(*args, **kwargs):
            request = kwargs.get("request")
            if request is None or (skip is not None and skip(kwargs)):
                return fn(*args, **kwargs)
            params = tuple(
                sorted((name, _frozen(value)) for name, value in kwargs.items()
                       if name != "request")
            )
            return serve_view(request, spec, params, lambda: fn(*args, **kwargs))

        return route

    return decorate


__all__ = [
    "COMPUTE_ONLY_PATHS",
    "Generations",
    "FRESH",
    "REFRESHING",
    "ViewSpec",
    "WarmViews",
    "as_of_read",
    "enabled",
    "not_json",
    "owner_of",
    "serve_view",
    "views",
    "warm_view",
]
