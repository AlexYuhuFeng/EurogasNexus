"""Point-in-time weather features and bounded regional gas-demand models.

This module is the pure-domain core between immutable ECMWF forecast vintages and
native-unit regional demand fitting. It deliberately contains no ingestion, API,
storage, scheduler or UI dependency.

The two halves are separate contracts:

* :func:`compute_degree_days` turns explicit, weighted location temperatures into
  named daily-mean HDD/CDD and true-time-integral degree-days. It freezes one
  available forecast vintage, never treats a forecast as an observation, and
  returns ``None`` rather than zero for insufficient coverage.
* :func:`fit_weather_demand_model` fits a calendar/seasonal baseline and a
  weather-plus-calendar ridge candidate on point-in-time rows, compares them on
  expanding daily out-of-sample folds, and returns a research model. Nothing here
  promotes a model, claims real accuracy, converts native units or builds a
  pan-European aggregate.

Demand fitting imports NumPy lazily and only when a candidate model is actually
fitted. NumPy remains a separately reviewed dependency: this module never installs
it, weakens its license gate or substitutes a hand-written solver. Degree-day
calculation itself is pure Python and does not import NumPy.

Physical calculations use binary floating point and are approximate. They are
not financial-exact arithmetic. Invalid, non-finite or implausibly bounded inputs
are refused before calculation.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_start_for_date,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    DemandTargetQuality,
    TargetScope,
    TemperatureDerivationMethod,
    TemperatureInputType,
    WeatherFeature,
)

DEGREE_DAY_METHOD_VERSION = "degree-day-mean-and-integral/v1"
DEMAND_MODEL_METHOD_VERSION = "weather-calendar-ridge/v1"
CALENDAR_FEATURE_METHOD = "annual-harmonic-1-weekday-monday-reference/v1"
BASELINE_METHOD_VERSION = "calendar-month-mean/v1"
RESIDUAL_INTERVAL_METHOD_VERSION = "empirical-heldout-residual-central/v1"

DEGREE_DAY_OUTPUT_NAMES = (
    "DAILY_MEAN_HDD",
    "DAILY_MEAN_CDD",
    "TIME_INTEGRAL_HEATING_DEGREE_DAY",
    "TIME_INTEGRAL_COOLING_DEGREE_DAY",
)

MAX_WEATHER_DAYS = 366
MAX_TEMPERATURE_INTERVALS = 100_000
MAX_TARGET_ROWS = 100_000
MAX_FEATURE_ROWS = 100_000
MAX_FOLDS = 366
MIN_TEMPERATURE_C = -100.0
MAX_TEMPERATURE_C = 70.0
MIN_DEGREE_BASE_C = -50.0
MAX_DEGREE_BASE_C = 50.0
MAX_DEGREE_DAY_VALUE = 10_000.0
MAX_DEMAND_VALUE = 1_000_000_000.0


class WeatherDemandInputError(ValueError):
    """Raised when weather or demand input violates the frozen contract."""


class AmbiguousWeatherInputError(WeatherDemandInputError):
    """Raised when more than one input could legitimately satisfy a selection."""


class SelectionEvidenceUnavailableError(WeatherDemandInputError):
    """Raised when selection or interval evidence is consumed before it exists."""

    code = "SELECTION_EVIDENCE_UNAVAILABLE"


class WeatherPredictionInputError(WeatherDemandInputError):
    """Base refusal for a prediction that cannot be made from the frozen result."""


class MissingWeatherFeatureError(WeatherPredictionInputError):
    """Raised when a weather model is asked to predict without a required column."""

    code = "MISSING_WEATHER_FEATURE"


class NegativeDemandEstimateError(WeatherPredictionInputError):
    """Raised rather than silently clamping a negative native-unit estimate."""

    code = "NEGATIVE_DEMAND_ESTIMATE"


class MissingNumpyError(RuntimeError):
    """Typed failure for the optional, lazily imported NumPy dependency."""

    code = "NUMPY_NOT_INSTALLED"
    dependency = "numpy"

    def __init__(self) -> None:
        super().__init__(
            "NumPy is required for demand fitting. Install the separately reviewed "
            "NumPy lock; this module does not add or install dependencies."
        )


class ValidationBasis(StrEnum):
    """What the out-of-sample evidence actually is."""

    SYNTHETIC_NOT_REAL = "SYNTHETIC_NOT_REAL"
    REALIZED_WEATHER_CALIBRATION = "REALIZED_WEATHER_CALIBRATION"
    GENUINE_FORECAST_VINTAGE_OOS = "GENUINE_FORECAST_VINTAGE_OOS"


class ModelKind(StrEnum):
    """Fitted model family."""

    CALENDAR_BASELINE = "CALENDAR_BASELINE"
    WEATHER_CALENDAR_RIDGE = "WEATHER_CALENDAR_RIDGE"


class ModelSelectionStatus(StrEnum):
    """Measured outcome of baseline-versus-candidate comparison."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    BASELINE_RETAINED = "BASELINE_RETAINED"
    CANDIDATE_SELECTED = "CANDIDATE_SELECTED"


class ModelUseStatus(StrEnum):
    """Use label; no value in this module is production-promoted."""

    CALENDAR_BASELINE_REFERENCE = "CALENDAR_BASELINE_REFERENCE"
    UNVALIDATED_OOS_RESEARCH_OUTPUT = "UNVALIDATED_OOS_RESEARCH_OUTPUT"


class PromotionStatus(StrEnum):
    """Promotion is always withheld by this core."""

    NOT_PROMOTED = "NOT_PROMOTED"


def _text(value: object, field_name: str) -> str:
    """Return a non-empty stripped string or refuse the value."""

    if not isinstance(value, str) or not value.strip():
        raise WeatherDemandInputError(f"{field_name} must be a non-empty string")
    return value.strip()


def _utc(value: datetime, field_name: str) -> datetime:
    """Require an aware datetime and normalize it to UTC."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise WeatherDemandInputError(f"{field_name} must be an aware UTC datetime")
    return value.astimezone(UTC)


def _number(value: float, field_name: str, *, minimum: float, maximum: float) -> float:
    """Require a finite bounded int/float and return it as float."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherDemandInputError(f"{field_name} must be numeric")
    resolved = float(value)
    if not math.isfinite(resolved) or resolved < minimum or resolved > maximum:
        raise WeatherDemandInputError(f"{field_name} must be finite and in [{minimum}, {maximum}]")
    return resolved


def _integer(value: int, field_name: str, *, minimum: int, maximum: int) -> int:
    """Require a bounded integer (booleans are not integers here)."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise WeatherDemandInputError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise WeatherDemandInputError(f"{field_name} must be in [{minimum}, {maximum}]")
    return value


def _validate_calendar(calendar: str) -> str:
    """Resolve a frozen gas-day calendar version or propagate its refusal."""

    resolved = _text(calendar, "calendar")
    gas_day_start_for_date(date(2020, 1, 1), resolved)
    return resolved


def _format_vintage(vintage: ForecastVintageRef) -> str:
    """Return a stable compact forecast-vintage reference."""

    return f"{vintage.provider}/{vintage.model}/{vintage.run_id}@{vintage.issued_at.isoformat()}"


@dataclass(frozen=True)
class RegionLocationWeight:
    """One explicit non-negative location weight in an exactly weighted region."""

    location_id: str
    weight: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "location_id", _text(self.location_id, "location_id"))
        if not isinstance(self.weight, Decimal):
            raise WeatherDemandInputError("location weight must be Decimal, not float text")
        if not self.weight.is_finite() or self.weight < 0 or self.weight > 1:
            raise WeatherDemandInputError("location weight must be finite and in [0, 1]")


@dataclass(frozen=True)
class ForecastVintageRef:
    """Provider, model, run and issue identity for one immutable forecast vintage."""

    provider: str
    model: str
    run_id: str
    issued_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        object.__setattr__(self, "model", _text(self.model, "model"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        object.__setattr__(self, "issued_at", _utc(self.issued_at, "issued_at"))


@dataclass(frozen=True)
class ForecastTemperatureInterval:
    """A forecast mean temperature over a half-open UTC interval.

    ``issued_at`` is forecast issue time and ``available_at`` is the independent
    provider-availability evidence. The valid interval may be wholly in the
    future relative to a prediction origin; eligibility is based on issue and
    availability, never on ``valid_start <= origin``.

    ``temporal_method`` is required provenance. A provider-supplied interval mean
    and an explicitly derived hold are different inputs even when their numeric
    means coincide; this module never converts an instant into a held mean.
    """

    location_id: str
    start_utc: datetime
    end_utc: datetime
    mean_temperature_c: float
    issued_at: datetime
    available_at: datetime
    provider: str
    model: str
    run_id: str
    source_ref: str
    temporal_method: TemperatureDerivationMethod

    def __post_init__(self) -> None:
        object.__setattr__(self, "location_id", _text(self.location_id, "location_id"))
        start = _utc(self.start_utc, "start_utc")
        end = _utc(self.end_utc, "end_utc")
        issued = _utc(self.issued_at, "issued_at")
        available = _utc(self.available_at, "available_at")
        if start >= end:
            raise WeatherDemandInputError("temperature interval start must precede end")
        if (end - start) > timedelta(days=31):
            raise WeatherDemandInputError("temperature interval exceeds 31 days")
        if issued > available:
            raise WeatherDemandInputError("forecast available_at cannot precede issued_at")
        object.__setattr__(self, "start_utc", start)
        object.__setattr__(self, "end_utc", end)
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(
            self,
            "mean_temperature_c",
            _number(
                self.mean_temperature_c,
                "mean_temperature_c",
                minimum=MIN_TEMPERATURE_C,
                maximum=MAX_TEMPERATURE_C,
            ),
        )
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        object.__setattr__(self, "model", _text(self.model, "model"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))
        try:
            temporal_method = TemperatureDerivationMethod(self.temporal_method)
        except ValueError as exc:
            raise WeatherDemandInputError("unsupported temporal derivation method") from exc
        object.__setattr__(self, "temporal_method", temporal_method)

    @property
    def input_type(self) -> TemperatureInputType:
        """Return the immutable forecast label."""

        return TemperatureInputType.FORECAST_VINTAGE

    @property
    def vintage(self) -> ForecastVintageRef:
        """Return the structured forecast-vintage reference."""

        return ForecastVintageRef(
            provider=self.provider,
            model=self.model,
            run_id=self.run_id,
            issued_at=self.issued_at,
        )


@dataclass(frozen=True)
class RealizedTemperatureInterval:
    """A realized mean temperature over a half-open UTC interval.

    This is observation-derived evidence and is deliberately a different type
    from :class:`ForecastTemperatureInterval`; a forecast cannot be relabelled as
    observed and a realized series cannot claim a forecast vintage.

    ``temporal_method`` is required provenance, exactly as for forecast
    intervals. A realized series must not claim a provider interval mean when it
    was actually constructed by holding an instant.
    """

    location_id: str
    start_utc: datetime
    end_utc: datetime
    mean_temperature_c: float
    available_at: datetime
    source_ref: str
    temporal_method: TemperatureDerivationMethod

    def __post_init__(self) -> None:
        object.__setattr__(self, "location_id", _text(self.location_id, "location_id"))
        start = _utc(self.start_utc, "start_utc")
        end = _utc(self.end_utc, "end_utc")
        available = _utc(self.available_at, "available_at")
        if start >= end:
            raise WeatherDemandInputError("temperature interval start must precede end")
        if available < end:
            raise WeatherDemandInputError("realized interval cannot be available before it ends")
        object.__setattr__(self, "start_utc", start)
        object.__setattr__(self, "end_utc", end)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(
            self,
            "mean_temperature_c",
            _number(
                self.mean_temperature_c,
                "mean_temperature_c",
                minimum=MIN_TEMPERATURE_C,
                maximum=MAX_TEMPERATURE_C,
            ),
        )
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))
        try:
            temporal_method = TemperatureDerivationMethod(self.temporal_method)
        except ValueError as exc:
            raise WeatherDemandInputError("unsupported temporal derivation method") from exc
        object.__setattr__(self, "temporal_method", temporal_method)

    @property
    def input_type(self) -> TemperatureInputType:
        """Return the immutable realized label."""

        return TemperatureInputType.REALIZED_OBSERVATION


TemperatureInterval = ForecastTemperatureInterval | RealizedTemperatureInterval


def _decimal_identity(value: Decimal) -> str:
    """Return a canonical exact string for a Decimal weight in policy hashes."""

    if value == 0:
        return "0"
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class DegreeDayPolicy:
    """Explicit degree-day bases and no-interpolation coverage policy."""

    heating_base_c: float
    cooling_base_c: float
    max_gap_minutes: int
    min_covered_fraction: float
    method_version: str = DEGREE_DAY_METHOD_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "heating_base_c",
            _number(
                self.heating_base_c,
                "heating_base_c",
                minimum=MIN_DEGREE_BASE_C,
                maximum=MAX_DEGREE_BASE_C,
            ),
        )
        object.__setattr__(
            self,
            "cooling_base_c",
            _number(
                self.cooling_base_c,
                "cooling_base_c",
                minimum=MIN_DEGREE_BASE_C,
                maximum=MAX_DEGREE_BASE_C,
            ),
        )
        object.__setattr__(
            self,
            "max_gap_minutes",
            _integer(self.max_gap_minutes, "max_gap_minutes", minimum=0, maximum=10_080),
        )
        object.__setattr__(
            self,
            "min_covered_fraction",
            _number(
                self.min_covered_fraction,
                "min_covered_fraction",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        if self.method_version != DEGREE_DAY_METHOD_VERSION:
            raise WeatherDemandInputError("unsupported degree-day method version")

    @property
    def max_gap_seconds(self) -> float:
        """Return the explicit maximum internal/edge gap in seconds."""

        return float(self.max_gap_minutes) * 60.0


@dataclass(frozen=True)
class DegreeDayFeaturePolicy:
    """Typed immutable identity of the degree-day features a model may consume.

    Region, exact location weights, bases, calendar, coverage policy and temporal
    derivation method are all required. There is no default region or weight.
    ``policy_hash`` is a stable fingerprint over this structured identity, not
    over caller free text or over a particular day's feature values.
    """

    region: str
    heating_base_c: float
    cooling_base_c: float
    max_gap_minutes: int
    min_covered_fraction: float
    location_weights: tuple[RegionLocationWeight, ...]
    gas_day_calendar: str
    temporal_method: TemperatureDerivationMethod
    method_version: str = DEGREE_DAY_METHOD_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "region", _text(self.region, "region"))
        object.__setattr__(
            self,
            "heating_base_c",
            _number(
                self.heating_base_c,
                "heating_base_c",
                minimum=MIN_DEGREE_BASE_C,
                maximum=MAX_DEGREE_BASE_C,
            ),
        )
        object.__setattr__(
            self,
            "cooling_base_c",
            _number(
                self.cooling_base_c,
                "cooling_base_c",
                minimum=MIN_DEGREE_BASE_C,
                maximum=MAX_DEGREE_BASE_C,
            ),
        )
        object.__setattr__(
            self,
            "max_gap_minutes",
            _integer(self.max_gap_minutes, "max_gap_minutes", minimum=0, maximum=10_080),
        )
        object.__setattr__(
            self,
            "min_covered_fraction",
            _number(
                self.min_covered_fraction,
                "min_covered_fraction",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        weights = tuple(self.location_weights)
        if not weights:
            raise WeatherDemandInputError("at least one location weight is required")
        if any(not isinstance(weight, RegionLocationWeight) for weight in weights):
            raise WeatherDemandInputError("unsupported location weight type")
        location_ids = [weight.location_id for weight in weights]
        if len(set(location_ids)) != len(location_ids):
            raise WeatherDemandInputError("location weights contain duplicate locations")
        total = sum((weight.weight for weight in weights), Decimal("0"))
        if total != Decimal("1"):
            raise WeatherDemandInputError("location weights must sum exactly to 1")
        object.__setattr__(self, "location_weights", weights)
        object.__setattr__(self, "gas_day_calendar", _validate_calendar(self.gas_day_calendar))
        try:
            temporal_method = TemperatureDerivationMethod(self.temporal_method)
        except ValueError as exc:
            raise WeatherDemandInputError("unsupported temporal derivation method") from exc
        object.__setattr__(self, "temporal_method", temporal_method)
        if self.method_version != DEGREE_DAY_METHOD_VERSION:
            raise WeatherDemandInputError("unsupported degree-day method version")

    @property
    def policy_hash(self) -> str:
        """Return the stable structured fingerprint of this feature policy."""

        ordered_weights = sorted(self.location_weights, key=lambda item: item.location_id)
        return _canonical_hash(
            {
                "schema": "degree-day-feature-policy/v1",
                "method_version": self.method_version,
                "region": self.region,
                "heating_base_c": self.heating_base_c,
                "cooling_base_c": self.cooling_base_c,
                "max_gap_minutes": self.max_gap_minutes,
                "min_covered_fraction": self.min_covered_fraction,
                "gas_day_calendar": self.gas_day_calendar,
                "temporal_method": self.temporal_method.value,
                "location_weights": [
                    [weight.location_id, _decimal_identity(weight.weight)]
                    for weight in ordered_weights
                ],
            }
        )


@dataclass(frozen=True)
class DegreeDayRequest:
    """A typed request for one region, calendar version and prediction origin.

    Weights are exact ``Decimal`` values and must sum to exactly one. Every
    interval location must have an explicit weight. All intervals must be either
    forecast vintages or realized observations, never a mixture.
    """

    region: str
    gas_days: tuple[date, ...]
    prediction_origin: datetime
    location_weights: tuple[RegionLocationWeight, ...]
    intervals: tuple[TemperatureInterval, ...]
    calendar: str = DEFAULT_GAS_DAY_CALENDAR
    forecast_vintage: ForecastVintageRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "region", _text(self.region, "region"))
        object.__setattr__(self, "prediction_origin", _utc(self.prediction_origin, "origin"))
        object.__setattr__(self, "calendar", _validate_calendar(self.calendar))
        days = tuple(self.gas_days)
        if not days or len(days) > MAX_WEATHER_DAYS:
            raise WeatherDemandInputError(f"gas_days must contain 1..{MAX_WEATHER_DAYS} dates")
        if any(not isinstance(day, date) or isinstance(day, datetime) for day in days):
            raise WeatherDemandInputError("gas_days must contain date values")
        if len(set(days)) != len(days):
            raise WeatherDemandInputError("gas_days contains duplicate dates")
        object.__setattr__(self, "gas_days", tuple(sorted(days)))

        weights = tuple(self.location_weights)
        if not weights:
            raise WeatherDemandInputError("at least one location weight is required")
        location_ids = [weight.location_id for weight in weights]
        if len(set(location_ids)) != len(location_ids):
            raise WeatherDemandInputError("location weights contain duplicate locations")
        total = sum((weight.weight for weight in weights), Decimal("0"))
        if total != Decimal("1"):
            raise WeatherDemandInputError("location weights must sum exactly to 1")
        object.__setattr__(self, "location_weights", weights)

        intervals = tuple(self.intervals)
        if not intervals or len(intervals) > MAX_TEMPERATURE_INTERVALS:
            raise WeatherDemandInputError(
                f"intervals must contain 1..{MAX_TEMPERATURE_INTERVALS} values"
            )
        if any(
            not isinstance(interval, (ForecastTemperatureInterval, RealizedTemperatureInterval))
            for interval in intervals
        ):
            raise WeatherDemandInputError("unsupported temperature interval type")
        kinds = {interval.input_type for interval in intervals}
        if len(kinds) != 1:
            raise WeatherDemandInputError(
                "forecast and realized temperatures cannot be mixed in one request"
            )
        temporal_methods = {interval.temporal_method for interval in intervals}
        if len(temporal_methods) != 1:
            raise WeatherDemandInputError(
                "provider interval means and explicitly derived holds cannot be mixed "
                "in one request"
            )
        allowed_locations = set(location_ids)
        if any(interval.location_id not in allowed_locations for interval in intervals):
            raise WeatherDemandInputError("temperature interval has no explicit region weight")
        if kinds == {TemperatureInputType.REALIZED_OBSERVATION} and self.forecast_vintage:
            raise WeatherDemandInputError("realized observations cannot name a forecast vintage")
        if self.forecast_vintage is not None and not isinstance(
            self.forecast_vintage, ForecastVintageRef
        ):
            raise WeatherDemandInputError("forecast_vintage must be a ForecastVintageRef")
        object.__setattr__(self, "intervals", intervals)


@dataclass(frozen=True)
class DailyLocationCoverage:
    """Per-location coverage and degree-day evidence for one gas day."""

    location_id: str
    weight: Decimal
    covered_fraction: float
    largest_gap_seconds: float
    available_at: datetime | None
    mean_temperature_c: float | None
    daily_mean_hdd: float | None
    daily_mean_cdd: float | None
    heating_degree_day_integral: float | None
    cooling_degree_day_integral: float | None
    complete: bool
    missing_reason: str | None
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class DailyDegreeDay:
    """One gas day with separately named daily-mean and time-integral outputs."""

    gas_day: date
    gas_day_start_utc: datetime
    gas_day_end_utc: datetime
    duration_hours: float
    daily_mean_temperature_c: float | None
    daily_mean_hdd: float | None
    daily_mean_cdd: float | None
    time_integral_heating_degree_day: float | None
    time_integral_cooling_degree_day: float | None
    covered_fraction: float
    coverage_complete: bool
    missing_reason: str | None
    available_at: datetime | None
    source_refs: tuple[str, ...]
    locations: tuple[DailyLocationCoverage, ...]

    def named_values(self) -> dict[str, float | None]:
        """Return outputs keyed by their frozen public feature names."""

        return {
            "DAILY_MEAN_HDD": self.daily_mean_hdd,
            "DAILY_MEAN_CDD": self.daily_mean_cdd,
            "TIME_INTEGRAL_HEATING_DEGREE_DAY": self.time_integral_heating_degree_day,
            "TIME_INTEGRAL_COOLING_DEGREE_DAY": self.time_integral_cooling_degree_day,
        }


def _feature_policy(
    request: DegreeDayRequest, policy: DegreeDayPolicy
) -> DegreeDayFeaturePolicy:
    """Build the feature identity from the actual request and degree-day policy."""

    return DegreeDayFeaturePolicy(
        region=request.region,
        heating_base_c=policy.heating_base_c,
        cooling_base_c=policy.cooling_base_c,
        max_gap_minutes=policy.max_gap_minutes,
        min_covered_fraction=policy.min_covered_fraction,
        location_weights=request.location_weights,
        gas_day_calendar=request.calendar,
        temporal_method=request.intervals[0].temporal_method,
        method_version=policy.method_version,
    )


@dataclass(frozen=True)
class DailyWeatherFeature:
    """One point-in-time weather feature row with its full degree-day identity."""

    gas_day: date
    input_type: TemperatureInputType
    daily_mean_hdd: float | None
    daily_mean_cdd: float | None
    heating_degree_day_integral: float | None
    cooling_degree_day_integral: float | None
    available_at: datetime
    prediction_origin: datetime
    source_ref: str
    feature_policy: DegreeDayFeaturePolicy
    forecast_vintage: ForecastVintageRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.gas_day, date) or isinstance(self.gas_day, datetime):
            raise WeatherDemandInputError("gas_day must be a date")
        if not isinstance(self.feature_policy, DegreeDayFeaturePolicy):
            raise WeatherDemandInputError(
                "feature_policy must be a DegreeDayFeaturePolicy"
            )
        object.__setattr__(self, "input_type", TemperatureInputType(self.input_type))
        object.__setattr__(self, "available_at", _utc(self.available_at, "available_at"))
        object.__setattr__(
            self, "prediction_origin", _utc(self.prediction_origin, "prediction_origin")
        )
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))
        if self.available_at > self.prediction_origin:
            raise WeatherDemandInputError("weather feature was not available at its origin")
        if self.input_type is TemperatureInputType.FORECAST_VINTAGE:
            if not isinstance(self.forecast_vintage, ForecastVintageRef):
                raise WeatherDemandInputError("forecast feature requires a vintage reference")
            if self.forecast_vintage.issued_at > self.available_at:
                raise WeatherDemandInputError("feature availability precedes its issue time")
        elif self.forecast_vintage is not None:
            raise WeatherDemandInputError("realized feature cannot carry a forecast vintage")
        for name in (
            "daily_mean_hdd",
            "daily_mean_cdd",
            "heating_degree_day_integral",
            "cooling_degree_day_integral",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            resolved = _number(
                value,
                name,
                minimum=0.0,
                maximum=MAX_DEGREE_DAY_VALUE,
            )
            object.__setattr__(self, name, resolved)

    @property
    def region(self) -> str:
        """Return the feature region from the frozen feature policy."""

        return self.feature_policy.region

    @property
    def gas_day_calendar(self) -> str:
        """Return the gas-day calendar identity from the frozen feature policy."""

        return self.feature_policy.gas_day_calendar

    @property
    def method_version(self) -> str:
        """Return the degree-day method version from the frozen feature policy."""

        return self.feature_policy.method_version

    @property
    def temporal_method(self) -> TemperatureDerivationMethod:
        """Return the required temporal derivation method."""

        return self.feature_policy.temporal_method

    @property
    def feature_policy_hash(self) -> str:
        """Return the stable fingerprint of the frozen feature policy."""

        return self.feature_policy.policy_hash

    def value_for(self, feature: WeatherFeature) -> float | None:
        """Return the requested weather column without inventing a value."""

        return {
            WeatherFeature.HDD_MEAN: self.daily_mean_hdd,
            WeatherFeature.CDD_MEAN: self.daily_mean_cdd,
            WeatherFeature.HDD_INTEGRAL: self.heating_degree_day_integral,
            WeatherFeature.CDD_INTEGRAL: self.cooling_degree_day_integral,
        }[WeatherFeature(feature)]


@dataclass(frozen=True)
class DegreeDayResult:
    """Frozen degree-day result with one selected vintage and explicit coverage."""

    region: str
    input_type: TemperatureInputType
    prediction_origin: datetime
    gas_day_calendar: str
    feature_policy: DegreeDayFeaturePolicy
    heating_base_c: float
    cooling_base_c: float
    max_gap_seconds: float
    min_covered_fraction: float
    selected_vintage: ForecastVintageRef | None
    method_version: str
    daily: tuple[DailyDegreeDay, ...]
    source_refs: tuple[str, ...]

    @property
    def feature_policy_hash(self) -> str:
        """Return the stable fingerprint of the actual request/policy identity."""

        return self.feature_policy.policy_hash

    def feature_rows(self) -> tuple[DailyWeatherFeature, ...]:
        """Return complete days as labelled point-in-time feature rows."""

        rows: list[DailyWeatherFeature] = []
        for day in self.daily:
            values = (
                day.daily_mean_hdd,
                day.daily_mean_cdd,
                day.time_integral_heating_degree_day,
                day.time_integral_cooling_degree_day,
            )
            if any(value is None for value in values):
                continue
            available = day.available_at or self.prediction_origin
            rows.append(
                DailyWeatherFeature(
                    gas_day=day.gas_day,
                    input_type=self.input_type,
                    daily_mean_hdd=day.daily_mean_hdd,
                    daily_mean_cdd=day.daily_mean_cdd,
                    heating_degree_day_integral=day.time_integral_heating_degree_day,
                    cooling_degree_day_integral=day.time_integral_cooling_degree_day,
                    available_at=available,
                    prediction_origin=self.prediction_origin,
                    source_ref="|".join(day.source_refs),
                    feature_policy=self.feature_policy,
                    forecast_vintage=self.selected_vintage,
                )
            )
        return tuple(rows)


def _select_forecast(
    request: DegreeDayRequest,
) -> tuple[tuple[ForecastTemperatureInterval, ...], ForecastVintageRef | None]:
    """Select exactly one forecast vintage available at the prediction origin."""

    eligible = [
        interval
        for interval in request.intervals
        if isinstance(interval, ForecastTemperatureInterval)
        and interval.issued_at <= request.prediction_origin
        and interval.available_at <= request.prediction_origin
    ]
    groups: dict[tuple[str, str, str, datetime], list[ForecastTemperatureInterval]] = {}
    for interval in eligible:
        key = (interval.provider, interval.model, interval.run_id, interval.issued_at)
        groups.setdefault(key, []).append(interval)

    if request.forecast_vintage is not None:
        requested = request.forecast_vintage
        key = (requested.provider, requested.model, requested.run_id, requested.issued_at)
        selected = groups.get(key)
        if not selected:
            raise WeatherDemandInputError(
                "requested forecast vintage was not issued and available by the origin"
            )
        return tuple(sorted(selected, key=lambda item: item.start_utc)), requested

    if not groups:
        return (), None

    ranks = {
        key: (key[3], max(interval.available_at for interval in values))
        for key, values in groups.items()
    }
    best = max(ranks.values())
    winners = [key for key, rank in ranks.items() if rank == best]
    if len(winners) != 1:
        raise AmbiguousWeatherInputError(
            "multiple latest forecast vintages are equally available; select one explicitly"
        )
    key = winners[0]
    selected = groups[key]
    vintage = ForecastVintageRef(
        provider=key[0],
        model=key[1],
        run_id=key[2],
        issued_at=key[3],
    )
    return tuple(sorted(selected, key=lambda item: item.start_utc)), vintage


def _assert_non_overlapping(intervals: tuple[TemperatureInterval, ...]) -> None:
    """Refuse overlapping or duplicate intervals per location within one vintage."""

    by_location: dict[str, list[TemperatureInterval]] = {}
    for interval in intervals:
        by_location.setdefault(interval.location_id, []).append(interval)
    for location_id, values in by_location.items():
        ordered = sorted(values, key=lambda item: item.start_utc)
        for index in range(1, len(ordered)):
            previous = ordered[index - 1]
            current = ordered[index]
            if current.start_utc < previous.end_utc:
                raise AmbiguousWeatherInputError(
                    f"overlapping or duplicate temperature intervals for {location_id}"
                )


def _location_metrics(
    location: RegionLocationWeight,
    day_start: datetime,
    day_end: datetime,
    intervals: tuple[TemperatureInterval, ...],
    policy: DegreeDayPolicy,
) -> DailyLocationCoverage:
    """Calculate one location's covered pieces without interpolation."""

    clipped: list[tuple[datetime, datetime, TemperatureInterval]] = []
    for interval in intervals:
        if interval.location_id != location.location_id:
            continue
        start = max(interval.start_utc, day_start)
        end = min(interval.end_utc, day_end)
        if start < end:
            clipped.append((start, end, interval))
    clipped.sort(key=lambda item: item[0])
    duration_seconds = (day_end - day_start).total_seconds()
    if not clipped:
        return DailyLocationCoverage(
            location_id=location.location_id,
            weight=location.weight,
            covered_fraction=0.0,
            largest_gap_seconds=duration_seconds,
            available_at=None,
            mean_temperature_c=None,
            daily_mean_hdd=None,
            daily_mean_cdd=None,
            heating_degree_day_integral=None,
            cooling_degree_day_integral=None,
            complete=False,
            missing_reason="NO_LOCATION_INTERVALS",
            source_refs=(),
        )

    covered_seconds = 0.0
    largest_gap = 0.0
    cursor = day_start
    for start, end, _ in clipped:
        if start > cursor:
            largest_gap = max(largest_gap, (start - cursor).total_seconds())
        covered_seconds += (end - start).total_seconds()
        cursor = max(cursor, end)
    if cursor < day_end:
        largest_gap = max(largest_gap, (day_end - cursor).total_seconds())
    fraction = covered_seconds / duration_seconds if duration_seconds > 0 else 0.0
    complete = (
        covered_seconds > 0
        and largest_gap <= policy.max_gap_seconds + 1e-9
        and fraction + 1e-12 >= policy.min_covered_fraction
    )
    source_refs = tuple(sorted({interval.source_ref for _, _, interval in clipped}))
    available_at = max(interval.available_at for _, _, interval in clipped)
    if not complete:
        reason = (
            "MAX_GAP_EXCEEDED"
            if largest_gap > policy.max_gap_seconds + 1e-9
            else "COVERAGE_BELOW_MINIMUM"
        )
        return DailyLocationCoverage(
            location_id=location.location_id,
            weight=location.weight,
            covered_fraction=fraction,
            largest_gap_seconds=largest_gap,
            available_at=available_at,
            mean_temperature_c=None,
            daily_mean_hdd=None,
            daily_mean_cdd=None,
            heating_degree_day_integral=None,
            cooling_degree_day_integral=None,
            complete=False,
            missing_reason=reason,
            source_refs=source_refs,
        )

    mean_temperature = (
        math.fsum(
            (end - start).total_seconds() * interval.mean_temperature_c
            for start, end, interval in clipped
        )
        / covered_seconds
    )
    heating_degree_seconds = math.fsum(
        (end - start).total_seconds()
        * max(0.0, policy.heating_base_c - interval.mean_temperature_c)
        for start, end, interval in clipped
    )
    cooling_degree_seconds = math.fsum(
        (end - start).total_seconds()
        * max(0.0, interval.mean_temperature_c - policy.cooling_base_c)
        for start, end, interval in clipped
    )
    return DailyLocationCoverage(
        location_id=location.location_id,
        weight=location.weight,
        covered_fraction=fraction,
        largest_gap_seconds=largest_gap,
        available_at=available_at,
        mean_temperature_c=mean_temperature,
        daily_mean_hdd=max(0.0, policy.heating_base_c - mean_temperature),
        daily_mean_cdd=max(0.0, mean_temperature - policy.cooling_base_c),
        heating_degree_day_integral=heating_degree_seconds / 86_400.0,
        cooling_degree_day_integral=cooling_degree_seconds / 86_400.0,
        complete=True,
        missing_reason=None,
        source_refs=source_refs,
    )


def compute_degree_days(request: DegreeDayRequest, policy: DegreeDayPolicy) -> DegreeDayResult:
    """Compute explicit daily-mean and true-time-integral degree-day features.

    一个 prediction origin 只选择一个最新且已发布的共同预报 vintage；不会用
    更早的 run 填补缺口。覆盖不足的日期四个数值全部为 ``None``，不会写成零。
    """

    if not isinstance(request, DegreeDayRequest):
        raise TypeError("request must be a DegreeDayRequest")
    if not isinstance(policy, DegreeDayPolicy):
        raise TypeError("policy must be a DegreeDayPolicy")

    if request.intervals and isinstance(request.intervals[0], ForecastTemperatureInterval):
        selected, vintage = _select_forecast(request)
        selected_intervals: tuple[TemperatureInterval, ...] = selected
    else:
        selected_intervals = tuple(
            interval
            for interval in request.intervals
            if isinstance(interval, RealizedTemperatureInterval)
            and interval.available_at <= request.prediction_origin
        )
        vintage = None
    _assert_non_overlapping(selected_intervals)

    daily: list[DailyDegreeDay] = []
    source_refs: set[str] = set()
    for gas_day in request.gas_days:
        day_start = gas_day_start_for_date(gas_day, request.calendar)
        day_end = gas_day_start_for_date(gas_day + timedelta(days=1), request.calendar)
        duration_hours = (day_end - day_start).total_seconds() / 3_600.0
        locations = tuple(
            _location_metrics(location, day_start, day_end, selected_intervals, policy)
            for location in request.location_weights
        )
        active = tuple(location for location in locations if location.weight > 0)
        covered_fraction = math.fsum(
            float(location.weight) * location.covered_fraction for location in active
        )
        complete = bool(active) and all(location.complete for location in active)
        day_source_refs = tuple(
            sorted({ref for location in active for ref in location.source_refs})
        )
        source_refs.update(day_source_refs)
        available_values = [
            location.available_at for location in active if location.available_at is not None
        ]
        available_at = max(available_values) if available_values else None

        if complete:
            mean_temperature = math.fsum(
                float(location.weight) * (location.mean_temperature_c or 0.0) for location in active
            )
            daily_hdd = math.fsum(
                float(location.weight) * (location.daily_mean_hdd or 0.0) for location in active
            )
            daily_cdd = math.fsum(
                float(location.weight) * (location.daily_mean_cdd or 0.0) for location in active
            )
            heating_integral = math.fsum(
                float(location.weight) * (location.heating_degree_day_integral or 0.0)
                for location in active
            )
            cooling_integral = math.fsum(
                float(location.weight) * (location.cooling_degree_day_integral or 0.0)
                for location in active
            )
            missing_reason = None
        else:
            mean_temperature = None
            daily_hdd = None
            daily_cdd = None
            heating_integral = None
            cooling_integral = None
            missing_reason = (
                "NO_ELIGIBLE_TEMPERATURE_INPUT"
                if not selected_intervals
                else "INSUFFICIENT_COVERAGE"
            )

        daily.append(
            DailyDegreeDay(
                gas_day=gas_day,
                gas_day_start_utc=day_start,
                gas_day_end_utc=day_end,
                duration_hours=duration_hours,
                daily_mean_temperature_c=mean_temperature,
                daily_mean_hdd=daily_hdd,
                daily_mean_cdd=daily_cdd,
                time_integral_heating_degree_day=heating_integral,
                time_integral_cooling_degree_day=cooling_integral,
                covered_fraction=covered_fraction,
                coverage_complete=complete,
                missing_reason=missing_reason,
                available_at=available_at,
                source_refs=day_source_refs,
                locations=locations,
            )
        )

    return DegreeDayResult(
        region=request.region,
        input_type=request.intervals[0].input_type,
        prediction_origin=request.prediction_origin,
        gas_day_calendar=request.calendar,
        feature_policy=_feature_policy(request, policy),
        heating_base_c=policy.heating_base_c,
        cooling_base_c=policy.cooling_base_c,
        max_gap_seconds=policy.max_gap_seconds,
        min_covered_fraction=policy.min_covered_fraction,
        selected_vintage=vintage,
        method_version=policy.method_version,
        daily=tuple(daily),
        source_refs=tuple(sorted(source_refs)),
    )


@dataclass(frozen=True)
class DemandTargetRow:
    """One native-unit actual demand revision with point-in-time availability."""

    gas_day: date
    scope: TargetScope
    region: str
    unit: str
    value: float
    quality: DemandTargetQuality
    revision: int
    revision_id: str
    available_at: datetime
    source_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.gas_day, date) or isinstance(self.gas_day, datetime):
            raise WeatherDemandInputError("gas_day must be a date")
        if not date(2000, 1, 1) <= self.gas_day <= date(2100, 12, 31):
            raise WeatherDemandInputError("gas_day is outside the supported range")
        object.__setattr__(self, "scope", TargetScope(self.scope))
        object.__setattr__(self, "quality", DemandTargetQuality(self.quality))
        object.__setattr__(self, "region", _text(self.region, "region"))
        object.__setattr__(self, "unit", _text(self.unit, "unit").upper())
        object.__setattr__(
            self,
            "value",
            _number(self.value, "value", minimum=0.0, maximum=MAX_DEMAND_VALUE),
        )
        object.__setattr__(
            self, "revision", _integer(self.revision, "revision", minimum=1, maximum=1_000_000)
        )
        object.__setattr__(self, "revision_id", _text(self.revision_id, "revision_id"))
        object.__setattr__(self, "available_at", _utc(self.available_at, "available_at"))
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))


@dataclass(frozen=True)
class DemandModelPolicy:
    """Frozen fitting cutoff, ridge penalty, selection rule and work bounds."""

    target_scope: TargetScope
    region: str
    target_unit: str
    gas_day_calendar: str
    training_cutoff: datetime
    validation_as_of: datetime
    ridge_lambda: float
    model_version: str
    validation_basis: ValidationBasis
    weather_features: tuple[WeatherFeature, ...]
    expected_feature_policy: DegreeDayFeaturePolicy
    min_training_rows: int
    min_validation_folds: int
    min_validation_predictions: int
    min_oos_coverage: float
    min_relative_mae_improvement: float
    min_fold_win_fraction: float
    min_residuals_for_interval: int
    interval_level: float = 0.8
    max_training_rows: int = 10_000
    max_features: int = 32
    max_folds: int = 31

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_scope", TargetScope(self.target_scope))
        object.__setattr__(self, "region", _text(self.region, "region"))
        object.__setattr__(self, "target_unit", _text(self.target_unit, "target_unit").upper())
        object.__setattr__(self, "gas_day_calendar", _validate_calendar(self.gas_day_calendar))
        cutoff = _utc(self.training_cutoff, "training_cutoff")
        validation_as_of = _utc(self.validation_as_of, "validation_as_of")
        if validation_as_of < cutoff:
            raise WeatherDemandInputError("validation_as_of cannot precede training_cutoff")
        object.__setattr__(self, "training_cutoff", cutoff)
        object.__setattr__(self, "validation_as_of", validation_as_of)
        object.__setattr__(
            self,
            "ridge_lambda",
            _number(self.ridge_lambda, "ridge_lambda", minimum=1e-12, maximum=1e6),
        )
        object.__setattr__(self, "model_version", _text(self.model_version, "model_version"))
        object.__setattr__(self, "validation_basis", ValidationBasis(self.validation_basis))
        features = tuple(WeatherFeature(feature) for feature in self.weather_features)
        if not features:
            raise WeatherDemandInputError("at least one weather feature is required")
        if len(set(features)) != len(features):
            raise WeatherDemandInputError("weather_features contains duplicates")
        object.__setattr__(self, "weather_features", features)
        if not isinstance(self.expected_feature_policy, DegreeDayFeaturePolicy):
            raise WeatherDemandInputError(
                "expected_feature_policy must be a DegreeDayFeaturePolicy"
            )
        if self.expected_feature_policy.region != self.region:
            raise WeatherDemandInputError(
                "expected feature policy region must match the model region"
            )
        if self.expected_feature_policy.gas_day_calendar != self.gas_day_calendar:
            raise WeatherDemandInputError(
                "expected feature policy calendar must match the model calendar"
            )
        object.__setattr__(
            self,
            "min_training_rows",
            _integer(
                self.min_training_rows, "min_training_rows", minimum=1, maximum=MAX_FEATURE_ROWS
            ),
        )
        object.__setattr__(
            self,
            "max_training_rows",
            _integer(
                self.max_training_rows, "max_training_rows", minimum=1, maximum=MAX_TARGET_ROWS
            ),
        )
        if self.min_training_rows > self.max_training_rows:
            raise WeatherDemandInputError("min_training_rows exceeds max_training_rows")
        object.__setattr__(
            self,
            "min_validation_folds",
            _integer(
                self.min_validation_folds, "min_validation_folds", minimum=1, maximum=MAX_FOLDS
            ),
        )
        object.__setattr__(
            self,
            "max_folds",
            _integer(self.max_folds, "max_folds", minimum=1, maximum=MAX_FOLDS),
        )
        if self.min_validation_folds > self.max_folds:
            raise WeatherDemandInputError("min_validation_folds exceeds max_folds")
        object.__setattr__(
            self,
            "min_validation_predictions",
            _integer(
                self.min_validation_predictions,
                "min_validation_predictions",
                minimum=1,
                maximum=MAX_FOLDS,
            ),
        )
        for name in (
            "min_oos_coverage",
            "min_relative_mae_improvement",
            "min_fold_win_fraction",
            "interval_level",
        ):
            value = _number(getattr(self, name), name, minimum=0.0, maximum=1.0)
            if name == "interval_level" and not 0.0 < value < 1.0:
                raise WeatherDemandInputError("interval_level must be strictly inside (0, 1)")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "min_residuals_for_interval",
            _integer(
                self.min_residuals_for_interval,
                "min_residuals_for_interval",
                minimum=0,
                maximum=MAX_FOLDS,
            ),
        )
        object.__setattr__(
            self,
            "max_features",
            _integer(self.max_features, "max_features", minimum=1, maximum=256),
        )
        if _feature_count(self) > self.max_features:
            raise WeatherDemandInputError("selected features exceed max_features")


@dataclass(frozen=True)
class ModelMetrics:
    """MAE, RMSE and bias in the target's native unit; never a percentage claim."""

    mae: float
    rmse: float
    bias: float
    count: int


@dataclass(frozen=True)
class DemandFoldResult:
    """One daily expanding-window fold with actual and model predictions separated."""

    fold_origin: datetime
    validation_gas_day: date
    training_rows: int
    actual_value: float
    baseline_prediction: float
    candidate_prediction: float
    input_type: TemperatureInputType


@dataclass(frozen=True)
class ResidualUncertainty:
    """Empirical held-out residual interval; offsets apply to a model prediction."""

    level: float
    lower_offset: float
    upper_offset: float
    residual_count: int
    method_version: str


@dataclass(frozen=True)
class FittedDemandModel:
    """A frozen fitted model; this module never marks one production-promoted."""

    kind: ModelKind
    model_version: str
    method_version: str
    target_scope: TargetScope
    region: str
    target_unit: str
    gas_day_calendar: str
    feature_policy_hash: str
    training_cutoff: datetime
    feature_names: tuple[str, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    month_means: tuple[tuple[int, float], ...]
    overall_mean: float
    ridge_lambda: float | None
    calendar_method: str
    training_rows: int
    source_refs: tuple[str, ...]
    target_revision_ids: tuple[str, ...]
    weather_vintage_ids: tuple[str, ...]
    validation_basis: ValidationBasis
    use_status: ModelUseStatus
    model_hash: str


def _fold_payload(fold: DemandFoldResult) -> dict[str, object]:
    """Return the complete deterministic identity a fold currently records.

    ``DemandFoldResult`` does not retain the raw target-revision/source payloads
    used to produce ``actual_value``. This payload therefore binds the fold
    origin/day/values and input type, but it is not a raw-data proof.
    """

    return {
        "fold_origin": fold.fold_origin.isoformat(),
        "validation_gas_day": fold.validation_gas_day.isoformat(),
        "training_rows": fold.training_rows,
        "actual_value": fold.actual_value,
        "baseline_prediction": fold.baseline_prediction,
        "candidate_prediction": fold.candidate_prediction,
        "input_type": fold.input_type.value,
    }


def _uncertainty_payload(
    uncertainty: ResidualUncertainty | None,
) -> dict[str, object] | None:
    """Return a deterministic JSON-safe identity for optional interval evidence."""

    if uncertainty is None:
        return None
    return {
        "level": uncertainty.level,
        "lower_offset": uncertainty.lower_offset,
        "upper_offset": uncertainty.upper_offset,
        "residual_count": uncertainty.residual_count,
        "method_version": uncertainty.method_version,
    }


def _fold_win_fraction(folds: tuple[DemandFoldResult, ...]) -> float:
    """Return the deterministic fraction of folds where the candidate won."""

    if not folds:
        return 0.0
    wins = sum(
        1
        for fold in folds
        if abs(fold.candidate_prediction - fold.actual_value)
        < abs(fold.baseline_prediction - fold.actual_value)
    )
    return wins / len(folds)


@dataclass(frozen=True)
class DemandSelectionEvidence:
    """Frozen selection evidence whose availability starts at ``validation_as_of``.

    The hash deterministically binds the selected/baseline/candidate model hashes,
    every measured fold currently retained, the uncertainty payload and reason,
    validation basis, selection status/reason, metrics, counts and policy
    thresholds. It contains no wall-clock execution time. Fold evidence is limited
    to the origin/day/actual/prediction values and input type that the fold type
    records; raw target-revision/source payload proofs are not retained. This is
    integrity consistency, not a cryptographic signature or raw-data proof.
    """

    validation_as_of: datetime
    selected_model_hash: str
    baseline_model_hash: str
    candidate_model_hash: str | None
    selection_status: ModelSelectionStatus
    selection_reason: str
    validation_basis: ValidationBasis
    baseline_oos: ModelMetrics | None
    candidate_oos: ModelMetrics | None
    fold_count: int
    fold_win_fraction: float
    oos_coverage: float
    residual_count: int
    policy_thresholds: tuple[tuple[str, float], ...]
    folds: tuple[DemandFoldResult, ...] = ()
    uncertainty: ResidualUncertainty | None = None
    uncertainty_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "validation_as_of", _utc(self.validation_as_of, "validation_as_of")
        )
        for name in ("selected_model_hash", "baseline_model_hash"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.candidate_model_hash is not None:
            object.__setattr__(
                self,
                "candidate_model_hash",
                _text(self.candidate_model_hash, "candidate_model_hash"),
            )
        object.__setattr__(
            self,
            "selection_status",
            ModelSelectionStatus(self.selection_status),
        )
        object.__setattr__(
            self,
            "selection_reason",
            _text(self.selection_reason, "selection_reason"),
        )
        object.__setattr__(
            self,
            "validation_basis",
            ValidationBasis(self.validation_basis),
        )
        object.__setattr__(
            self,
            "fold_count",
            _integer(self.fold_count, "fold_count", minimum=0, maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "fold_win_fraction",
            _number(
                self.fold_win_fraction,
                "fold_win_fraction",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "oos_coverage",
            _number(self.oos_coverage, "oos_coverage", minimum=0.0, maximum=1.0),
        )
        object.__setattr__(
            self,
            "residual_count",
            _integer(
                self.residual_count,
                "residual_count",
                minimum=0,
                maximum=1_000_000,
            ),
        )
        thresholds = tuple(
            (
                _text(name, "policy_threshold name"),
                _number(value, name, minimum=-1e12, maximum=1e12),
            )
            for name, value in self.policy_thresholds
        )
        object.__setattr__(self, "policy_thresholds", thresholds)
        folds = tuple(self.folds)
        if any(not isinstance(fold, DemandFoldResult) for fold in folds):
            raise WeatherDemandInputError(
                "selection evidence folds must contain DemandFoldResult values"
            )
        object.__setattr__(self, "folds", folds)
        if self.uncertainty is not None and not isinstance(
            self.uncertainty, ResidualUncertainty
        ):
            raise WeatherDemandInputError(
                "selection evidence uncertainty must be a ResidualUncertainty or None"
            )
        if self.uncertainty_reason is not None:
            object.__setattr__(
                self,
                "uncertainty_reason",
                _text(self.uncertainty_reason, "uncertainty_reason"),
            )

    @property
    def selection_hash(self) -> str:
        """Return the deterministic selection-evidence fingerprint."""

        return _canonical_hash(
            {
                "schema": "demand-selection-evidence/v2",
                "validation_as_of": self.validation_as_of.isoformat(),
                "selected_model_hash": self.selected_model_hash,
                "baseline_model_hash": self.baseline_model_hash,
                "candidate_model_hash": self.candidate_model_hash,
                "selection_status": self.selection_status.value,
                "selection_reason": self.selection_reason,
                "validation_basis": self.validation_basis.value,
                "baseline_oos": _metrics_payload(self.baseline_oos),
                "candidate_oos": _metrics_payload(self.candidate_oos),
                "fold_count": self.fold_count,
                "folds": [_fold_payload(fold) for fold in self.folds],
                "fold_win_fraction": self.fold_win_fraction,
                "oos_coverage": self.oos_coverage,
                "residual_count": self.residual_count,
                "uncertainty": _uncertainty_payload(self.uncertainty),
                "uncertainty_reason": self.uncertainty_reason,
                "policy_thresholds": sorted(
                    [[name, value] for name, value in self.policy_thresholds]
                ),
            }
        )


@dataclass(frozen=True)
class DemandModelResult:
    """Baseline, optional weather candidate and measured OOS selection outcome."""

    baseline_model: FittedDemandModel
    candidate_model: FittedDemandModel | None
    selected_model: FittedDemandModel
    selection_status: ModelSelectionStatus
    selection_reason: str
    validation_basis: ValidationBasis
    folds: tuple[DemandFoldResult, ...]
    baseline_oos: ModelMetrics | None
    candidate_oos: ModelMetrics | None
    oos_coverage: float
    residual_count: int
    uncertainty: ResidualUncertainty | None
    uncertainty_reason: str | None
    production_promotion: PromotionStatus
    prediction_label: str = "MODEL_OUTPUT"
    selection_evidence: DemandSelectionEvidence | None = None

    @property
    def selection_as_of(self) -> datetime | None:
        """Return the validation cutoff that makes selection evidence available."""

        if self.selection_evidence is None:
            return None
        return self.selection_evidence.validation_as_of

    @property
    def validation_as_of(self) -> datetime | None:
        """Alias for the selection-evidence availability cutoff."""

        return self.selection_as_of

    @property
    def selection_hash(self) -> str | None:
        """Return the deterministic selection-evidence hash when present."""

        if self.selection_evidence is None:
            return None
        return self.selection_evidence.selection_hash


@dataclass(frozen=True)
class PredictionFeatureRef:
    """One frozen weather column actually consumed by a prediction."""

    name: str
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "feature name"))
        object.__setattr__(
            self,
            "value",
            _number(self.value, "feature value", minimum=0.0, maximum=MAX_DEGREE_DAY_VALUE),
        )


@dataclass(frozen=True)
class DemandPredictionRequest:
    """Explicit target, prediction origin and optional forward weather candidate."""

    gas_day: date
    prediction_origin: datetime
    target_scope: TargetScope
    region: str
    target_unit: str
    gas_day_calendar: str = DEFAULT_GAS_DAY_CALENDAR
    weather_feature: DailyWeatherFeature | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.gas_day, date) or isinstance(self.gas_day, datetime):
            raise WeatherDemandInputError("gas_day must be a date")
        if not date(2000, 1, 1) <= self.gas_day <= date(2100, 12, 31):
            raise WeatherDemandInputError("gas_day is outside the supported range")
        object.__setattr__(
            self, "prediction_origin", _utc(self.prediction_origin, "prediction_origin")
        )
        object.__setattr__(self, "target_scope", TargetScope(self.target_scope))
        object.__setattr__(self, "region", _text(self.region, "region"))
        object.__setattr__(self, "target_unit", _text(self.target_unit, "target_unit").upper())
        object.__setattr__(self, "gas_day_calendar", _validate_calendar(self.gas_day_calendar))
        if self.weather_feature is not None and not isinstance(
            self.weather_feature, DailyWeatherFeature
        ):
            raise WeatherDemandInputError("weather_feature must be a DailyWeatherFeature or None")


@dataclass(frozen=True)
class DemandPredictionInterval:
    """Empirical held-out residual interval, never a coverage guarantee."""

    lower: float
    upper: float
    level: float
    residual_count: int
    method_version: str
    label: str = "EMPIRICAL_HELDOUT_RESIDUAL_RESEARCH_INTERVAL"
    coverage_guarantee: bool = False
    production_promotion: PromotionStatus = PromotionStatus.NOT_PROMOTED

    def __post_init__(self) -> None:
        lower = _number(self.lower, "interval lower", minimum=-1e30, maximum=1e30)
        upper = _number(self.upper, "interval upper", minimum=-1e30, maximum=1e30)
        if lower > upper:
            raise WeatherDemandInputError("interval lower cannot exceed interval upper")
        level = _number(self.level, "interval level", minimum=0.0, maximum=1.0)
        if not 0.0 < level < 1.0:
            raise WeatherDemandInputError("interval level must be strictly inside (0, 1)")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(self, "level", level)
        object.__setattr__(
            self,
            "residual_count",
            _integer(self.residual_count, "residual_count", minimum=1, maximum=1_000_000),
        )
        object.__setattr__(self, "method_version", _text(self.method_version, "method_version"))
        object.__setattr__(self, "label", _text(self.label, "label"))
        if self.coverage_guarantee:
            raise WeatherDemandInputError("empirical research intervals have no coverage guarantee")
        object.__setattr__(self, "coverage_guarantee", False)
        object.__setattr__(
            self, "production_promotion", PromotionStatus(self.production_promotion)
        )


@dataclass(frozen=True)
class DemandPrediction:
    """One pure native-unit prediction from an already fitted research result."""

    gas_day: date
    prediction_origin: datetime
    target_scope: TargetScope
    region: str
    target_unit: str
    gas_day_calendar: str
    model_kind: ModelKind
    model_version: str
    method_version: str
    prediction_label: str
    use_status: ModelUseStatus
    value: float
    model_hash: str
    selection_hash: str
    selection_as_of: datetime
    feature_policy_hash: str
    feature_refs: tuple[PredictionFeatureRef, ...]
    weather_source_ref: str | None
    weather_available_at: datetime | None
    forecast_vintage: ForecastVintageRef | None
    interval: DemandPredictionInterval | None
    interval_reason: str | None
    production_promotion: PromotionStatus = PromotionStatus.NOT_PROMOTED

    def __post_init__(self) -> None:
        if not isinstance(self.gas_day, date) or isinstance(self.gas_day, datetime):
            raise WeatherDemandInputError("gas_day must be a date")
        object.__setattr__(
            self, "prediction_origin", _utc(self.prediction_origin, "prediction_origin")
        )
        object.__setattr__(self, "selection_as_of", _utc(self.selection_as_of, "selection_as_of"))
        object.__setattr__(self, "target_scope", TargetScope(self.target_scope))
        object.__setattr__(self, "region", _text(self.region, "region"))
        object.__setattr__(self, "target_unit", _text(self.target_unit, "target_unit").upper())
        object.__setattr__(self, "gas_day_calendar", _validate_calendar(self.gas_day_calendar))
        object.__setattr__(self, "model_kind", ModelKind(self.model_kind))
        for name in (
            "model_version",
            "method_version",
            "prediction_label",
            "model_hash",
            "selection_hash",
            "feature_policy_hash",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "use_status", ModelUseStatus(self.use_status))
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise WeatherDemandInputError("prediction value must be numeric")
        value = float(self.value)
        if not math.isfinite(value):
            raise WeatherDemandInputError("prediction value must be finite")
        if value < 0.0:
            raise NegativeDemandEstimateError(
                "prediction is negative in the native demand unit; refusing to clamp it"
            )
        object.__setattr__(self, "value", value)
        refs = tuple(self.feature_refs)
        if any(not isinstance(ref, PredictionFeatureRef) for ref in refs):
            raise WeatherDemandInputError("feature_refs must contain PredictionFeatureRef values")
        object.__setattr__(self, "feature_refs", refs)
        if self.weather_source_ref is not None:
            object.__setattr__(
                self, "weather_source_ref", _text(self.weather_source_ref, "weather_source_ref")
            )
        if self.weather_available_at is not None:
            object.__setattr__(
                self,
                "weather_available_at",
                _utc(self.weather_available_at, "weather_available_at"),
            )
        if self.forecast_vintage is not None and not isinstance(
            self.forecast_vintage, ForecastVintageRef
        ):
            raise WeatherDemandInputError("forecast_vintage must be a ForecastVintageRef or None")
        if self.interval is not None and not isinstance(self.interval, DemandPredictionInterval):
            raise WeatherDemandInputError("interval must be a DemandPredictionInterval or None")
        if self.interval_reason is not None:
            object.__setattr__(
                self, "interval_reason", _text(self.interval_reason, "interval_reason")
            )
        object.__setattr__(
            self, "production_promotion", PromotionStatus(self.production_promotion)
        )


def _numpy() -> object:
    """Import NumPy lazily and raise the typed dependency failure."""

    try:
        import numpy as np
    except ImportError as exc:
        raise MissingNumpyError() from exc
    return np


def _feature_names(policy: DemandModelPolicy) -> tuple[str, ...]:
    """Return the explicit ordered candidate feature names."""

    names = ["calendar_sin_annual", "calendar_cos_annual"]
    names.extend(f"weekday_{day}" for day in ("tue", "wed", "thu", "fri", "sat", "sun"))
    names.extend(
        {
            WeatherFeature.HDD_MEAN: "weather_hdd_mean",
            WeatherFeature.CDD_MEAN: "weather_cdd_mean",
            WeatherFeature.HDD_INTEGRAL: "weather_hdd_integral",
            WeatherFeature.CDD_INTEGRAL: "weather_cdd_integral",
        }[feature]
        for feature in policy.weather_features
    )
    return tuple(names)


def _feature_count(policy: DemandModelPolicy) -> int:
    """Return the bounded candidate dimension without materializing a matrix."""

    return 8 + len(policy.weather_features)


def _calendar_values(gas_day: date) -> tuple[float, ...]:
    """Return the frozen annual-harmonic and Monday-reference weekday values."""

    day_of_year = gas_day.timetuple().tm_yday
    theta = 2.0 * math.pi * (day_of_year - 1) / 365.2425
    values = [math.sin(theta), math.cos(theta)]
    weekday = gas_day.weekday()
    values.extend(1.0 if weekday == index else 0.0 for index in range(1, 7))
    return tuple(values)


def _candidate_row(
    gas_day: date, feature: DailyWeatherFeature, policy: DemandModelPolicy
) -> tuple[float, ...] | None:
    """Build one calendar-plus-weather row, or return None for missing weather."""

    values = list(_calendar_values(gas_day))
    for name in policy.weather_features:
        value = feature.value_for(name)
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _validate_targets(targets: tuple[DemandTargetRow, ...], policy: DemandModelPolicy) -> None:
    """Refuse heterogeneous targets, duplicate revisions and excessive rows."""

    if not targets:
        raise WeatherDemandInputError("at least one actual demand target is required")
    if len(targets) > MAX_TARGET_ROWS:
        raise WeatherDemandInputError("target row budget exceeded")
    seen: set[tuple[date, int]] = set()
    for target in targets:
        if not isinstance(target, DemandTargetRow):
            raise WeatherDemandInputError("unsupported target row type")
        if (
            target.scope is not policy.target_scope
            or target.region != policy.region
            or target.unit != policy.target_unit
        ):
            raise WeatherDemandInputError(
                "target scope, region or native unit does not match the explicit policy"
            )
        key = (target.gas_day, target.revision)
        if key in seen:
            raise AmbiguousWeatherInputError("duplicate target gas_day/revision")
        seen.add(key)


def _validate_features(
    features: tuple[DailyWeatherFeature, ...], policy: DemandModelPolicy
) -> TemperatureInputType:
    """Refuse mixed provenance and basis/input mismatches before fitting."""

    if not features:
        raise WeatherDemandInputError("at least one weather feature row is required")
    if len(features) > MAX_FEATURE_ROWS:
        raise WeatherDemandInputError("weather feature row budget exceeded")
    input_types: set[TemperatureInputType] = set()
    for feature in features:
        if not isinstance(feature, DailyWeatherFeature):
            raise WeatherDemandInputError("unsupported weather feature row type")
        if feature.feature_policy.region != policy.region:
            raise WeatherDemandInputError(
                "weather feature region does not match the explicit model region"
            )
        if feature.feature_policy_hash != policy.expected_feature_policy.policy_hash:
            raise WeatherDemandInputError(
                "weather feature policy fingerprint does not match the model policy"
            )
        if feature.gas_day_calendar != policy.gas_day_calendar:
            raise WeatherDemandInputError("weather feature calendar differs from policy")
        input_types.add(feature.input_type)
    if len(input_types) != 1:
        raise WeatherDemandInputError("forecast and realized weather features cannot be mixed")
    input_type = next(iter(input_types))
    if (
        policy.validation_basis is ValidationBasis.REALIZED_WEATHER_CALIBRATION
        and input_type is not TemperatureInputType.REALIZED_OBSERVATION
    ):
        raise WeatherDemandInputError("realized calibration requires realized weather features")
    if (
        policy.validation_basis is ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS
        and input_type is not TemperatureInputType.FORECAST_VINTAGE
    ):
        raise WeatherDemandInputError("genuine forecast OOS requires forecast features")
    return input_type


def _resolve_targets(
    targets: tuple[DemandTargetRow, ...], cutoff: datetime
) -> dict[date, DemandTargetRow]:
    """Resolve the latest target revision that was genuinely available at cutoff."""

    grouped: dict[date, list[DemandTargetRow]] = {}
    for target in targets:
        if target.available_at <= cutoff:
            grouped.setdefault(target.gas_day, []).append(target)
    resolved: dict[date, DemandTargetRow] = {}
    for gas_day, rows in grouped.items():
        latest_revision = max(row.revision for row in rows)
        winners = [row for row in rows if row.revision == latest_revision]
        if len(winners) != 1:
            raise AmbiguousWeatherInputError("ambiguous latest target revision at cutoff")
        resolved[gas_day] = winners[0]
    return resolved


def _pick_feature(
    features: tuple[DailyWeatherFeature, ...],
    gas_day: date,
    cutoff: datetime,
    input_type: TemperatureInputType,
) -> DailyWeatherFeature | None:
    """Select one latest available feature row for a day without fill-forward."""

    eligible = [
        feature
        for feature in features
        if feature.gas_day == gas_day
        and feature.input_type is input_type
        and feature.available_at <= cutoff
        and feature.prediction_origin <= cutoff
    ]
    if not eligible:
        return None
    best_key = max((feature.available_at, feature.prediction_origin) for feature in eligible)
    winners = [
        feature
        for feature in eligible
        if (feature.available_at, feature.prediction_origin) == best_key
    ]
    if len(winners) != 1:
        raise AmbiguousWeatherInputError(
            "multiple equally available weather features for one gas day"
        )
    return winners[0]


TrainingRow = tuple[date, float, DemandTargetRow, DailyWeatherFeature]


def _prepare_training(
    targets: tuple[DemandTargetRow, ...],
    features: tuple[DailyWeatherFeature, ...],
    policy: DemandModelPolicy,
    cutoff: datetime,
    *,
    before_day: date | None = None,
) -> tuple[TrainingRow, ...]:
    """Apply target/weather cutoff filters before any transform or feature use."""

    resolved_targets = _resolve_targets(targets, cutoff)
    input_type = features[0].input_type
    rows: list[TrainingRow] = []
    for gas_day in sorted(resolved_targets):
        if before_day is not None and gas_day >= before_day:
            continue
        target = resolved_targets[gas_day]
        end = gas_day_start_for_date(gas_day + timedelta(days=1), policy.gas_day_calendar)
        if end > cutoff:
            continue
        feature = _pick_feature(features, gas_day, cutoff, input_type)
        if feature is None:
            continue
        if any(feature.value_for(name) is None for name in policy.weather_features):
            continue
        rows.append((gas_day, target.value, target, feature))
        if len(rows) > policy.max_training_rows:
            raise WeatherDemandInputError("training row budget exceeded")
    return tuple(rows)


def _training_provenance(
    rows: tuple[TrainingRow, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Return sorted source, revision and weather-vintage identities."""

    sources: set[str] = set()
    revisions: set[str] = set()
    vintages: set[str] = set()
    for _, _, target, feature in rows:
        sources.update((target.source_ref, feature.source_ref))
        revisions.add(target.revision_id)
        if feature.forecast_vintage is not None:
            vintages.add(_format_vintage(feature.forecast_vintage))
    return tuple(sorted(sources)), tuple(sorted(revisions)), tuple(sorted(vintages))


def _canonical_hash(payload: dict[str, object]) -> str:
    """Hash a canonical JSON payload with deterministic key ordering."""

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _base_payload(
    policy: DemandModelPolicy,
    kind: ModelKind,
    cutoff: datetime,
    rows: tuple[TrainingRow, ...],
) -> dict[str, object]:
    """Build the shared canonical model-hash fields."""

    sources, revisions, vintages = _training_provenance(rows)
    return {
        "method_version": DEMAND_MODEL_METHOD_VERSION,
        "model_version": policy.model_version,
        "kind": kind.value,
        "target_scope": policy.target_scope.value,
        "region": policy.region,
        "target_unit": policy.target_unit,
        "gas_day_calendar": policy.gas_day_calendar,
        "feature_policy_hash": policy.expected_feature_policy.policy_hash,
        "training_cutoff": cutoff.isoformat(),
        "calendar_method": CALENDAR_FEATURE_METHOD,
        "training_rows": len(rows),
        "source_refs": list(sources),
        "target_revision_ids": list(revisions),
        "weather_vintage_ids": list(vintages),
        "validation_basis": policy.validation_basis.value,
    }


def _fit_baseline(
    rows: tuple[TrainingRow, ...],
    policy: DemandModelPolicy,
    cutoff: datetime,
) -> FittedDemandModel:
    """Fit the explicit month-mean seasonal calendar baseline."""

    if not rows:
        raise WeatherDemandInputError("cannot fit baseline without training rows")
    values_by_month: dict[int, list[float]] = {}
    for gas_day, value, _, _ in rows:
        values_by_month.setdefault(gas_day.month, []).append(value)
    month_means = tuple(
        (month, math.fsum(values) / len(values))
        for month, values in sorted(values_by_month.items())
    )
    overall_mean = math.fsum(row[1] for row in rows) / len(rows)
    sources, revisions, vintages = _training_provenance(rows)
    payload = _base_payload(policy, ModelKind.CALENDAR_BASELINE, cutoff, rows)
    payload.update(
        {
            "month_means": [[month, value] for month, value in month_means],
            "overall_mean": overall_mean,
        }
    )
    return FittedDemandModel(
        kind=ModelKind.CALENDAR_BASELINE,
        model_version=policy.model_version,
        method_version=BASELINE_METHOD_VERSION,
        target_scope=policy.target_scope,
        region=policy.region,
        target_unit=policy.target_unit,
        gas_day_calendar=policy.gas_day_calendar,
        feature_policy_hash=policy.expected_feature_policy.policy_hash,
        training_cutoff=cutoff,
        feature_names=(),
        feature_means=(),
        feature_scales=(),
        coefficients=(),
        intercept=0.0,
        month_means=month_means,
        overall_mean=overall_mean,
        ridge_lambda=None,
        calendar_method=CALENDAR_FEATURE_METHOD,
        training_rows=len(rows),
        source_refs=sources,
        target_revision_ids=revisions,
        weather_vintage_ids=vintages,
        validation_basis=policy.validation_basis,
        use_status=ModelUseStatus.CALENDAR_BASELINE_REFERENCE,
        model_hash=_canonical_hash(payload),
    )


def _fit_candidate(
    rows: tuple[TrainingRow, ...],
    policy: DemandModelPolicy,
    cutoff: datetime,
) -> FittedDemandModel | None:
    """Fit the standardized weather-plus-calendar ridge candidate via NumPy SVD."""

    if not rows:
        return None
    np = _numpy()
    feature_names = _feature_names(policy)
    if len(feature_names) > policy.max_features:
        raise WeatherDemandInputError("candidate feature budget exceeded")
    matrix_rows: list[tuple[float, ...]] = []
    targets: list[float] = []
    for gas_day, value, _, feature in rows:
        vector = _candidate_row(gas_day, feature, policy)
        if vector is None:
            continue
        matrix_rows.append(vector)
        targets.append(value)
    if not matrix_rows:
        return None
    matrix = np.asarray(matrix_rows, dtype=float)
    target_array = np.asarray(targets, dtype=float)
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales > 0.0, scales, 1.0)
    standardized = (matrix - means) / scales
    design = np.column_stack((np.ones(len(matrix_rows)), standardized))
    # Penalize standardized feature coefficients only; the intercept stays free.
    penalty = math.sqrt(policy.ridge_lambda) * np.eye(len(feature_names) + 1)
    penalty[0, 0] = 0.0
    augmented = np.vstack((design, penalty))
    augmented_target = np.concatenate((target_array, np.zeros(len(feature_names) + 1)))
    solution = np.linalg.lstsq(augmented, augmented_target, rcond=None)[0]
    if not np.all(np.isfinite(solution)):
        raise WeatherDemandInputError("ridge solver produced non-finite coefficients")
    intercept = float(solution[0])
    coefficients = tuple(float(value) for value in solution[1:])
    feature_means = tuple(float(value) for value in means)
    feature_scales = tuple(float(value) for value in scales)
    sources, revisions, vintages = _training_provenance(rows)
    payload = _base_payload(policy, ModelKind.WEATHER_CALENDAR_RIDGE, cutoff, rows)
    payload.update(
        {
            "feature_names": list(feature_names),
            "feature_means": list(feature_means),
            "feature_scales": list(feature_scales),
            "intercept": intercept,
            "coefficients": list(coefficients),
            "ridge_lambda": policy.ridge_lambda,
        }
    )
    return FittedDemandModel(
        kind=ModelKind.WEATHER_CALENDAR_RIDGE,
        model_version=policy.model_version,
        method_version=DEMAND_MODEL_METHOD_VERSION,
        target_scope=policy.target_scope,
        region=policy.region,
        target_unit=policy.target_unit,
        gas_day_calendar=policy.gas_day_calendar,
        feature_policy_hash=policy.expected_feature_policy.policy_hash,
        training_cutoff=cutoff,
        feature_names=feature_names,
        feature_means=feature_means,
        feature_scales=feature_scales,
        coefficients=coefficients,
        intercept=intercept,
        month_means=(),
        overall_mean=float(target_array.mean()),
        ridge_lambda=policy.ridge_lambda,
        calendar_method=CALENDAR_FEATURE_METHOD,
        training_rows=len(rows),
        source_refs=sources,
        target_revision_ids=revisions,
        weather_vintage_ids=vintages,
        validation_basis=policy.validation_basis,
        use_status=ModelUseStatus.UNVALIDATED_OOS_RESEARCH_OUTPUT,
        model_hash=_canonical_hash(payload),
    )


def _predict_baseline(model: FittedDemandModel, gas_day: date) -> float:
    """Predict from the explicit month mean, falling back only to overall mean."""

    for month, value in model.month_means:
        if month == gas_day.month:
            return value
    return model.overall_mean


def _predict_candidate(model: FittedDemandModel, row: tuple[float, ...]) -> float:
    """Apply the frozen training scaler and coefficients to one feature row."""

    total = model.intercept
    for coefficient, mean, scale, value in zip(
        model.coefficients, model.feature_means, model.feature_scales, row, strict=True
    ):
        total += coefficient * ((value - mean) / scale)
    return total


def _metrics(actual: list[float], predicted: list[float]) -> ModelMetrics | None:
    """Calculate aggregate errors only when paired held-out values exist."""

    count = len(actual)
    if count == 0 or len(predicted) != count:
        return None
    errors = [pred - observed for pred, observed in zip(predicted, actual, strict=True)]
    return ModelMetrics(
        mae=math.fsum(abs(error) for error in errors) / count,
        rmse=math.sqrt(math.fsum(error * error for error in errors) / count),
        bias=math.fsum(errors) / count,
        count=count,
    )


def _run_oos(
    targets: tuple[DemandTargetRow, ...],
    features: tuple[DailyWeatherFeature, ...],
    policy: DemandModelPolicy,
) -> tuple[
    tuple[DemandFoldResult, ...],
    ModelMetrics | None,
    ModelMetrics | None,
    float,
    tuple[float, ...],
]:
    """Run deterministic daily expanding folds after the frozen training cutoff."""

    final_truth = _resolve_targets(targets, policy.validation_as_of)
    holdout_days = []
    for gas_day in sorted(final_truth):
        start = gas_day_start_for_date(gas_day, policy.gas_day_calendar)
        end = gas_day_start_for_date(gas_day + timedelta(days=1), policy.gas_day_calendar)
        if start < policy.training_cutoff:
            continue
        if end > policy.validation_as_of:
            continue
        holdout_days.append(gas_day)
    if len(holdout_days) > policy.max_folds:
        holdout_days = holdout_days[-policy.max_folds :]

    input_type = features[0].input_type
    folds: list[DemandFoldResult] = []
    actual_values: list[float] = []
    baseline_values: list[float] = []
    candidate_values: list[float] = []
    residuals: list[float] = []
    for gas_day in holdout_days:
        day_start = gas_day_start_for_date(gas_day, policy.gas_day_calendar)
        if input_type is TemperatureInputType.FORECAST_VINTAGE:
            fold_origin = day_start
            feature = _pick_feature(features, gas_day, fold_origin, input_type)
        else:
            feature = _pick_feature(features, gas_day, policy.validation_as_of, input_type)
            if feature is not None:
                fold_origin = max(day_start, feature.available_at, feature.prediction_origin)
            else:
                fold_origin = day_start
        if feature is None:
            continue
        training = _prepare_training(
            targets,
            features,
            policy,
            fold_origin,
            before_day=gas_day,
        )
        if len(training) < policy.min_training_rows:
            continue
        baseline = _fit_baseline(training, policy, fold_origin)
        candidate = _fit_candidate(training, policy, fold_origin)
        if candidate is None:
            continue
        row = _candidate_row(gas_day, feature, policy)
        if row is None:
            continue
        actual = final_truth[gas_day].value
        baseline_prediction = _predict_baseline(baseline, gas_day)
        candidate_prediction = _predict_candidate(candidate, row)
        folds.append(
            DemandFoldResult(
                fold_origin=fold_origin,
                validation_gas_day=gas_day,
                training_rows=len(training),
                actual_value=actual,
                baseline_prediction=baseline_prediction,
                candidate_prediction=candidate_prediction,
                input_type=input_type,
            )
        )
        actual_values.append(actual)
        baseline_values.append(baseline_prediction)
        candidate_values.append(candidate_prediction)
        residuals.append(actual - candidate_prediction)

    coverage = len(folds) / len(holdout_days) if holdout_days else 0.0
    return (
        tuple(folds),
        _metrics(actual_values, baseline_values),
        _metrics(actual_values, candidate_values),
        coverage,
        tuple(residuals),
    )


def _estimate_uncertainty(
    selected: FittedDemandModel,
    basis: ValidationBasis,
    residuals: tuple[float, ...],
    policy: DemandModelPolicy,
) -> tuple[ResidualUncertainty | None, str | None]:
    """Return an empirical interval only when held-out residual evidence permits it."""

    if selected.kind is not ModelKind.WEATHER_CALENDAR_RIDGE:
        return None, "SELECTED_MODEL_HAS_NO_HELDOUT_WEATHER_RESIDUALS"
    if basis is ValidationBasis.SYNTHETIC_NOT_REAL:
        return None, "SYNTHETIC_BASIS_HAS_NO_VALIDATED_INTERVAL"
    if len(residuals) < policy.min_residuals_for_interval:
        return (
            None,
            f"INSUFFICIENT_HELDOUT_RESIDUALS:{len(residuals)}<{policy.min_residuals_for_interval}",
        )
    np = _numpy()
    alpha = (1.0 - policy.interval_level) / 2.0
    lower, upper = np.quantile(np.asarray(residuals, dtype=float), [alpha, 1.0 - alpha])
    return (
        ResidualUncertainty(
            level=policy.interval_level,
            lower_offset=float(lower),
            upper_offset=float(upper),
            residual_count=len(residuals),
            method_version=RESIDUAL_INTERVAL_METHOD_VERSION,
        ),
        None,
    )


def fit_weather_demand_model(
    targets: tuple[DemandTargetRow, ...],
    features: tuple[DailyWeatherFeature, ...],
    policy: DemandModelPolicy,
) -> DemandModelResult:
    """Fit and compare the baseline and weather candidate at explicit cutoffs.

    All target revisions and weather rows are filtered by their independent
    availability and prediction origin before transformation. Standardization is
    learned only from each fold's training rows, the intercept is unpenalized,
    and the solver is NumPy ``lstsq`` (SVD), never a hand-rolled matrix inverse.
    Selection is reported as insufficient, baseline-retained, or candidate-selected
    using the policy's measured rule. The result is always research-only.
    """

    _numpy()
    if not isinstance(policy, DemandModelPolicy):
        raise TypeError("policy must be a DemandModelPolicy")
    target_rows = tuple(targets)
    feature_rows = tuple(features)
    _validate_targets(target_rows, policy)
    _validate_features(feature_rows, policy)
    if _feature_count(policy) > policy.max_features:
        raise WeatherDemandInputError("candidate feature budget exceeded")
    training = _prepare_training(
        target_rows,
        feature_rows,
        policy,
        policy.training_cutoff,
    )
    if not training:
        raise WeatherDemandInputError("no training rows were available at training_cutoff")

    baseline_model = _fit_baseline(training, policy, policy.training_cutoff)
    candidate_model = _fit_candidate(training, policy, policy.training_cutoff)
    folds, baseline_oos, candidate_oos, coverage, residuals = _run_oos(
        target_rows, feature_rows, policy
    )
    fold_win_fraction = _fold_win_fraction(folds)

    status = ModelSelectionStatus.INSUFFICIENT_DATA
    reason = "NO_HELDOUT_FOLDS"
    if len(training) < policy.min_training_rows:
        reason = f"TRAINING_ROWS:{len(training)}<{policy.min_training_rows}"
    elif candidate_model is None:
        reason = "CANDIDATE_NOT_FITTED"
    elif len(folds) < policy.min_validation_folds:
        reason = f"VALIDATION_FOLDS:{len(folds)}<{policy.min_validation_folds}"
    elif len(folds) < policy.min_validation_predictions:
        reason = f"VALIDATION_PREDICTIONS:{len(folds)}<{policy.min_validation_predictions}"
    elif coverage + 1e-12 < policy.min_oos_coverage:
        reason = f"OOS_COVERAGE:{coverage:.4f}<{policy.min_oos_coverage:.4f}"
    elif baseline_oos is None or candidate_oos is None:
        reason = "BASELINE_OR_CANDIDATE_ERROR_NOT_MEASURABLE"
    elif baseline_oos.mae <= 0.0:
        status = ModelSelectionStatus.BASELINE_RETAINED
        reason = "BASELINE_ZERO_ERROR;CANDIDATE_CANNOT_BE_SHOWN_BETTER"
    else:
        improvement = (baseline_oos.mae - candidate_oos.mae) / baseline_oos.mae
        rmse_not_worse = candidate_oos.rmse <= baseline_oos.rmse
        if (
            improvement + 1e-12 >= policy.min_relative_mae_improvement
            and fold_win_fraction + 1e-12 >= policy.min_fold_win_fraction
            and rmse_not_worse
        ):
            status = ModelSelectionStatus.CANDIDATE_SELECTED
            reason = (
                f"MAE_IMPROVEMENT:{improvement:.4f}>={policy.min_relative_mae_improvement:.4f}"
                f";FOLD_WIN_FRACTION:{fold_win_fraction:.4f}"
                f">={policy.min_fold_win_fraction:.4f};RMSE_NOT_WORSE"
            )
        else:
            status = ModelSelectionStatus.BASELINE_RETAINED
            reason = (
                f"MAE_IMPROVEMENT:{improvement:.4f}<{policy.min_relative_mae_improvement:.4f}"
                f" OR FOLD_WIN_FRACTION:{fold_win_fraction:.4f}"
                f"<{policy.min_fold_win_fraction:.4f} OR RMSE_WORSE"
            )

    selected = (
        candidate_model
        if status is ModelSelectionStatus.CANDIDATE_SELECTED and candidate_model is not None
        else baseline_model
    )
    uncertainty, uncertainty_reason = _estimate_uncertainty(
        selected, policy.validation_basis, residuals, policy
    )
    selection_evidence = DemandSelectionEvidence(
        validation_as_of=policy.validation_as_of,
        selected_model_hash=selected.model_hash,
        baseline_model_hash=baseline_model.model_hash,
        candidate_model_hash=(
            candidate_model.model_hash if candidate_model is not None else None
        ),
        selection_status=status,
        selection_reason=reason,
        validation_basis=policy.validation_basis,
        baseline_oos=baseline_oos,
        candidate_oos=candidate_oos,
        fold_count=len(folds),
        fold_win_fraction=fold_win_fraction,
        oos_coverage=coverage,
        residual_count=len(residuals),
        folds=folds,
        uncertainty=uncertainty,
        uncertainty_reason=uncertainty_reason,
        policy_thresholds=(
            ("min_training_rows", float(policy.min_training_rows)),
            ("min_validation_folds", float(policy.min_validation_folds)),
            ("min_validation_predictions", float(policy.min_validation_predictions)),
            ("min_oos_coverage", policy.min_oos_coverage),
            ("min_relative_mae_improvement", policy.min_relative_mae_improvement),
            ("min_fold_win_fraction", policy.min_fold_win_fraction),
            ("min_residuals_for_interval", float(policy.min_residuals_for_interval)),
            ("interval_level", policy.interval_level),
            ("max_training_rows", float(policy.max_training_rows)),
            ("max_folds", float(policy.max_folds)),
            ("max_features", float(policy.max_features)),
            ("ridge_lambda", policy.ridge_lambda),
        ),
    )
    return DemandModelResult(
        baseline_model=baseline_model,
        candidate_model=candidate_model,
        selected_model=selected,
        selection_status=status,
        selection_reason=reason,
        validation_basis=policy.validation_basis,
        folds=folds,
        baseline_oos=baseline_oos,
        candidate_oos=candidate_oos,
        oos_coverage=coverage,
        residual_count=len(residuals),
        uncertainty=uncertainty,
        uncertainty_reason=uncertainty_reason,
        production_promotion=PromotionStatus.NOT_PROMOTED,
        prediction_label="MODEL_OUTPUT",
        selection_evidence=selection_evidence,
    )


_WEATHER_COLUMN_TO_FEATURE = {
    "weather_hdd_mean": WeatherFeature.HDD_MEAN,
    "weather_cdd_mean": WeatherFeature.CDD_MEAN,
    "weather_hdd_integral": WeatherFeature.HDD_INTEGRAL,
    "weather_cdd_integral": WeatherFeature.CDD_INTEGRAL,
}

_CALENDAR_FEATURE_NAMES = (
    "calendar_sin_annual",
    "calendar_cos_annual",
    "weekday_tue",
    "weekday_wed",
    "weekday_thu",
    "weekday_fri",
    "weekday_sat",
    "weekday_sun",
)


def _metrics_payload(metrics: ModelMetrics | None) -> dict[str, object] | None:
    """Return a deterministic JSON-safe identity for optional measured metrics."""

    if metrics is None:
        return None
    return {
        "mae": metrics.mae,
        "rmse": metrics.rmse,
        "bias": metrics.bias,
        "count": metrics.count,
    }


def _assert_result_matches_evidence(
    result: DemandModelResult, evidence: DemandSelectionEvidence
) -> None:
    """Refuse a result whose retained selection evidence no longer describes it."""

    candidate_hash = (
        result.candidate_model.model_hash if result.candidate_model is not None else None
    )
    checks = (
        (
            evidence.selected_model_hash == result.selected_model.model_hash,
            "selection evidence selected-model hash does not match the fitted selected model",
        ),
        (
            evidence.baseline_model_hash == result.baseline_model.model_hash,
            "selection evidence baseline-model hash does not match the fitted baseline model",
        ),
        (
            evidence.candidate_model_hash == candidate_hash,
            "selection evidence candidate-model hash does not match the fitted candidate model",
        ),
        (
            evidence.selection_status is result.selection_status,
            "selection evidence selection status does not match the fitted result",
        ),
        (
            evidence.selection_reason == result.selection_reason,
            "selection evidence selection reason does not match the fitted result",
        ),
        (
            evidence.validation_basis is result.validation_basis,
            "selection evidence validation basis does not match the fitted result",
        ),
        (
            evidence.baseline_oos == result.baseline_oos,
            "selection evidence baseline metrics do not match the fitted result",
        ),
        (
            evidence.candidate_oos == result.candidate_oos,
            "selection evidence candidate metrics do not match the fitted result",
        ),
        (
            evidence.folds == result.folds,
            "selection evidence fold evidence does not match the fitted result",
        ),
        (
            evidence.fold_count == len(result.folds),
            "selection evidence fold count does not match the fitted result",
        ),
        (
            evidence.fold_win_fraction == _fold_win_fraction(result.folds),
            "selection evidence fold-win fraction does not match the fold evidence",
        ),
        (
            evidence.oos_coverage == result.oos_coverage,
            "selection evidence OOS coverage does not match the fitted result",
        ),
        (
            evidence.residual_count == result.residual_count,
            "selection evidence residual count does not match the fitted result",
        ),
        (
            evidence.uncertainty == result.uncertainty,
            "selection evidence uncertainty payload does not match the fitted result",
        ),
        (
            evidence.uncertainty_reason == result.uncertainty_reason,
            "selection evidence uncertainty reason does not match the fitted result",
        ),
    )
    for matches, message in checks:
        if not matches:
            raise WeatherDemandInputError(message)


def _require_selection_evidence(
    result: DemandModelResult, prediction_origin: datetime
) -> DemandSelectionEvidence:
    """Refuse unavailable or inconsistent selection evidence before consumption."""

    if not isinstance(result, DemandModelResult):
        raise TypeError("result must be a DemandModelResult")
    evidence = result.selection_evidence
    if evidence is None:
        raise SelectionEvidenceUnavailableError(
            "fitted result has no selection evidence; refusing to consume coefficients"
        )
    origin = _utc(prediction_origin, "prediction_origin")
    if origin < evidence.validation_as_of:
        raise SelectionEvidenceUnavailableError(
            "selected model and interval evidence are unavailable before "
            f"validation_as_of {evidence.validation_as_of.isoformat()}"
        )
    _assert_result_matches_evidence(result, evidence)
    return evidence


def _validate_prediction_target(
    model: FittedDemandModel, request: DemandPredictionRequest
) -> None:
    """Check the explicit target identity against the frozen fitted model."""

    if request.target_scope is not model.target_scope:
        raise WeatherDemandInputError("prediction target scope does not match the fitted model")
    if request.region != model.region:
        raise WeatherDemandInputError("prediction target region does not match the fitted model")
    if request.target_unit != model.target_unit:
        raise WeatherDemandInputError("prediction native unit does not match the fitted model")
    if request.gas_day_calendar != model.gas_day_calendar:
        raise WeatherDemandInputError("prediction gas-day calendar does not match the fitted model")
    gas_day_end = gas_day_start_for_date(
        request.gas_day + timedelta(days=1), request.gas_day_calendar
    )
    if gas_day_end <= request.prediction_origin:
        raise WeatherDemandInputError(
            "prediction gas day is already complete at the explicit prediction origin"
        )


def _validate_forecast_feature(
    model: FittedDemandModel,
    request: DemandPredictionRequest,
    feature: DailyWeatherFeature,
) -> ForecastVintageRef:
    """Validate point-in-time forecast evidence without requiring past validity."""

    if feature.gas_day != request.gas_day:
        raise WeatherDemandInputError("weather feature gas day does not match the target gas day")
    if feature.feature_policy.region != model.region:
        raise WeatherDemandInputError("weather feature region does not match the fitted model")
    if feature.feature_policy.gas_day_calendar != model.gas_day_calendar:
        raise WeatherDemandInputError("weather feature calendar does not match the fitted model")
    if feature.feature_policy_hash != model.feature_policy_hash:
        raise WeatherDemandInputError(
            "weather feature policy fingerprint does not match the fitted model"
        )
    if feature.input_type is not TemperatureInputType.FORECAST_VINTAGE:
        raise WeatherDemandInputError(
            "forward weather prediction requires a forecast vintage; realized weather "
            "cannot masquerade as a forecast"
        )
    vintage = feature.forecast_vintage
    if vintage is None:
        raise WeatherDemandInputError("forward weather prediction requires a forecast vintage")
    if feature.available_at > request.prediction_origin:
        raise WeatherDemandInputError("weather feature was not available at the prediction origin")
    if feature.prediction_origin > request.prediction_origin:
        raise WeatherDemandInputError(
            "weather feature prediction origin is after the requested prediction origin"
        )
    if vintage.issued_at > request.prediction_origin:
        raise WeatherDemandInputError(
            "weather forecast issue time is after the requested prediction origin"
        )
    return vintage


def _validate_weather_model_shape(model: FittedDemandModel) -> None:
    """Refuse a malformed frozen weather model before applying any coefficient."""

    if model.kind is not ModelKind.WEATHER_CALENDAR_RIDGE:
        raise WeatherDemandInputError("selected model is not a weather-calendar ridge model")
    if len(model.feature_names) <= len(_CALENDAR_FEATURE_NAMES):
        raise WeatherDemandInputError("fitted weather model has no weather feature columns")
    if model.feature_names[: len(_CALENDAR_FEATURE_NAMES)] != _CALENDAR_FEATURE_NAMES:
        raise WeatherDemandInputError("fitted weather model calendar feature names are unsupported")
    lengths = {
        len(model.feature_names),
        len(model.feature_means),
        len(model.feature_scales),
        len(model.coefficients),
    }
    if len(lengths) != 1:
        raise WeatherDemandInputError("fitted weather model arrays have inconsistent lengths")
    if not math.isfinite(model.intercept):
        raise WeatherDemandInputError("fitted weather model intercept is not finite")
    if any(not math.isfinite(value) for value in model.feature_means):
        raise WeatherDemandInputError("fitted weather model means are not finite")
    if any(not math.isfinite(value) or value <= 0.0 for value in model.feature_scales):
        raise WeatherDemandInputError("fitted weather model scales are not finite and positive")
    if any(not math.isfinite(value) for value in model.coefficients):
        raise WeatherDemandInputError("fitted weather model coefficients are not finite")


def _validate_baseline_model_shape(model: FittedDemandModel) -> None:
    """Refuse a malformed frozen baseline before returning a month mean."""

    if model.kind is not ModelKind.CALENDAR_BASELINE:
        raise WeatherDemandInputError("model is not a calendar baseline")
    if not math.isfinite(model.overall_mean):
        raise WeatherDemandInputError("fitted baseline overall mean is not finite")
    if any(not math.isfinite(value) for _, value in model.month_means):
        raise WeatherDemandInputError("fitted baseline month means are not finite")


def _prediction_row(
    model: FittedDemandModel, gas_day: date, feature: DailyWeatherFeature
) -> tuple[tuple[float, ...], tuple[PredictionFeatureRef, ...]]:
    """Build the candidate row from the frozen feature names and scalers."""

    values = list(_calendar_values(gas_day))
    refs: list[PredictionFeatureRef] = []
    for name in model.feature_names[len(_CALENDAR_FEATURE_NAMES) :]:
        weather_feature = _WEATHER_COLUMN_TO_FEATURE.get(name)
        if weather_feature is None:
            raise WeatherDemandInputError(
                f"fitted weather model contains unsupported feature name {name!r}"
            )
        value = feature.value_for(weather_feature)
        if value is None:
            raise MissingWeatherFeatureError(
                f"weather model requires {weather_feature.value}, but the feature row is missing it"
            )
        values.append(value)
        refs.append(PredictionFeatureRef(name=name, value=value))
    return tuple(values), tuple(refs)


def _finite_prediction(value: float) -> float:
    """Refuse non-finite or negative native-unit estimates without clamping."""

    resolved = float(value)
    if not math.isfinite(resolved):
        raise WeatherDemandInputError("prediction value must be finite")
    if resolved < 0.0:
        raise NegativeDemandEstimateError(
            "prediction is negative in the native demand unit; refusing to clamp it"
        )
    return resolved


def _prediction_interval(
    result: DemandModelResult,
    model: FittedDemandModel,
    value: float,
) -> tuple[DemandPredictionInterval | None, str | None]:
    """Use only stored, supported held-out residual evidence for an interval."""

    if model.kind is not ModelKind.WEATHER_CALENDAR_RIDGE:
        return None, "BASELINE_MODEL_HAS_NO_HELDOUT_RESIDUAL_INTERVAL"
    uncertainty = result.uncertainty
    if uncertainty is None:
        return None, result.uncertainty_reason or "NO_HELDOUT_RESIDUAL_INTERVAL"
    if result.validation_basis is ValidationBasis.SYNTHETIC_NOT_REAL:
        raise WeatherPredictionInputError(
            "synthetic validation evidence cannot support a prediction interval"
        )
    if uncertainty.method_version != RESIDUAL_INTERVAL_METHOD_VERSION:
        raise WeatherPredictionInputError("unsupported held-out residual interval method")
    if uncertainty.residual_count < 1 or uncertainty.residual_count > result.residual_count:
        raise WeatherPredictionInputError(
            "held-out residual count does not support the stored interval"
        )
    lower = value + uncertainty.lower_offset
    upper = value + uncertainty.upper_offset
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise WeatherPredictionInputError("held-out residual interval is not finite and ordered")
    return (
        DemandPredictionInterval(
            lower=lower,
            upper=upper,
            level=uncertainty.level,
            residual_count=uncertainty.residual_count,
            method_version=uncertainty.method_version,
        ),
        None,
    )


def predict_selected_demand(
    result: DemandModelResult, request: DemandPredictionRequest
) -> DemandPrediction:
    """Predict from the selected frozen model for an explicit future target.

    Selection and interval evidence are available only at ``validation_as_of``.
    A weather model consumes exactly one already-available forecast feature row
    and never refits, consults targets or uses a realized observation as a
    forward forecast. A selected calendar baseline refuses weather input and
    returns an explicitly labelled baseline reference.
    """

    if not isinstance(request, DemandPredictionRequest):
        raise TypeError("request must be a DemandPredictionRequest")
    evidence = _require_selection_evidence(result, request.prediction_origin)
    model = result.selected_model
    _validate_prediction_target(model, request)

    if model.kind is ModelKind.WEATHER_CALENDAR_RIDGE:
        feature = request.weather_feature
        if feature is None:
            raise MissingWeatherFeatureError(
                "weather model prediction requires one DailyWeatherFeature"
            )
        vintage = _validate_forecast_feature(model, request, feature)
        _validate_weather_model_shape(model)
        row, refs = _prediction_row(model, request.gas_day, feature)
        value = _finite_prediction(_predict_candidate(model, row))
        interval, interval_reason = _prediction_interval(result, model, value)
        return DemandPrediction(
            gas_day=request.gas_day,
            prediction_origin=request.prediction_origin,
            target_scope=request.target_scope,
            region=request.region,
            target_unit=request.target_unit,
            gas_day_calendar=request.gas_day_calendar,
            model_kind=model.kind,
            model_version=model.model_version,
            method_version=model.method_version,
            prediction_label="MODEL_OUTPUT",
            use_status=model.use_status,
            value=value,
            model_hash=model.model_hash,
            selection_hash=evidence.selection_hash,
            selection_as_of=evidence.validation_as_of,
            feature_policy_hash=model.feature_policy_hash,
            feature_refs=refs,
            weather_source_ref=feature.source_ref,
            weather_available_at=feature.available_at,
            forecast_vintage=vintage,
            interval=interval,
            interval_reason=interval_reason,
        )

    if model.kind is ModelKind.CALENDAR_BASELINE:
        if request.weather_feature is not None:
            raise WeatherDemandInputError(
                "selected calendar baseline does not consume weather features; use "
                "predict_baseline_demand for an explicit baseline reference"
            )
        _validate_baseline_model_shape(model)
        value = _finite_prediction(_predict_baseline(model, request.gas_day))
        return DemandPrediction(
            gas_day=request.gas_day,
            prediction_origin=request.prediction_origin,
            target_scope=request.target_scope,
            region=request.region,
            target_unit=request.target_unit,
            gas_day_calendar=request.gas_day_calendar,
            model_kind=model.kind,
            model_version=model.model_version,
            method_version=model.method_version,
            prediction_label=ModelUseStatus.CALENDAR_BASELINE_REFERENCE.value,
            use_status=model.use_status,
            value=value,
            model_hash=model.model_hash,
            selection_hash=evidence.selection_hash,
            selection_as_of=evidence.validation_as_of,
            feature_policy_hash=model.feature_policy_hash,
            feature_refs=(),
            weather_source_ref=None,
            weather_available_at=None,
            forecast_vintage=None,
            interval=None,
            interval_reason="BASELINE_MODEL_HAS_NO_HELDOUT_RESIDUAL_INTERVAL",
        )

    raise WeatherDemandInputError("unsupported selected model kind")


def predict_baseline_demand(
    result: DemandModelResult, request: DemandPredictionRequest
) -> DemandPrediction:
    """Return an explicitly labelled calendar-baseline prediction.

    This path always uses the frozen baseline month means. It refuses weather
    input instead of pretending weather sensitivity, and it never applies a
    weather candidate's residual interval. Selection evidence is still required
    because the fitted result's selection status is unavailable before
    ``validation_as_of``.
    """

    if not isinstance(request, DemandPredictionRequest):
        raise TypeError("request must be a DemandPredictionRequest")
    evidence = _require_selection_evidence(result, request.prediction_origin)
    if request.weather_feature is not None:
        raise WeatherDemandInputError(
            "explicit baseline prediction does not consume weather features"
        )
    model = result.baseline_model
    _validate_prediction_target(model, request)
    _validate_baseline_model_shape(model)
    value = _finite_prediction(_predict_baseline(model, request.gas_day))
    return DemandPrediction(
        gas_day=request.gas_day,
        prediction_origin=request.prediction_origin,
        target_scope=request.target_scope,
        region=request.region,
        target_unit=request.target_unit,
        gas_day_calendar=request.gas_day_calendar,
        model_kind=model.kind,
        model_version=model.model_version,
        method_version=model.method_version,
        prediction_label=ModelUseStatus.CALENDAR_BASELINE_REFERENCE.value,
        use_status=ModelUseStatus.CALENDAR_BASELINE_REFERENCE,
        value=value,
        model_hash=model.model_hash,
        selection_hash=evidence.selection_hash,
        selection_as_of=evidence.validation_as_of,
        feature_policy_hash=model.feature_policy_hash,
        feature_refs=(),
        weather_source_ref=None,
        weather_available_at=None,
        forecast_vintage=None,
        interval=None,
        interval_reason="EXPLICIT_BASELINE_REFERENCE_HAS_NO_HELDOUT_RESIDUAL_INTERVAL",
    )
