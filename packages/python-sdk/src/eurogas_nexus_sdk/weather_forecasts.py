"""SDK-owned point-in-time ECMWF grid forecast DTO contracts.

These models deliberately mirror the backend API contract without importing
backend modules. They carry one forecast instant per reading: no interval
aggregation, station identity, persistence, routing or fetch behaviour belongs
here.
"""

from __future__ import annotations

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
