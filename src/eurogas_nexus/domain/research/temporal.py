"""Point-in-time temporal semantics for research datasets.

``observed_at``, ``available_at``, and ``ingested_at`` are different facts and
must never be conflated. Historical eligibility is driven by ``available_at``,
never by ``created_at`` or a latest-row query.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol


class ObservationKind(StrEnum):
    """What kind of value an observation carries."""

    ACTUAL = "ACTUAL"
    FORECAST = "FORECAST"
    ASSESSMENT = "ASSESSMENT"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    SIMULATED = "SIMULATED"


class TemporalIntegrityState(StrEnum):
    """How well a source reconstructs historical availability."""

    TEMPORAL_VERIFIED = "TEMPORAL_VERIFIED"
    TEMPORAL_APPROXIMATE = "TEMPORAL_APPROXIMATE"
    TEMPORAL_INSUFFICIENT = "TEMPORAL_INSUFFICIENT"


class DatasetMode(StrEnum):
    """Build policy for temporal-insufficient inputs."""

    STRICT = "STRICT"
    EXPLORATORY = "EXPLORATORY"


@dataclass(frozen=True)
class DatasetPointInTimePolicy:
    """One versioned point-in-time policy."""

    policy_id: str = "pit-policy/v1"
    cutoff_semantics: str = "available_at_lt_or_eq_cutoff"
    allow_forecast_vintages: bool = True
    allow_simulated: bool = False
    mode: DatasetMode = DatasetMode.STRICT

    def version(self) -> str:
        return self.policy_id


class TemporalRecord(Protocol):
    """Structural temporal contract used by the point-in-time engine."""

    observed_at: datetime
    available_at: datetime | None
    ingested_at: datetime | None
    temporal_integrity: TemporalIntegrityState | str | None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def effective_available_at(record: TemporalRecord) -> datetime | None:
    """Resolve the earliest legitimate availability timestamp for a record."""

    return _as_utc(record.available_at) if record.available_at is not None else None


def as_of_eligible(
    record: TemporalRecord,
    cutoff: datetime,
    *,
    policy: DatasetPointInTimePolicy | None = None,
) -> tuple[bool, str | None]:
    """Return whether ``record`` was legitimately visible at ``cutoff``.

    Rules:
    - ``available_at <= cutoff`` is the only positive proof.
    - ``ingested_at`` alone is never positive proof; it is ingestion time.
    - ``observed_at`` alone is not positive proof for historical rows.
    - For exploration only, a missing available_at may be approximated from
      observed_at when the source declares TEMPORAL_APPROXIMATE; STRICT mode
      rejects it.
    """

    resolved_policy = policy or DatasetPointInTimePolicy()
    cutoff_utc = _as_utc(cutoff)
    if record.available_at is not None:
        if _as_utc(record.available_at) <= cutoff_utc:
            return True, None
        return False, "OBSERVATION_AVAILABLE_AFTER_CUTOFF"
    if resolved_policy.mode is DatasetMode.EXPLORATORY and (
        str(record.temporal_integrity).upper() in {"TEMPORAL_APPROXIMATE", "TEMPORAL_INSUFFICIENT"}
    ):
        observed = _as_utc(record.observed_at)
        if observed <= cutoff_utc:
            return True, "OBSERVATION_AVAILABILITY_APPROXIMATED_FROM_OBSERVED_AT"
    return False, "OBSERVATION_AVAILABILITY_UNKNOWN"


def forecast_vintage_at(
    *,
    forecasts: list[TemporalRecord],
    cutoff: datetime,
    valid_start: datetime | None = None,
    valid_end: datetime | None = None,
) -> TemporalRecord | None:
    """Select the latest forecast vintage legitimately available at cutoff.

    The latest actual/realized row must never replace an historical forecast
    vintage. Callers must keep vintages separate (ForecastObservation).
    """

    cutoff_utc = _as_utc(cutoff)
    eligible = []
    for forecast in forecasts:
        available = effective_available_at(forecast)
        if available is None or available > cutoff_utc:
            continue
        if valid_start is not None and _as_utc(valid_start) < available:
            continue
        if valid_end is not None and forecast.observed_at > _as_utc(valid_end):
            continue
        eligible.append(forecast)
    if not eligible:
        return None
    epoch = datetime.min.replace(tzinfo=UTC)
    return max(
        eligible,
        key=lambda item: (
            _as_utc(item.available_at) if item.available_at is not None else epoch,
            _as_utc(item.observed_at),
        ),
    )


def as_of_cutoff_for_origin(
    origin: datetime,
    *,
    min_availability_delay_seconds: int = 0,
) -> datetime:
    """Derive the data cutoff used for a research decision at ``origin``."""

    return _as_utc(origin) - timedelta(seconds=min_availability_delay_seconds)
