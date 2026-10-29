"""Read-only point-in-time composition of persisted demand and ECMWF weather.

This module is the bounded application path from an explicit caller request to
the already-frozen domain fitter.  It reads National Gas target revisions and
persisted ECMWF forecast observations, projects the forecast rows, derives
degree-day features, and calls :func:`fit_weather_demand_model`.  It contains no
alternative degree-day mathematics, no replacement solver, no synthetic fill and
no prediction path.

The caller owns authorization, entitlement and source activation.  This module
grants none of them.  It performs no write, commit, flush, network request,
source-registry mutation or model promotion.  Both repository reads run under
their own query-scoped ``no_autoflush`` guard, so pending caller work is left
untouched.

Every target revision admitted by the point-in-time reader/mapper is passed to
the fitter once the explicit training-readiness gate is satisfied.  If the
paired target/weather training days visible at ``training_cutoff`` are fewer than
the policy's ``min_training_rows``, the composer returns
``INSUFFICIENT_REAL_HISTORY`` before invoking the fitter, so the core cannot emit
a fitted calendar baseline from an under-populated selection.  The fitter
independently resolves the revision genuinely available at each fold cutoff; this
composer never narrows the target history to a global latest revision. Each
requested gas day has its own explicit prediction origin
and its own forecast read, so a later issue/receipt cannot leak into an earlier
day's feature row.  A missing or incomplete day is reported and omitted, never
filled with zero or an older vintage.

Successful output remains research-only.  The frozen core may select the
calendar baseline or the weather candidate, and both carry the core's own use
label and model/selection hashes.  No model is promoted, persisted or exposed as
a client forecast claim.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from eurogas_nexus.application.research.demand_target_inputs import (
    SUPPORTED_REGION,
    SUPPORTED_SOURCE_FORMATS,
    TARGET_UNIT,
    DemandTargetInputs,
    build_demand_target_rows,
)
from eurogas_nexus.application.research.weather_demand_inputs import (
    BridgeDiagnostic,
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
    build_weather_demand_inputs,
    compute_degree_days_from_bundle,
    project_forecast_observation_record,
)
from eurogas_nexus.db.repositories.demand import (
    MAX_DEMAND_TARGET_READ_LIMIT,
    read_demand_target_revisions,
)
from eurogas_nexus.db.repositories.ecmwf_forecast_reads import (
    MAX_LIMIT as MAX_FORECAST_READ_LIMIT,
)
from eurogas_nexus.db.repositories.ecmwf_forecast_reads import (
    read_ecmwf_forecasts,
)
from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
from eurogas_nexus.domain.ontology.vocabulary import TargetScope
from eurogas_nexus.domain.research.weather_demand import (
    DailyWeatherFeature,
    DegreeDayFeaturePolicy,
    DegreeDayPolicy,
    DegreeDayResult,
    DemandModelPolicy,
    DemandModelResult,
    ForecastVintageRef,
    MissingNumpyError,
    PromotionStatus,
    ValidationBasis,
    WeatherDemandInputError,
    fit_weather_demand_model,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RUNTIME_SCHEMA = "weather-demand-runtime/v1"
MAX_BRIDGE_DAYS = 366
RESEARCH_ONLY_LABEL = "RESEARCH_ONLY_UNVALIDATED_OOS"
REGIONAL_WEIGHTING_EVIDENCE_BASIS = "CALLER_DECLARED_PROVENANCE_NOT_REVIEWED"
_TARGET_DATE_MIN = date(2000, 1, 1)
_TARGET_DATE_MAX = date(2100, 12, 31)
_NO_TRAINING_ROWS = "no training rows were available at training_cutoff"


class WeatherDemandRuntimeError(ValueError):
    """Base typed refusal for runtime composition."""

    code = "WEATHER_DEMAND_RUNTIME_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class WeatherDemandRuntimeValidationError(WeatherDemandRuntimeError):
    """An explicit runtime request violates the frozen composition contract."""

    code = "WEATHER_DEMAND_RUNTIME_VALIDATION_ERROR"


class WeatherDemandRuntimeSyntheticBasisError(WeatherDemandRuntimeValidationError):
    """Synthetic validation evidence is not admissible through this runtime."""

    code = "SYNTHETIC_VALIDATION_BASIS_REJECTED"


class WeatherDemandRuntimeStatus(StrEnum):
    """Whether the frozen fitter produced an actual research model."""

    READY = "READY"
    INSUFFICIENT_REAL_HISTORY = "INSUFFICIENT_REAL_HISTORY"
    NUMPY_NOT_INSTALLED = "NUMPY_NOT_INSTALLED"


class WeatherDemandRuntimeDiagnosticCode(StrEnum):
    """Stable, operator-safe runtime composition diagnostics."""

    NO_ADMITTED_TARGET_REVISIONS = "NO_ADMITTED_TARGET_REVISIONS"
    NO_ELIGIBLE_FEATURES = "NO_ELIGIBLE_FEATURES"
    FORECAST_DAY_OMITTED = "FORECAST_DAY_OMITTED"
    INSUFFICIENT_TRAINING_HISTORY = "INSUFFICIENT_TRAINING_HISTORY"
    NUMPY_NOT_INSTALLED = "NUMPY_NOT_INSTALLED"


class WeatherDemandOmissionReason(StrEnum):
    """Why one requested weather day produced no usable feature row."""

    FORECAST_BRIDGE_MISSING = "FORECAST_BRIDGE_MISSING"
    DEGREE_DAY_INCOMPLETE = "DEGREE_DAY_INCOMPLETE"
    NO_FEATURE_ROW = "NO_FEATURE_ROW"


@dataclass(frozen=True)
class WeatherDemandRuntimeDiagnostic:
    """One runtime-level diagnostic with an optional gas-day scope."""

    code: WeatherDemandRuntimeDiagnosticCode
    detail: str
    gas_day: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", WeatherDemandRuntimeDiagnosticCode(self.code))
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise WeatherDemandRuntimeValidationError("diagnostic detail must be non-empty")
        if self.gas_day is not None and (
            not isinstance(self.gas_day, date) or isinstance(self.gas_day, datetime)
        ):
            raise WeatherDemandRuntimeValidationError("diagnostic gas_day must be a date")


@dataclass(frozen=True)
class OmittedWeatherDay:
    """One requested day that produced no feature row, with retained evidence."""

    gas_day: date
    reason: WeatherDemandOmissionReason
    detail: str
    bridge_diagnostics: tuple[BridgeDiagnostic, ...] = ()
    forecast_observation_ids: tuple[str, ...] = ()
    selected_vintage: ForecastVintageRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.gas_day, date) or isinstance(self.gas_day, datetime):
            raise WeatherDemandRuntimeValidationError("omitted gas_day must be a date")
        object.__setattr__(self, "reason", WeatherDemandOmissionReason(self.reason))
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise WeatherDemandRuntimeValidationError("omission detail must be non-empty")
        object.__setattr__(self, "bridge_diagnostics", tuple(self.bridge_diagnostics))
        object.__setattr__(
            self,
            "forecast_observation_ids",
            tuple(sorted(set(self.forecast_observation_ids))),
        )


@dataclass(frozen=True)
class WeatherDemandRuntimeEvidence:
    """Immutable identifiers, hashes and declared evidence for one composition."""

    request_hash: str
    target_revision_ids: tuple[str, ...]
    target_source_refs: tuple[str, ...]
    forecast_observation_ids: tuple[str, ...]
    feature_source_refs: tuple[str, ...]
    degree_day_source_refs: tuple[str, ...]
    selected_vintage_ids: tuple[str, ...]
    feature_policy_hash: str
    degree_day_method_version: str
    validation_basis: ValidationBasis
    training_cutoff: datetime
    validation_as_of: datetime
    baseline_model_hash: str | None
    candidate_model_hash: str | None
    selected_model_hash: str | None
    model_selection_hash: str | None
    regional_weighting_evidence_ref: str
    regional_weighting_evidence_basis: str = REGIONAL_WEIGHTING_EVIDENCE_BASIS

    def __post_init__(self) -> None:
        for name in (
            "request_hash",
            "feature_policy_hash",
            "degree_day_method_version",
            "regional_weighting_evidence_ref",
            "regional_weighting_evidence_basis",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise WeatherDemandRuntimeValidationError(f"{name} must be non-empty")
        object.__setattr__(self, "validation_basis", ValidationBasis(self.validation_basis))
        object.__setattr__(
            self, "training_cutoff", _utc(self.training_cutoff, "training_cutoff")
        )
        object.__setattr__(
            self, "validation_as_of", _utc(self.validation_as_of, "validation_as_of")
        )
        for name in (
            "target_revision_ids",
            "target_source_refs",
            "forecast_observation_ids",
            "feature_source_refs",
            "degree_day_source_refs",
            "selected_vintage_ids",
        ):
            object.__setattr__(self, name, tuple(sorted(set(getattr(self, name)))))


@dataclass(frozen=True)
class WeatherDemandRuntimeRequest:
    """Explicit caller-owned selection, policies, bindings and work bounds."""

    model_policy: DemandModelPolicy
    degree_day_policy: DegreeDayPolicy
    bridge_configs: tuple[WeatherDemandBridgeConfig, ...]
    point_bindings: tuple[ForecastPointBinding, ...]
    provider_item_id: str
    source_format: str
    target_gas_day_from: date
    target_gas_day_to: date
    allow_provisional_targets: bool
    regional_weighting_evidence_ref: str
    target_read_limit: int = 1_000
    forecast_read_limit: int = MAX_FORECAST_READ_LIMIT

    def __post_init__(self) -> None:
        if not isinstance(self.model_policy, DemandModelPolicy):
            raise WeatherDemandRuntimeValidationError(
                "model_policy must be a DemandModelPolicy"
            )
        if not isinstance(self.degree_day_policy, DegreeDayPolicy):
            raise WeatherDemandRuntimeValidationError(
                "degree_day_policy must be a DegreeDayPolicy"
            )
        if (
            self.model_policy.validation_basis
            is ValidationBasis.SYNTHETIC_NOT_REAL
        ):
            raise WeatherDemandRuntimeSyntheticBasisError(
                "the runtime composition refuses ValidationBasis.SYNTHETIC_NOT_REAL"
            )
        if self.model_policy.target_scope is not TargetScope.GB_NTS_THROUGHPUT:
            raise WeatherDemandRuntimeValidationError(
                "only the GB_NTS_THROUGHPUT target scope is supported"
            )
        if self.model_policy.region != SUPPORTED_REGION:
            raise WeatherDemandRuntimeValidationError(
                f"only the {SUPPORTED_REGION} target region is supported"
            )
        if self.model_policy.target_unit != TARGET_UNIT:
            raise WeatherDemandRuntimeValidationError(
                f"only the native {TARGET_UNIT} target unit is supported"
            )
        expected = self.model_policy.expected_feature_policy
        self._validate_degree_day_policy(expected)
        self._validate_bridges(expected)
        self._validate_bindings(expected)
        self._validate_target_selection()

    def _validate_degree_day_policy(self, expected: DegreeDayFeaturePolicy) -> None:
        policy = self.degree_day_policy
        mismatches = []
        if policy.heating_base_c != expected.heating_base_c:
            mismatches.append("heating_base_c")
        if policy.cooling_base_c != expected.cooling_base_c:
            mismatches.append("cooling_base_c")
        if policy.max_gap_minutes != expected.max_gap_minutes:
            mismatches.append("max_gap_minutes")
        if policy.min_covered_fraction != expected.min_covered_fraction:
            mismatches.append("min_covered_fraction")
        if policy.method_version != expected.method_version:
            mismatches.append("method_version")
        if mismatches:
            raise WeatherDemandRuntimeValidationError(
                "degree-day policy does not match the model feature policy: "
                + ", ".join(mismatches)
            )

    def _validate_bridges(self, expected: DegreeDayFeaturePolicy) -> None:
        raw = self.bridge_configs
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise WeatherDemandRuntimeValidationError(
                "bridge_configs must be a sequence of WeatherDemandBridgeConfig values"
            )
        configs = tuple(raw)
        if not 1 <= len(configs) <= MAX_BRIDGE_DAYS:
            raise WeatherDemandRuntimeValidationError(
                f"bridge_configs must contain 1..{MAX_BRIDGE_DAYS} entries"
            )
        days: list[date] = []
        for config in configs:
            if not isinstance(config, WeatherDemandBridgeConfig):
                raise WeatherDemandRuntimeValidationError(
                    "bridge_configs must contain WeatherDemandBridgeConfig values"
                )
            if len(config.gas_days) != 1:
                raise WeatherDemandRuntimeValidationError(
                    "each bridge config must contain exactly one gas day"
                )
            day = config.gas_days[0]
            policy = config.feature_policy
            if policy.policy_hash != expected.policy_hash:
                raise WeatherDemandRuntimeValidationError(
                    "every bridge feature-policy hash must match the model policy"
                )
            if policy.region != expected.region:
                raise WeatherDemandRuntimeValidationError(
                    "every bridge feature region must match the model region"
                )
            if policy.gas_day_calendar != expected.gas_day_calendar:
                raise WeatherDemandRuntimeValidationError(
                    "every bridge feature calendar must match the model calendar"
                )
            if policy.location_weights != expected.location_weights:
                raise WeatherDemandRuntimeValidationError(
                    "every bridge must use the model's explicit location weights"
                )
            if policy.temporal_method is not expected.temporal_method:
                raise WeatherDemandRuntimeValidationError(
                    "every bridge feature must use the model temporal method"
                )
            day_end = gas_day_start_for_date(
                day + timedelta(days=1), policy.gas_day_calendar
            )
            if config.prediction_origin >= day_end:
                raise WeatherDemandRuntimeValidationError(
                    "bridge prediction origin must precede the requested gas-day end"
                )
            days.append(day)
        if len(set(days)) != len(days):
            raise WeatherDemandRuntimeValidationError(
                "bridge_configs contain duplicate gas days"
            )
        object.__setattr__(
            self,
            "bridge_configs",
            tuple(sorted(configs, key=lambda item: item.gas_days[0])),
        )

    def _validate_bindings(self, expected: DegreeDayFeaturePolicy) -> None:
        raw = self.point_bindings
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise WeatherDemandRuntimeValidationError(
                "point_bindings must be a sequence of ForecastPointBinding values"
            )
        bindings = tuple(raw)
        if not bindings:
            raise WeatherDemandRuntimeValidationError(
                "at least one explicit point binding is required"
            )
        weighted_locations = {
            weight.location_id for weight in expected.location_weights
        }
        seen_points: set[str] = set()
        seen_locations: set[str] = set()
        for binding in bindings:
            if not isinstance(binding, ForecastPointBinding):
                raise WeatherDemandRuntimeValidationError(
                    "point_bindings must contain ForecastPointBinding values"
                )
            for name in ("point_id", "series_id", "entity_id", "location_id", "region"):
                value = getattr(binding, name)
                if not isinstance(value, str) or not value.strip():
                    raise WeatherDemandRuntimeValidationError(
                        f"point binding {name} must be non-empty"
                    )
            if binding.region != expected.region:
                raise WeatherDemandRuntimeValidationError(
                    "every point binding region must match the model region"
                )
            if binding.location_id not in weighted_locations:
                raise WeatherDemandRuntimeValidationError(
                    "every point binding location must have an explicit model weight"
                )
            if binding.point_id in seen_points:
                raise WeatherDemandRuntimeValidationError(
                    "point_bindings contain a duplicate point id"
                )
            if binding.location_id in seen_locations:
                raise WeatherDemandRuntimeValidationError(
                    "point_bindings contain a duplicate weighted location"
                )
            seen_points.add(binding.point_id)
            seen_locations.add(binding.location_id)
        object.__setattr__(self, "point_bindings", bindings)

    def _validate_target_selection(self) -> None:
        if not isinstance(self.provider_item_id, str) or not self.provider_item_id.strip():
            raise WeatherDemandRuntimeValidationError(
                "provider_item_id must be a non-empty explicit source item"
            )
        if (
            not isinstance(self.source_format, str)
            or self.source_format not in SUPPORTED_SOURCE_FORMATS
        ):
            raise WeatherDemandRuntimeValidationError("source_format must be CSV or REST")
        for name, value in (
            ("target_gas_day_from", self.target_gas_day_from),
            ("target_gas_day_to", self.target_gas_day_to),
        ):
            if not isinstance(value, date) or isinstance(value, datetime):
                raise WeatherDemandRuntimeValidationError(f"{name} must be a calendar date")
            if not _TARGET_DATE_MIN <= value <= _TARGET_DATE_MAX:
                raise WeatherDemandRuntimeValidationError(
                    f"{name} is outside the supported range"
                )
        if self.target_gas_day_from > self.target_gas_day_to:
            raise WeatherDemandRuntimeValidationError(
                "target_gas_day_from must not be after target_gas_day_to"
            )
        if not isinstance(self.allow_provisional_targets, bool):
            raise WeatherDemandRuntimeValidationError(
                "allow_provisional_targets must be a bool"
            )
        if (
            not isinstance(self.regional_weighting_evidence_ref, str)
            or not self.regional_weighting_evidence_ref.strip()
        ):
            raise WeatherDemandRuntimeValidationError(
                "regional_weighting_evidence_ref must be explicit caller provenance"
            )
        object.__setattr__(
            self,
            "regional_weighting_evidence_ref",
            self.regional_weighting_evidence_ref.strip(),
        )
        if (
            isinstance(self.target_read_limit, bool)
            or not isinstance(self.target_read_limit, int)
            or not 1 <= self.target_read_limit <= MAX_DEMAND_TARGET_READ_LIMIT
        ):
            raise WeatherDemandRuntimeValidationError(
                f"target_read_limit must be in [1, {MAX_DEMAND_TARGET_READ_LIMIT}]"
            )
        if (
            isinstance(self.forecast_read_limit, bool)
            or not isinstance(self.forecast_read_limit, int)
            or not 1 <= self.forecast_read_limit <= MAX_FORECAST_READ_LIMIT
        ):
            raise WeatherDemandRuntimeValidationError(
                f"forecast_read_limit must be in [1, {MAX_FORECAST_READ_LIMIT}]"
            )

    @property
    def request_hash(self) -> str:
        """Return a deterministic hash of every explicit runtime selection."""

        return _canonical_hash(
            {
                "schema": RUNTIME_SCHEMA,
                "model_policy": _model_policy_payload(self.model_policy),
                "degree_day_policy": {
                    "heating_base_c": self.degree_day_policy.heating_base_c,
                    "cooling_base_c": self.degree_day_policy.cooling_base_c,
                    "max_gap_minutes": self.degree_day_policy.max_gap_minutes,
                    "min_covered_fraction": self.degree_day_policy.min_covered_fraction,
                    "method_version": self.degree_day_policy.method_version,
                },
                "bridges": [
                    {
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
                    for config in self.bridge_configs
                ],
                "bindings": [
                    {
                        "point_id": binding.point_id,
                        "series_id": binding.series_id,
                        "entity_id": binding.entity_id,
                        "location_id": binding.location_id,
                        "region": binding.region,
                    }
                    for binding in self.point_bindings
                ],
                "provider_item_id": self.provider_item_id,
                "source_format": self.source_format,
                "target_gas_day_from": self.target_gas_day_from.isoformat(),
                "target_gas_day_to": self.target_gas_day_to.isoformat(),
                "allow_provisional_targets": self.allow_provisional_targets,
                "regional_weighting_evidence_ref": self.regional_weighting_evidence_ref,
                "target_read_limit": self.target_read_limit,
                "forecast_read_limit": self.forecast_read_limit,
            }
        )


@dataclass(frozen=True)
class WeatherDemandRuntimeResult:
    """Immutable composition outcome, counts, omitted-day reasons and evidence."""

    status: WeatherDemandRuntimeStatus
    request_hash: str
    target_inputs: DemandTargetInputs
    feature_rows: tuple[DailyWeatherFeature, ...]
    degree_day_results: tuple[DegreeDayResult, ...]
    model_result: DemandModelResult | None
    omitted_days: tuple[OmittedWeatherDay, ...]
    diagnostics: tuple[WeatherDemandRuntimeDiagnostic, ...]
    source_format: str
    provider_item_id: str
    native_unit: str
    target_revision_count: int
    target_distinct_gas_days: int
    feature_day_count: int
    forecast_raw_count: int
    selected_vintages: tuple[ForecastVintageRef, ...]
    paired_eligible_training_day_count: int
    evidence: WeatherDemandRuntimeEvidence
    research_only: bool = True
    production_promotion: PromotionStatus = PromotionStatus.NOT_PROMOTED

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", WeatherDemandRuntimeStatus(self.status))
        if not isinstance(self.target_inputs, DemandTargetInputs):
            raise WeatherDemandRuntimeValidationError(
                "target_inputs must be DemandTargetInputs"
            )
        object.__setattr__(self, "feature_rows", tuple(self.feature_rows))
        object.__setattr__(self, "degree_day_results", tuple(self.degree_day_results))
        object.__setattr__(self, "omitted_days", tuple(self.omitted_days))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "selected_vintages", tuple(self.selected_vintages))
        object.__setattr__(
            self,
            "production_promotion",
            PromotionStatus(self.production_promotion),
        )
        if self.status is WeatherDemandRuntimeStatus.READY and self.model_result is None:
            raise WeatherDemandRuntimeValidationError(
                "READY composition must carry the actual fitted model result"
            )
        if self.status is not WeatherDemandRuntimeStatus.READY and self.model_result is not None:
            raise WeatherDemandRuntimeValidationError(
                "non-READY composition must not carry a model result"
            )
        for name in (
            "target_revision_count",
            "target_distinct_gas_days",
            "feature_day_count",
            "forecast_raw_count",
            "paired_eligible_training_day_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WeatherDemandRuntimeValidationError(
                    f"{name} must be a non-negative integer"
                )
        if self.target_revision_count != len(self.target_inputs.rows):
            raise WeatherDemandRuntimeValidationError(
                "target_revision_count does not match admitted target revisions"
            )
        if self.target_distinct_gas_days != len(
            {row.gas_day for row in self.target_inputs.rows}
        ):
            raise WeatherDemandRuntimeValidationError(
                "target_distinct_gas_days does not match admitted target revisions"
            )
        if self.feature_day_count != len(self.feature_rows):
            raise WeatherDemandRuntimeValidationError(
                "feature_day_count does not match actual feature rows"
            )
        if not self.research_only:
            raise WeatherDemandRuntimeValidationError(
                "runtime composition is always research-only"
            )
        if self.production_promotion is not PromotionStatus.NOT_PROMOTED:
            raise WeatherDemandRuntimeValidationError(
                "runtime composition never promotes a model"
            )

    @property
    def forecast_row_count(self) -> int:
        """Alias for the number of raw persisted forecast rows read."""

        return self.forecast_raw_count

    @property
    def model(self) -> DemandModelResult | None:
        """Alias for the actual fitted core result, when one exists."""

        return self.model_result

    @property
    def target_revisions(self) -> tuple[object, ...]:
        """Return every admitted target revision in point-in-time order."""

        return self.target_inputs.rows

    @property
    def target_revision_ids(self) -> tuple[str, ...]:
        """Return the immutable admitted target revision identifiers."""

        return self.evidence.target_revision_ids

    @property
    def forecast_observation_ids(self) -> tuple[str, ...]:
        """Return every raw forecast observation identifier read."""

        return self.evidence.forecast_observation_ids

    @property
    def has_model(self) -> bool:
        """Return whether the actual frozen fitter produced a model result."""

        return self.model_result is not None

    @property
    def dependency_code(self) -> str | None:
        """Return the typed dependency code when fitting was unavailable."""

        if self.status is WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED:
            return MissingNumpyError.code
        return None

    @property
    def selected_model_hash(self) -> str | None:
        """Return the selected core model hash when a model exists."""

        if self.model_result is None:
            return None
        return self.model_result.selected_model.model_hash

    @property
    def model_selection_hash(self) -> str | None:
        """Return the core selection-evidence hash when a model exists."""

        if self.model_result is None:
            return None
        return self.model_result.selection_hash

    @property
    def model_use_label(self) -> str | None:
        """Return the core's actual use label, never a promoted claim."""

        if self.model_result is None:
            return None
        return self.model_result.selected_model.use_status.value

    @property
    def research_label(self) -> str:
        """Return the stable runtime research-only label."""

        return RESEARCH_ONLY_LABEL


def run_weather_demand_runtime(
    session: Session,
    request: WeatherDemandRuntimeRequest,
) -> WeatherDemandRuntimeResult:
    """Compose the actual read-only target/forecast/degree-day/fit path.

    The explicit request owns all policies, days, origins, bindings and limits.
    The caller must already have authorized the source, series and entities.  The
    function does not query anything outside the supplied session, write, flush,
    commit, fetch over the network, activate a source or promote a model.
    """

    if not isinstance(request, WeatherDemandRuntimeRequest):
        raise TypeError("request must be a WeatherDemandRuntimeRequest")
    request_hash = request.request_hash

    target_records = read_demand_target_revisions(
        session,
        provider_item_id=request.provider_item_id,
        source_format=request.source_format,
        gas_day_from=request.target_gas_day_from,
        gas_day_to=request.target_gas_day_to,
        available_at_utc=request.model_policy.validation_as_of,
        limit=request.target_read_limit,
    )
    target_inputs = build_demand_target_rows(
        target_records,
        provider_item_id=request.provider_item_id,
        source_format=request.source_format,
        gas_day_from=request.target_gas_day_from,
        gas_day_to=request.target_gas_day_to,
        available_at_utc=request.model_policy.validation_as_of,
        allow_provisional_targets=request.allow_provisional_targets,
    )
    if not target_inputs.rows:
        diagnostic = WeatherDemandRuntimeDiagnostic(
            code=WeatherDemandRuntimeDiagnosticCode.NO_ADMITTED_TARGET_REVISIONS,
            detail=(
                "no target revision passed the explicit source, window, provisional "
                "and receipt-availability contract"
            ),
        )
        return _result(
            request,
            request_hash=request_hash,
            target_inputs=target_inputs,
            feature_rows=(),
            degree_day_results=(),
            model_result=None,
            omitted_days=(),
            diagnostics=(diagnostic,),
            forecast_raw_count=0,
            selected_vintages=(),
            paired_eligible_training_day_count=0,
            status=WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY,
            forecast_observation_ids=(),
            feature_source_refs=(),
            degree_day_source_refs=(),
        )

    series_ids = tuple(sorted({binding.series_id for binding in request.point_bindings}))
    entity_ids = tuple(sorted({binding.entity_id for binding in request.point_bindings}))

    feature_rows: list[DailyWeatherFeature] = []
    degree_day_results: list[DegreeDayResult] = []
    omitted_days: list[OmittedWeatherDay] = []
    diagnostics: list[WeatherDemandRuntimeDiagnostic] = []
    forecast_observation_ids: set[str] = set()
    selected_vintages: dict[tuple[str, str, str, datetime], ForecastVintageRef] = {}
    degree_day_source_refs: set[str] = set()
    forecast_raw_count = 0

    for config in request.bridge_configs:
        gas_day = config.gas_days[0]
        hold = timedelta(minutes=config.max_hold_minutes)
        valid_from = config.window_start_utc - hold
        valid_to = config.window_end_utc + hold
        read_limit = min(request.forecast_read_limit, config.max_rows)
        records = read_ecmwf_forecasts(
            session,
            series_ids,
            entity_ids,
            config.prediction_origin,
            valid_from,
            valid_to,
            read_limit,
        )
        forecast_raw_count += len(records)
        day_ids = []
        for record in records:
            observation_id = getattr(record, "forecast_observation_id", None)
            if isinstance(observation_id, str) and observation_id:
                day_ids.append(observation_id)
                forecast_observation_ids.add(observation_id)
        projected = tuple(
            project_forecast_observation_record(record) for record in records
        )
        bundle = build_weather_demand_inputs(
            projected, request.point_bindings, config
        )
        if bundle.selected_vintage is not None:
            vintage = bundle.selected_vintage
            selected_vintages[
                (vintage.provider, vintage.model, vintage.run_id, vintage.issued_at)
            ] = vintage
        if not bundle.ready:
            detail = (
                "forecast bridge status "
                f"{bundle.status.value} produced no derived interval for the day"
            )
            omitted_days.append(
                OmittedWeatherDay(
                    gas_day=gas_day,
                    reason=WeatherDemandOmissionReason.FORECAST_BRIDGE_MISSING,
                    detail=detail,
                    bridge_diagnostics=bundle.diagnostics,
                    forecast_observation_ids=tuple(day_ids),
                    selected_vintage=bundle.selected_vintage,
                )
            )
            diagnostics.append(
                WeatherDemandRuntimeDiagnostic(
                    code=WeatherDemandRuntimeDiagnosticCode.FORECAST_DAY_OMITTED,
                    detail=detail,
                    gas_day=gas_day,
                )
            )
            continue

        degree_result = compute_degree_days_from_bundle(
            bundle, request.degree_day_policy
        )
        if degree_result is None:
            detail = "degree-day solver returned no result for a ready bridge"
            omitted_days.append(
                OmittedWeatherDay(
                    gas_day=gas_day,
                    reason=WeatherDemandOmissionReason.NO_FEATURE_ROW,
                    detail=detail,
                    bridge_diagnostics=bundle.diagnostics,
                    forecast_observation_ids=tuple(day_ids),
                    selected_vintage=bundle.selected_vintage,
                )
            )
            diagnostics.append(
                WeatherDemandRuntimeDiagnostic(
                    code=WeatherDemandRuntimeDiagnosticCode.FORECAST_DAY_OMITTED,
                    detail=detail,
                    gas_day=gas_day,
                )
            )
            continue

        degree_day_source_refs.update(degree_result.source_refs)
        day_features = degree_result.feature_rows()
        if not day_features:
            day_detail = degree_result.daily[0].missing_reason if degree_result.daily else None
            detail = (
                "degree-day coverage was incomplete; no zero-valued feature was invented"
                + (f" ({day_detail})" if day_detail else "")
            )
            omitted_days.append(
                OmittedWeatherDay(
                    gas_day=gas_day,
                    reason=WeatherDemandOmissionReason.DEGREE_DAY_INCOMPLETE,
                    detail=detail,
                    bridge_diagnostics=bundle.diagnostics,
                    forecast_observation_ids=tuple(day_ids),
                    selected_vintage=bundle.selected_vintage,
                )
            )
            diagnostics.append(
                WeatherDemandRuntimeDiagnostic(
                    code=WeatherDemandRuntimeDiagnosticCode.FORECAST_DAY_OMITTED,
                    detail=detail,
                    gas_day=gas_day,
                )
            )
            continue
        feature_rows.extend(day_features)
        degree_day_results.append(degree_result)

    ordered_features = tuple(sorted(feature_rows, key=lambda row: row.gas_day))
    ordered_degree_results = tuple(
        sorted(degree_day_results, key=lambda result: result.daily[0].gas_day)
    )
    ordered_omitted = tuple(sorted(omitted_days, key=lambda day: day.gas_day))
    ordered_vintages = tuple(
        sorted(
            selected_vintages.values(),
            key=lambda item: (item.issued_at, item.provider, item.model, item.run_id),
        )
    )
    paired_days = _paired_training_days(
        target_inputs.rows, ordered_features, request.model_policy
    )

    if not ordered_features:
        diagnostics.append(
            WeatherDemandRuntimeDiagnostic(
                code=WeatherDemandRuntimeDiagnosticCode.NO_ELIGIBLE_FEATURES,
                detail=(
                    "no requested day produced a complete point-in-time weather "
                    "feature row"
                ),
            )
        )
        return _result(
            request,
            request_hash=request_hash,
            target_inputs=target_inputs,
            feature_rows=(),
            degree_day_results=ordered_degree_results,
            model_result=None,
            omitted_days=ordered_omitted,
            diagnostics=tuple(diagnostics),
            forecast_raw_count=forecast_raw_count,
            selected_vintages=ordered_vintages,
            paired_eligible_training_day_count=paired_days,
            status=WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY,
            forecast_observation_ids=tuple(forecast_observation_ids),
            feature_source_refs=(),
            degree_day_source_refs=tuple(degree_day_source_refs),
        )

    minimum_training_rows = request.model_policy.min_training_rows
    if paired_days < minimum_training_rows:
        diagnostics.append(
            WeatherDemandRuntimeDiagnostic(
                code=WeatherDemandRuntimeDiagnosticCode.INSUFFICIENT_TRAINING_HISTORY,
                detail=(
                    f"paired_eligible_training_days={paired_days} "
                    f"required_min_training_rows={minimum_training_rows}; "
                    "the frozen fitter was not called and no model or calendar "
                    "baseline was produced"
                ),
            )
        )
        return _result(
            request,
            request_hash=request_hash,
            target_inputs=target_inputs,
            feature_rows=ordered_features,
            degree_day_results=ordered_degree_results,
            model_result=None,
            omitted_days=ordered_omitted,
            diagnostics=tuple(diagnostics),
            forecast_raw_count=forecast_raw_count,
            selected_vintages=ordered_vintages,
            paired_eligible_training_day_count=paired_days,
            status=WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY,
            forecast_observation_ids=tuple(forecast_observation_ids),
            feature_source_refs=_feature_source_refs(ordered_features),
            degree_day_source_refs=tuple(degree_day_source_refs),
        )

    try:
        model_result = fit_weather_demand_model(
            target_inputs.rows,
            ordered_features,
            request.model_policy,
        )
    except MissingNumpyError:
        diagnostics.append(
            WeatherDemandRuntimeDiagnostic(
                code=WeatherDemandRuntimeDiagnosticCode.NUMPY_NOT_INSTALLED,
                detail=(
                    "NumPy is not installed; no demand model was fitted and no "
                    "alternative solver or baseline was substituted"
                ),
            )
        )
        return _result(
            request,
            request_hash=request_hash,
            target_inputs=target_inputs,
            feature_rows=ordered_features,
            degree_day_results=ordered_degree_results,
            model_result=None,
            omitted_days=ordered_omitted,
            diagnostics=tuple(diagnostics),
            forecast_raw_count=forecast_raw_count,
            selected_vintages=ordered_vintages,
            paired_eligible_training_day_count=paired_days,
            status=WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED,
            forecast_observation_ids=tuple(forecast_observation_ids),
            feature_source_refs=_feature_source_refs(ordered_features),
            degree_day_source_refs=tuple(degree_day_source_refs),
        )
    except WeatherDemandInputError as exc:
        if str(exc) != _NO_TRAINING_ROWS:
            raise
        diagnostics.append(
            WeatherDemandRuntimeDiagnostic(
                code=WeatherDemandRuntimeDiagnosticCode.INSUFFICIENT_TRAINING_HISTORY,
                detail=(
                    "the frozen fitter found no target/weather training pair at "
                    "training_cutoff; no zero-valued feature or fake baseline was used"
                ),
            )
        )
        return _result(
            request,
            request_hash=request_hash,
            target_inputs=target_inputs,
            feature_rows=ordered_features,
            degree_day_results=ordered_degree_results,
            model_result=None,
            omitted_days=ordered_omitted,
            diagnostics=tuple(diagnostics),
            forecast_raw_count=forecast_raw_count,
            selected_vintages=ordered_vintages,
            paired_eligible_training_day_count=paired_days,
            status=WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY,
            forecast_observation_ids=tuple(forecast_observation_ids),
            feature_source_refs=_feature_source_refs(ordered_features),
            degree_day_source_refs=tuple(degree_day_source_refs),
        )

    return _result(
        request,
        request_hash=request_hash,
        target_inputs=target_inputs,
        feature_rows=ordered_features,
        degree_day_results=ordered_degree_results,
        model_result=model_result,
        omitted_days=ordered_omitted,
        diagnostics=tuple(diagnostics),
        forecast_raw_count=forecast_raw_count,
        selected_vintages=ordered_vintages,
        paired_eligible_training_day_count=paired_days,
        status=WeatherDemandRuntimeStatus.READY,
        forecast_observation_ids=tuple(forecast_observation_ids),
        feature_source_refs=_feature_source_refs(ordered_features),
        degree_day_source_refs=tuple(degree_day_source_refs),
    )


def _result(
    request: WeatherDemandRuntimeRequest,
    *,
    request_hash: str,
    target_inputs: DemandTargetInputs,
    feature_rows: tuple[DailyWeatherFeature, ...],
    degree_day_results: tuple[DegreeDayResult, ...],
    model_result: DemandModelResult | None,
    omitted_days: tuple[OmittedWeatherDay, ...],
    diagnostics: tuple[WeatherDemandRuntimeDiagnostic, ...],
    forecast_raw_count: int,
    selected_vintages: tuple[ForecastVintageRef, ...],
    paired_eligible_training_day_count: int,
    status: WeatherDemandRuntimeStatus,
    forecast_observation_ids: tuple[str, ...],
    feature_source_refs: tuple[str, ...],
    degree_day_source_refs: tuple[str, ...],
) -> WeatherDemandRuntimeResult:
    """Build the immutable result and its evidence from one composed path."""

    evidence = WeatherDemandRuntimeEvidence(
        request_hash=request_hash,
        target_revision_ids=tuple(row.revision_id for row in target_inputs.rows),
        target_source_refs=tuple(row.source_ref for row in target_inputs.rows),
        forecast_observation_ids=forecast_observation_ids,
        feature_source_refs=feature_source_refs,
        selected_vintage_ids=tuple(_vintage_id(vintage) for vintage in selected_vintages),
        feature_policy_hash=request.model_policy.expected_feature_policy.policy_hash,
        degree_day_method_version=request.degree_day_policy.method_version,
        validation_basis=request.model_policy.validation_basis,
        training_cutoff=request.model_policy.training_cutoff,
        validation_as_of=request.model_policy.validation_as_of,
        baseline_model_hash=(
            model_result.baseline_model.model_hash if model_result is not None else None
        ),
        candidate_model_hash=(
            model_result.candidate_model.model_hash
            if model_result is not None and model_result.candidate_model is not None
            else None
        ),
        selected_model_hash=(
            model_result.selected_model.model_hash if model_result is not None else None
        ),
        model_selection_hash=(
            model_result.selection_hash if model_result is not None else None
        ),
        regional_weighting_evidence_ref=request.regional_weighting_evidence_ref,
        degree_day_source_refs=degree_day_source_refs,
    )
    return WeatherDemandRuntimeResult(
        status=status,
        request_hash=request_hash,
        target_inputs=target_inputs,
        feature_rows=feature_rows,
        degree_day_results=degree_day_results,
        model_result=model_result,
        omitted_days=omitted_days,
        diagnostics=diagnostics,
        source_format=request.source_format,
        provider_item_id=request.provider_item_id,
        native_unit=target_inputs.native_unit,
        target_revision_count=len(target_inputs.rows),
        target_distinct_gas_days=len({row.gas_day for row in target_inputs.rows}),
        feature_day_count=len(feature_rows),
        forecast_raw_count=forecast_raw_count,
        selected_vintages=selected_vintages,
        paired_eligible_training_day_count=paired_eligible_training_day_count,
        evidence=evidence,
    )


def _paired_training_days(
    target_rows: Sequence[object],
    feature_rows: Sequence[DailyWeatherFeature],
    policy: DemandModelPolicy,
) -> int:
    """Count target/feature pairs visible at training_cutoff for diagnostics only.

    This does not decide training membership.  The frozen fitter independently
    resolves revisions and features for the training cutoff and every OOS fold.
    """

    cutoff = policy.training_cutoff
    targets_by_day = {}
    for row in target_rows:
        if row.available_at > cutoff:
            continue
        previous = targets_by_day.get(row.gas_day)
        if previous is None or row.revision > previous.revision:
            targets_by_day[row.gas_day] = row
    features_by_day = {}
    for feature in feature_rows:
        if feature.available_at > cutoff or feature.prediction_origin > cutoff:
            continue
        previous = features_by_day.get(feature.gas_day)
        if previous is None or (
            feature.available_at,
            feature.prediction_origin,
        ) > (previous.available_at, previous.prediction_origin):
            features_by_day[feature.gas_day] = feature
    paired: set[date] = set()
    for gas_day in set(targets_by_day) & set(features_by_day):
        day_end = gas_day_start_for_date(
            gas_day + timedelta(days=1), policy.gas_day_calendar
        )
        if day_end <= cutoff:
            paired.add(gas_day)
    return len(paired)


def _feature_source_refs(features: Sequence[DailyWeatherFeature]) -> tuple[str, ...]:
    """Return the sorted source lineage of actual feature rows."""

    return tuple(sorted({feature.source_ref for feature in features}))


def _model_policy_payload(policy: DemandModelPolicy) -> dict[str, object]:
    """Return the deterministic explicit model-policy identity."""

    return {
        "target_scope": policy.target_scope.value,
        "region": policy.region,
        "target_unit": policy.target_unit,
        "gas_day_calendar": policy.gas_day_calendar,
        "training_cutoff": policy.training_cutoff.isoformat(),
        "validation_as_of": policy.validation_as_of.isoformat(),
        "ridge_lambda": policy.ridge_lambda,
        "model_version": policy.model_version,
        "validation_basis": policy.validation_basis.value,
        "weather_features": [feature.value for feature in policy.weather_features],
        "expected_feature_policy_hash": policy.expected_feature_policy.policy_hash,
        "min_training_rows": policy.min_training_rows,
        "min_validation_folds": policy.min_validation_folds,
        "min_validation_predictions": policy.min_validation_predictions,
        "min_oos_coverage": policy.min_oos_coverage,
        "min_relative_mae_improvement": policy.min_relative_mae_improvement,
        "min_fold_win_fraction": policy.min_fold_win_fraction,
        "min_residuals_for_interval": policy.min_residuals_for_interval,
        "interval_level": policy.interval_level,
        "max_training_rows": policy.max_training_rows,
        "max_features": policy.max_features,
        "max_folds": policy.max_folds,
    }


def _vintage_id(vintage: ForecastVintageRef) -> str:
    """Return a stable compact forecast-vintage reference."""

    return (
        f"{vintage.provider}/{vintage.model}/{vintage.run_id}"
        f"@{vintage.issued_at.isoformat()}"
    )


def _utc(value: object, name: str) -> datetime:
    """Require an aware datetime and normalize it to UTC."""

    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise WeatherDemandRuntimeValidationError(f"{name} must be an aware datetime")
    return value.astimezone(UTC)


def _canonical_hash(payload: dict[str, object]) -> str:
    """Hash canonical JSON with deterministic ordering and no non-finite values."""

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# Readability aliases for callers that describe the operation as composition or
# model fitting.  All aliases are the same read-only runtime implementation.
compose_weather_demand_runtime = run_weather_demand_runtime
compose_weather_demand_model = run_weather_demand_runtime
build_weather_demand_runtime = run_weather_demand_runtime
run_weather_demand_model = run_weather_demand_runtime
