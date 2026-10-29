"""SDK-owned point-in-time ECMWF grid forecast DTO contracts.

These models deliberately mirror the backend API contract without importing
backend modules. They carry one forecast instant per reading: no interval
aggregation, station identity, persistence or routing belongs here. The fetch
helper only validates query bounds and delegates transport to the SDK HTTP
layer.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from eurogas_nexus_sdk import _http

_STRICT_FROZEN = ConfigDict(strict=True, frozen=True, extra="forbid")
_NonEmptyStr = Annotated[str, Field(min_length=1)]
_Sha256Hex = Annotated[
    str,
    Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]
_FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
_Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
_Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


def _freeze_string_sequence(value: object) -> object:
    """Accept a JSON-style list, then store it as an immutable tuple."""
    return tuple(value) if isinstance(value, list) else value


_FrozenStrings = Annotated[
    tuple[_NonEmptyStr, ...], BeforeValidator(_freeze_string_sequence)
]


class ForecastPointReading(BaseModel):
    """One immutable ECMWF forecast-grid reading at a single instant."""

    model_config = _STRICT_FROZEN

    observation_id: _NonEmptyStr
    point_id: _NonEmptyStr
    series_id: _NonEmptyStr
    entity_id: _NonEmptyStr
    source_system: Literal["ECMWF_OPEN_DATA"]
    provider: Literal["ECMWF"]
    model: _NonEmptyStr
    run_id: _NonEmptyStr
    issued_at_utc: AwareDatetime
    valid_at_utc: AwareDatetime
    available_at_utc: AwareDatetime
    temperature_c: _FiniteFloat
    unit: Literal["degC"]
    raw_grib_sha256: _Sha256Hex
    record_content_sha256: _Sha256Hex
    requested_latitude: _Latitude
    requested_longitude: _Longitude
    grid_latitude: _Latitude
    grid_longitude: _Longitude

    @field_validator("issued_at_utc", "valid_at_utc", "available_at_utc")
    @classmethod
    def _explicit_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be explicit UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _receipt_not_before_issue(self) -> ForecastPointReading:
        if self.valid_at_utc < self.issued_at_utc:
            raise ValueError("valid_at_utc must not precede issued_at_utc")
        if self.available_at_utc < self.issued_at_utc:
            raise ValueError("available_at_utc must not precede issued_at_utc")
        return self


class ForecastReadMeta(BaseModel):
    """Immutable envelope metadata for the research-only forecast surface."""

    model_config = _STRICT_FROZEN

    research_only: Literal[True] = True
    source_references: _FrozenStrings = Field(min_length=1)
    warnings: _FrozenStrings = ()
    attribution: _NonEmptyStr
    point_kind: Literal["FORECAST_GRID_POINT"] = "FORECAST_GRID_POINT"


class ForecastReadEnvelope(BaseModel):
    """Bounded response envelope for forecast-grid point readings."""

    model_config = _STRICT_FROZEN

    data: list[ForecastPointReading] = Field(max_length=256)
    meta: ForecastReadMeta


_MAX_IDENTIFIERS = 256
_MAX_LIMIT = 256
_MAX_FORECAST_WINDOW = timedelta(days=32)


def fetch_weather_forecasts(
    base_url: str,
    *,
    series_ids: Iterable[str],
    entity_ids: Iterable[str],
    prediction_origin: datetime,
    valid_from: datetime,
    valid_to: datetime,
    limit: int = 100,
) -> ForecastReadEnvelope:
    """Fetch bounded ECMWF forecast points from ``/api/weather/forecasts``.

    All times are explicit UTC instants; the window is inclusive of the values
    supplied and must be positive and no longer than 32 days. The response is
    parsed from its raw JSON bytes so the strict datetime contract is applied by
    Pydantic rather than the standard JSON decoder.

    Args:
        base_url: Base URL of the backend server.
        series_ids: Forecast series identifiers to read (1-256, non-empty).
        entity_ids: Entity identifiers to read (1-256, non-empty).
        prediction_origin: Forecast run origin as an explicit-UTC datetime.
        valid_from: First valid instant of the forecast window.
        valid_to: Last valid instant of the forecast window.
        limit: Maximum number of readings to return (1-256).

    Returns:
        The typed forecast envelope, including its full metadata.

    Raises:
        ValueError: If any argument is invalid; no HTTP request is made.
        httpx.HTTPStatusError: If the backend rejects the request.
    """

    series = _identifiers(series_ids, "series_ids")
    entities = _identifiers(entity_ids, "entity_ids")
    origin = _utc(prediction_origin, "prediction_origin")
    start = _utc(valid_from, "valid_from")
    end = _utc(valid_to, "valid_to")

    if end <= start:
        raise ValueError("valid_to must follow valid_from")
    if end - start > _MAX_FORECAST_WINDOW:
        raise ValueError("forecast window must not exceed 32 days")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= _MAX_LIMIT
    ):
        raise ValueError("limit must be an integer between 1 and 256")

    response = _http.get(
        f"{base_url}/api/weather/forecasts",
        params={
            "series_ids": list(series),
            "entity_ids": list(entities),
            "prediction_origin": origin.isoformat(),
            "valid_from": start.isoformat(),
            "valid_to": end.isoformat(),
            "limit": limit,
        },
        timeout=10,
    )
    response.raise_for_status()
    return ForecastReadEnvelope.model_validate_json(response.content)


def _identifiers(values: Iterable[str], name: str) -> tuple[str, ...]:
    """Normalize and validate a bounded collection of non-empty identifiers."""

    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a collection of identifiers")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} must be a collection of identifiers") from exc

    if not items:
        raise ValueError(f"{name} must not be empty")
    if len(items) > _MAX_IDENTIFIERS:
        raise ValueError(f"{name} must contain at most 256 identifiers")

    normalized: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"{name} identifiers must be strings")
        identifier = item.strip()
        if not identifier:
            raise ValueError(f"{name} identifiers must be non-empty")
        normalized.append(identifier)
    return tuple(normalized)


def _utc(value: datetime, name: str) -> datetime:
    """Require an aware datetime and normalize it to explicit UTC."""

    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)
