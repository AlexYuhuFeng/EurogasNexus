"""Strict request schema for caller-weighted degree-day computation.

Every point identity and exact Decimal weight is caller-supplied. No region,
station, climate value or coverage policy is inferred or defaulted.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

MAX_POINTS = 64
MAX_GAS_DAYS = 7
MAX_HOLD_MINUTES = 10_080


class WeatherDegreeDayPointBinding(BaseModel):
    """One explicit persisted-point identity and exact region weight."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    point_id: str = Field(min_length=1, max_length=160)
    series_id: str = Field(min_length=1, max_length=160)
    entity_id: str = Field(min_length=1, max_length=128)
    location_id: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=1, max_length=160)
    weight: Decimal = Field(
        ge=Decimal("0"), le=Decimal("1"), max_digits=18, decimal_places=12
    )

    @field_validator("weight")
    @classmethod
    def _finite_weight(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("weight must be finite")
        return value


class WeatherDegreeDayRequest(BaseModel):
    """Explicit region weights, window, bases, calendar and coverage policy."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )

    region: str | None = Field(default=None, min_length=1, max_length=160)
    point_bindings: list[WeatherDegreeDayPointBinding] = Field(
        min_length=1,
        max_length=MAX_POINTS,
        validation_alias=AliasChoices("point_bindings", "bindings"),
    )
    gas_days: list[date] = Field(min_length=1, max_length=MAX_GAS_DAYS)
    prediction_origin: datetime
    heating_base_c: float = Field(ge=-50.0, le=50.0)
    cooling_base_c: float = Field(ge=-50.0, le=50.0)
    gas_day_calendar: str = Field(
        min_length=1,
        max_length=64,
        validation_alias=AliasChoices("gas_day_calendar", "calendar"),
    )
    max_hold_minutes: int = Field(ge=1, le=MAX_HOLD_MINUTES)
    min_covered_fraction: float = Field(ge=0.0, le=1.0)

    @field_validator("prediction_origin")
    @classmethod
    def _aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("prediction_origin must include a UTC offset")
        return value.astimezone(UTC)

    @field_validator("gas_days")
    @classmethod
    def _ordered_unique_days(cls, value: list[date]) -> list[date]:
        if len(set(value)) != len(value):
            raise ValueError("gas_days must not contain duplicate dates")
        return sorted(value)

    @model_validator(mode="after")
    def _validate_bindings(self) -> WeatherDegreeDayRequest:
        bindings = self.point_bindings
        regions = {binding.region for binding in bindings}
        if self.region is None:
            if len(regions) != 1:
                raise ValueError("point bindings must name exactly one region")
            self.region = next(iter(regions))
        elif any(binding.region != self.region for binding in bindings):
            raise ValueError("every binding region must equal the request region")
        if len({binding.point_id for binding in bindings}) != len(bindings):
            raise ValueError("point_id values must be unique")
        if len({binding.location_id for binding in bindings}) != len(bindings):
            raise ValueError("location_id values must be unique")
        if sum((binding.weight for binding in bindings), Decimal("0")) != Decimal("1"):
            raise ValueError("point binding weights must sum exactly to 1")
        try:
            gas_day_start_for_date(self.gas_days[0], self.gas_day_calendar)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "gas_day_calendar is not an approved calendar version"
            ) from exc
        return self
