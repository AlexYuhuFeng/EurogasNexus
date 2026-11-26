"""Secret-safe data-operations observability.

Structured JSON events and the Prometheus text exposition (process metrics from
:mod:`eurogas_nexus.application.process_metrics`, database metrics rendered here).
Never log credential values, DB URLs, or provider payload bodies.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
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
    """The whole exposition: this deployment's process metrics, then the database's.

    ``/metrics`` (for Prometheus) and ``/api/runtime/metrics`` (the JSON-wrapped copy the
    Runtime page reads) both render this. The session's pool is published first, so the
    pool gauges are current even on a process that has served no request yet.
    """

    from eurogas_nexus.application import process_metrics

    pool = getattr(session.get_bind(), "pool", None)
    if pool is not None:
        process_metrics.observe_pools([pool], force=True)
    return process_metrics.render() + database_metric_text(session, now_utc=now_utc)


#: Freshness states that mean "beyond the source's stale rule".
_STALE_STATES = frozenset({"STALE", "MISSING"})
#: Job outcomes counted in the last-hour window.
_JOB_WINDOW = timedelta(hours=1)
#: Market quotes older than this are not read for the feed metrics (index range scan).
_FEED_WINDOW = timedelta(days=2)
_ACTIVE_JOB_STATES = ("QUEUED", "RUNNING", "WAITING_FOR_INPUT")


def _label(value: object) -> str:
    text = str(value)
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _number(value: float | int) -> str:
    if value == float("inf"):
        return "+Inf"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".") if value == value else "NaN"
    return str(int(value))


class _Family:
    """One metric family: HELP, TYPE and its samples."""

    def __init__(self, lines: list[str], name: str, kind: str, help_text: str) -> None:
        self.lines = lines
        self.name = name
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")

    def sample(self, value: float | int, **labels: object) -> None:
        if labels:
            rendered = ",".join(f'{key}="{_label(item)}"' for key, item in labels.items())
            self.lines.append(f"{self.name}{{{rendered}}} {_number(value)}")
        else:
            self.lines.append(f"{self.name} {_number(value)}")


def _age_seconds(now: datetime, value: datetime | None) -> float | None:
    from eurogas_nexus.domain.dataops.contracts import as_utc

    if value is None:
        return None
    return max(0.0, (now - as_utc(value)).total_seconds())


def database_metric_text(session, *, now_utc: datetime | None = None) -> str:
    """Scrape-time metrics read from the database (identical whichever worker answers).

    Aggregates only: no family loads a whole table (the earlier exporter read every
    ingestion run on every scrape). Each collector runs on its own; one that fails reports
    ``eurogas_metrics_collector_up{collector=...} 0`` and the scrape still succeeds.
    """

    from eurogas_nexus.domain.dataops.contracts import as_utc

    now = as_utc(now_utc or datetime.now(UTC))
    lines: list[str] = []
    status: dict[str, int] = {}
    for name, collector in (
        ("ingestion", _ingestion_lines),
        ("sources", _source_lines),
        ("scheduler", _scheduler_lines),
        ("jobs", _job_lines),
        ("feed", _feed_lines),
        ("market_events", _market_event_lines),
    ):
        block: list[str] = []
        try:
            collector(session, now, block)
        except Exception:  # noqa: BLE001 - one failing table must not lose the scrape
            status[name] = 0
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
            continue
        status[name] = 1
        lines.extend(block)
    up = _Family(
        lines,
        "eurogas_metrics_collector_up",
        "gauge",
        "1 when the named database collector answered at this scrape.",
    )
    for name, value in status.items():
        up.sample(value, collector=name)
    lines.append("")
    return "\n".join(lines)


def _ingestion_lines(session, now: datetime, lines: list[str]) -> None:
    from sqlalchemy import func, select

    from eurogas_nexus.db.models import IngestionRunRecord
    from eurogas_nexus.domain.dataops.run_status import is_failed_run_status

    rows = session.execute(
        select(
            IngestionRunRecord.status,
            func.count(),
            func.coalesce(func.sum(IngestionRunRecord.rows_received), 0),
            func.coalesce(func.sum(IngestionRunRecord.rows_rejected), 0),
        ).group_by(IngestionRunRecord.status)
    ).all()
    total = sum(int(row[1]) for row in rows)
    failed = sum(int(row[1]) for row in rows if is_failed_run_status(row[0]))
    _Family(
        lines, "eurogas_ingestion_runs_total", "counter", "Total persisted ingestion runs."
    ).sample(total)
    _Family(
        lines,
        "eurogas_ingestion_failures_total",
        "counter",
        "Persisted ingestion runs classified as failed.",
    ).sample(failed)
    _Family(
        lines, "eurogas_source_rows_received_total", "counter", "Rows received by source."
    ).sample(sum(int(row[2] or 0) for row in rows))
    _Family(
        lines, "eurogas_source_rows_rejected_total", "counter", "Rows rejected by source."
    ).sample(sum(int(row[3] or 0) for row in rows))

    recent = session.execute(
        select(IngestionRunRecord.source_id, IngestionRunRecord.status, func.count())
        .where(IngestionRunRecord.started_at_utc >= now - _JOB_WINDOW)
        .group_by(IngestionRunRecord.source_id, IngestionRunRecord.status)
    ).all()
    family = _Family(
        lines,
        "eurogas_ingestion_failures_last_hour",
        "gauge",
        "Ingestion runs started in the last hour that failed, by source.",
    )
    failures: dict[str, int] = {}
    for source_id, run_status, count in recent:
        if source_id and is_failed_run_status(run_status):
            failures[str(source_id)] = failures.get(str(source_id), 0) + int(count)
    for source_id, count in sorted(failures.items()):
        family.sample(count, source_id=source_id)


def _source_lines(session, now: datetime, lines: list[str]) -> None:
    from eurogas_nexus.db.models import SourceRuntimeStateRecord
    from eurogas_nexus.domain.dataops.contracts import as_utc

    states = sorted(
        session.query(SourceRuntimeStateRecord).all(), key=lambda state: state.source_id
    )
    enabled = _Family(
        lines,
        "eurogas_source_enabled",
        "gauge",
        "1 when the scheduler runs the source on its schedule.",
    )
    for state in states:
        enabled.sample(1 if state.enabled else 0, source_id=state.source_id)
    failures = _Family(
        lines,
        "eurogas_source_consecutive_failures",
        "gauge",
        "Consecutive failures by source.",
    )
    for state in states:
        failures.sample(int(state.consecutive_failures or 0), source_id=state.source_id)
    # The age is computed now, from the last success, not read from the state row: the row
    # is aged only by a scheduler scan, so a dead scheduler would freeze it as fresh.
    freshness = _Family(
        lines,
        "eurogas_source_freshness_seconds",
        "gauge",
        "Seconds since the source last succeeded (enabled sources that ever succeeded).",
    )
    for state in states:
        age = _age_seconds(now, state.last_success_at_utc) if state.enabled else None
        if age is not None:
            freshness.sample(round(age, 1), source_id=state.source_id)
    stale_after = _Family(
        lines,
        "eurogas_source_stale_after_seconds",
        "gauge",
        "The source's freshness rule: age beyond which it is stale.",
    )
    for state in states:
        policy = state.freshness_policy_json or {}
        minutes = policy.get("stale_after_minutes") if isinstance(policy, dict) else None
        if isinstance(minutes, (int, float)) and minutes > 0:
            stale_after.sample(int(minutes) * 60, source_id=state.source_id)
    stale = _Family(
        lines,
        "eurogas_source_stale",
        "gauge",
        "1 when an enabled source's last freshness evaluation was STALE or MISSING.",
    )
    for state in states:
        stale.sample(
            1 if state.enabled and state.freshness_state in _STALE_STATES else 0,
            source_id=state.source_id,
        )
    overdue = _Family(
        lines,
        "eurogas_source_scheduler_overdue",
        "gauge",
        "1 when a scheduled source is overdue.",
    )
    for state in states:
        late = (
            1
            if state.enabled
            and state.next_run_at_utc is not None
            and as_utc(state.next_run_at_utc) <= now
            else 0
        )
        overdue.sample(late, source_id=state.source_id)
    certification = _Family(
        lines,
        "eurogas_source_certification_state",
        "gauge",
        "Certification gap by source.",
    )
    for state in states:
        gap = 0 if state.certification_state in {"CERTIFIED", "NOT_REQUIRED"} else 1
        certification.sample(gap, source_id=state.source_id)


def _scheduler_lines(session, now: datetime, lines: list[str]) -> None:
    from eurogas_nexus.db.models import (
        DataOperationsHeartbeatRecord,
        StrategyShadowSchedulerHeartbeatRecord,
    )

    dataops = session.get(DataOperationsHeartbeatRecord, "primary")
    shadow = session.get(StrategyShadowSchedulerHeartbeatRecord, "primary")
    age = _Family(
        lines,
        "eurogas_scheduler_heartbeat_age_seconds",
        "gauge",
        "Seconds since the scheduler's last heartbeat (+Inf when it never beat).",
    )
    for name, row in (("dataops", dataops), ("shadow", shadow)):
        value = _age_seconds(now, row.last_heartbeat_at_utc if row else None)
        age.sample(float("inf") if value is None else round(value, 1), scheduler=name)
    scan = _Family(
        lines,
        "eurogas_scheduler_last_scan_age_seconds",
        "gauge",
        "Seconds since the data-operations scheduler last scanned its sources.",
    )
    value = _age_seconds(now, dataops.last_scan_at_utc if dataops else None)
    scan.sample(float("inf") if value is None else round(value, 1), scheduler="dataops")
    _Family(
        lines,
        "eurogas_scheduler_sources_scheduled",
        "gauge",
        "Sources the data-operations scheduler had on a schedule at its last scan.",
    ).sample(int(dataops.sources_scheduled) if dataops else 0)


def _job_lines(session, now: datetime, lines: list[str]) -> None:
    from sqlalchemy import func, select

    from eurogas_nexus.db.models.jobs import JobRecord

    finished = session.execute(
        select(JobRecord.kind, JobRecord.status, func.count())
        .where(JobRecord.finished_at_utc >= now - _JOB_WINDOW)
        .group_by(JobRecord.kind, JobRecord.status)
    ).all()
    family = _Family(
        lines,
        "eurogas_jobs_finished_last_hour",
        "gauge",
        "Jobs that finished in the last hour, by kind and outcome.",
    )
    for kind, outcome, count in sorted(finished, key=lambda row: (str(row[0]), str(row[1]))):
        family.sample(int(count), kind=kind, status=outcome)
    active = session.execute(
        select(JobRecord.kind, func.count())
        .where(JobRecord.status.in_(_ACTIVE_JOB_STATES))
        .group_by(JobRecord.kind)
    ).all()
    family = _Family(
        lines, "eurogas_jobs_active", "gauge", "Jobs queued, running or waiting, by kind."
    )
    for kind, count in sorted(active, key=lambda row: str(row[0])):
        family.sample(int(count), kind=kind)


def _feed_lines(session, now: datetime, lines: list[str]) -> None:
    from sqlalchemy import func, select

    from eurogas_nexus.db.models.market_intelligence import MarketQuoteRecord

    rows = session.execute(
        select(
            MarketQuoteRecord.source_system,
            func.max(MarketQuoteRecord.observed_at_utc),
            func.max(MarketQuoteRecord.received_at_utc),
        )
        .where(MarketQuoteRecord.observed_at_utc >= now - _FEED_WINDOW)
        .group_by(MarketQuoteRecord.source_system)
    ).all()
    rows = sorted(rows, key=lambda row: str(row[0]))
    age = _Family(
        lines,
        "eurogas_feed_last_quote_age_seconds",
        "gauge",
        "Seconds since the newest quote a price feed delivered (feeds seen in two days).",
    )
    for source_system, observed, _received in rows:
        value = _age_seconds(now, observed)
        if value is not None:
            age.sample(round(value, 1), source_system=source_system)
    lag = _Family(
        lines,
        "eurogas_feed_receive_lag_seconds",
        "gauge",
        "Newest receipt minus newest quote time, by feed: how far behind the venue we are.",
    )
    for source_system, observed, received in rows:
        if observed is None or received is None:
            continue
        from eurogas_nexus.domain.dataops.contracts import as_utc

        delay = max(0.0, (as_utc(received) - as_utc(observed)).total_seconds())
        lag.sample(round(delay, 3), source_system=source_system)


def _market_event_lines(session, now: datetime, lines: list[str]) -> None:
    from sqlalchemy import func, select

    from eurogas_nexus.db.models.market_events import MarketEventDeliveryRecord

    rows = session.execute(
        select(
            MarketEventDeliveryRecord.consumer,
            MarketEventDeliveryRecord.status,
            func.count(),
            func.min(MarketEventDeliveryRecord.available_at_utc),
        )
        .where(MarketEventDeliveryRecord.status.in_(("pending", "failed", "dead")))
        .group_by(MarketEventDeliveryRecord.consumer, MarketEventDeliveryRecord.status)
    ).all()
    backlog: dict[str, int] = {}
    oldest: dict[str, float] = {}
    dead: dict[str, int] = {}
    for consumer, delivery_status, count, first_due in rows:
        key = str(consumer)
        if delivery_status == "dead":
            dead[key] = dead.get(key, 0) + int(count)
            continue
        backlog[key] = backlog.get(key, 0) + int(count)
        value = _age_seconds(now, first_due)
        if value is not None:
            oldest[key] = max(oldest.get(key, 0.0), value)
    family = _Family(
        lines,
        "eurogas_market_events_backlog",
        "gauge",
        "Market-event deliveries waiting for a consumer (pending or to retry).",
    )
    for consumer, count in sorted(backlog.items()):
        family.sample(count, consumer=consumer)
    family = _Family(
        lines,
        "eurogas_market_events_oldest_due_age_seconds",
        "gauge",
        "Age of the oldest due market-event delivery: the outbox lag, by consumer.",
    )
    for consumer, value in sorted(oldest.items()):
        family.sample(round(value, 1), consumer=consumer)
    family = _Family(
        lines,
        "eurogas_market_events_dead",
        "gauge",
        "Market-event deliveries that gave up after their retries, by consumer.",
    )
    for consumer, count in sorted(dead.items()):
        family.sample(count, consumer=consumer)
