"""Per-process metrics (HTTP latency, database pool, open streams), safe with N workers.

The API may run as several worker processes. Prometheus scrapes one of them per scrape, so
a counter kept in one process's memory would show a different, partial number each time.
``prometheus_client``'s multi-process mode solves this: every worker writes its samples to
memory-mapped files in one shared directory, and whichever worker answers the scrape adds
them up. It is on when ``PROMETHEUS_MULTIPROC_DIR`` names a directory (the runtime compose
file mounts an empty ``tmpfs`` there, so a restart starts from clean files); without it,
as in tests and a single development process, the samples stay in this process.

Only process-local facts live here. Facts read from the database (source freshness, the
scheduler heartbeat, job outcomes, feed lag) are the same whichever worker answers and are
rendered at scrape time by :mod:`eurogas_nexus.application.dataops_observability`.

Labels are bounded: the route label is the matched route's group (``/api/<area>``), never a
raw path, and unmatched paths share ``unmatched``.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

#: The standard ``prometheus_client`` setting; read by the library at import.
MULTIPROC_ENV = "PROMETHEUS_MULTIPROC_DIR"

#: Seconds; covers a 10 ms cached read up to a 30 s report.
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

_POOL_SAMPLE_INTERVAL_SECONDS = 1.0
_pool_lock = threading.Lock()
_pool_sampled_at = 0.0
_stream_lock = threading.Lock()
_open_streams: dict[str, int] = {}


def multiprocess_dir() -> str | None:
    """The shared metric directory, or ``None`` in single-process mode."""

    value = (os.environ.get(MULTIPROC_ENV) or "").strip()
    return value or None


@lru_cache(maxsize=1)
def _metrics() -> dict[str, Any]:
    """Create the metric objects once per process (lazy: importing stays cheap)."""

    directory = multiprocess_dir()
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        disable_created_metrics,
    )

    # ``*_created`` timestamps double the series and no alert reads them.
    disable_created_metrics()
    registry = CollectorRegistry(auto_describe=True)
    return {
        "registry": registry,
        "http_duration": Histogram(
            "eurogas_http_request_duration_seconds",
            "API request duration by route group and method.",
            ("route_group", "method"),
            buckets=LATENCY_BUCKETS,
            registry=registry,
        ),
        "http_requests": Counter(
            "eurogas_http_requests",
            "API requests by route group, method and status class (2xx, 4xx, 5xx).",
            ("route_group", "method", "status_class"),
            registry=registry,
        ),
        "pool_checked_out": Gauge(
            "eurogas_db_pool_checked_out",
            "Database connections in use, summed over the live API processes.",
            registry=registry,
            multiprocess_mode="livesum",
        ),
        "pool_size": Gauge(
            "eurogas_db_pool_size",
            "Configured database pool size, summed over the live API processes.",
            registry=registry,
            multiprocess_mode="livesum",
        ),
        "pool_overflow": Gauge(
            "eurogas_db_pool_overflow",
            "Maximum pool overflow, summed over the live API processes.",
            registry=registry,
            multiprocess_mode="livesum",
        ),
        "streams": Gauge(
            "eurogas_stream_connections",
            "Open live-update (server-sent events) connections by topic.",
            ("topic",),
            registry=registry,
            multiprocess_mode="livesum",
        ),
    }


def status_class(status_code: int) -> str:
    """``2xx`` for 204; bounded to five values."""

    return f"{max(1, min(5, int(status_code) // 100))}xx"


def route_group(route_path: str | None) -> str:
    """The bounded route label: ``/api/<area>`` of the matched route template."""

    if not route_path:
        return "unmatched"
    parts = [part for part in route_path.split("/") if part]
    if not parts:
        return "/"
    if parts[0] == "api" and len(parts) >= 2 and not parts[1].startswith("{"):
        return f"/api/{parts[1]}"
    if parts[0] == "api":
        return "/api"
    return f"/{parts[0]}" if not parts[0].startswith("{") else "unmatched"


def observe_request(route_path: str | None, method: str, status_code: int, seconds: float) -> None:
    """Record one finished request; never raises."""

    try:
        metrics = _metrics()
        group = route_group(route_path)
        verb = method.upper() if method.upper() in _METHODS else "OTHER"
        metrics["http_duration"].labels(group, verb).observe(max(0.0, seconds))
        metrics["http_requests"].labels(group, verb, status_class(status_code)).inc()
    except Exception:  # noqa: BLE001 - a metric must never fail a request
        return


_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def _pool_number(pool: Any, name: str) -> int:
    value = getattr(pool, name, None)
    if value is None:
        return 0
    if callable(value):
        try:
            value = value()
        except Exception:  # noqa: BLE001 - a metric must never break the scrape
            return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def pool_numbers(pools: Iterable[Any]) -> tuple[int, int, int]:
    """``(checked_out, size, overflow)`` summed over SQLAlchemy pools.

    ``QueuePool.checkedout``/``size`` are methods, so they are called (an earlier exporter
    printed the bound method's ``repr``, which made Prometheus reject the whole scrape).
    """

    checked_out = size = overflow = 0
    for pool in pools:
        inner = getattr(pool, "_pool", None)
        checked_out += _pool_number(pool, "checkedout")
        size += _pool_number(pool, "size") or _pool_number(inner, "maxsize")
        overflow += max(0, _pool_number(pool, "_max_overflow"))
    return checked_out, size, overflow


def observe_pools(pools: Iterable[Any] | None = None, *, force: bool = False) -> None:
    """Publish this process's pool state (at most once a second unless forced)."""

    global _pool_sampled_at
    now = time.monotonic()
    with _pool_lock:
        if not force and now - _pool_sampled_at < _POOL_SAMPLE_INTERVAL_SECONDS:
            return
        _pool_sampled_at = now
    try:
        if pools is None:
            # Not imported here: a process that never opened the database has no pools, and
            # serving a request must not load the database layer (product boundary contract).
            session_module = sys.modules.get("eurogas_nexus.db.session")
            if session_module is None:
                return
            pools = session_module.cached_engine_pools()
        checked_out, size, overflow = pool_numbers(pools)
        metrics = _metrics()
        metrics["pool_checked_out"].set(checked_out)
        metrics["pool_size"].set(size)
        metrics["pool_overflow"].set(overflow)
    except Exception:  # noqa: BLE001 - a metric must never fail a request
        return


def stream_opened(topic: str) -> None:
    _stream_change(topic, +1)


def stream_closed(topic: str) -> None:
    _stream_change(topic, -1)


def _stream_change(topic: str, delta: int) -> None:
    try:
        with _stream_lock:
            count = max(0, _open_streams.get(topic, 0) + delta)
            _open_streams[topic] = count
        # ``set`` rather than ``inc``: a restarted process that reuses a pid's file starts
        # from its own count, not from the dead process's.
        _metrics()["streams"].labels(topic).set(count)
    except Exception:  # noqa: BLE001
        return


def prepare_process() -> None:
    """Called once per worker at start: clear dead workers' live gauges, zero our own.

    Counters and histograms of a dead worker stay (a total must not drop); its live gauges
    (pool, streams) are removed so they stop counting.
    """

    directory = multiprocess_dir()
    if directory:
        try:
            from prometheus_client import multiprocess

            Path(directory).mkdir(parents=True, exist_ok=True)
            for pid in _dead_pids(Path(directory)):
                multiprocess.mark_process_dead(pid, directory)
        except Exception:  # noqa: BLE001 - metrics never stop the server starting
            pass
    with _stream_lock:
        topics = list(_open_streams)
        _open_streams.clear()
    for topic in topics:
        _stream_change(topic, 0)
    observe_pools(force=True)


def _dead_pids(directory: Path) -> set[int]:
    pids: set[int] = set()
    for path in directory.glob("gauge_live*_*.db"):
        try:
            pid = int(path.stem.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if pid != os.getpid() and not _alive(pid):
            pids.add(pid)
    return pids


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def render() -> str:
    """The process metric families in Prometheus text format (all workers' sum)."""

    from prometheus_client import CollectorRegistry, generate_latest

    metrics = _metrics()
    directory = multiprocess_dir()
    if directory:
        from prometheus_client import multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry, path=directory)
        return generate_latest(registry).decode("utf-8")
    return generate_latest(metrics["registry"]).decode("utf-8")


__all__ = [
    "LATENCY_BUCKETS",
    "MULTIPROC_ENV",
    "multiprocess_dir",
    "observe_pools",
    "observe_request",
    "pool_numbers",
    "prepare_process",
    "render",
    "route_group",
    "status_class",
    "stream_closed",
    "stream_opened",
]
