"""Focused contracts for the frozen-model weather-demand prediction runtime.

Every weather value here is an explicitly synthetic mechanics fixture.  The
successful prediction path uses the actual frozen fitter once (to obtain an
explicit ``DemandModelResult``) and the actual domain predictor thereafter; the
persisted-row read itself is exercised in the PostgreSQL module.  These tests do
not claim provider history, prospective accuracy, GB representativeness or model
promotion.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from eurogas_nexus.application.research import weather_demand_prediction_runtime as runtime
from eurogas_nexus.application.research.weather_demand_inputs import (
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
)
from eurogas_nexus.db.repositories.ecmwf_forecast_reads import (
    MAX_LIMIT,
    EcmwfForecastReadOverflowError,
)
from eurogas_nexus.domain.ontology.vocabulary import TargetScope
from eurogas_nexus.domain.research.weather_demand import (
    DemandModelResult,
    ModelKind,
    ModelSelectionStatus,
    ModelUseStatus,
    PromotionStatus,
    ValidationBasis,
    fit_weather_demand_model,
)
from tests.unit.test_weather_demand import _fit_fixture, _fit_policy
from tests.unit.test_weather_demand_runtime import (
    _assert_no_writes,
    _binding,
    _configs,
    _day_end,
    _day_start,
    _degree_policy,
    _FakeSession,
    _feature_policy,
    _forecast_rows,
)

GAS_DAY = date(2025, 3, 15)
WEIGHT_EVIDENCE = "evidence://regional-weighting/synthetic-prediction-runtime"


def _gb_nts_policy():
    return _feature_policy()


def _model_policy(policy: Any):
    return replace(
        _fit_policy(),
        target_scope=TargetScope.GB_NTS_THROUGHPUT,
        region="GB_NTS",
        expected_feature_policy=policy,
        validation_basis=ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS,
    )


def _fit_weather_result() -> DemandModelResult:
    policy = _gb_nts_policy()
    targets, features = _fit_fixture()
    targets = tuple(
        replace(target, scope=TargetScope.GB_NTS_THROUGHPUT, region="GB_NTS")
        for target in targets
    )
    features = tuple(replace(feature, feature_policy=policy) for feature in features)
    result = fit_weather_demand_model(targets, features, _model_policy(policy))
    assert result.selected_model.kind is ModelKind.WEATHER_CALENDAR_RIDGE
    return result


def _fit_baseline_result() -> DemandModelResult:
    policy = _gb_nts_policy()
    targets, features = _fit_fixture()
    targets = tuple(
        replace(
            target,
            scope=TargetScope.GB_NTS_THROUGHPUT,
            region="GB_NTS",
            value=100.0,
        )
        for target in targets
    )
    features = tuple(
        replace(
            feature,
            feature_policy=policy,
            daily_mean_hdd=5.0,
            daily_mean_cdd=0.0,
            heating_degree_day_integral=5.0,
            cooling_degree_day_integral=0.0,
        )
        for feature in features
    )
    result = fit_weather_demand_model(targets, features, _model_policy(policy))
    assert result.selection_status is ModelSelectionStatus.BASELINE_RETAINED
    assert result.selected_model.kind is ModelKind.CALENDAR_BASELINE
    return result


@pytest.fixture(scope="module")
def weather_result() -> DemandModelResult:
    pytest.importorskip("numpy")
    return _fit_weather_result()


@pytest.fixture(scope="module")
def baseline_result() -> DemandModelResult:
    pytest.importorskip("numpy")
    return _fit_baseline_result()


def _request(
    result: DemandModelResult,
    *,
    day: date = GAS_DAY,
    origin: datetime | None = None,
    config: WeatherDemandBridgeConfig | None = None,
    bindings: tuple[ForecastPointBinding, ...] | None = None,
    read_limit: int = MAX_LIMIT,
    basis: object = runtime.ForecastEvidenceBasis.GENUINE_RECEIPT_AVAILABILITY,
) -> runtime.WeatherDemandPredictionRequest:
    policy = _gb_nts_policy()
    resolved_origin = origin or (_day_start(day) - timedelta(days=1))
    resolved_config = config or replace(
        _configs(policy, (day,))[0],
        prediction_origin=resolved_origin,
    )
    return runtime.WeatherDemandPredictionRequest(
        model_result=result,
        gas_day=day,
        prediction_origin=resolved_origin,
        degree_day_policy=_degree_policy(policy),
        bridge_config=resolved_config,
        point_bindings=bindings or (_binding(),),
        regional_weighting_evidence_ref=WEIGHT_EVIDENCE,
        forecast_read_limit=read_limit,
        forecast_evidence_basis=basis,
    )


def _rows(
    day: date,
    origin: datetime,
    *,
    run_id: str = "run-eligible",
    issued: datetime | None = None,
    available: datetime | None = None,
):
    return _forecast_rows(
        day,
        run_id=run_id,
        issued=issued or (origin - timedelta(hours=12)),
        available=available or (origin - timedelta(hours=1)),
    )


def _identity_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime,
        "project_forecast_observation_record",
        lambda record: record,
    )


def test_weather_prediction_uses_actual_bridge_solver_and_core_predictor(
    monkeypatch: pytest.MonkeyPatch,
    weather_result: DemandModelResult,
) -> None:
    origin = _day_start(GAS_DAY) - timedelta(days=1)
    rows = _rows(GAS_DAY, origin)
    session = _FakeSession([rows])
    _identity_projection(monkeypatch)
    request = _request(weather_result, origin=origin)

    outcome = runtime.run_weather_demand_prediction_runtime(session, request)

    assert outcome.status is runtime.WeatherDemandPredictionStatus.READY
    assert outcome.has_prediction
    assert outcome.weather_consumed
    assert outcome.baseline_reference is False
    assert outcome.evidence.consumption_basis is (
        runtime.PredictionConsumptionBasis.WEATHER_FORECAST_VINTAGE
    )
    assert outcome.evidence.forecast_evidence_basis is (
        runtime.ForecastEvidenceBasis.GENUINE_RECEIPT_AVAILABILITY
    )
    prediction = outcome.prediction
    assert prediction is not None
    assert prediction.model_kind is ModelKind.WEATHER_CALENDAR_RIDGE
    assert prediction.use_status is ModelUseStatus.UNVALIDATED_OOS_RESEARCH_OUTPUT
    assert prediction.value >= 0.0
    assert outcome.native_unit == "MSCM"
    assert prediction.model_hash == weather_result.selected_model.model_hash
    assert prediction.selection_hash == weather_result.selection_hash
    assert prediction.feature_policy_hash == (
        weather_result.selected_model.feature_policy_hash
    )
    assert prediction.forecast_vintage is not None
    assert prediction.forecast_vintage.run_id == "run-eligible"
    assert outcome.evidence.selected_vintage_id is not None
    assert outcome.evidence.selected_vintage == prediction.forecast_vintage
    assert outcome.forecast_observation_ids == tuple(
        sorted(row.forecast_observation_id for row in rows)
    )
    assert outcome.evidence.model_source_refs == (
        weather_result.selected_model.source_refs
    )
    assert outcome.evidence.model_target_revision_ids == (
        weather_result.selected_model.target_revision_ids
    )
    assert len(outcome.evidence.feature_policy_hash) == 64
    assert outcome.evidence.regional_weighting_evidence_ref == WEIGHT_EVIDENCE
    assert outcome.evidence.regional_weighting_evidence_basis == (
        "CALLER_DECLARED_PROVENANCE_NOT_REVIEWED"
    )
    assert outcome.request_hash == request.request_hash
    assert outcome.research_only
    assert outcome.production_promotion is PromotionStatus.NOT_PROMOTED
    assert not outcome.prospective_accuracy_claim
    assert not outcome.gb_representative_claim
    assert outcome.feature_row is not None
    assert outcome.degree_day_result is not None
    _assert_no_writes(session)
    assert session.no_autoflush_entries == 1
    assert session.autoflush_depth == 0


def test_request_hash_is_deterministic_and_binds_explicit_bounds(
    weather_result: DemandModelResult,
) -> None:
    first = _request(weather_result)
    second = _request(weather_result)
    changed_limit = _request(weather_result, read_limit=128)
    changed_weight = replace(
        first,
        regional_weighting_evidence_ref="evidence://regional-weighting/changed",
    )
    changed_model = replace(
        weather_result,
        selected_model=replace(
            weather_result.selected_model,
            model_hash="a" * 64,
        ),
    )
    changed_model_request = _request(changed_model)

    assert first.request_hash == second.request_hash
    assert first.request_hash != changed_limit.request_hash
    assert first.request_hash != changed_weight.request_hash
    assert first.request_hash != changed_model_request.request_hash


def test_baseline_selected_returns_reference_without_reading_weather(
    monkeypatch: pytest.MonkeyPatch,
    baseline_result: DemandModelResult,
) -> None:
    def _tripwire(*args: object, **kwargs: object) -> None:
        pytest.fail("a selected calendar baseline must not read forecast rows")

    monkeypatch.setattr(runtime, "read_ecmwf_forecasts", _tripwire)
    session = _FakeSession([])

    outcome = runtime.run_weather_demand_prediction_runtime(
        session, _request(baseline_result)
    )

    assert outcome.status is runtime.WeatherDemandPredictionStatus.READY
    assert outcome.baseline_reference
    assert not outcome.weather_consumed
    assert outcome.evidence.consumption_basis is (
        runtime.PredictionConsumptionBasis.CALENDAR_BASELINE_REFERENCE
    )
    assert outcome.feature_row is None
    assert outcome.degree_day_result is None
    assert outcome.forecast_raw_count == 0
    assert outcome.forecast_observation_ids == ()
    assert outcome.selected_vintage is None
    assert outcome.evidence.selected_vintage_id is None
    assert outcome.evidence.feature_source_refs == ()
    assert outcome.evidence.degree_day_source_refs == ()
    prediction = outcome.prediction
    assert prediction is not None
    assert prediction.model_kind is ModelKind.CALENDAR_BASELINE
    assert prediction.prediction_label == "CALENDAR_BASELINE_REFERENCE"
    assert prediction.use_status is ModelUseStatus.CALENDAR_BASELINE_REFERENCE
    assert prediction.weather_source_ref is None
    assert prediction.forecast_vintage is None
    assert prediction.feature_refs == ()
    assert outcome.native_unit == "MSCM"
    _assert_no_writes(session)


def test_missing_bridge_and_incomplete_degree_day_are_typed_insufficient(
    monkeypatch: pytest.MonkeyPatch,
    weather_result: DemandModelResult,
) -> None:
    origin = _day_start(GAS_DAY) - timedelta(days=1)
    rows = _rows(GAS_DAY, origin)
    _identity_projection(monkeypatch)

    def _no_prediction(*args: object, **kwargs: object) -> None:
        pytest.fail("missing coverage must not fall back to a prediction or baseline")

    monkeypatch.setattr(runtime, "predict_selected_demand", _no_prediction)

    missing_session = _FakeSession([[rows[0]]])
    missing = runtime.run_weather_demand_prediction_runtime(
        missing_session, _request(weather_result, origin=origin)
    )
    assert missing.status is (
        runtime.WeatherDemandPredictionStatus.INSUFFICIENT_FORECAST_COVERAGE
    )
    assert missing.prediction is None
    assert not missing.weather_consumed
    assert missing.evidence.consumption_basis is runtime.PredictionConsumptionBasis.NONE
    assert missing.evidence.forecast_observation_ids == (rows[0].forecast_observation_id,)
    assert missing.feature_row is None
    assert missing.diagnostics[0].code is (
        runtime.WeatherDemandPredictionDiagnosticCode.FORECAST_BRIDGE_MISSING
    )
    _assert_no_writes(missing_session)

    incomplete_session = _FakeSession([[rows[0], rows[1]]])
    incomplete = runtime.run_weather_demand_prediction_runtime(
        incomplete_session, _request(weather_result, origin=origin)
    )
    assert incomplete.status is (
        runtime.WeatherDemandPredictionStatus.INSUFFICIENT_FORECAST_COVERAGE
    )
    assert incomplete.prediction is None
    assert incomplete.feature_row is None
    assert incomplete.degree_day_result is not None
    assert incomplete.diagnostics[0].code is (
        runtime.WeatherDemandPredictionDiagnosticCode.DEGREE_DAY_INCOMPLETE
    )
    assert incomplete.forecast_raw_count == 2
    _assert_no_writes(incomplete_session)


def test_late_issue_and_receipt_do_not_enter_selected_vintage_and_read_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
    weather_result: DemandModelResult,
) -> None:
    origin = _day_start(GAS_DAY) - timedelta(days=1)
    eligible = _rows(GAS_DAY, origin, run_id="run-eligible")
    late = _rows(
        GAS_DAY,
        origin,
        run_id="run-late",
        issued=origin + timedelta(hours=1),
        available=origin + timedelta(hours=2),
    )
    session = _FakeSession([eligible + late])
    _identity_projection(monkeypatch)
    actual_read = runtime.read_ecmwf_forecasts
    calls: list[tuple[object, ...]] = []

    def _recording_read(*args: object) -> list[object]:
        calls.append(args)
        return actual_read(*args)

    monkeypatch.setattr(runtime, "read_ecmwf_forecasts", _recording_read)

    outcome = runtime.run_weather_demand_prediction_runtime(
        session, _request(weather_result, origin=origin)
    )

    assert len(calls) == 1
    _, series_ids, entity_ids, selected_origin, valid_from, valid_to, limit = calls[0]
    assert series_ids == ("S1",)
    assert entity_ids == ("E1",)
    assert selected_origin == origin
    assert valid_from == _day_start(GAS_DAY) - timedelta(minutes=240)
    assert valid_to == (
        _day_end(GAS_DAY) + timedelta(minutes=240, microseconds=1)
    )
    assert limit == MAX_LIMIT
    assert outcome.status is runtime.WeatherDemandPredictionStatus.READY
    assert outcome.prediction is not None
    assert outcome.prediction.forecast_vintage is not None
    assert outcome.prediction.forecast_vintage.run_id == "run-eligible"
    assert outcome.selected_vintage is not None
    assert outcome.selected_vintage.run_id == "run-eligible"
    assert outcome.forecast_raw_count == len(eligible) + len(late)
    assert {row.forecast_observation_id for row in late} <= set(
        outcome.forecast_observation_ids
    )
    _assert_no_writes(session)


def test_forecast_read_overflow_and_db_error_are_typed_without_raw_text(
    monkeypatch: pytest.MonkeyPatch,
    weather_result: DemandModelResult,
) -> None:
    secret = "postgresql://user:secret@example.invalid/runtime"

    def _overflow(*args: object, **kwargs: object) -> None:
        raise EcmwfForecastReadOverflowError(secret)

    monkeypatch.setattr(runtime, "read_ecmwf_forecasts", _overflow)
    with pytest.raises(runtime.WeatherDemandPredictionReadOverflowError) as overflow:
        runtime.run_weather_demand_prediction_runtime(
            object(), _request(weather_result)
        )
    assert overflow.value.code == "WEATHER_DEMAND_PREDICTION_FORECAST_READ_OVERFLOW"
    assert secret not in str(overflow.value)
    assert overflow.value.__cause__ is None

    def _database_error(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError(secret)

    monkeypatch.setattr(runtime, "read_ecmwf_forecasts", _database_error)
    with pytest.raises(runtime.WeatherDemandPredictionReadError) as read_error:
        runtime.run_weather_demand_prediction_runtime(object(), _request(weather_result))
    assert read_error.value.code == "WEATHER_DEMAND_PREDICTION_FORECAST_READ_ERROR"
    assert secret not in str(read_error.value)
    assert read_error.value.__cause__ is None


def test_request_rejects_model_target_policy_binding_and_time_mismatches(
    weather_result: DemandModelResult,
) -> None:
    valid = _request(weather_result)
    policy = _gb_nts_policy()
    selection_as_of = weather_result.selection_as_of
    assert selection_as_of is not None

    with pytest.raises(runtime.WeatherDemandPredictionValidationError, match="region"):
        _request(
            replace(
                weather_result,
                selected_model=replace(weather_result.selected_model, region="DE"),
            )
        )
    with pytest.raises(runtime.WeatherDemandPredictionValidationError, match="native unit"):
        _request(
            replace(
                weather_result,
                selected_model=replace(
                    weather_result.selected_model, target_unit="MWH"
                ),
            )
        )
    with pytest.raises(runtime.WeatherDemandPredictionValidationError, match="calendar"):
        _request(
            replace(
                weather_result,
                selected_model=replace(
                    weather_result.selected_model,
                    gas_day_calendar="UNKNOWN_GAS_DAY_CALENDAR",
                ),
            )
        )
    with pytest.raises(
        runtime.WeatherDemandPredictionValidationError, match="feature-policy"
    ):
        _request(
            replace(
                weather_result,
                selected_model=replace(
                    weather_result.selected_model,
                    feature_policy_hash="f" * 64,
                ),
            )
        )
    with pytest.raises(
        runtime.WeatherDemandPredictionValidationError, match="forecast_read_limit"
    ):
        _request(weather_result, read_limit=MAX_LIMIT + 1)
    with pytest.raises(
        runtime.WeatherDemandPredictionValidationError, match="requested gas day"
    ):
        _request(
            weather_result,
            config=replace(
                _configs(policy, (GAS_DAY + timedelta(days=1),))[0],
                prediction_origin=valid.prediction_origin,
            ),
        )
    with pytest.raises(
        runtime.WeatherDemandPredictionValidationError, match="point binding region"
    ):
        _request(weather_result, bindings=(_binding(region="DE"),))
    with pytest.raises(
        runtime.WeatherDemandPredictionValidationError, match="precedes"
    ):
        _request(
            weather_result,
            origin=selection_as_of - timedelta(seconds=1),
        )
    with pytest.raises(runtime.WeatherDemandPredictionArchiveBasisError) as archive:
        _request(weather_result, basis="S4_ARCHIVE_REANALYSIS")
    assert archive.value.code == "ARCHIVE_FORECAST_BASIS_UNSUPPORTED"
    assert valid.request_hash == _request(weather_result).request_hash


def test_core_tamper_and_future_target_bound_are_typed_core_refusals(
    monkeypatch: pytest.MonkeyPatch,
    weather_result: DemandModelResult,
) -> None:
    origin = _day_start(GAS_DAY) - timedelta(days=1)
    rows = _rows(GAS_DAY, origin)
    _identity_projection(monkeypatch)
    evidence = weather_result.selection_evidence
    assert evidence is not None

    tampered = replace(
        weather_result,
        selection_evidence=replace(evidence, baseline_model_hash="0" * 64),
    )
    with pytest.raises(runtime.WeatherDemandPredictionCoreError, match="baseline-model"):
        runtime.run_weather_demand_prediction_runtime(
            _FakeSession([rows]), _request(tampered, origin=origin)
        )

    complete_origin = _day_end(GAS_DAY) + timedelta(hours=1)
    complete_rows = _rows(
        GAS_DAY,
        complete_origin,
        issued=_day_start(GAS_DAY) - timedelta(hours=12),
        available=complete_origin - timedelta(hours=1),
    )
    with pytest.raises(runtime.WeatherDemandPredictionCoreError, match="already complete"):
        runtime.run_weather_demand_prediction_runtime(
            _FakeSession([complete_rows]),
            _request(weather_result, origin=complete_origin),
        )


def test_prediction_runtime_does_not_require_numpy_or_a_solver(
    monkeypatch: pytest.MonkeyPatch,
    weather_result: DemandModelResult,
) -> None:
    origin = _day_start(GAS_DAY) - timedelta(days=1)
    rows = _rows(GAS_DAY, origin)
    session = _FakeSession([rows])
    _identity_projection(monkeypatch)
    monkeypatch.setitem(sys.modules, "numpy", None)

    outcome = runtime.run_weather_demand_prediction_runtime(
        session, _request(weather_result, origin=origin)
    )

    assert outcome.status is runtime.WeatherDemandPredictionStatus.READY
    assert outcome.prediction is not None
    assert not hasattr(runtime, "fit_weather_demand_model")
    _assert_no_writes(session)
