"""Typed SDK client for ``POST /api/weather/degree-days``.

The backend computes degree days only from caller-supplied point bindings,
region weights, gas days, base temperatures, prediction origin and coverage
policy. This module mirrors that request schema without importing backend code
and without choosing a region, date or base temperature on the caller's behalf.

All exact weights stay :class:`~decimal.Decimal` values and are serialized by
``model_dump(mode="json")`` as decimal strings. The response keeps nullable
temperature and degree-day evidence, explicit per-day coverage, gas-day
boundaries, provenance references, and every warning the backend emits. A
``NOT_READY`` response remains typed and exposes its diagnostics instead of
being converted into zero-valued degree days.

The output is research decision support that requires human review; it is not a
trading, nomination, settlement or delivery instruction.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk._transport import ResponseMeta

WEATHER_DEGREE_DAYS_PATH = "/api/weather/degree-days"

MAX_POINTS = 64
MAX_GAS_DAYS = 7
MAX_HOLD_MINUTES = 10_080

# Frozen calendar versions accepted by the backend. The SDK repeats the
# identifiers instead of importing the backend's gas-day module.
SUPPORTED_GAS_DAY_CALENDARS = (
    "EU-CAM-2025",
    "EU-CAM-UTC-2025",
    "UK-NBP-LEGACY",
)


class WeatherDegreeDayPointBinding(BaseModel):
    """One explicit persisted-point identity and exact region weight.

    Attributes:
        point_id: Caller-supplied persisted point identifier.
        series_id: Caller-supplied weather series identifier.
        entity_id: Caller-supplied entity identifier.
        location_id: Caller-supplied location identifier.
        region: Caller-supplied region named by the binding.
        weight: Exact decimal weight in ``[0, 1]``; never inferred.
    """

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
        """Refuse non-finite weights before exact summation is attempted."""

        if not value.is_finite():
            raise ValueError("weight must be finite")
        return value


class WeatherDegreeDayRequest(BaseModel):
    """Explicit weights, window, bases, prediction origin and coverage policy.

    The request deliberately has no default prediction origin, gas-day window,
    base temperature, hold limit or minimum coverage. The optional region is
    only filled from the bindings when every binding names the same region,
    which mirrors the backend's explicit-binding rule.
    """

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
        """Require an explicit offset and normalize the origin to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("prediction_origin must include a UTC offset")
        return value.astimezone(UTC)

    @field_validator("gas_day_calendar")
    @classmethod
    def _approved_calendar(cls, value: str) -> str:
        """Refuse a calendar version the backend does not support."""

        if value not in SUPPORTED_GAS_DAY_CALENDARS:
            raise ValueError("gas_day_calendar is not an approved calendar version")
        return value

    @field_validator("gas_days")
    @classmethod
    def _ordered_unique_days(cls, value: list[date]) -> list[date]:
        """Keep the declared gas days unique and deterministic."""

        if len(set(value)) != len(value):
            raise ValueError("gas_days must not contain duplicate dates")
        return sorted(value)

    @model_validator(mode="after")
    def _validate_bindings(self) -> WeatherDegreeDayRequest:
        """Validate the explicit binding set and exact weight total."""

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
        return self


class _StrictResponseModel(BaseModel):
    """Response core with no silent absorption of unknown fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegionLocationWeight(_StrictResponseModel):
    """One exact location weight echoed by the backend.

    Attributes:
        location_id: Location the weight applies to.
        weight: Exact decimal weight, serialized as a string on the wire.
    """

    location_id: str
    weight: Decimal


class ForecastVintageRef(_StrictResponseModel):
    """Selected forecast vintage that supplied the temperature evidence.

    Attributes:
        provider: Forecast provider identifier.
        model: Forecast model identifier.
        run_id: Provider run identifier.
        issued_at: Time at which the vintage was issued.
    """

    provider: str
    model: str
    run_id: str
    issued_at: datetime


class DegreeDayFeaturePolicy(_StrictResponseModel):
    """Actual feature policy used by the backend computation.

    Attributes:
        region: Region named by the request bindings.
        heating_base_c: Heating base temperature in Celsius.
        cooling_base_c: Cooling base temperature in Celsius.
        max_gap_minutes: Largest allowed hold gap in minutes.
        min_covered_fraction: Required daily coverage fraction.
        location_weights: Exact location weights used by the policy.
        gas_day_calendar: Explicit gas-day calendar version.
        temporal_method: Temporal derivation method.
        method_version: Backend degree-day method version.
    """

    region: str
    heating_base_c: float
    cooling_base_c: float
    max_gap_minutes: int
    min_covered_fraction: float
    location_weights: list[RegionLocationWeight] = Field(default_factory=list)
    gas_day_calendar: str
    temporal_method: str
    method_version: str


class DailyLocationCoverage(_StrictResponseModel):
    """Per-location coverage and degree-day evidence for one gas day.

    Null temperature and degree-day fields mean missing coverage; they are
    never converted into zero. ``weight`` remains an exact decimal value.
    """

    location_id: str
    weight: Decimal
    covered_fraction: float
    largest_gap_seconds: float
    available_at: datetime | None = None
    mean_temperature_c: float | None = None
    daily_mean_hdd: float | None = None
    daily_mean_cdd: float | None = None
    heating_degree_day_integral: float | None = None
    cooling_degree_day_integral: float | None = None
    complete: bool
    missing_reason: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class DailyDegreeDay(_StrictResponseModel):
    """One gas day with nullable daily-mean and time-integral outputs.

    Attributes:
        gas_day: Gas-day date.
        gas_day_start_utc: Inclusive gas-day start in UTC.
        gas_day_end_utc: Exclusive gas-day end in UTC.
        duration_hours: Explicit gas-day duration in hours.
        daily_mean_temperature_c: Daily mean temperature, or null when missing.
        daily_mean_hdd: Daily mean heating degree days, or null when missing.
        daily_mean_cdd: Daily mean cooling degree days, or null when missing.
        time_integral_heating_degree_day: Heating time integral, or null.
        time_integral_cooling_degree_day: Cooling time integral, or null.
        covered_fraction: Fraction of the gas day with usable evidence.
        coverage_complete: Whether coverage met the requested policy.
        missing_reason: Stable reason when coverage is incomplete.
        available_at: Time the evidence became available, or null.
        source_refs: Provenance references for this gas day.
        locations: Per-location coverage and evidence.
    """

    gas_day: date
    gas_day_start_utc: datetime
    gas_day_end_utc: datetime
    duration_hours: float
    daily_mean_temperature_c: float | None = None
    daily_mean_hdd: float | None = None
    daily_mean_cdd: float | None = None
    time_integral_heating_degree_day: float | None = None
    time_integral_cooling_degree_day: float | None = None
    covered_fraction: float
    coverage_complete: bool
    missing_reason: str | None = None
    available_at: datetime | None = None
    source_refs: list[str] = Field(default_factory=list)
    locations: list[DailyLocationCoverage] = Field(default_factory=list)

    @property
    def gas_day_boundaries(self) -> tuple[datetime, datetime]:
        """Return the explicit inclusive/exclusive gas-day boundaries."""

        return (self.gas_day_start_utc, self.gas_day_end_utc)


class WeatherDegreeDayDiagnostic(_StrictResponseModel):
    """One explicit NOT_READY diagnostic from the weather-input bridge.

    Attributes:
        code: Stable diagnostic code.
        detail: Human-readable diagnostic detail.
        location_id: Location concerned by the diagnostic, if any.
        valid_at_utc: Evidence time concerned by the diagnostic, if any.
    """

    code: str
    detail: str
    location_id: str | None = None
    valid_at_utc: datetime | None = None


class WeatherDegreeDayMeta(ResponseMeta):
    """Response metadata, including the policy hash and all emitted warnings.

    Unknown metadata keys are preserved because the backend meta object is the
    open-ended envelope field. Core result rows remain strict.
    """

    model_config = ConfigDict(extra="allow")

    status: Literal["READY", "NOT_READY"]
    attribution: str
    feature_policy_hash: str
    prediction_origin: datetime
    gas_days: list[date]
    max_hold_minutes: int
    query_limit: int
    selected_forecast_vintage: ForecastVintageRef | None = None

    @property
    def policy_hash(self) -> str:
        """Return the backend feature-policy hash under its short name."""

        return self.feature_policy_hash

    @property
    def caller_weights(self) -> bool:
        """Return whether the backend warned that weights are caller-defined."""

        return "CALLER_DEFINED_REGION_WEIGHTS" in self.warnings

    @property
    def left_hold_warnings(self) -> list[str]:
        """Return the retained left-hold approximation warnings."""

        return [
            warning for warning in self.warnings if warning == "LEFT_HOLD_APPROXIMATION"
        ]


class WeatherDegreeDayResult(_StrictResponseModel):
    """Typed READY data or typed NOT_READY diagnostics.

    READY payloads carry the computed daily rows and explicit policy. NOT_READY
    payloads carry ``status='NOT_READY'`` and diagnostics without fabricated
    degree-day values.
    """

    status: Literal["READY", "NOT_READY"] | None = None
    diagnostics: list[WeatherDegreeDayDiagnostic] = Field(default_factory=list)
    region: str | None = None
    input_type: str | None = None
    prediction_origin: datetime | None = None
    gas_day_calendar: str | None = None
    feature_policy: DegreeDayFeaturePolicy | None = None
    heating_base_c: float | None = None
    cooling_base_c: float | None = None
    max_gap_seconds: float | None = None
    min_covered_fraction: float | None = None
    selected_vintage: ForecastVintageRef | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "selected_vintage", "selected_forecast_vintage"
        ),
    )
    method_version: str | None = None
    daily: list[DailyDegreeDay] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _infer_missing_status(self) -> WeatherDegreeDayResult:
        """Expose READY when the backend omits status on a computed payload."""

        if self.status is None:
            self.status = (
                "READY" if self.daily or self.region is not None else "NOT_READY"
            )
        return self


class WeatherDegreeDayEnvelope(_StrictResponseModel):
    """Typed ``data``/``meta`` envelope returned by the degree-day endpoint."""

    data: WeatherDegreeDayResult
    meta: WeatherDegreeDayMeta

    @model_validator(mode="after")
    def _align_status(self) -> WeatherDegreeDayEnvelope:
        """Keep the data status aligned with the authoritative meta status."""

        self.data.status = self.meta.status
        return self

    @property
    def status(self) -> Literal["READY", "NOT_READY"]:
        """Return the authoritative READY/NOT_READY status."""

        return self.meta.status

    @property
    def diagnostics(self) -> list[WeatherDegreeDayDiagnostic]:
        """Return diagnostics from a NOT_READY payload."""

        return self.data.diagnostics

    @property
    def policy_hash(self) -> str:
        """Return the backend feature-policy hash."""

        return self.meta.feature_policy_hash

    @property
    def feature_policy_hash(self) -> str:
        """Return the backend feature-policy hash under its wire name."""

        return self.meta.feature_policy_hash

    @property
    def daily(self) -> list[DailyDegreeDay]:
        """Return the computed daily rows (empty when not ready)."""

        return self.data.daily


def compute_weather_degree_days(
    base_url: str,
    request: WeatherDegreeDayRequest,
) -> WeatherDegreeDayEnvelope:
    """Compute caller-weighted degree days via the public weather endpoint.

    The SDK posts the explicit request without adding a region, date or base
    temperature and without performing local degree-day arithmetic. ``READY``
    and ``NOT_READY`` responses both return as the typed envelope; HTTP refusals
    propagate unchanged from ``raise_for_status``.

    Args:
        base_url: Operator-provided backend base URL.
        request: Validated explicit request with exact Decimal weights.

    Returns:
        Typed envelope with daily degree days, coverage, provenance and metadata.

    Raises:
        httpx.HTTPStatusError: When the backend refuses the request or is not
            ready to serve it.
        pydantic.ValidationError: When the response violates the public schema.
    """

    response = _http.post(
        f"{base_url.rstrip('/')}/api/weather/degree-days",
        json=request.model_dump(mode="json"),
        timeout=30,
    )
    response.raise_for_status()
    return WeatherDegreeDayEnvelope.model_validate_json(response.content)


# Explicit aliases keep the singular/plural domain spelling discoverable without
# changing the canonical names above.
WeatherDegreeDaysEnvelope = WeatherDegreeDayEnvelope
WeatherDegreeDaysResult = WeatherDegreeDayResult
WeatherDegreeDaysMeta = WeatherDegreeDayMeta
WeatherDegreeDayResponse = WeatherDegreeDayEnvelope
DegreeDayEnvelope = WeatherDegreeDayEnvelope
DegreeDayResult = WeatherDegreeDayResult
DegreeDayMeta = WeatherDegreeDayMeta

__all__ = [
    "MAX_GAS_DAYS",
    "MAX_HOLD_MINUTES",
    "MAX_POINTS",
    "SUPPORTED_GAS_DAY_CALENDARS",
    "WEATHER_DEGREE_DAYS_PATH",
    "DailyDegreeDay",
    "DailyLocationCoverage",
    "DegreeDayEnvelope",
    "DegreeDayFeaturePolicy",
    "DegreeDayMeta",
    "DegreeDayResult",
    "ForecastVintageRef",
    "RegionLocationWeight",
    "WeatherDegreeDayDiagnostic",
    "WeatherDegreeDayEnvelope",
    "WeatherDegreeDayMeta",
    "WeatherDegreeDayPointBinding",
    "WeatherDegreeDayRequest",
    "WeatherDegreeDayResponse",
    "WeatherDegreeDayResult",
    "WeatherDegreeDaysEnvelope",
    "WeatherDegreeDaysMeta",
    "WeatherDegreeDaysResult",
    "compute_weather_degree_days",
]
