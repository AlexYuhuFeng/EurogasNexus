"""Secret-safe data-operations observability.

Structured JSON events and a Prometheus text exporter without an external
dependency. Never log credential values, DB URLs, or provider payload bodies.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "body",
    "credential",
    "db_url",
    "database_url",
    "password",
    "payload",
    "secret",
    "token",
}

_EVENT_KEYS = (
    "timestamp",
    "level",
    "service",
    "event",
    "source_id",
    "run_id",
    "correlation_id",
    "error_category",
    "adapter_version",
    "attempt",
)


def redact(value: Any, *, key: str = "") -> Any:
    """Recursively redact sensitive fields before any event emission."""

    normalized_key = str(key or "").lower()
    if normalized_key in _SENSITIVE_KEYS or any(
        marker in normalized_key for marker in ("credential", "secret", "token", "password")
    ):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact(item, key=key) for item in value]
    if isinstance(value, str):
        return value
    return value


def emit_event(
    *,
    event: str,
    level: str = "info",
    source_id: str | None = None,
    run_id: str | None = None,
    correlation_id: str | None = None,
    error_category: str | None = None,
    adapter_version: str | None = None,
    attempt: int | None = None,
    details: Mapping[str, Any] | None = None,
    now_utc: datetime | None = None,
    destination: Callable[[str], None] = print,
) -> None:
    """Emit one structured JSON data-operations event (never raises)."""

    payload: dict[str, Any] = {
        "timestamp": (now_utc or datetime.now(UTC)).isoformat(),
        "level": level,
        "service": "eurogas-nexus-dataops",
        "event": event,
    }
    if source_id is not None:
        payload["source_id"] = source_id
    if run_id is not None:
        payload["run_id"] = run_id
    if correlation_id is not None:
        payload["correlation_id"] = correlation_id
    if error_category is not None:
        payload["error_category"] = error_category
    if adapter_version is not None:
        payload["adapter_version"] = adapter_version
    if attempt is not None:
        payload["attempt"] = attempt
    for key, value in (details or {}).items():
        payload[str(key)] = redact(value, key=str(key))
    try:
        destination(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    except Exception:
        return


def _pool_gauge(pool, name: str, default: int = 0) -> int:
    """Read one numeric pool attribute, calling it when it is a method.

    Two mistakes this removes, both of which produced a metric Prometheus cannot parse
    rather than a number:

    * ``SQLAlchemy``'s ``QueuePool.checkedout`` is a *method*, so
      ``getattr(pool, "checkedout", 0) or 0`` yields the bound method 鈥?truthy, so the
      ``or`` never fires 鈥?and the exposition line became
      ``eurogas_db_pool_checked_out <bound method QueuePool.checkedout of ...>``. The
      scrape fails on it, which loses every metric in the family, not just this one.
    * ``size``/``maxsize`` differ by pool implementation, so a single attribute name is
      not reliable; the caller passes candidates.

    A non-numeric or raising attribute is reported as the default rather than leaking a
    ``repr`` into the exposition text.
    """

    value = getattr(pool, name, None)
    if value is None:
        return default
    if callable(value):
        try:
            value = value()
        except Exception:  # noqa: BLE001 - a metric must never break the scrape
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _serving_metric_lines() -> list[str]:
    """This process's pool counters and live-update poller (per process: the scraper sums)."""

    from eurogas_nexus.db.session import pool_counters

    pool = pool_counters().snapshot()
    lines = [
        "# HELP eurogas_db_pool_checkouts_total Connections handed out by this process's pool.",
        "# TYPE eurogas_db_pool_checkouts_total counter",
        f"eurogas_db_pool_checkouts_total {pool['checkouts']}",
        "# HELP eurogas_db_pool_waits_total Checkouts that waited for a connection "
        "(the pool was exhausted).",
        "# TYPE eurogas_db_pool_waits_total counter",
        f"eurogas_db_pool_waits_total {pool['waits']}",
        "# HELP eurogas_db_pool_timeouts_total Checkouts that gave up after the pool timeout.",
        "# TYPE eurogas_db_pool_timeouts_total counter",
        f"eurogas_db_pool_timeouts_total {pool['timeouts']}",
        "# HELP eurogas_db_pool_wait_seconds_total Time spent waiting for a connection.",
        "# TYPE eurogas_db_pool_wait_seconds_total counter",
        f"eurogas_db_pool_wait_seconds_total {pool['wait_seconds']:.6f}",
    ]
    from eurogas_nexus.api import stream_hub

    hub = stream_hub._HUB
    if hub is not None:
        stats = hub.stats
        lines.extend(
            [
                "# HELP eurogas_stream_open Live-update streams open on this process.",
                "# TYPE eurogas_stream_open gauge",
                f"eurogas_stream_open {hub.open_streams()}",
                "# HELP eurogas_stream_polls_total Polls of this process's live-update poller.",
                "# TYPE eurogas_stream_polls_total counter",
                f"eurogas_stream_polls_total {stats.polls}",
                "# HELP eurogas_stream_poll_seconds_total Time spent in those polls.",
                "# TYPE eurogas_stream_poll_seconds_total counter",
                f"eurogas_stream_poll_seconds_total {stats.poll_seconds_total:.6f}",
                "# HELP eurogas_stream_poll_failures_total Polls that could not reach the store.",
                "# TYPE eurogas_stream_poll_failures_total counter",
                f"eurogas_stream_poll_failures_total {stats.failed_polls}",
                "# HELP eurogas_stream_refused_total Streams refused over the per-caller cap.",
                "# TYPE eurogas_stream_refused_total counter",
                f"eurogas_stream_refused_total {stats.refused_over_cap}",
            ]
        )
    return lines


def prometheus_metrics(session, *, now_utc: datetime | None = None) -> str:
    """Render the low-cardinality data-operations metric family."""

    from eurogas_nexus.api.middleware.observability import http_metric_lines
    from eurogas_nexus.db.models import IngestionRunRecord, SourceRuntimeStateRecord
    from eurogas_nexus.domain.dataops.contracts import as_utc
    from eurogas_nexus.domain.dataops.run_status import is_failed_run_status

    now = as_utc(now_utc or datetime.now(UTC))
    lines: list[str] = [*http_metric_lines()]
    pool = getattr(session.get_bind(), "pool", None)
    if pool is not None:
        # `_pool` is the underlying implementation on a proxied pool; fall back to the
        # pool itself when the attribute is absent.
        inner = getattr(pool, "_pool", None) or pool
        lines.extend(
            [
                "# HELP eurogas_db_pool_checked_out Checked-out connections.",
                "# TYPE eurogas_db_pool_checked_out gauge",
                f"eurogas_db_pool_checked_out {_pool_gauge(pool, 'checkedout')}",
                "# HELP eurogas_db_pool_size Configured pool size.",
                "# TYPE eurogas_db_pool_size gauge",
                f"eurogas_db_pool_size {_pool_gauge(inner, 'maxsize')}",
                "# HELP eurogas_db_pool_overflow Maximum overflow.",
                "# TYPE eurogas_db_pool_overflow gauge",
                f"eurogas_db_pool_overflow {_pool_gauge(pool, '_max_overflow')}",
            ]
        )
    lines.extend(_serving_metric_lines())
    states = session.query(SourceRuntimeStateRecord).all()
    # Full persisted-run read: the run totals below are exact all-history counts
    # (not a sampled list), at the cost of loading the whole table per scrape.
    runs = session.query(IngestionRunRecord).all()

    lines.append("# HELP eurogas_ingestion_runs_total Total persisted ingestion runs.")
    lines.append("# TYPE eurogas_ingestion_runs_total counter")
    lines.append(f"eurogas_ingestion_runs_total {len(runs)}")

    lines.append(
        "# HELP eurogas_ingestion_failures_total Persisted ingestion runs "
        "classified as failed."
    )
    lines.append("# TYPE eurogas_ingestion_failures_total counter")
    lines.append(
        "eurogas_ingestion_failures_total "
        f"{sum(1 for run in runs if is_failed_run_status(run.status))}"
    )

    lines.append("# HELP eurogas_source_rows_received_total Rows received by source.")
    lines.append("# TYPE eurogas_source_rows_received_total counter")
    lines.append(
        f"eurogas_source_rows_received_total {sum(int(run.rows_received) for run in runs)}"
    )

    lines.append("# HELP eurogas_source_rows_rejected_total Rows rejected by source.")
    lines.append("# TYPE eurogas_source_rows_rejected_total counter")
    lines.append(
        f"eurogas_source_rows_rejected_total {sum(int(run.rows_rejected) for run in runs)}"
    )

    lines.append("# HELP eurogas_source_consecutive_failures Consecutive failures by source.")
    lines.append("# TYPE eurogas_source_consecutive_failures gauge")
    for state in states:
        lines.append(
            f'eurogas_source_consecutive_failures{{source_id="{state.source_id}"}} '
            f"{state.consecutive_failures}"
        )

    lines.append("# HELP eurogas_source_freshness_seconds Current source age in seconds.")
    lines.append("# TYPE eurogas_source_freshness_seconds gauge")
    for state in states:
        if state.source_age_seconds is not None:
            lines.append(
                f'eurogas_source_freshness_seconds{{source_id="{state.source_id}"}} '
                f"{state.source_age_seconds}"
            )

    lines.append("# HELP eurogas_source_scheduler_overdue 1 when a scheduled source is overdue.")
    lines.append("# TYPE eurogas_source_scheduler_overdue gauge")
    for state in states:
        overdue = (
            1
            if state.enabled
            and state.next_run_at_utc is not None
            and as_utc(state.next_run_at_utc) <= now
            else 0
        )
        lines.append(
            f'eurogas_source_scheduler_overdue{{source_id="{state.source_id}"}} {overdue}'
        )

    lines.append("# HELP eurogas_source_certification_state Certification gap by source.")
    lines.append("# TYPE eurogas_source_certification_state gauge")
    for state in states:
        gap = 0 if state.certification_state in {"CERTIFIED", "NOT_REQUIRED"} else 1
        lines.append(
            f'eurogas_source_certification_state{{source_id="{state.source_id}"}} {gap}'
        )

    lines.append("")
    return "\n".join(lines)

