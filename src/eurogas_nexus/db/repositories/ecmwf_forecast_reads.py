"""Bounded read-only retrieval of persisted ECMWF forecast observations.

The caller must authorize source, series and entity access before calling this
module.  It grants no authorization and performs no write.  Every matching row
revision is returned within the explicit budget; this layer does not select a
latest vintage or revision.  The application bridge performs that selection
globally over the returned rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.research import ForecastObservationRecord

SOURCE_SYSTEM = "ECMWF_OPEN_DATA"
MODEL_PROVIDER = "ECMWF"
QUALITY_STATE = "FORECAST"
CANONICAL_UNIT = "degC"
MAX_LIMIT = 256
MAX_IDENTIFIERS = 256
MAX_SERIES_ID_LENGTH = 160
MAX_ENTITY_ID_LENGTH = 128
MAX_VALID_WINDOW = timedelta(days=32)


class EcmwfForecastReadError(RuntimeError):
    """Base typed refusal for bounded ECMWF forecast retrieval."""


class EcmwfForecastReadValidationError(EcmwfForecastReadError, ValueError):
    """The request is unbounded, ambiguous or not explicitly UTC-aware."""


class EcmwfForecastReadOverflowError(EcmwfForecastReadError):
    """More rows match than the explicit limit; refusing to truncate."""


def _identifiers(
    values: Sequence[str] | None,
    *,
    name: str,
    max_length: int,
) -> tuple[str, ...]:
    if (
        values is None
        or isinstance(values, (str, bytes))
        or not isinstance(values, Sequence)
    ):
        raise EcmwfForecastReadValidationError(
            f"{name} must be an explicit sequence of identifiers"
        )
    items = tuple(values)
    if not items:
        raise EcmwfForecastReadValidationError(f"{name} must not be empty")
    if len(items) > MAX_IDENTIFIERS:
        raise EcmwfForecastReadValidationError(
            f"{name} exceeds the bound of {MAX_IDENTIFIERS} identifiers"
        )
    if any(
        not isinstance(value, str) or not value.strip() or len(value) > max_length
        for value in items
    ):
        raise EcmwfForecastReadValidationError(
            f"{name} contains an empty, non-string or overlong identifier"
        )
    return tuple(dict.fromkeys(items))


def _utc(value: datetime, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise EcmwfForecastReadValidationError(
            f"{name} must be a timezone-aware UTC datetime"
        )
    return value.astimezone(UTC)


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EcmwfForecastReadValidationError("limit must be an integer")
    if not 1 <= value <= MAX_LIMIT:
        raise EcmwfForecastReadValidationError(
            f"limit must be between 1 and {MAX_LIMIT}"
        )
    return value


def read_ecmwf_forecasts(
    session: Session,
    explicit_series_ids: Sequence[str],
    entity_ids: Sequence[str],
    prediction_origin: datetime,
    valid_from: datetime,
    valid_to: datetime,
    limit: int,
) -> list[ForecastObservationRecord]:
    """Read eligible persisted ECMWF rows without truncation or mutation.

    The caller must already have authorized the source, the explicit series and
    the explicit entities; this function is not an authorization grant.  It
    returns the actual read-only ORM rows for the caller's projection and does
    not flush pending work, rewrite availability or choose a latest vintage.

    Only ``forecast_valid_start`` defines the half-open validity window: a row
    is eligible when ``valid_from <= start < valid_to``.  Future valid times are
    allowed; ``forecast_valid_end`` is neither inspected nor reinterpreted as a
    period or availability boundary.
    """

    series_ids = _identifiers(
        explicit_series_ids,
        name="explicit_series_ids",
        max_length=MAX_SERIES_ID_LENGTH,
    )
    selected_entity_ids = _identifiers(
        entity_ids,
        name="entity_ids",
        max_length=MAX_ENTITY_ID_LENGTH,
    )
    origin = _utc(prediction_origin, "prediction_origin")
    start = _utc(valid_from, "valid_from")
    end = _utc(valid_to, "valid_to")
    if end <= start:
        raise EcmwfForecastReadValidationError(
            "valid_to must be after valid_from"
        )
    if end - start > MAX_VALID_WINDOW:
        raise EcmwfForecastReadValidationError(
            "validity window must not exceed 32 days"
        )
    bounded_limit = _limit(limit)

    statement = (
        select(ForecastObservationRecord)
        .where(
            ForecastObservationRecord.source_system == SOURCE_SYSTEM,
            ForecastObservationRecord.model_provider == MODEL_PROVIDER,
            ForecastObservationRecord.quality_state == QUALITY_STATE,
            ForecastObservationRecord.unit == CANONICAL_UNIT,
            ForecastObservationRecord.series_id.in_(series_ids),
            ForecastObservationRecord.entity_id.in_(selected_entity_ids),
            ForecastObservationRecord.forecast_issued_at <= origin,
            ForecastObservationRecord.available_at_utc <= origin,
            ForecastObservationRecord.forecast_valid_start >= start,
            ForecastObservationRecord.forecast_valid_start < end,
        )
        .order_by(
            ForecastObservationRecord.forecast_issued_at,
            ForecastObservationRecord.forecast_valid_start,
            ForecastObservationRecord.available_at_utc,
            ForecastObservationRecord.forecast_observation_id,
        )
        .limit(bounded_limit + 1)
    )
    with session.no_autoflush:
        rows = list(session.scalars(statement))
    if len(rows) > bounded_limit:
        raise EcmwfForecastReadOverflowError(
            f"ECMWF forecast read matched more than {bounded_limit} rows; "
            "refusing to truncate the caller's vintage selection"
        )
    return rows
