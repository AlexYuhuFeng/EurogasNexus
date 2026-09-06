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


def prometheus_metrics(session, *, now_utc: datetime | None = None) -> str:
    """Render the low-cardinality data-operations metric family."""

    from eurogas_nexus.api.middleware.observability import http_metric_lines
    from eurogas_nexus.db.models import IngestionRunRecord, SourceRuntimeStateRecord
    from eurogas_nexus.domain.dataops.contracts import as_utc

    now = as_utc(now_utc or datetime.now(UTC))
    lines: list[str] = [*http_metric_lines()]
    pool = getattr(session.get_bind(), "pool", None)
    if pool is not None:
        lines.extend(
            [
                "# HELP eurogas_db_pool_checked_out Checked-out connections.",
                "# TYPE eurogas_db_pool_checked_out gauge",
                f"eurogas_db_pool_checked_out {getattr(pool, 'checkedout', 0) or 0}",
                "# HELP eurogas_db_pool_size Configured pool size.",
                "# TYPE eurogas_db_pool_size gauge",
                f"eurogas_db_pool_size "
                f"{getattr(pool, '_pool', None) and getattr(pool._pool, 'maxsize', 0) or 0}",
                "# HELP eurogas_db_pool_overflow Maximum overflow.",
                "# TYPE eurogas_db_pool_overflow gauge",
                f"eurogas_db_pool_overflow {getattr(pool, '_max_overflow', 0) or 0}",
            ]
        )
    states = session.query(SourceRuntimeStateRecord).all()
    runs = session.query(IngestionRunRecord).all()

    lines.append("# HELP eurogas_ingestion_runs_total Total persisted ingestion runs.")
    lines.append("# TYPE eurogas_ingestion_runs_total counter")
    lines.append(f"eurogas_ingestion_runs_total {len(runs)}")

    lines.append("# HELP eurogas_ingestion_failures_total Persisted failed ingestion runs.")
    lines.append("# TYPE eurogas_ingestion_failures_total counter")
    lines.append(
        f"eurogas_ingestion_failures_total {sum(1 for run in runs if run.status == 'FAILED')}"
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
