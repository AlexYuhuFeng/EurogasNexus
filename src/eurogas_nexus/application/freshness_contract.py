"""The freshness contract: per dataset, what is expected, what arrived and when next (FRESH-01).

One service answers, for every dataset a connector manifest declares:

- **expected**: the schedule the data-operations scheduler runs (cadence and time), the
  publication in words, the receipt thresholds (``FreshnessPolicy``) and the newest
  period's late and stale ages (``DatasetFreshness``), all from the manifest;
- **last received**: the later of first receipt and a provider revision
  (``last_received_column``), measured with the data-quality report's own dataset query;
- **next expected update**: the scheduler's own next run (``source_runtime_states``), or
  what the scheduler would set (``schedule.next_scheduled_instant``) when it has no state yet;
- **state**: ``current``, ``late``, ``stale`` or ``never``; ``manual`` for a register an
  operator keeps (TSO tariffs, DATA-05) and for file imports, templates and model
  services, which have no schedule and raise no freshness alarm.

Receipt age is judged against the source's ``FreshnessPolicy`` as the scheduler's freshness
engine judges it (within ``normal_max_age``: current; within ``stale_after``: late; beyond:
stale). For a weekday-only source (ECB, the rate administrators, EIA) a weekend is not
counted, so Monday morning is not "late" for a Friday fixing. The data-quality report reads
the period thresholds from the same declaration; nothing else holds an age threshold.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from eurogas_nexus.domain.dataops.contracts import (
    MANUAL_REGISTER,
    ScheduleType,
    SourceCalendar,
    SourceDefinition,
    as_utc,
)
from eurogas_nexus.domain.dataops.schedule import next_expected_after, next_scheduled_instant

FRESHNESS_STATES = ("current", "late", "stale", "never", "manual")
#: Integrations nobody fetches on a schedule: no freshness alarm applies to them.
UNSCHEDULED_INTEGRATIONS = frozenset({MANUAL_REGISTER, "file_import", "template", "model_service"})


def counted_age_minutes(
    definition: SourceDefinition, received: datetime, now: datetime
) -> float:
    """Minutes since ``received``; weekend days are left out for a weekday-only source."""

    received, now = as_utc(received), as_utc(now)
    age = max(0.0, (now - received).total_seconds() / 60.0)
    if definition.calendar != SourceCalendar.WEEKDAYS_ONLY:
        return age
    zone = ZoneInfo(definition.schedule.timezone or "UTC")
    start, end = received.astimezone(zone), now.astimezone(zone)
    weekend = 0.0
    day = start.date()
    while day <= end.date():
        if day.weekday() >= 5:
            day_start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
            day_end = day_start + timedelta(days=1)
            overlap = (min(day_end, end) - max(day_start, start)).total_seconds() / 60.0
            weekend += max(0.0, overlap)
        day += timedelta(days=1)
    return max(0.0, age - weekend)


def receipt_state(
    definition: SourceDefinition, last_received: datetime | None, now: datetime
) -> str:
    """``manual``, ``never``, ``current``, ``late`` or ``stale`` for one source's receipt."""

    if definition.integration in UNSCHEDULED_INTEGRATIONS:
        return "manual"
    if last_received is None:
        return "never"
    policy = definition.freshness_policy
    if policy.normal_max_age_minutes <= 0:
        return "manual"  # nothing declared to judge against (model services)
    age = counted_age_minutes(definition, last_received, now)
    if age <= policy.normal_max_age_minutes:
        return "current"
    if age <= policy.stale_after_minutes:
        return "late"
    return "stale"


def next_expected_update(
    definition: SourceDefinition,
    runtime_state: Mapping[str, Any] | None,
    now: datetime,
) -> tuple[datetime | None, str]:
    """When the next update is expected, and on what basis.

    The scheduler's own ``next_run_at_utc`` when it holds the source (``scheduler``); what
    the scheduler would set on first sight (``schedule``); ``None`` with the reason
    otherwise (``scheduler_disabled``, ``not_scheduled``).
    """

    if definition.integration in UNSCHEDULED_INTEGRATIONS or not definition.schedulable:
        return None, "not_scheduled"
    if definition.schedule.schedule_type == ScheduleType.EXTERNAL:
        return None, "not_scheduled"
    if runtime_state is not None:
        if not runtime_state.get("enabled"):
            return None, "scheduler_disabled"
        stored = runtime_state.get("next_run_at_utc")
        if stored:
            moment = stored if isinstance(stored, datetime) else _parse(str(stored))
            if moment is not None:
                return as_utc(moment), "scheduler"
    if definition.calendar == SourceCalendar.WEEKDAYS_ONLY:
        return next_expected_after(definition, now_utc=now), "schedule"
    return next_scheduled_instant(definition, activated_at=now, after=now), "schedule"


def expectation_payload(definition: SourceDefinition, declared: Any | None) -> dict[str, Any]:
    """What the manifest promises, as plain data."""

    schedule = definition.schedule
    payload: dict[str, Any] = {
        "integration": definition.integration,
        "schedule_type": schedule.schedule_type.value,
        "interval_minutes": (
            int(schedule.interval_seconds) // 60 if schedule.interval_seconds else None
        ),
        "daily_at": schedule.daily_at,
        "timezone": schedule.timezone,
        "calendar": definition.calendar.value,
        "normal_max_age_minutes": definition.freshness_policy.normal_max_age_minutes,
        "stale_after_minutes": definition.freshness_policy.stale_after_minutes,
        "publication": "",
        "period_late_hours": None,
        "period_stale_hours": None,
    }
    if declared is not None:
        payload.update(
            publication=declared.publication,
            period_late_hours=declared.period_late_hours,
            period_stale_hours=declared.period_stale_hours,
        )
    return payload


def freshness_rows(
    definitions: tuple[SourceDefinition, ...] | list[SourceDefinition],
    *,
    now: datetime,
    received_by_dataset: Mapping[tuple[str, str], tuple[datetime | None, datetime | None]],
    received_by_source: Mapping[str, datetime | None],
    runtime_states: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One row per declared dataset (or per source when it declares none). Pure."""

    from eurogas_nexus.domain.connectors.registry import connector_manifests

    declared_by_source = {m.source_id: m.dataset_freshness for m in connector_manifests()}
    rows: list[dict[str, Any]] = []
    for definition in definitions:
        declared = declared_by_source.get(definition.source_id) or ()
        next_at, next_basis = next_expected_update(
            definition, runtime_states.get(definition.source_id), now
        )
        items = [(item.dataset, item) for item in declared] or [(None, None)]
        for dataset, item in items:
            if dataset is not None:
                received, period = received_by_dataset.get(
                    (definition.source_id, dataset), (None, None)
                )
            else:
                received, period = received_by_source.get(definition.source_id), None
            state = receipt_state(definition, received, now)
            rows.append(
                {
                    "source_id": definition.source_id,
                    "dataset": dataset or ", ".join(definition.datasets),
                    "expected": expectation_payload(definition, item),
                    "last_received_at_utc": _iso(received),
                    "last_period_at_utc": _iso(period),
                    "next_expected_at_utc": _iso(next_at),
                    "next_expected_basis": next_basis,
                    # The scheduler's next run has passed without a run: it is not running.
                    "next_expected_overdue": next_at is not None and as_utc(next_at) < now,
                    "state": state,
                }
            )
    return rows


def measured_receipts(session) -> dict[tuple[str, str], tuple[datetime | None, datetime | None]]:
    """(source id, dataset) -> (last received, newest period), from the report's queries."""

    from eurogas_nexus.application.data_quality_report import SPECS, last_received

    return {(spec.source_id, spec.dataset): last_received(session, spec) for spec in SPECS}


def freshness_contract(
    session,
    *,
    now: datetime | None = None,
    received_by_source: Mapping[str, datetime | None] | None = None,
    runtime_states: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The freshness contract for every registered source, measured in this store."""

    from eurogas_nexus.domain.dataops.registry import source_definitions

    return freshness_rows(
        source_definitions(),
        now=as_utc(now or datetime.now(UTC)),
        received_by_dataset=measured_receipts(session),
        received_by_source=received_by_source or {},
        runtime_states=runtime_states or {},
    )


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat() if value is not None else None
