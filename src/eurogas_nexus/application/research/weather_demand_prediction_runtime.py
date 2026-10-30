"""Bounded read-only composition of persisted forecasts to a frozen prediction.

The explicit input is an already-fitted ``DemandModelResult``; this module never
fits/refits, reads actual target demand, promotes a model or substitutes a
baseline.  A selected weather model consumes persisted ECMWF rows through the
existing bounded SQL prefilter, the actual projection/bridge/degree-day path and
``predict_selected_demand``.  An already-selected calendar baseline calls the same
predictor without weather.  Only genuine receipt availability is implemented; S4
archive evidence is absent and has no fallback.  Missing coverage is a typed
insufficient result, never zero weather, a baseline or a fitted model.  The
repository's own ``no_autoflush`` scope leaves caller work untouched, and this
module never writes, flushes, commits, rolls back or calls the network.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from eurogas_nexus.application.research.demand_target_inputs import (
    SUPPORTED_REGION,
    TARGET_UNIT,
)
from eurogas_nexus.application.research.weather_demand_inputs import (
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
    WeatherDemandInputBundle,
    build_weather_demand_inputs,
    compute_degree_days_from_bundle,
    project_forecast_observation_record,
)
from eurogas_nexus.db.repositories.ecmwf_forecast_reads import (
    MAX_IDENTIFIERS,
    EcmwfForecastReadError,
    EcmwfForecastReadOverflowError,
    EcmwfForecastReadValidationError,
    read_ecmwf_forecasts,
)
from eurogas_nexus.db.repositories.ecmwf_forecast_reads import (
    MAX_LIMIT as MAX_FORECAST_READ_LIMIT,
)
from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
from eurogas_nexus.domain.ontology.vocabulary import TargetScope
from eurogas_nexus.domain.research.weather_demand import (
    DailyWeatherFeature,
    DegreeDayPolicy,
    DegreeDayResult,
    DemandModelResult,
    DemandPrediction,
    DemandPredictionRequest,
    ForecastVintageRef,
    ModelKind,
    PromotionStatus,
    ValidationBasis,
    WeatherDemandInputError,
    predict_selected_demand,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RUNTIME_SCHEMA = "weather-demand-prediction-runtime/v1"
RESEARCH_ONLY_LABEL = "RESEARCH_ONLY_FROZEN_MODEL_PREDICTION"
REGIONAL_WEIGHTING_EVIDENCE_BASIS = "CALLER_DECLARED_PROVENANCE_NOT_REVIEWED"
DEFAULT_FORECAST_EVIDENCE_BASIS = "GENUINE_RECEIPT_AVAILABILITY"
_ONE_MICROSECOND = timedelta(microseconds=1)


class WeatherDemandPredictionStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_FORECAST_COVERAGE = "INSUFFICIENT_FORECAST_COVERAGE"


class PredictionConsumptionBasis(StrEnum):
    WEATHER_FORECAST_VINTAGE = "WEATHER_FORECAST_VINTAGE"
    CALENDAR_BASELINE_REFERENCE = "CALENDAR_BASELINE_REFERENCE"
    NONE = "NONE"


class ForecastEvidenceBasis(StrEnum):
    GENUINE_RECEIPT_AVAILABILITY = DEFAULT_FORECAST_EVIDENCE_BASIS


class WeatherDemandPredictionDiagnosticCode(StrEnum):
    FORECAST_BRIDGE_MISSING = "FORECAST_BRIDGE_MISSING"
    DEGREE_DAY_INCOMPLETE = "DEGREE_DAY_INCOMPLETE"
    NO_FEATURE_ROW = "NO_FEATURE_ROW"


class WeatherDemandPredictionError(ValueError):
    code = "WEATHER_DEMAND_PREDICTION_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class WeatherDemandPredictionValidationError(WeatherDemandPredictionError):
    code = "WEATHER_DEMAND_PREDICTION_VALIDATION_ERROR"


class WeatherDemandPredictionArchiveBasisError(WeatherDemandPredictionValidationError):
    code = "ARCHIVE_FORECAST_BASIS_UNSUPPORTED"


class WeatherDemandPredictionCoreError(WeatherDemandPredictionError):
    code = "WEATHER_DEMAND_PREDICTION_CORE_ERROR"


class WeatherDemandPredictionReadError(WeatherDemandPredictionError):
    code = "WEATHER_DEMAND_PREDICTION_FORECAST_READ_ERROR"


class WeatherDemandPredictionReadOverflowError(WeatherDemandPredictionReadError):
    code = "WEATHER_DEMAND_PREDICTION_FORECAST_READ_OVERFLOW"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WeatherDemandPredictionValidationError(message)


def _text(value: object, name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{name} must be non-empty")
    return value.strip()


def _utc(value: object, name: str) -> datetime:
    _require(
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None,
        f"{name} must be an aware UTC datetime",
    )
    return value.astimezone(UTC)


def _hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _vintage_id(vintage: ForecastVintageRef | None) -> str | None:
    if vintage is None:
        return None
    return f"{vintage.provider}/{vintage.model}/{vintage.run_id}@{vintage.issued_at.isoformat()}"


def _bridge_payload(config: WeatherDemandBridgeConfig) -> dict[str, object]:
    return {
        "feature_policy_hash": config.feature_policy.policy_hash,
        "prediction_origin": config.prediction_origin.isoformat(),
        "gas_days": [day.isoformat() for day in config.gas_days],
        "max_hold_minutes": config.max_hold_minutes,
        "max_rows": config.max_rows,
        "max_points": config.max_points,
        "max_window_days": config.max_window_days,
        "max_cross_product": config.max_cross_product,
        "max_intervals": config.max_intervals,
    }


@dataclass(frozen=True)
class WeatherDemandPredictionDiagnostic:
    code: WeatherDemandPredictionDiagnosticCode
    detail: str
    gas_day: date


@dataclass(frozen=True)
class WeatherDemandPredictionEvidence:
    request_hash: str
    model_result: DemandModelResult
    feature_policy_hash: str
    forecast_evidence_basis: ForecastEvidenceBasis
    consumption_basis: PredictionConsumptionBasis
    weather_consumed: bool
    forecast_observation_ids: tuple[str, ...]
    selected_vintage: ForecastVintageRef | None
    selected_vintage_id: str | None
    feature_source_refs: tuple[str, ...]
    degree_day_source_refs: tuple[str, ...]
    regional_weighting_evidence_ref: str
    regional_weighting_evidence_basis: str = REGIONAL_WEIGHTING_EVIDENCE_BASIS
    research_label: str = RESEARCH_ONLY_LABEL

    @property
    def model_source_refs(self) -> tuple[str, ...]:
        return self.model_result.selected_model.source_refs

    @property
    def model_target_revision_ids(self) -> tuple[str, ...]:
        return self.model_result.selected_model.target_revision_ids

    @property
    def native_unit(self) -> str:
        return self.model_result.selected_model.target_unit


@dataclass(frozen=True)
class WeatherDemandPredictionRequest:
    model_result: DemandModelResult
    gas_day: date
    prediction_origin: datetime
    degree_day_policy: DegreeDayPolicy
    bridge_config: WeatherDemandBridgeConfig
    point_bindings: tuple[ForecastPointBinding, ...]
    regional_weighting_evidence_ref: str
    forecast_read_limit: int = MAX_FORECAST_READ_LIMIT
    forecast_evidence_basis: ForecastEvidenceBasis = (
        ForecastEvidenceBasis.GENUINE_RECEIPT_AVAILABILITY
    )

    def __post_init__(self) -> None:
        _require(isinstance(self.model_result, DemandModelResult), "bad model_result")
        _require(type(self.gas_day) is date, "gas_day must be a date")
        object.__setattr__(
            self, "prediction_origin", _utc(self.prediction_origin, "prediction_origin")
        )
        _require(
            isinstance(self.degree_day_policy, DegreeDayPolicy),
            "degree_day_policy invalid",
        )
        _require(
            isinstance(self.bridge_config, WeatherDemandBridgeConfig),
            "bridge_config invalid",
        )
        raw = self.point_bindings
        _require(
            not isinstance(raw, (str, bytes)) and isinstance(raw, Sequence),
            "point_bindings must be a sequence",
        )
        bindings = tuple(raw)
        _require(
            1 <= len(bindings) <= MAX_IDENTIFIERS,
            f"point_bindings must contain 1..{MAX_IDENTIFIERS} entries",
        )
        _require(
            all(isinstance(binding, ForecastPointBinding) for binding in bindings),
            "point_bindings have an unsupported type",
        )
        object.__setattr__(self, "point_bindings", bindings)
        object.__setattr__(
            self,
            "regional_weighting_evidence_ref",
            _text(self.regional_weighting_evidence_ref, "regional_weighting_evidence_ref"),
        )
        limit = self.forecast_read_limit
        _require(
            not isinstance(limit, bool) and isinstance(limit, int),
            "forecast_read_limit must be an integer",
        )
        _require(
            1 <= limit <= MAX_FORECAST_READ_LIMIT,
            f"forecast_read_limit must be in [1, {MAX_FORECAST_READ_LIMIT}]",
        )
        try:
            basis = ForecastEvidenceBasis(self.forecast_evidence_basis)
        except (TypeError, ValueError) as exc:
            raise WeatherDemandPredictionArchiveBasisError(
                "only genuine receipt availability is implemented; no archive fallback exists"
            ) from exc
        _require(
            basis is ForecastEvidenceBasis.GENUINE_RECEIPT_AVAILABILITY,
            "only genuine receipt availability is implemented; no archive fallback exists",
        )
        object.__setattr__(self, "forecast_evidence_basis", basis)
        self._validate_model()
        self._validate_bridge_and_bindings()

    def _validate_model(self) -> None:
        result = self.model_result
        evidence = result.selection_evidence
        _require(evidence is not None, "no selection evidence")
        _require(
            evidence.validation_as_of <= self.prediction_origin,
            "prediction origin precedes selection evidence",
        )
        _require(
            result.production_promotion is PromotionStatus.NOT_PROMOTED,
            "only a non-promoted research result is accepted",
        )
        _require(
            result.validation_basis is not ValidationBasis.SYNTHETIC_NOT_REAL,
            "synthetic validation evidence is not accepted",
        )
        selected = result.selected_model
        _require(
            selected.kind
            in {ModelKind.WEATHER_CALENDAR_RIDGE, ModelKind.CALENDAR_BASELINE},
            "selected model kind is unsupported",
        )
        if selected.kind is ModelKind.WEATHER_CALENDAR_RIDGE:
            _require(
                result.validation_basis is ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS,
                "weather prediction requires genuine forecast-vintage OOS validation",
            )
        policy = self.bridge_config.feature_policy
        _require(
            selected.target_scope is TargetScope.GB_NTS_THROUGHPUT,
            "model target scope is unsupported",
        )
        _require(selected.region == SUPPORTED_REGION, f"model region is not {SUPPORTED_REGION}")
        _require(selected.target_unit == TARGET_UNIT, f"model native unit is not {TARGET_UNIT}")
        _require(
            selected.gas_day_calendar == policy.gas_day_calendar,
            "model gas-day calendar mismatch",
        )
        _require(
            selected.feature_policy_hash == policy.policy_hash,
            "model feature-policy hash mismatch",
        )

    def _validate_bridge_and_bindings(self) -> None:
        config = self.bridge_config
        policy = config.feature_policy
        _require(
            config.gas_days == (self.gas_day,),
            "bridge_config must contain exactly the requested gas day",
        )
        _require(
            config.prediction_origin == self.prediction_origin,
            "bridge prediction origin mismatch",
        )
        degree = self.degree_day_policy
        _require(
            degree.heating_base_c == policy.heating_base_c
            and degree.cooling_base_c == policy.cooling_base_c
            and degree.max_gap_minutes == policy.max_gap_minutes
            and degree.min_covered_fraction == policy.min_covered_fraction
            and degree.method_version == policy.method_version,
            "degree-day policy mismatch",
        )
        _require(
            len(self.point_bindings) <= config.max_points,
            "point_bindings exceed max_points",
        )
        weighted = {weight.location_id for weight in policy.location_weights}
        points: set[str] = set()
        locations: set[str] = set()
        names = ("point_id", "series_id", "entity_id", "location_id", "region")
        for binding in self.point_bindings:
            _require(
                all(
                    isinstance(getattr(binding, name), str)
                    and bool(getattr(binding, name).strip())
                    for name in names
                ),
                "point binding fields must be non-empty",
            )
            _require(
                binding.region == policy.region,
                "every point binding region must match the feature policy region",
            )
            _require(
                binding.location_id in weighted,
                "point binding location has no explicit feature weight",
            )
            _require(
                binding.point_id not in points and binding.location_id not in locations,
                "point_bindings contain a duplicate point or weighted location",
            )
            points.add(binding.point_id)
            locations.add(binding.location_id)

    @property
    def request_hash(self) -> str:
        result = self.model_result
        selected = result.selected_model
        evidence = result.selection_evidence
        _require(evidence is not None, "no selection evidence")
        return _hash(
            {
                "schema": RUNTIME_SCHEMA,
                "model": {
                    "selected_model_hash": selected.model_hash,
                    "baseline_model_hash": result.baseline_model.model_hash,
                    "candidate_model_hash": (
                        result.candidate_model.model_hash
                        if result.candidate_model is not None
                        else None
                    ),
                    "selection_hash": result.selection_hash,
                    "selection_as_of": evidence.validation_as_of.isoformat(),
                    "kind": selected.kind.value,
                    "feature_policy_hash": selected.feature_policy_hash,
                    "validation_basis": result.validation_basis.value,
                },
                "gas_day": self.gas_day.isoformat(),
                "prediction_origin": self.prediction_origin.isoformat(),
                "degree_day_policy": {
                    "heating_base_c": self.degree_day_policy.heating_base_c,
                    "cooling_base_c": self.degree_day_policy.cooling_base_c,
                    "max_gap_minutes": self.degree_day_policy.max_gap_minutes,
                    "min_covered_fraction": self.degree_day_policy.min_covered_fraction,
                    "method_version": self.degree_day_policy.method_version,
                },
                "bridge": _bridge_payload(self.bridge_config),
                "bindings": [asdict(binding) for binding in self.point_bindings],
                "regional_weighting_evidence_ref": self.regional_weighting_evidence_ref,
                "forecast_read_limit": self.forecast_read_limit,
                "forecast_evidence_basis": self.forecast_evidence_basis.value,
            }
        )


@dataclass(frozen=True)
class WeatherDemandPredictionResult:
    status: WeatherDemandPredictionStatus
    request_hash: str
    prediction: DemandPrediction | None
    evidence: WeatherDemandPredictionEvidence
    feature_row: DailyWeatherFeature | None
    degree_day_result: DegreeDayResult | None
    diagnostics: tuple[WeatherDemandPredictionDiagnostic, ...]
    forecast_raw_count: int
    research_only: bool = True
    production_promotion: PromotionStatus = PromotionStatus.NOT_PROMOTED
    prospective_accuracy_claim: bool = False
    gb_representative_claim: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", WeatherDemandPredictionStatus(self.status))
        _require(isinstance(self.evidence, WeatherDemandPredictionEvidence), "bad evidence type")
        _require(
            self.prediction is None or isinstance(self.prediction, DemandPrediction),
            "bad prediction type",
        )
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        _require(self.research_only, "research-only required")
        object.__setattr__(
            self, "production_promotion", PromotionStatus(self.production_promotion)
        )
        _require(
            self.production_promotion is PromotionStatus.NOT_PROMOTED,
            "promotion is not allowed",
        )
        _require(
            not self.prospective_accuracy_claim and not self.gb_representative_claim,
            "accuracy or representative claims are not allowed",
        )
        if self.status is WeatherDemandPredictionStatus.READY:
            _require(self.prediction is not None, "READY prediction is missing")
        else:
            _require(
                self.prediction is None
                and self.evidence.consumption_basis is PredictionConsumptionBasis.NONE,
                "insufficient result is inconsistent",
            )

    @property
    def has_prediction(self) -> bool:
        return self.prediction is not None

    @property
    def native_unit(self) -> str:
        return self.evidence.native_unit

    @property
    def selected_vintage(self) -> ForecastVintageRef | None:
        return self.evidence.selected_vintage

    @property
    def forecast_observation_ids(self) -> tuple[str, ...]:
        return self.evidence.forecast_observation_ids

    @property
    def weather_consumed(self) -> bool:
        return self.evidence.weather_consumed

    @property
    def baseline_reference(self) -> bool:
        return (
            self.evidence.consumption_basis
            is PredictionConsumptionBasis.CALENDAR_BASELINE_REFERENCE
        )


def _observation_ids(records: Sequence[object]) -> tuple[str, ...]:
    ids = {
        value
        for record in records
        if isinstance(value := getattr(record, "forecast_observation_id", None), str)
        and value
    }
    return tuple(sorted(ids))


def _read_forecast_records(
    session: Session, request: WeatherDemandPredictionRequest
) -> list[object]:
    config = request.bridge_config
    policy = config.feature_policy
    series_ids = tuple(sorted({binding.series_id for binding in request.point_bindings}))
    entity_ids = tuple(sorted({binding.entity_id for binding in request.point_bindings}))
    day_start = gas_day_start_for_date(request.gas_day, policy.gas_day_calendar)
    day_end = gas_day_start_for_date(
        request.gas_day + timedelta(days=1), policy.gas_day_calendar
    )
    hold = timedelta(minutes=config.max_hold_minutes)
    return read_ecmwf_forecasts(
        session,
        series_ids,
        entity_ids,
        request.prediction_origin,
        day_start - hold,
        day_end + hold + _ONE_MICROSECOND,
        min(request.forecast_read_limit, config.max_rows),
    )


def _prediction_request(
    request: WeatherDemandPredictionRequest, feature: DailyWeatherFeature | None
) -> DemandPredictionRequest:
    model = request.model_result.selected_model
    return DemandPredictionRequest(
        gas_day=request.gas_day,
        prediction_origin=request.prediction_origin,
        target_scope=model.target_scope,
        region=model.region,
        target_unit=model.target_unit,
        gas_day_calendar=model.gas_day_calendar,
        weather_feature=feature,
    )


def _build_result(
    request: WeatherDemandPredictionRequest,
    *,
    status: WeatherDemandPredictionStatus,
    prediction: DemandPrediction | None,
    consumption_basis: PredictionConsumptionBasis,
    weather_consumed: bool,
    forecast_observation_ids: tuple[str, ...],
    selected_vintage: ForecastVintageRef | None,
    feature_source_refs: tuple[str, ...],
    degree_day_source_refs: tuple[str, ...],
    feature_row: DailyWeatherFeature | None,
    degree_day_result: DegreeDayResult | None,
    diagnostics: tuple[WeatherDemandPredictionDiagnostic, ...],
    forecast_raw_count: int,
) -> WeatherDemandPredictionResult:
    result = request.model_result
    return WeatherDemandPredictionResult(
        status=status,
        request_hash=request.request_hash,
        prediction=prediction,
        evidence=WeatherDemandPredictionEvidence(
            request_hash=request.request_hash,
            model_result=result,
            feature_policy_hash=request.bridge_config.feature_policy.policy_hash,
            forecast_evidence_basis=request.forecast_evidence_basis,
            consumption_basis=consumption_basis,
            weather_consumed=weather_consumed,
            forecast_observation_ids=forecast_observation_ids,
            selected_vintage=selected_vintage,
            selected_vintage_id=_vintage_id(selected_vintage),
            feature_source_refs=feature_source_refs,
            degree_day_source_refs=degree_day_source_refs,
            regional_weighting_evidence_ref=request.regional_weighting_evidence_ref,
        ),
        feature_row=feature_row,
        degree_day_result=degree_day_result,
        diagnostics=diagnostics,
        forecast_raw_count=forecast_raw_count,
    )


def _insufficient(
    request: WeatherDemandPredictionRequest,
    *,
    records: Sequence[object],
    bundle: WeatherDemandInputBundle | None,
    degree_result: DegreeDayResult | None,
    code: WeatherDemandPredictionDiagnosticCode,
    detail: str,
) -> WeatherDemandPredictionResult:
    observation_ids = _observation_ids(records)
    selected_vintage = bundle.selected_vintage if bundle is not None else None
    return _build_result(
        request,
        status=WeatherDemandPredictionStatus.INSUFFICIENT_FORECAST_COVERAGE,
        prediction=None,
        consumption_basis=PredictionConsumptionBasis.NONE,
        weather_consumed=False,
        forecast_observation_ids=observation_ids,
        selected_vintage=selected_vintage,
        feature_source_refs=(),
        degree_day_source_refs=(
            degree_result.source_refs if degree_result is not None else ()
        ),
        feature_row=None,
        degree_day_result=degree_result,
        diagnostics=(
            WeatherDemandPredictionDiagnostic(
                code=code,
                detail=detail,
                gas_day=request.gas_day,
            ),
        ),
        forecast_raw_count=len(records),
    )


def run_weather_demand_prediction_runtime(
    session: Session, request: WeatherDemandPredictionRequest
) -> WeatherDemandPredictionResult:
    """Compose the bounded persisted-forecast-to-frozen-prediction path."""

    if not isinstance(request, WeatherDemandPredictionRequest):
        raise TypeError("request must be a WeatherDemandPredictionRequest")
    selected = request.model_result.selected_model
    try:
        if selected.kind is ModelKind.CALENDAR_BASELINE:
            prediction = predict_selected_demand(
                request.model_result, _prediction_request(request, None)
            )
            return _build_result(
                request,
                status=WeatherDemandPredictionStatus.READY,
                prediction=prediction,
                consumption_basis=PredictionConsumptionBasis.CALENDAR_BASELINE_REFERENCE,
                weather_consumed=False,
                forecast_observation_ids=(),
                selected_vintage=None,
                feature_source_refs=(),
                degree_day_source_refs=(),
                feature_row=None,
                degree_day_result=None,
                diagnostics=(),
                forecast_raw_count=0,
            )
        records = _read_forecast_records(session, request)
        observation_ids = _observation_ids(records)
        bundle = build_weather_demand_inputs(
            tuple(project_forecast_observation_record(row) for row in records),
            request.point_bindings,
            request.bridge_config,
        )
        if not bundle.ready:
            return _insufficient(
                request,
                records=records,
                bundle=bundle,
                degree_result=None,
                code=WeatherDemandPredictionDiagnosticCode.FORECAST_BRIDGE_MISSING,
                detail="no derived interval; no zero weather or baseline was invented",
            )
        degree_result = compute_degree_days_from_bundle(bundle, request.degree_day_policy)
        if degree_result is None:
            return _insufficient(
                request,
                records=records,
                bundle=bundle,
                degree_result=None,
                code=WeatherDemandPredictionDiagnosticCode.NO_FEATURE_ROW,
                detail="the actual degree-day solver returned no result",
            )
        feature_rows = degree_result.feature_rows()
        if len(feature_rows) != 1 or feature_rows[0].gas_day != request.gas_day:
            reason = degree_result.daily[0].missing_reason if degree_result.daily else None
            return _insufficient(
                request,
                records=records,
                bundle=bundle,
                degree_result=degree_result,
                code=WeatherDemandPredictionDiagnosticCode.DEGREE_DAY_INCOMPLETE,
                detail=(
                    "degree-day coverage was incomplete; no zero-valued feature was invented"
                    + (f" ({reason})" if reason else "")
                ),
            )
        feature = feature_rows[0]
        prediction = predict_selected_demand(
            request.model_result, _prediction_request(request, feature)
        )
        if prediction.forecast_vintage is None:
            raise WeatherDemandPredictionCoreError("core prediction has no forecast vintage")
        return _build_result(
            request,
            status=WeatherDemandPredictionStatus.READY,
            prediction=prediction,
            consumption_basis=PredictionConsumptionBasis.WEATHER_FORECAST_VINTAGE,
            weather_consumed=True,
            forecast_observation_ids=observation_ids,
            selected_vintage=prediction.forecast_vintage,
            feature_source_refs=(feature.source_ref,),
            degree_day_source_refs=degree_result.source_refs,
            feature_row=feature,
            degree_day_result=degree_result,
            diagnostics=(),
            forecast_raw_count=len(records),
        )
    except WeatherDemandPredictionError:
        raise
    except EcmwfForecastReadOverflowError:
        raise WeatherDemandPredictionReadOverflowError(
            "persisted forecast read exceeded the explicit bound; no partial prediction "
            "was produced"
        ) from None
    except EcmwfForecastReadValidationError:
        raise WeatherDemandPredictionValidationError(
            "persisted forecast read rejected the explicit bound or identifiers"
        ) from None
    except (EcmwfForecastReadError, SQLAlchemyError):
        raise WeatherDemandPredictionReadError(
            "persisted forecast read failed; no prediction was produced"
        ) from None
    except WeatherDemandInputError as exc:
        raise WeatherDemandPredictionCoreError(str(exc)) from None
