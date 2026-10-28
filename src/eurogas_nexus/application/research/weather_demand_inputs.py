"""Bounded, pure bridge from persisted ECMWF 2t instants to degree-day inputs.

The caller owns persistence access, entitlement/ACL checks and source activation.
This adapter consumes already-projected, read-only forecast rows and explicit
point bindings only: it performs no query, ORM write, fetch, API/SDK call or
registry mutation.

ECMWF ``2t`` is an instantaneous field.  The adapter therefore never labels an
instant as a provider interval mean and never invents a mean.  It holds the left
sample forward only to the next observed instant, and only when that adjacent
gap is explicitly bounded.  The right sample is retained as bracketing evidence,
not as a value to interpolate.  Means are approximate physical floats, not
financial-exact arithmetic.

The bridge selects one newest eligible provider/model/run/issue vintage globally.
Within that vintage it selects one source-field revision per point and valid
time by actual receipt availability, and refuses to mix two field revisions at
one valid time.  Missing point coverage remains missing; no older run fills it.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
from eurogas_nexus.domain.research.weather_demand import (
    DegreeDayFeaturePolicy,
    DegreeDayPolicy,
    DegreeDayRequest,
    DegreeDayResult,
    ForecastTemperatureInterval,
    ForecastVintageRef,
    TemperatureDerivationMethod,
    WeatherDemandInputError,
    compute_degree_days,
)

if TYPE_CHECKING:
    # Imported for typing only: the projection is a pure structural read of the
    # existing persisted record and does not import or query the ORM at runtime.
    from eurogas_nexus.db.models.research import ForecastObservationRecord

SOURCE_SYSTEM = "ECMWF_OPEN_DATA"
MODEL_PROVIDER = "ECMWF"
QUALITY_STATE = "FORECAST"
CANONICAL_UNIT = "degC"
KELVIN_OFFSET = 273.15
KELVIN_TOLERANCE = 1e-9
MIN_TEMPERATURE_C = -100.0
MAX_TEMPERATURE_C = 70.0
MAX_HOLD_MINUTES = 10_080
MAX_ROWS = 1_000_000
MAX_POINTS = 10_000
MAX_WINDOW_DAYS = 366
MAX_CROSS_PRODUCT = 10_000_000
MAX_INTERVALS = 1_000_000
DERIVED_LEFT_HOLD_APPROXIMATION = "DERIVED_LEFT_HOLD"
# The reviewed ECMWF Open Data product is IFS.  The persistence schema has no
# model-name column, so the projection accepts this name only when the persisted
# asset URL names that same reviewed model.
ECMWF_MODEL = "ifs"
PERSISTED_PROVENANCE_SCHEMA = "ecmwf-open-data-forecast-observation/v3"
PERSISTED_TEMPORAL_END = "zero_length_interval_due_to_existing_non_null_schema"

# The accepted domain core currently spells explicit left-hold as
# ``EXPLICIT_DERIVED_HOLD``.  Keep the bridge's semantic name explicit rather
# than pretending the provider supplied an interval mean.
LEFT_HOLD_INSTANT = TemperatureDerivationMethod.EXPLICIT_DERIVED_HOLD


class ForecastBridgeError(WeatherDemandInputError):
    """Base typed refusal for the forecast-to-degree-day adapter."""

    code = "FORECAST_BRIDGE_ERROR"


class ForecastBridgeValidationError(ForecastBridgeError):
    """A row, binding, policy or provenance field violates the frozen contract."""

    code = "FORECAST_BRIDGE_VALIDATION_ERROR"


class ForecastBridgeAmbiguityError(ForecastBridgeError):
    """Two equally eligible inputs would require an arbitrary selection."""

    code = "FORECAST_BRIDGE_AMBIGUITY_ERROR"


class ForecastFieldRevisionConflictError(ForecastBridgeError):
    """Required points at one valid time carry different source-field revisions."""

    code = "FORECAST_FIELD_REVISION_CONFLICT"


class ForecastBridgeNotReadyError(ForecastBridgeError):
    """No typed degree-day request can be built from an all-missing bridge."""

    code = "FORECAST_BRIDGE_NOT_READY"


class WeatherDemandInputStatus(StrEnum):
    """Whether at least one derived interval is available for the window."""

    READY = "READY"
    MISSING = "MISSING"


class WeatherDemandDiagnosticCode(StrEnum):
    """Stable, operator-safe reasons for missing bridge coverage."""

    NO_ELIGIBLE_FORECAST = "NO_ELIGIBLE_FORECAST"
    MISSING_POINT_BINDING = "MISSING_POINT_BINDING"
    NO_POINT_OBSERVATIONS = "NO_POINT_OBSERVATIONS"
    HOLD_GAP_EXCEEDED = "HOLD_GAP_EXCEEDED"
    NO_LEFT_BRACKET = "NO_LEFT_BRACKET"
    NO_RIGHT_BRACKET = "NO_RIGHT_BRACKET"
    NO_INTERVALS_IN_WINDOW = "NO_INTERVALS_IN_WINDOW"


@dataclass(frozen=True)
class ForecastPointBinding:
    """Explicit caller-supplied identity and region weight binding for one point.

    The binding is input only.  This module never discovers, creates or infers a
    series, canonical entity, source mapping or observing station.
    """

    point_id: str
    series_id: str
    entity_id: str
    location_id: str
    region: str


@dataclass(frozen=True)
class ForecastInstantRow:
    """Read-only projection of one persisted instantaneous forecast observation.

    ``valid_end_utc`` must be ``None``: the existing database table stores a
    non-null zero-length end for schema reasons, while the semantic provider
    metadata records an absent interval end.  ``source_field_hash`` is the
    canonical hash of ``provenance.source_field_version``; the repository's
    per-point ``record_content_sha256`` and raw ``grib_sha256`` travel separately
    so both boundaries can be bound into an interval reference.
    """

    forecast_observation_id: str
    point_id: str
    series_id: str
    entity_id: str
    issued_at_utc: datetime
    valid_at_utc: datetime
    available_at_utc: datetime
    temperature_c: float
    run_id: str
    model: str
    source_field_hash: str
    raw_grib_sha256: str
    record_content_sha256: str
    valid_end_utc: datetime | None = None
    temperature_kelvin: float | None = None
    unit: str = CANONICAL_UNIT
    source_system: str = SOURCE_SYSTEM
    model_provider: str = MODEL_PROVIDER
    quality_state: str = QUALITY_STATE
    provenance: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WeatherDemandBridgeConfig:
    """Explicit prediction origin, requested window and hard work bounds."""

    feature_policy: DegreeDayFeaturePolicy
    prediction_origin: datetime
    gas_days: tuple[date, ...]
    max_hold_minutes: int
    max_rows: int = 20_000
    max_points: int = 256
    max_window_days: int = MAX_WINDOW_DAYS
    max_cross_product: int = 500_000
    max_intervals: int = 100_000

    def __post_init__(self) -> None:
        if not isinstance(self.feature_policy, DegreeDayFeaturePolicy):
            raise ForecastBridgeValidationError(
                "feature_policy must be a DegreeDayFeaturePolicy"
            )
        if self.feature_policy.temporal_method is not LEFT_HOLD_INSTANT:
            raise ForecastBridgeValidationError(
                "feature policy temporal_method must be LEFT_HOLD_INSTANT "
                f"(domain spelling {LEFT_HOLD_INSTANT.value})"
            )
        object.__setattr__(
            self, "prediction_origin", _utc(self.prediction_origin, "prediction_origin")
        )

        raw_days = self.gas_days
        if isinstance(raw_days, (str, bytes)) or not isinstance(raw_days, Sequence):
            raise ForecastBridgeValidationError("gas_days must be a sequence of dates")
        days = tuple(raw_days)
        if not 1 <= len(days) <= MAX_WINDOW_DAYS:
            raise ForecastBridgeValidationError("gas_days must contain 1..366 dates")
        if any(not isinstance(day, date) or isinstance(day, datetime) for day in days):
            raise ForecastBridgeValidationError("gas_days must contain date values")
        if any(not date(2000, 1, 1) <= day <= date(2100, 12, 31) for day in days):
            raise ForecastBridgeValidationError("gas_days is outside the supported range")
        if len(set(days)) != len(days):
            raise ForecastBridgeValidationError("gas_days contains duplicate dates")
        days = tuple(sorted(days))
        object.__setattr__(self, "gas_days", days)

        for name, maximum in (
            ("max_hold_minutes", MAX_HOLD_MINUTES),
            ("max_rows", MAX_ROWS),
            ("max_points", MAX_POINTS),
            ("max_window_days", MAX_WINDOW_DAYS),
            ("max_cross_product", MAX_CROSS_PRODUCT),
            ("max_intervals", MAX_INTERVALS),
        ):
            value = _integer(getattr(self, name), name, minimum=1, maximum=maximum)
            object.__setattr__(self, name, value)
        window_days = (days[-1] - days[0]).days + 1
        if window_days > self.max_window_days:
            raise ForecastBridgeValidationError(
                f"requested window spans {window_days} days, above max_window_days"
            )

    @property
    def window_start_utc(self) -> datetime:
        """Return the first requested gas-day start in the frozen calendar."""

        return gas_day_start_for_date(
            self.gas_days[0], self.feature_policy.gas_day_calendar
        )

    @property
    def window_end_utc(self) -> datetime:
        """Return the exclusive end of the last requested gas day."""

        return gas_day_start_for_date(
            self.gas_days[-1] + timedelta(days=1),
            self.feature_policy.gas_day_calendar,
        )


@dataclass(frozen=True)
class BridgeDiagnostic:
    """One explicit missing-coverage or selection diagnostic."""

    code: WeatherDemandDiagnosticCode
    detail: str
    location_id: str | None = None
    valid_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", WeatherDemandDiagnosticCode(self.code))
        object.__setattr__(self, "detail", _text(self.detail, "detail"))
        if self.location_id is not None:
            object.__setattr__(
                self, "location_id", _text(self.location_id, "location_id")
            )
        if self.valid_at_utc is not None:
            object.__setattr__(
                self, "valid_at_utc", _utc(self.valid_at_utc, "valid_at_utc")
            )


@dataclass(frozen=True)
class WeatherDemandInputBundle:
    """Typed derived intervals, one selected vintage, diagnostics and policy."""

    status: WeatherDemandInputStatus
    feature_policy: DegreeDayFeaturePolicy
    prediction_origin: datetime
    gas_days: tuple[date, ...]
    window_start_utc: datetime
    window_end_utc: datetime
    max_hold_minutes: int
    selected_vintage: ForecastVintageRef | None
    intervals: tuple[ForecastTemperatureInterval, ...]
    diagnostics: tuple[BridgeDiagnostic, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", WeatherDemandInputStatus(self.status))
        if not isinstance(self.feature_policy, DegreeDayFeaturePolicy):
            raise ForecastBridgeValidationError(
                "feature_policy must be a DegreeDayFeaturePolicy"
            )
        object.__setattr__(
            self, "prediction_origin", _utc(self.prediction_origin, "prediction_origin")
        )
        object.__setattr__(self, "window_start_utc", _utc(self.window_start_utc, "window_start"))
        object.__setattr__(self, "window_end_utc", _utc(self.window_end_utc, "window_end"))
        object.__setattr__(self, "gas_days", tuple(self.gas_days))
        object.__setattr__(self, "intervals", tuple(self.intervals))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "source_refs", tuple(sorted(set(self.source_refs))))
        if self.selected_vintage is not None and not isinstance(
            self.selected_vintage, ForecastVintageRef
        ):
            raise ForecastBridgeValidationError(
                "selected_vintage must be a ForecastVintageRef"
            )
        allowed_locations = {
            weight.location_id for weight in self.feature_policy.location_weights
        }
        for interval in self.intervals:
            if not isinstance(interval, ForecastTemperatureInterval):
                raise ForecastBridgeValidationError(
                    "intervals must be ForecastTemperatureInterval values"
                )
            if interval.temporal_method is not LEFT_HOLD_INSTANT:
                raise ForecastBridgeValidationError(
                    "bridge intervals must be explicit left-hold derivations"
                )
            if interval.location_id not in allowed_locations:
                raise ForecastBridgeValidationError(
                    "bridge interval has no explicit feature-policy weight"
                )

    @property
    def ready(self) -> bool:
        """Return whether at least one derived interval exists."""

        return self.status is WeatherDemandInputStatus.READY and bool(self.intervals)

    def to_degree_day_request(self) -> DegreeDayRequest:
        """Build the domain request with the exact frozen feature-policy identity."""

        if not self.ready:
            raise ForecastBridgeNotReadyError(
                "forecast bridge has no derived intervals for the requested window"
            )
        return DegreeDayRequest(
            region=self.feature_policy.region,
            gas_days=self.gas_days,
            prediction_origin=self.prediction_origin,
            location_weights=self.feature_policy.location_weights,
            intervals=self.intervals,
            calendar=self.feature_policy.gas_day_calendar,
            forecast_vintage=self.selected_vintage,
        )


def canonical_source_field_hash(source_field_version: Mapping[str, Any]) -> str:
    """Return the canonical hash of a persisted provider source-field version."""

    if not isinstance(source_field_version, Mapping) or not source_field_version:
        raise ForecastBridgeValidationError(
            "source_field_version must be a non-empty mapping"
        )
    try:
        return _sha256_json(dict(source_field_version))
    except (TypeError, ValueError) as exc:
        raise ForecastBridgeValidationError(
            "source_field_version must be canonical JSON data"
        ) from exc


def _required_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ForecastBridgeValidationError(f"{name} must be a non-empty mapping")
    return value


def _persisted_utc(value: object, name: str) -> datetime:
    """Normalize a persisted UTC column, including SQLite's naive read-back."""

    if not isinstance(value, datetime):
        raise ForecastBridgeValidationError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        # The repository writes aware UTC values.  SQLite's DateTime type does
        # not retain the offset, so a naive read-back is the stored UTC contract,
        # never a local wall clock.  A non-UTC datetime is normalized to UTC.
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_date(value: object, name: str) -> date:
    text = _text(value, name)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ForecastBridgeValidationError(f"{name} is not an ISO date") from exc


def project_forecast_observation_record(
    record: ForecastObservationRecord,
) -> ForecastInstantRow:
    """Project one existing persisted ECMWF row without IO or metadata invention.

    The existing ``forecast_observations`` table stores an instantaneous 2t field
    as a zero-length interval because its end column is non-null.  This function
    accepts that actual stored representation only when the table values and the
    persisted provenance agree, then emits the semantic instant end ``None``.

    It also cross-checks the persisted source-field version, GRIB/content hashes,
    point identity/temperature, run/receipt times, unit, quality and binding.  It
    performs no query, write, registry lookup or fallback to another record.

    The persistence schema has no run-id or model-name column.  A stable run label
    is therefore derived from the persisted ``run_date`` and ``cycle_hour``, and
    the reviewed IFS model name is used only after the persisted asset URL names
    it.  This is a projection label, not a newly inventoried provider fact or a
    claim that the source is activated.
    """

    provenance = _required_mapping(
        getattr(record, "provenance", None), "record provenance"
    )
    if provenance.get("schema") != PERSISTED_PROVENANCE_SCHEMA:
        raise ForecastBridgeValidationError(
            "record provenance is not the "
            f"{PERSISTED_PROVENANCE_SCHEMA} repository schema"
        )
    if provenance.get("source_system") != SOURCE_SYSTEM:
        raise ForecastBridgeValidationError(
            "provenance source_system is not ECMWF_OPEN_DATA"
        )
    if provenance.get("provider") != MODEL_PROVIDER:
        raise ForecastBridgeValidationError("provenance provider is not ECMWF")

    record_id = _text(
        getattr(record, "forecast_observation_id", None),
        "record forecast_observation_id",
    )
    series_id = _text(getattr(record, "series_id", None), "record series_id")
    entity_id = _text(getattr(record, "entity_id", None), "record entity_id")
    if getattr(record, "source_system", None) != SOURCE_SYSTEM:
        raise ForecastBridgeValidationError(
            "record source_system must be ECMWF_OPEN_DATA"
        )
    if getattr(record, "model_provider", None) != MODEL_PROVIDER:
        raise ForecastBridgeValidationError("record model_provider must be ECMWF")
    quality_state = _text(
        getattr(record, "quality_state", None), "record quality_state"
    )
    if quality_state != QUALITY_STATE:
        raise ForecastBridgeValidationError(
            f"record quality_state must be {QUALITY_STATE}"
        )
    unit = _text(getattr(record, "unit", None), "record unit")
    if unit != CANONICAL_UNIT:
        raise ForecastBridgeValidationError(
            f"record unit must be {CANONICAL_UNIT}; persisted values are degC"
        )
    temperature = _finite(
        getattr(record, "value", None),
        "record value",
        minimum=MIN_TEMPERATURE_C,
        maximum=MAX_TEMPERATURE_C,
    )

    issued = _persisted_utc(
        getattr(record, "forecast_issued_at", None), "record forecast_issued_at"
    )
    valid = _persisted_utc(
        getattr(record, "forecast_valid_start", None), "record forecast_valid_start"
    )
    valid_end = _persisted_utc(
        getattr(record, "forecast_valid_end", None), "record forecast_valid_end"
    )
    available = _persisted_utc(
        getattr(record, "available_at_utc", None), "record available_at_utc"
    )
    if valid_end != valid:
        raise ForecastBridgeValidationError(
            "persisted ECMWF 2t row must carry a zero-length instant end; "
            "a real interval end cannot be reinterpreted as an instant"
        )

    grib_sha256 = _hash64(
        provenance.get("grib_sha256"), "provenance grib_sha256"
    )
    content_sha256 = _hash64(
        provenance.get("content_sha256"), "provenance content_sha256"
    )
    grib = _required_mapping(provenance.get("grib"), "provenance grib")
    if grib.get("sha256") != grib_sha256:
        raise ForecastBridgeValidationError(
            "provenance grib hash does not match the persisted top-level grib hash"
        )

    version = _required_mapping(
        provenance.get("source_field_version"),
        "provenance source_field_version",
    )
    if version.get("grib_sha256") != grib_sha256:
        raise ForecastBridgeValidationError(
            "provenance source-field GRIB hash does not match the persisted GRIB hash"
        )
    if version.get("param_id") != 167:
        raise ForecastBridgeValidationError(
            "provenance source-field param_id is not ECMWF 2t (167)"
        )
    if version.get("units") != "K":
        raise ForecastBridgeValidationError(
            "provenance source-field units are not the persisted ECMWF K units"
        )
    run_date = _iso_date(
        version.get("run_date"), "provenance source-field run_date"
    )
    cycle_hour = _integer(
        version.get("cycle_hour"),
        "provenance source-field cycle_hour",
        minimum=0,
        maximum=23,
    )
    step_hours = _integer(
        version.get("step_hours"),
        "provenance source-field step_hours",
        minimum=0,
        maximum=360,
    )
    if issued + timedelta(hours=step_hours) != valid:
        raise ForecastBridgeValidationError(
            "persisted issue/validity/step times do not describe one forecast step"
        )
    if (
        _parse_iso(
            version.get("valid_at_utc"),
            "provenance source-field valid_at_utc",
        )
        != valid
    ):
        raise ForecastBridgeValidationError(
            "provenance source-field validity does not match the persisted row"
        )

    reference = _required_mapping(
        provenance.get("reference"), "provenance reference"
    )
    if _iso_date(reference.get("run_date"), "provenance reference run_date") != run_date:
        raise ForecastBridgeValidationError(
            "provenance reference run_date does not match the source field"
        )
    if (
        _integer(
            reference.get("cycle_hour"),
            "provenance reference cycle_hour",
            minimum=0,
            maximum=23,
        )
        != cycle_hour
    ):
        raise ForecastBridgeValidationError(
            "provenance reference cycle_hour does not match the source field"
        )
    if (
        _integer(
            reference.get("step_hours"),
            "provenance reference step_hours",
            minimum=0,
            maximum=360,
        )
        != step_hours
    ):
        raise ForecastBridgeValidationError(
            "provenance reference step_hours does not match the source field"
        )
    if _parse_iso(
        reference.get("valid_at_utc"), "provenance reference valid_at_utc"
    ) != valid:
        raise ForecastBridgeValidationError(
            "provenance reference validity does not match the persisted row"
        )
    if reference.get("grib_sha256") != grib_sha256:
        raise ForecastBridgeValidationError(
            "provenance reference GRIB hash does not match the persisted GRIB hash"
        )
    asset_url = _text(
        reference.get("asset_url"), "provenance reference asset_url"
    )
    if f"/{ECMWF_MODEL}/" not in asset_url:
        raise ForecastBridgeValidationError(
            "persisted asset URL does not identify the reviewed ECMWF IFS model"
        )

    request = _required_mapping(
        provenance.get("request"), "provenance request"
    )
    if _iso_date(request.get("run_date"), "provenance request run_date") != run_date:
        raise ForecastBridgeValidationError(
            "provenance request run_date does not match the source field"
        )
    if (
        _integer(
            request.get("cycle_hour"),
            "provenance request cycle_hour",
            minimum=0,
            maximum=23,
        )
        != cycle_hour
    ):
        raise ForecastBridgeValidationError(
            "provenance request cycle_hour does not match the source field"
        )
    if (
        _integer(
            request.get("step_hours"),
            "provenance request step_hours",
            minimum=0,
            maximum=360,
        )
        != step_hours
    ):
        raise ForecastBridgeValidationError(
            "provenance request step_hours does not match the source field"
        )

    run = _required_mapping(provenance.get("run"), "provenance run")
    if (
        _parse_iso(
            run.get("forecast_issued_at_utc"),
            "provenance run forecast_issued_at_utc",
        )
        != issued
    ):
        raise ForecastBridgeValidationError(
            "provenance issue time does not match the persisted row"
        )
    if (
        _parse_iso(
            run.get("forecast_valid_at_utc"),
            "provenance run forecast_valid_at_utc",
        )
        != valid
    ):
        raise ForecastBridgeValidationError(
            "provenance validity time does not match the persisted row"
        )
    if (
        _parse_iso(
            run.get("receipt_completed_at_utc"),
            "provenance run receipt_completed_at_utc",
        )
        != available
    ):
        raise ForecastBridgeValidationError(
            "provenance receipt time does not match the persisted availability"
        )

    availability = _required_mapping(
        provenance.get("availability"), "provenance availability"
    )
    if (
        _parse_iso(
            availability.get("available_at_utc"),
            "provenance availability available_at_utc",
        )
        != available
    ):
        raise ForecastBridgeValidationError(
            "provenance availability does not match the persisted receipt"
        )

    temporal = _required_mapping(
        provenance.get("temporal"), "provenance temporal"
    )
    if temporal.get("scope") != "instant":
        raise ForecastBridgeValidationError("provenance temporal scope is not instant")
    if temporal.get("forecast_valid_end") is not None:
        raise ForecastBridgeValidationError(
            "provenance must record an absent instant end"
        )
    if temporal.get("database_end_representation") != PERSISTED_TEMPORAL_END:
        raise ForecastBridgeValidationError(
            "provenance does not record the persisted zero-length instant end"
        )
    if (
        _parse_iso(
            temporal.get("forecast_valid_start"),
            "provenance temporal forecast_valid_start",
        )
        != valid
    ):
        raise ForecastBridgeValidationError(
            "provenance temporal start does not match the persisted row"
        )

    point = _required_mapping(provenance.get("point"), "provenance point")
    binding = _required_mapping(
        provenance.get("binding"), "provenance binding"
    )
    point_id = _text(point.get("point_id"), "provenance point_id")
    if _text(binding.get("point_id"), "provenance binding point_id") != point_id:
        raise ForecastBridgeValidationError(
            "provenance point/binding point_id do not match"
        )
    if _text(binding.get("series_id"), "provenance binding series_id") != series_id:
        raise ForecastBridgeValidationError(
            "provenance binding series_id does not match the persisted row"
        )
    if _text(binding.get("entity_id"), "provenance binding entity_id") != entity_id:
        raise ForecastBridgeValidationError(
            "provenance binding entity_id does not match the persisted row"
        )
    if provenance.get("entity_id") != entity_id:
        raise ForecastBridgeValidationError(
            "provenance entity_id does not match the persisted row"
        )
    if point.get("represents_observing_station") is not False:
        raise ForecastBridgeValidationError(
            "a forecast grid point must not claim to be an observing station"
        )
    point_celsius = _finite(
        point.get("temperature_celsius"),
        "provenance point temperature_celsius",
        minimum=MIN_TEMPERATURE_C,
        maximum=MAX_TEMPERATURE_C,
    )
    if not math.isclose(
        point_celsius,
        temperature,
        rel_tol=0.0,
        abs_tol=KELVIN_TOLERANCE,
    ):
        raise ForecastBridgeValidationError(
            "provenance point temperature does not match the persisted value"
        )
    kelvin = _finite(
        point.get("temperature_kelvin"),
        "provenance point temperature_kelvin",
        minimum=0.0,
        maximum=1_000.0,
    )
    if kelvin <= 0.0 or not math.isclose(
        kelvin - KELVIN_OFFSET,
        temperature,
        rel_tol=0.0,
        abs_tol=KELVIN_TOLERANCE,
    ):
        raise ForecastBridgeValidationError(
            "provenance point kelvin is not consistent with the persisted degC value"
        )

    quality = _required_mapping(
        provenance.get("quality"), "provenance quality"
    )
    if quality.get("quality_state") != QUALITY_STATE:
        raise ForecastBridgeValidationError(
            "provenance quality_state is not FORECAST"
        )

    projected = ForecastInstantRow(
        forecast_observation_id=record_id,
        point_id=point_id,
        series_id=series_id,
        entity_id=entity_id,
        issued_at_utc=issued,
        valid_at_utc=valid,
        available_at_utc=available,
        temperature_c=temperature,
        run_id=f"{run_date:%Y%m%d}T{cycle_hour:02d}Z",
        model=ECMWF_MODEL,
        source_field_hash=canonical_source_field_hash(version),
        raw_grib_sha256=grib_sha256,
        record_content_sha256=content_sha256,
        valid_end_utc=None,
        temperature_kelvin=kelvin,
        unit=unit,
        source_system=SOURCE_SYSTEM,
        model_provider=MODEL_PROVIDER,
        quality_state=QUALITY_STATE,
        provenance=provenance,
    )
    return _validate_row(projected)


def build_weather_demand_inputs(
    rows: Sequence[ForecastInstantRow],
    bindings: Sequence[ForecastPointBinding],
    config: WeatherDemandBridgeConfig,
) -> WeatherDemandInputBundle:
    """Derive bounded left-hold intervals from already-projected forecast rows.

    The caller must apply its ACL/entitlement policy and source activation before
    calling this adapter.  The adapter only validates the projected identities
    and the frozen feature policy.
    """

    if not isinstance(config, WeatherDemandBridgeConfig):
        raise TypeError("config must be a WeatherDemandBridgeConfig")
    raw_rows = _sequence(rows, "rows")
    raw_bindings = _sequence(bindings, "bindings")
    if len(raw_rows) > config.max_rows:
        raise ForecastBridgeValidationError(
            f"row count {len(raw_rows)} exceeds max_rows {config.max_rows}"
        )
    if len(raw_bindings) > config.max_points:
        raise ForecastBridgeValidationError(
            f"binding count {len(raw_bindings)} exceeds max_points {config.max_points}"
        )

    normalized_rows = tuple(_validate_row(row) for row in raw_rows)
    normalized_bindings = _normalize_bindings(raw_bindings, config.feature_policy)
    binding_by_point = {binding.point_id: binding for binding in normalized_bindings}
    bound_locations = {binding.location_id for binding in normalized_bindings}
    diagnostics: list[BridgeDiagnostic] = []

    for weight in config.feature_policy.location_weights:
        if weight.location_id not in bound_locations:
            diagnostics.append(
                BridgeDiagnostic(
                    code=WeatherDemandDiagnosticCode.MISSING_POINT_BINDING,
                    detail=(
                        f"no explicit point binding for weighted location "
                        f"{weight.location_id}; coverage remains missing"
                    ),
                    location_id=weight.location_id,
                )
            )

    for row in normalized_rows:
        binding = binding_by_point.get(row.point_id)
        if binding is None:
            raise ForecastBridgeValidationError(
                f"row point_id {row.point_id!r} has no explicit caller binding"
            )
        if row.series_id != binding.series_id or row.entity_id != binding.entity_id:
            raise ForecastBridgeValidationError(
                f"row identity for {row.point_id!r} does not match its explicit "
                "series/entity binding"
            )
    eligible = tuple(
        row
        for row in normalized_rows
        if row.issued_at_utc <= config.prediction_origin
        and row.available_at_utc <= config.prediction_origin
    )
    if not eligible:
        diagnostics.append(
            BridgeDiagnostic(
                code=WeatherDemandDiagnosticCode.NO_ELIGIBLE_FORECAST,
                detail="no forecast issue/availability is at or before the prediction origin",
            )
        )
        return _bundle(
            config,
            status=WeatherDemandInputStatus.MISSING,
            selected_vintage=None,
            intervals=(),
            diagnostics=tuple(diagnostics),
        )

    vintage, vintage_rows = _select_vintage(eligible)
    selected = _select_revisions(
        vintage_rows,
        point_count=len(normalized_bindings),
        max_cross_product=config.max_cross_product,
    )
    _assert_one_field_revision_per_valid(selected)

    intervals, interval_diagnostics = _derive_intervals(
        selected,
        normalized_bindings,
        config,
    )
    diagnostics.extend(interval_diagnostics)
    if not intervals:
        diagnostics.append(
            BridgeDiagnostic(
                code=WeatherDemandDiagnosticCode.NO_INTERVALS_IN_WINDOW,
                detail="no adjacent bracket pair produced an interval inside the window",
            )
        )
    return _bundle(
        config,
        status=(
            WeatherDemandInputStatus.READY
            if intervals
            else WeatherDemandInputStatus.MISSING
        ),
        selected_vintage=vintage,
        intervals=tuple(intervals),
        diagnostics=tuple(diagnostics),
    )


def compute_degree_days_from_bundle(
    bundle: WeatherDemandInputBundle,
    policy: DegreeDayPolicy,
) -> DegreeDayResult | None:
    """Run the existing domain solver only when the bridge is ready.

    The helper carries the exact region, weights, calendar, bases, coverage and
    temporal policy, and refuses a degree-day policy whose basis differs from the
    frozen feature policy.  It does not reimplement HDD/CDD mathematics.
    """

    if not isinstance(bundle, WeatherDemandInputBundle):
        raise TypeError("bundle must be a WeatherDemandInputBundle")
    if not isinstance(policy, DegreeDayPolicy):
        raise TypeError("policy must be a DegreeDayPolicy")
    if not bundle.ready:
        return None
    expected = bundle.feature_policy
    if (
        policy.heating_base_c != expected.heating_base_c
        or policy.cooling_base_c != expected.cooling_base_c
        or policy.max_gap_minutes != expected.max_gap_minutes
        or policy.min_covered_fraction != expected.min_covered_fraction
        or policy.method_version != expected.method_version
    ):
        raise ForecastBridgeValidationError(
            "degree-day policy does not match the frozen feature policy"
        )
    return compute_degree_days(bundle.to_degree_day_request(), policy)


def _bundle(
    config: WeatherDemandBridgeConfig,
    *,
    status: WeatherDemandInputStatus,
    selected_vintage: ForecastVintageRef | None,
    intervals: tuple[ForecastTemperatureInterval, ...],
    diagnostics: tuple[BridgeDiagnostic, ...],
) -> WeatherDemandInputBundle:
    return WeatherDemandInputBundle(
        status=status,
        feature_policy=config.feature_policy,
        prediction_origin=config.prediction_origin,
        gas_days=config.gas_days,
        window_start_utc=config.window_start_utc,
        window_end_utc=config.window_end_utc,
        max_hold_minutes=config.max_hold_minutes,
        selected_vintage=selected_vintage,
        intervals=intervals,
        diagnostics=diagnostics,
        source_refs=tuple(interval.source_ref for interval in intervals),
    )


def _sequence(value: object, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ForecastBridgeValidationError(f"{name} must be a sequence")
    return value


def _validate_row(row: object) -> ForecastInstantRow:
    if not isinstance(row, ForecastInstantRow):
        raise ForecastBridgeValidationError("rows must be ForecastInstantRow values")

    record_id = _text(row.forecast_observation_id, "forecast_observation_id")
    point_id = _text(row.point_id, "point_id")
    series_id = _text(row.series_id, "series_id")
    entity_id = _text(row.entity_id, "entity_id")
    run_id = _text(row.run_id, "run_id")
    model = _text(row.model, "model")
    issued = _utc(row.issued_at_utc, "issued_at_utc")
    valid = _utc(row.valid_at_utc, "valid_at_utc")
    available = _utc(row.available_at_utc, "available_at_utc")
    if available < issued:
        raise ForecastBridgeValidationError(
            "available_at_utc cannot precede issued_at_utc"
        )
    if row.valid_end_utc is not None:
        raise ForecastBridgeValidationError(
            "ECMWF 2t is instantaneous; valid_end_utc must be None"
        )
    if row.source_system != SOURCE_SYSTEM:
        raise ForecastBridgeValidationError(
            f"source_system must be {SOURCE_SYSTEM}"
        )
    if row.model_provider != MODEL_PROVIDER:
        raise ForecastBridgeValidationError(
            f"model_provider must be {MODEL_PROVIDER}"
        )
    if row.quality_state != QUALITY_STATE:
        raise ForecastBridgeValidationError(f"quality_state must be {QUALITY_STATE}")
    if row.unit != CANONICAL_UNIT:
        raise ForecastBridgeValidationError(f"unit must be {CANONICAL_UNIT}")

    temperature = _finite(
        row.temperature_c,
        "temperature_c",
        minimum=MIN_TEMPERATURE_C,
        maximum=MAX_TEMPERATURE_C,
    )
    kelvin = row.temperature_kelvin
    if kelvin is not None:
        kelvin = _finite(kelvin, "temperature_kelvin", minimum=0.0, maximum=1_000.0)
        if kelvin <= 0.0 or not math.isclose(
            temperature,
            kelvin - KELVIN_OFFSET,
            rel_tol=0.0,
            abs_tol=KELVIN_TOLERANCE,
        ):
            raise ForecastBridgeValidationError(
                "temperature_kelvin is not finite and consistent with temperature_c"
            )

    normalized = replace(
        row,
        forecast_observation_id=record_id,
        point_id=point_id,
        series_id=series_id,
        entity_id=entity_id,
        run_id=run_id,
        model=model,
        issued_at_utc=issued,
        valid_at_utc=valid,
        available_at_utc=available,
        temperature_c=temperature,
        temperature_kelvin=kelvin,
        source_field_hash=_hash64(row.source_field_hash, "source_field_hash"),
        raw_grib_sha256=_hash64(row.raw_grib_sha256, "raw_grib_sha256"),
        record_content_sha256=_hash64(
            row.record_content_sha256, "record_content_sha256"
        ),
    )
    return _validate_provenance(normalized)


def _validate_provenance(row: ForecastInstantRow) -> ForecastInstantRow:
    provenance = row.provenance
    if provenance is None:
        return row
    if not isinstance(provenance, Mapping):
        raise ForecastBridgeValidationError("provenance must be a mapping")

    if "source_system" in provenance and provenance["source_system"] != SOURCE_SYSTEM:
        raise ForecastBridgeValidationError("provenance source_system is not ECMWF_OPEN_DATA")
    if "provider" in provenance and provenance["provider"] != MODEL_PROVIDER:
        raise ForecastBridgeValidationError("provenance provider is not ECMWF")

    temporal = provenance.get("temporal")
    if temporal is not None:
        if not isinstance(temporal, Mapping):
            raise ForecastBridgeValidationError("provenance temporal must be a mapping")
        if temporal.get("scope") != "instant":
            raise ForecastBridgeValidationError("provenance temporal scope is not instant")
        if temporal.get("forecast_valid_end") is not None:
            raise ForecastBridgeValidationError(
                "provenance must record an absent instant end"
            )

    grib = provenance.get("grib")
    if grib is not None:
        if not isinstance(grib, Mapping) or grib.get("sha256") != row.raw_grib_sha256:
            raise ForecastBridgeValidationError(
                "provenance GRIB hash does not match the projected raw hash"
            )
    if "content_sha256" in provenance and (
        provenance["content_sha256"] != row.record_content_sha256
    ):
        raise ForecastBridgeValidationError(
            "provenance content hash does not match the projected record hash"
        )

    version = provenance.get("source_field_version")
    if version is not None:
        if not isinstance(version, Mapping):
            raise ForecastBridgeValidationError(
                "provenance source_field_version must be a mapping"
            )
        if canonical_source_field_hash(version) != row.source_field_hash:
            raise ForecastBridgeValidationError(
                "projected source_field_hash does not match provenance source_field_version"
            )

    point = provenance.get("point")
    kelvin = row.temperature_kelvin
    if point is not None:
        if not isinstance(point, Mapping):
            raise ForecastBridgeValidationError("provenance point must be a mapping")
        if point.get("point_id") not in (None, row.point_id):
            raise ForecastBridgeValidationError(
                "provenance point_id does not match the projected point"
            )
        if point.get("represents_observing_station") not in (None, False):
            raise ForecastBridgeValidationError(
                "a forecast grid point must not claim to be an observing station"
            )
        if "temperature_celsius" in point:
            projected = _finite(
                point["temperature_celsius"],
                "provenance temperature_celsius",
                minimum=MIN_TEMPERATURE_C,
                maximum=MAX_TEMPERATURE_C,
            )
            if not math.isclose(
                projected,
                row.temperature_c,
                rel_tol=0.0,
                abs_tol=KELVIN_TOLERANCE,
            ):
                raise ForecastBridgeValidationError(
                    "provenance temperature does not match the projected value"
                )
        if kelvin is None and "temperature_kelvin" in point:
            kelvin = _finite(
                point["temperature_kelvin"],
                "provenance temperature_kelvin",
                minimum=0.0,
                maximum=1_000.0,
            )

    run = provenance.get("run")
    if run is not None:
        if not isinstance(run, Mapping):
            raise ForecastBridgeValidationError("provenance run must be a mapping")
        issued = run.get("forecast_issued_at_utc")
        if (
            issued is not None
            and _parse_iso(issued, "provenance issue") != row.issued_at_utc
        ):
            raise ForecastBridgeValidationError(
                "provenance issue time does not match the projected row"
            )
        valid = run.get("forecast_valid_at_utc")
        if (
            valid is not None
            and _parse_iso(valid, "provenance validity") != row.valid_at_utc
        ):
            raise ForecastBridgeValidationError(
                "provenance validity time does not match the projected row"
            )

    if kelvin is not None:
        kelvin = _finite(kelvin, "temperature_kelvin", minimum=0.0, maximum=1_000.0)
        if kelvin <= 0.0 or not math.isclose(
            row.temperature_c,
            kelvin - KELVIN_OFFSET,
            rel_tol=0.0,
            abs_tol=KELVIN_TOLERANCE,
        ):
            raise ForecastBridgeValidationError(
                "provenance kelvin is not consistent with the projected Celsius value"
            )
    return replace(row, temperature_kelvin=kelvin)


def _normalize_bindings(
    bindings: Sequence[object],
    policy: DegreeDayFeaturePolicy,
) -> tuple[ForecastPointBinding, ...]:
    location_weights = {weight.location_id: weight for weight in policy.location_weights}
    normalized: list[ForecastPointBinding] = []
    seen_points: set[str] = set()
    seen_locations: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, ForecastPointBinding):
            raise ForecastBridgeValidationError(
                "bindings must be ForecastPointBinding values"
            )
        point_id = _text(binding.point_id, "binding point_id")
        series_id = _text(binding.series_id, "binding series_id")
        entity_id = _text(binding.entity_id, "binding entity_id")
        location_id = _text(binding.location_id, "binding location_id")
        region = _text(binding.region, "binding region")
        if region != policy.region:
            raise ForecastBridgeValidationError(
                f"binding region {region!r} does not match policy region {policy.region!r}"
            )
        if location_id not in location_weights:
            raise ForecastBridgeValidationError(
                f"binding location {location_id!r} has no explicit policy weight"
            )
        if point_id in seen_points:
            raise ForecastBridgeValidationError(
                f"duplicate binding for point {point_id!r}"
            )
        if location_id in seen_locations:
            raise ForecastBridgeValidationError(
                f"duplicate binding for weighted location {location_id!r}"
            )
        seen_points.add(point_id)
        seen_locations.add(location_id)
        normalized.append(
            ForecastPointBinding(
                point_id=point_id,
                series_id=series_id,
                entity_id=entity_id,
                location_id=location_id,
                region=region,
            )
        )
    return tuple(normalized)


def _select_vintage(
    rows: Sequence[ForecastInstantRow],
) -> tuple[ForecastVintageRef, tuple[ForecastInstantRow, ...]]:
    groups: dict[tuple[str, str, str, datetime], list[ForecastInstantRow]] = {}
    for row in rows:
        key = (row.model_provider, row.model, row.run_id, row.issued_at_utc)
        groups.setdefault(key, []).append(row)

    ranks = {
        key: (key[3], max(row.available_at_utc for row in group))
        for key, group in groups.items()
    }
    best = max(ranks.values())
    winners = [key for key, rank in ranks.items() if rank == best]
    if len(winners) != 1:
        raise ForecastBridgeAmbiguityError(
            "multiple forecast vintages are equally newest and available; "
            "refusing to choose by hash or caller order"
        )
    provider, model, run_id, issued = winners[0]
    vintage = ForecastVintageRef(
        provider=provider,
        model=model,
        run_id=run_id,
        issued_at=issued,
    )
    return vintage, tuple(groups[winners[0]])


def _select_revisions(
    rows: Sequence[ForecastInstantRow],
    *,
    point_count: int,
    max_cross_product: int,
) -> dict[tuple[str, datetime], ForecastInstantRow]:
    by_point_valid: dict[tuple[str, datetime], list[ForecastInstantRow]] = {}
    valid_times: set[datetime] = set()
    for row in rows:
        by_point_valid.setdefault((row.point_id, row.valid_at_utc), []).append(row)
        valid_times.add(row.valid_at_utc)
    if point_count * len(valid_times) > max_cross_product:
        raise ForecastBridgeValidationError(
            "point-by-valid-time cross product exceeds max_cross_product"
        )

    selected: dict[tuple[str, datetime], ForecastInstantRow] = {}
    for key, group in by_point_valid.items():
        latest_available = max(row.available_at_utc for row in group)
        latest = [
            row for row in group if row.available_at_utc == latest_available
        ]
        hashes = {row.source_field_hash for row in latest}
        if len(hashes) != 1:
            raise ForecastBridgeAmbiguityError(
                "two source-field revisions share the same latest receipt time; "
                "refusing to choose by hash"
            )
        signatures = {
            (
                row.temperature_c,
                row.raw_grib_sha256,
                row.record_content_sha256,
                row.temperature_kelvin,
            )
            for row in latest
        }
        if len(signatures) != 1:
            raise ForecastBridgeAmbiguityError(
                "two different records claim the same source-field revision and receipt"
            )
        # Exact duplicates are deterministically collapsed by record id.  This is
        # not a hash-based choice between different field revisions.
        selected[key] = min(latest, key=lambda row: row.forecast_observation_id)
    return selected


def _assert_one_field_revision_per_valid(
    selected: Mapping[tuple[str, datetime], ForecastInstantRow],
) -> None:
    by_valid: dict[datetime, set[str]] = {}
    for (_, valid), row in selected.items():
        by_valid.setdefault(valid, set()).add(row.source_field_hash)
    for valid, hashes in by_valid.items():
        if len(hashes) != 1:
            raise ForecastFieldRevisionConflictError(
                "required points at one valid time carry different source-field "
                f"revisions at {valid.isoformat()}; refusing to mix revisions"
            )


def _derive_intervals(
    selected: Mapping[tuple[str, datetime], ForecastInstantRow],
    bindings: Sequence[ForecastPointBinding],
    config: WeatherDemandBridgeConfig,
) -> tuple[list[ForecastTemperatureInterval], list[BridgeDiagnostic]]:
    diagnostics: list[BridgeDiagnostic] = []
    intervals: list[ForecastTemperatureInterval] = []
    binding_by_location = {binding.location_id: binding for binding in bindings}
    selected_by_point: dict[str, list[ForecastInstantRow]] = {}
    for (point_id, _), row in selected.items():
        selected_by_point.setdefault(point_id, []).append(row)
    for values in selected_by_point.values():
        values.sort(key=lambda row: row.valid_at_utc)

    window_start = config.window_start_utc
    window_end = config.window_end_utc
    max_hold_seconds = float(config.max_hold_minutes) * 60.0 + 1e-9
    for weight in config.feature_policy.location_weights:
        binding = binding_by_location.get(weight.location_id)
        if binding is None:
            continue  # A MISSING_POINT_BINDING diagnostic was already emitted.
        rows = selected_by_point.get(binding.point_id, [])
        if not rows:
            diagnostics.append(
                BridgeDiagnostic(
                    code=WeatherDemandDiagnosticCode.NO_POINT_OBSERVATIONS,
                    detail=(
                        f"selected vintage has no eligible observation for point "
                        f"{binding.point_id!r}; coverage remains missing"
                    ),
                    location_id=binding.location_id,
                )
            )
            continue
        if rows[0].valid_at_utc > window_start:
            diagnostics.append(
                BridgeDiagnostic(
                    code=WeatherDemandDiagnosticCode.NO_LEFT_BRACKET,
                    detail=(
                        "no sample brackets the requested window start; no value "
                        "is extrapolated backwards"
                    ),
                    location_id=binding.location_id,
                    valid_at_utc=rows[0].valid_at_utc,
                )
            )
        if rows[-1].valid_at_utc < window_end:
            diagnostics.append(
                BridgeDiagnostic(
                    code=WeatherDemandDiagnosticCode.NO_RIGHT_BRACKET,
                    detail=(
                        "no sample brackets the requested window end; the last "
                        "value is not extended forwards"
                    ),
                    location_id=binding.location_id,
                    valid_at_utc=rows[-1].valid_at_utc,
                )
            )

        for left, right in zip(rows, rows[1:], strict=False):
            gap_seconds = (right.valid_at_utc - left.valid_at_utc).total_seconds()
            if gap_seconds <= 0.0:
                continue
            if gap_seconds > max_hold_seconds:
                diagnostics.append(
                    BridgeDiagnostic(
                        code=WeatherDemandDiagnosticCode.HOLD_GAP_EXCEEDED,
                        detail=(
                            f"adjacent instant gap {gap_seconds / 60.0:.0f} minutes "
                            f"exceeds explicit max_hold_minutes {config.max_hold_minutes}; "
                            "no interval is fabricated across the gap"
                        ),
                        location_id=binding.location_id,
                        valid_at_utc=left.valid_at_utc,
                    )
                )
                continue
            start = max(left.valid_at_utc, window_start)
            end = min(right.valid_at_utc, window_end)
            if start >= end:
                continue
            source_ref = _interval_source_ref(
                config,
                left=left,
                right=right,
                start=start,
                end=end,
            )
            intervals.append(
                ForecastTemperatureInterval(
                    location_id=binding.location_id,
                    start_utc=start,
                    end_utc=end,
                    mean_temperature_c=left.temperature_c,
                    issued_at=left.issued_at_utc,
                    available_at=max(left.available_at_utc, right.available_at_utc),
                    provider=left.model_provider,
                    model=left.model,
                    run_id=left.run_id,
                    source_ref=source_ref,
                    temporal_method=LEFT_HOLD_INSTANT,
                )
            )
            if len(intervals) > config.max_intervals:
                raise ForecastBridgeValidationError(
                    f"derived interval count exceeds max_intervals {config.max_intervals}"
                )
    return intervals, diagnostics


def _interval_source_ref(
    config: WeatherDemandBridgeConfig,
    *,
    left: ForecastInstantRow,
    right: ForecastInstantRow,
    start: datetime,
    end: datetime,
) -> str:
    payload = {
        "schema": "weather-demand-ecmwf-left-hold-interval-ref/v1",
        "derivation": DERIVED_LEFT_HOLD_APPROXIMATION,
        "temporal_method": LEFT_HOLD_INSTANT.value,
        "max_hold_minutes": config.max_hold_minutes,
        "feature_policy_hash": config.feature_policy.policy_hash,
        "requested_window": [
            _iso(config.window_start_utc),
            _iso(config.window_end_utc),
        ],
        "reporting_interval": [_iso(start), _iso(end)],
        "vintage": {
            "provider": left.model_provider,
            "model": left.model,
            "run_id": left.run_id,
            "issued_at_utc": _iso(left.issued_at_utc),
        },
        "boundaries": [
            _boundary_payload("LEFT_VALUE", left),
            _boundary_payload("RIGHT_BRACKET", right),
        ],
    }
    return "sha256:" + _sha256_json(payload)


def _boundary_payload(role: str, row: ForecastInstantRow) -> dict[str, Any]:
    return {
        "role": role,
        "forecast_observation_id": row.forecast_observation_id,
        "point_id": row.point_id,
        "series_id": row.series_id,
        "entity_id": row.entity_id,
        "valid_at_utc": _iso(row.valid_at_utc),
        "available_at_utc": _iso(row.available_at_utc),
        "temperature_c": row.temperature_c,
        "source_field_hash": row.source_field_hash,
        "raw_grib_sha256": row.raw_grib_sha256,
        "record_content_sha256": row.record_content_sha256,
    }


def _sha256_json(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_iso(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ForecastBridgeValidationError(f"{name} must be an ISO datetime string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ForecastBridgeValidationError(f"{name} is not a valid ISO datetime") from exc
    return _utc(parsed, name)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForecastBridgeValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _utc(value: object, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ForecastBridgeValidationError(f"{name} must be an aware datetime")
    return value.astimezone(UTC)


def _finite(
    value: object,
    name: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForecastBridgeValidationError(f"{name} must be numeric")
    resolved = float(value)
    if not math.isfinite(resolved) or resolved < minimum or resolved > maximum:
        raise ForecastBridgeValidationError(
            f"{name} must be finite and in [{minimum}, {maximum}]"
        )
    return resolved


def _integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ForecastBridgeValidationError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ForecastBridgeValidationError(
            f"{name} must be in [{minimum}, {maximum}]"
        )
    return value


def _hash64(value: object, name: str) -> str:
    text = _text(value, name)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ForecastBridgeValidationError(
            f"{name} must be a canonical lowercase SHA-256 hex digest"
        )
    return text


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
