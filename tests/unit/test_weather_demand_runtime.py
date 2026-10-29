"""Synthetic mechanics for the read-only weather-demand runtime composition.

Every row in this file is an explicitly synthetic fixture used only to exercise
selection, omission, no-leakage and no-write contracts.  The successful test runs
the actual frozen bridge and fitter when the separately reviewed NumPy dependency
is present, but its data is not provider evidence and no accuracy claim is made.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from eurogas_nexus.application.research import weather_demand_runtime as runtime
from eurogas_nexus.application.research.demand_target_inputs import (
    DemandTargetAmbiguityError,
    RevisionOrderPolicy,
)
from eurogas_nexus.application.research.weather_demand_inputs import (
    ForecastInstantRow,
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
    WeatherDemandDiagnosticCode,
    WeatherDemandInputStatus,
    build_weather_demand_inputs,
)
from eurogas_nexus.application.research.weather_demand_runtime import (
    WeatherDemandOmissionReason,
    WeatherDemandRuntimeDiagnosticCode,
    WeatherDemandRuntimeRequest,
    WeatherDemandRuntimeStatus,
    WeatherDemandRuntimeSyntheticBasisError,
    WeatherDemandRuntimeValidationError,
    run_weather_demand_runtime,
)
from eurogas_nexus.db.repositories.demand_rest import _to_record
from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_start_for_date,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    TargetScope,
    TemperatureDerivationMethod,
    WeatherFeature,
)
from eurogas_nexus.domain.research.weather_demand import (
    DegreeDayFeaturePolicy,
    DegreeDayPolicy,
    DemandModelPolicy,
    MissingNumpyError,
    ModelUseStatus,
    PromotionStatus,
    RegionLocationWeight,
    ValidationBasis,
)
from eurogas_nexus.ingestion.national_gas_rest import (
    D1_PUBLICATION_ID,
    parse_national_gas_rest,
)

PROVIDER_ITEM = "PUBOB637"
CALENDAR = DEFAULT_GAS_DAY_CALENDAR
START = date(2026, 1, 1)
WEIGHT_EVIDENCE = "evidence://regional-weighting/synthetic-mechanics"


def _numpy_available() -> bool:
    return importlib.util.find_spec("numpy") is not None


def _day_start(day: date) -> datetime:
    return gas_day_start_for_date(day, CALENDAR)


def _day_end(day: date) -> datetime:
    return gas_day_start_for_date(day + timedelta(days=1), CALENDAR)


def _feature_policy(
    *,
    region: str = "GB_NTS",
    max_gap_minutes: int = 240,
) -> DegreeDayFeaturePolicy:
    return DegreeDayFeaturePolicy(
        region=region,
        heating_base_c=15.5,
        cooling_base_c=22.0,
        max_gap_minutes=max_gap_minutes,
        min_covered_fraction=1.0,
        location_weights=(RegionLocationWeight("L1", Decimal("1")),),
        gas_day_calendar=CALENDAR,
        temporal_method=TemperatureDerivationMethod.EXPLICIT_DERIVED_HOLD,
    )


def _degree_policy(policy: DegreeDayFeaturePolicy) -> DegreeDayPolicy:
    return DegreeDayPolicy(
        heating_base_c=policy.heating_base_c,
        cooling_base_c=policy.cooling_base_c,
        max_gap_minutes=policy.max_gap_minutes,
        min_covered_fraction=policy.min_covered_fraction,
    )


def _model_policy(
    policy: DegreeDayFeaturePolicy,
    *,
    cutoff: datetime,
    validation: datetime,
    basis: ValidationBasis = ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS,
    target_unit: str = "MSCM",
) -> DemandModelPolicy:
    return DemandModelPolicy(
        target_scope=TargetScope.GB_NTS_THROUGHPUT,
        region=policy.region,
        target_unit=target_unit,
        gas_day_calendar=CALENDAR,
        training_cutoff=cutoff,
        validation_as_of=validation,
        ridge_lambda=1e-8,
        model_version="synthetic-weather-demand-runtime/v1",
        validation_basis=basis,
        weather_features=(WeatherFeature.HDD_MEAN,),
        expected_feature_policy=policy,
        min_training_rows=8,
        min_validation_folds=3,
        min_validation_predictions=3,
        min_oos_coverage=0.5,
        min_relative_mae_improvement=0.0,
        min_fold_win_fraction=0.5,
        min_residuals_for_interval=0,
        interval_level=0.8,
        max_training_rows=100,
        max_features=16,
        max_folds=10,
    )


def _binding(*, region: str = "GB_NTS") -> ForecastPointBinding:
    return ForecastPointBinding(
        point_id="P1",
        series_id="S1",
        entity_id="E1",
        location_id="L1",
        region=region,
    )


def _configs(
    policy: DegreeDayFeaturePolicy,
    days: tuple[date, ...],
    *,
    max_hold_minutes: int = 240,
) -> tuple[WeatherDemandBridgeConfig, ...]:
    return tuple(
        WeatherDemandBridgeConfig(
            feature_policy=policy,
            prediction_origin=_day_start(day) - timedelta(hours=1),
            gas_days=(day,),
            max_hold_minutes=max_hold_minutes,
            max_rows=20_000,
            max_points=16,
        )
        for day in days
    )


def _request(
    policy: DegreeDayFeaturePolicy,
    days: tuple[date, ...],
    *,
    cutoff: datetime,
    validation: datetime,
    basis: ValidationBasis = ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS,
    source_format: str = "CSV",
    target_unit: str = "MSCM",
    configs: tuple[WeatherDemandBridgeConfig, ...] | None = None,
    degree_policy: DegreeDayPolicy | None = None,
    point_bindings: tuple[ForecastPointBinding, ...] | None = None,
    revision_order_policy: RevisionOrderPolicy | str | None = None,
) -> WeatherDemandRuntimeRequest:
    policy_args: dict[str, object] = {}
    if revision_order_policy is not None:
        policy_args["target_revision_order_policy"] = revision_order_policy
    return WeatherDemandRuntimeRequest(
        model_policy=_model_policy(
            policy,
            cutoff=cutoff,
            validation=validation,
            basis=basis,
            target_unit=target_unit,
        ),
        degree_day_policy=degree_policy or _degree_policy(policy),
        bridge_configs=configs or _configs(policy, days),
        point_bindings=point_bindings or (_binding(),),
        provider_item_id=PROVIDER_ITEM,
        source_format=source_format,
        target_gas_day_from=days[0],
        target_gas_day_to=days[-1],
        allow_provisional_targets=True,
        regional_weighting_evidence_ref=WEIGHT_EVIDENCE,
        **policy_args,
    )


def _temperature(day: date, offset_hours: int) -> float:
    return (
        10.0
        + 5.0 * math.sin(2.0 * math.pi * day.toordinal() / 11.0)
        + 2.0 * math.sin(2.0 * math.pi * offset_hours / 24.0)
    )


def _target_value(day: date) -> float:
    offsets = tuple(range(0, 25, 3))
    mean = math.fsum(_temperature(day, offset) for offset in offsets) / len(offsets)
    return 100.0 + 40.0 * max(0.0, 15.5 - mean)


def _target_record(
    day: date,
    value: float,
    *,
    record_id: str,
    available: datetime | None = None,
) -> SimpleNamespace:
    end = _day_end(day)
    resolved_available = available or (end + timedelta(hours=6))
    return SimpleNamespace(
        record_id=record_id,
        source_publication_id=f"pub-{record_id}",
        provider_item_id=PROVIDER_ITEM,
        series_key="national-gas:actual:GB_NTS:D+1:CSV",
        region="GB_NTS",
        term="D+1",
        label="Synthetic demand actual",
        gas_day=day,
        period_start_utc=_day_start(day),
        period_end_utc=end,
        value_text=f"{value:.3f}",
        unit="mscm",
        received_at_utc=resolved_available - timedelta(minutes=1),
        available_at_utc=resolved_available,
        ingested_at_utc=resolved_available,
        published_at_utc=None,
        applicable_at_raw=day.isoformat(),
        generated_at_raw=resolved_available.isoformat(),
        applicable_at_naive=_day_start(day).replace(tzinfo=None),
        generated_at_naive=resolved_available.replace(tzinfo=None),
        quality_indicator=None,
        provisional_status="PROVISIONAL_INITIAL",
        is_provisional=True,
        raw_sha256=hashlib.sha256(record_id.encode("utf-8")).hexdigest(),
        source_url="https://example.test/synthetic-demand",
        hash_schema="synthetic-runtime.v1",
        value_is_blank=False,
        source_format="CSV",
        rest_provenance=None,
    )


def _target_records(days: tuple[date, ...]) -> list[SimpleNamespace]:
    return [
        _target_record(day, _target_value(day), record_id=f"rec-{day.isoformat()}")
        for day in days
    ]


REST_RECEIVED = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def _rest_row(*, gas_day: date, applicable_at: str, value: str) -> dict[str, object]:
    """Build one synthetic source row whose provenance comes from the actual parser."""

    return {
        "applicableAt": applicable_at,
        "applicableFor": gas_day.isoformat(),
        "value": value,
        "generatedTimeStamp": applicable_at,
        "qualityIndicator": "",
        "substituted": "N",
        "createdDate": applicable_at,
    }


def _rest_records(
    source_rows: list[dict[str, object]],
    *,
    date_from: date,
    date_to: date,
) -> list[object]:
    """Parse synthetic REST text and persist it through the actual record mapper."""

    payload = json.dumps(
        [
            {
                "publicationId": D1_PUBLICATION_ID,
                "publicationName": "Demand Actual, NTS, D+1",
                "publications": source_rows,
            }
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    publications = parse_national_gas_rest(
        payload,
        date_from=date_from,
        date_to=date_to,
        received_at_utc=REST_RECEIVED,
        publication_ids=[D1_PUBLICATION_ID],
    )
    return [_to_record(publication) for publication in publications]


def _forecast_rows(
    day: date,
    *,
    run_id: str = "run-eligible",
    issued: datetime | None = None,
    available: datetime | None = None,
) -> list[ForecastInstantRow]:
    start = _day_start(day)
    resolved_issued = issued or (start - timedelta(hours=12))
    resolved_available = available or (start - timedelta(hours=1))
    rows: list[ForecastInstantRow] = []
    for offset in range(0, 25, 3):
        valid = start + timedelta(hours=offset)
        temperature = _temperature(day, offset)
        observation_id = f"{run_id}-{day.isoformat()}-{offset:02d}"
        rows.append(
            ForecastInstantRow(
                forecast_observation_id=observation_id,
                point_id="P1",
                series_id="S1",
                entity_id="E1",
                issued_at_utc=resolved_issued,
                valid_at_utc=valid,
                available_at_utc=resolved_available,
                temperature_c=temperature,
                run_id=run_id,
                model="ifs",
                source_field_hash=hashlib.sha256(
                    f"field-{observation_id}".encode()
                ).hexdigest(),
                raw_grib_sha256=hashlib.sha256(
                    f"grib-{observation_id}".encode()
                ).hexdigest(),
                record_content_sha256=hashlib.sha256(
                    f"content-{observation_id}".encode()
                ).hexdigest(),
            )
        )
    return rows


class _Rows(list):
    """Minimal SQLAlchemy scalar-result double supporting ``.all()`` and iteration."""

    def all(self) -> list[object]:
        return list(self)


class _NoAutoflush:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __enter__(self) -> _NoAutoflush:
        self._session.no_autoflush_entries += 1
        self._session.autoflush_depth += 1
        return self

    def __exit__(self, *args: object) -> None:
        self._session.autoflush_depth -= 1


class _FakeSession:
    """Read-only session double; any write or unexpected query fails the test."""

    def __init__(self, responses: list[list[object]]) -> None:
        self.responses = [_Rows(response) for response in responses]
        self.no_autoflush = _NoAutoflush(self)
        self.no_autoflush_entries = 0
        self.autoflush_depth = 0
        self.flush_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.pending_writes = ["caller-pending-write"]

    def scalars(self, statement: object) -> _Rows:
        if not self.responses:
            raise AssertionError("unexpected repository read")
        return self.responses.pop(0)

    def flush(self) -> None:
        self.flush_calls += 1
        raise AssertionError("runtime must not flush caller work")

    def commit(self) -> None:
        self.commit_calls += 1
        raise AssertionError("runtime must not commit caller work")

    def rollback(self) -> None:
        self.rollback_calls += 1
        raise AssertionError("runtime must not roll back caller work")


def _assert_no_writes(session: _FakeSession) -> None:
    assert session.flush_calls == 0
    assert session.commit_calls == 0
    assert session.rollback_calls == 0
    assert session.pending_writes == ["caller-pending-write"]


def _raise_missing_numpy(*args: object, **kwargs: object) -> None:
    raise MissingNumpyError()


def test_successful_runtime_uses_actual_core_and_keeps_all_target_revisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not _numpy_available():
        pytest.skip(
            "optional NumPy is absent; the actual frozen fitter is covered by the "
            "isolated numerical environment, not by a fake baseline"
        )
    days = tuple(START + timedelta(days=index) for index in range(21))
    policy = _feature_policy()
    cutoff = _day_start(days[14])
    validation = _day_start(days[-1] + timedelta(days=2))
    extra_day = days[9]
    extra_available = _day_start(days[14] + timedelta(days=1)) + timedelta(hours=1)
    targets = _target_records(days)
    targets.append(
        _target_record(
            extra_day,
            140.0,
            record_id="rec-extra-revision",
            available=extra_available,
        )
    )
    responses = [targets] + [
        _forecast_rows(day, run_id=f"run-{day.isoformat()}") for day in days
    ]
    session = _FakeSession(responses)
    monkeypatch.setattr(
        runtime,
        "project_forecast_observation_record",
        lambda record: record,
    )

    result = run_weather_demand_runtime(
        session,
        _request(policy, days, cutoff=cutoff, validation=validation),
    )

    assert result.status is WeatherDemandRuntimeStatus.READY
    assert result.model_result is not None
    assert result.model_result.production_promotion is PromotionStatus.NOT_PROMOTED
    assert result.model_result.selected_model.use_status is (
        ModelUseStatus.UNVALIDATED_OOS_RESEARCH_OUTPUT
    )
    assert result.model_use_label == "UNVALIDATED_OOS_RESEARCH_OUTPUT"
    assert result.model_selection_hash == result.model_result.selection_hash
    assert result.selected_model_hash == result.model_result.selected_model.model_hash
    assert result.target_revision_count == len(days) + 1
    assert result.target_distinct_gas_days == len(days)
    assert result.feature_day_count == len(days)
    assert result.forecast_raw_count == len(days) * 9
    assert result.paired_eligible_training_day_count >= 8
    assert "rec-extra-revision" in result.evidence.target_revision_ids
    assert "rec-extra-revision" not in result.model_result.baseline_model.target_revision_ids
    assert result.evidence.regional_weighting_evidence_ref == WEIGHT_EVIDENCE
    assert result.evidence.regional_weighting_evidence_basis == (
        "CALLER_DECLARED_PROVENANCE_NOT_REVIEWED"
    )
    assert result.evidence.validation_basis is ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS
    assert result.research_only
    assert result.production_promotion is PromotionStatus.NOT_PROMOTED
    assert all(feature.daily_mean_hdd is not None for feature in result.feature_rows)
    _assert_no_writes(session)


def test_all_admitted_revisions_reach_the_fitter_without_global_latest_narrowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    days = tuple(START + timedelta(days=index) for index in range(8))
    policy = _feature_policy()
    cutoff = _day_start(days[-1] + timedelta(days=1)) + timedelta(hours=6)
    validation = _day_start(days[-1] + timedelta(days=2))
    targets = _target_records(days)
    targets.append(
        _target_record(
            days[0],
            130.0,
            record_id="rec-later",
            available=_day_end(days[0]) + timedelta(hours=12),
        )
    )
    captured: dict[str, object] = {}

    def fake_fit(targets_arg, features_arg, policy_arg):
        captured["targets"] = targets_arg
        captured["features"] = features_arg
        captured["policy"] = policy_arg
        raise MissingNumpyError()

    monkeypatch.setattr(runtime, "fit_weather_demand_model", fake_fit)
    monkeypatch.setattr(
        runtime,
        "project_forecast_observation_record",
        lambda record: record,
    )
    session = _FakeSession(
        [targets]
        + [_forecast_rows(day, run_id=f"run-{day.isoformat()}") for day in days]
    )

    result = run_weather_demand_runtime(
        session,
        _request(policy, days, cutoff=cutoff, validation=validation),
    )

    assert result.status is WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED
    assert result.model_result is None
    assert result.target_revision_count == len(days) + 1
    assert result.paired_eligible_training_day_count == len(days)
    assert [row.revision_id for row in result.target_inputs.rows].count("rec-later") == 1
    passed_targets = captured["targets"]
    assert isinstance(passed_targets, tuple)
    expected_revision_ids = {f"rec-{day.isoformat()}" for day in days} | {"rec-later"}
    assert {row.revision_id for row in passed_targets} == expected_revision_ids
    _assert_no_writes(session)


def test_each_day_reads_its_own_origin_brackets_and_explicit_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    days = (START, START + timedelta(days=1))
    policy = _feature_policy()
    cutoff = _day_start(days[0])
    validation = _day_start(days[-1] + timedelta(days=2))
    calls: list[tuple[object, ...]] = []

    def fake_read(*args: object) -> list[object]:
        calls.append(args)
        return []

    monkeypatch.setattr(runtime, "read_ecmwf_forecasts", fake_read)
    monkeypatch.setattr(
        runtime,
        "fit_weather_demand_model",
        lambda *args, **kwargs: pytest.fail("no feature row should reach the fitter"),
    )
    session = _FakeSession([_target_records(days)])

    result = run_weather_demand_runtime(
        session,
        _request(policy, days, cutoff=cutoff, validation=validation),
    )

    assert result.status is WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY
    assert result.forecast_raw_count == 0
    assert len(result.omitted_days) == 2
    assert len(calls) == 2
    for args, day in zip(calls, days, strict=True):
        _, series_ids, entity_ids, origin, valid_from, valid_to, limit = args
        assert series_ids == ("S1",)
        assert entity_ids == ("E1",)
        assert origin == _day_start(day) - timedelta(hours=1)
        assert valid_from == _day_start(day) - timedelta(minutes=240)
        assert valid_to == _day_end(day) + timedelta(minutes=240)
        assert limit == 256
    _assert_no_writes(session)


def test_paired_history_below_policy_minimum_never_calls_the_fitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    day = START
    policy = _feature_policy()
    cutoff = _day_start(day + timedelta(days=1)) + timedelta(hours=6)
    fit_calls: list[tuple[object, ...]] = []

    def tripwire(*args: object) -> None:
        fit_calls.append(args)
        pytest.fail("fitter must not run when paired history is below the policy minimum")

    monkeypatch.setattr(runtime, "fit_weather_demand_model", tripwire)
    monkeypatch.setattr(
        runtime,
        "project_forecast_observation_record",
        lambda record: record,
    )
    session = _FakeSession(
        [
            _target_records((day,)),
            _forecast_rows(day, run_id="run-single-paired-day"),
        ]
    )

    result = run_weather_demand_runtime(
        session,
        _request(
            policy,
            (day,),
            cutoff=cutoff,
            validation=_day_start(day + timedelta(days=2)),
        ),
    )

    assert fit_calls == []
    assert result.status is WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY
    assert result.model_result is None
    assert result.paired_eligible_training_day_count == 1
    assert result.target_revision_count == 1
    assert result.target_distinct_gas_days == 1
    assert result.feature_day_count == 1
    assert result.forecast_raw_count == 9
    assert result.omitted_days == ()
    assert result.evidence.target_revision_ids == (f"rec-{day.isoformat()}",)
    assert len(result.evidence.forecast_observation_ids) == 9
    assert [item.code for item in result.diagnostics] == [
        WeatherDemandRuntimeDiagnosticCode.INSUFFICIENT_TRAINING_HISTORY
    ]
    detail = result.diagnostics[0].detail
    assert "paired_eligible_training_days=1" in detail
    assert "required_min_training_rows=8" in detail
    _assert_no_writes(session)


def test_missing_dependency_is_typed_and_never_substitutes_a_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    days = tuple(START + timedelta(days=index) for index in range(8))
    policy = _feature_policy()
    session = _FakeSession(
        [_target_records(days)]
        + [_forecast_rows(day, run_id=f"run-{day.isoformat()}") for day in days]
    )
    monkeypatch.setattr(
        runtime,
        "project_forecast_observation_record",
        lambda record: record,
    )
    monkeypatch.setattr(
        runtime,
        "fit_weather_demand_model",
        _raise_missing_numpy,
    )

    result = run_weather_demand_runtime(
        session,
        _request(
            policy,
            days,
            cutoff=_day_start(days[-1] + timedelta(days=1)) + timedelta(hours=6),
            validation=_day_start(days[-1] + timedelta(days=2)),
        ),
    )

    assert result.status is WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED
    assert result.model_result is None
    assert result.paired_eligible_training_day_count == len(days)
    assert result.feature_day_count == len(days)
    assert [item.code for item in result.diagnostics] == [
        WeatherDemandRuntimeDiagnosticCode.NUMPY_NOT_INSTALLED
    ]
    assert all(feature.daily_mean_hdd is not None for feature in result.feature_rows)
    _assert_no_writes(session)


def test_missing_coverage_is_omitted_with_reason_not_filled_with_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    days = tuple(START + timedelta(days=index) for index in range(9))
    policy = _feature_policy()
    incomplete = _forecast_rows(days[0], run_id="run-incomplete")[0]
    session = _FakeSession(
        [_target_records(days), [incomplete]]
        + [_forecast_rows(day, run_id=f"run-{day.isoformat()}") for day in days[1:]]
    )
    monkeypatch.setattr(
        runtime,
        "project_forecast_observation_record",
        lambda record: record,
    )
    monkeypatch.setattr(
        runtime,
        "fit_weather_demand_model",
        _raise_missing_numpy,
    )

    result = run_weather_demand_runtime(
        session,
        _request(
            policy,
            days,
            cutoff=_day_start(days[-1] + timedelta(days=1)) + timedelta(hours=6),
            validation=_day_start(days[-1] + timedelta(days=2)),
        ),
    )

    assert result.status is WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED
    assert result.paired_eligible_training_day_count == len(days) - 1
    assert result.feature_day_count == len(days) - 1
    assert result.feature_rows[0].gas_day == days[1]
    assert result.forecast_raw_count == 1 + 9 * (len(days) - 1)
    assert len(result.omitted_days) == 1
    omitted = result.omitted_days[0]
    assert omitted.gas_day == days[0]
    assert omitted.reason is WeatherDemandOmissionReason.FORECAST_BRIDGE_MISSING
    assert omitted.selected_vintage is not None
    assert WeatherDemandDiagnosticCode.NO_INTERVALS_IN_WINDOW in {
        item.code for item in omitted.bridge_diagnostics
    }
    assert any(
        item.code is WeatherDemandRuntimeDiagnosticCode.FORECAST_DAY_OMITTED
        and item.gas_day == days[0]
        for item in result.diagnostics
    )
    _assert_no_writes(session)


def test_future_issue_or_receipt_cannot_enter_the_selected_vintage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    day = START
    policy = _feature_policy()
    origin = _day_start(day) - timedelta(hours=1)
    future = _forecast_rows(
        day,
        run_id="run-future",
        issued=origin + timedelta(hours=1),
        available=origin + timedelta(hours=2),
    )[0]
    session = _FakeSession(
        [
            _target_records((day,)),
            _forecast_rows(day, run_id="run-eligible") + [future],
        ]
    )
    monkeypatch.setattr(
        runtime,
        "project_forecast_observation_record",
        lambda record: record,
    )
    monkeypatch.setattr(
        runtime,
        "fit_weather_demand_model",
        _raise_missing_numpy,
    )

    result = run_weather_demand_runtime(
        session,
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_start(day + timedelta(days=2)),
        ),
    )

    assert result.feature_day_count == 1
    assert len(result.selected_vintages) == 1
    assert result.selected_vintages[0].run_id == "run-eligible"
    assert result.forecast_raw_count == 10
    assert future.forecast_observation_id in result.evidence.forecast_observation_ids
    assert all(
        feature.forecast_vintage is not None
        and feature.forecast_vintage.run_id == "run-eligible"
        for feature in result.feature_rows
    )


def test_no_admitted_targets_returns_explicit_insufficient_history() -> None:
    day = START
    policy = _feature_policy()
    session = _FakeSession([[]])

    result = run_weather_demand_runtime(
        session,
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
        ),
    )

    assert result.status is WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY
    assert result.model_result is None
    assert result.target_revision_count == 0
    assert result.target_distinct_gas_days == 0
    assert result.feature_day_count == 0
    assert result.forecast_raw_count == 0
    assert result.omitted_days == ()
    assert [item.code for item in result.diagnostics] == [
        WeatherDemandRuntimeDiagnosticCode.NO_ADMITTED_TARGET_REVISIONS
    ]
    _assert_no_writes(session)
    assert session.no_autoflush_entries == 1
    assert session.autoflush_depth == 0


def test_target_source_format_window_cutoff_and_limit_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    day = START
    policy = _feature_policy()
    cutoff = _day_start(day)
    validation = _day_end(day)
    captured: dict[str, object] = {}

    def fake_read(_session, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(runtime, "read_demand_target_revisions", fake_read)

    result = run_weather_demand_runtime(
        object(),
        _request(
            policy,
            (day,),
            cutoff=cutoff,
            validation=validation,
            source_format="REST",
        ),
    )

    assert result.status is WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY
    assert captured == {
        "provider_item_id": PROVIDER_ITEM,
        "source_format": "REST",
        "gas_day_from": day,
        "gas_day_to": day,
        "available_at_utc": validation,
        "limit": 1_000,
    }


def test_request_hash_preserves_legacy_default_and_binds_opt_in_policy() -> None:
    day = START
    policy = _feature_policy()
    cutoff = _day_start(day)
    validation = _day_end(day)
    implicit_default = _request(
        policy,
        (day,),
        cutoff=cutoff,
        validation=validation,
    )
    explicit_default = _request(
        policy,
        (day,),
        cutoff=cutoff,
        validation=validation,
        revision_order_policy=RevisionOrderPolicy.DERIVED_RECEIPT_ORDER,
    )
    rest_default = _request(
        policy,
        (day,),
        cutoff=cutoff,
        validation=validation,
        source_format="REST",
    )
    rest_explicit_default = _request(
        policy,
        (day,),
        cutoff=cutoff,
        validation=validation,
        source_format="REST",
        revision_order_policy=RevisionOrderPolicy.DERIVED_RECEIPT_ORDER,
    )
    rest_opt_in = _request(
        policy,
        (day,),
        cutoff=cutoff,
        validation=validation,
        source_format="REST",
        revision_order_policy=(
            RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
        ),
    )

    assert implicit_default.request_hash == explicit_default.request_hash
    assert rest_default.request_hash == rest_explicit_default.request_hash
    assert rest_opt_in.request_hash != rest_default.request_hash
    assert rest_opt_in.target_revision_order_policy is (
        RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
    )


def test_opt_in_policy_requires_rest_and_a_known_enum_before_any_read() -> None:
    day = START
    policy = _feature_policy()
    cutoff = _day_start(day)
    validation = _day_end(day)
    opt_in = RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1

    with pytest.raises(WeatherDemandRuntimeValidationError, match="REST"):
        _request(
            policy,
            (day,),
            cutoff=cutoff,
            validation=validation,
            source_format="CSV",
            revision_order_policy=opt_in,
        )
    with pytest.raises(
        WeatherDemandRuntimeValidationError,
        match="supported revision-order policy",
    ):
        _request(
            policy,
            (day,),
            cutoff=cutoff,
            validation=validation,
            revision_order_policy="UNKNOWN_POLICY",
        )

    request = _request(
        policy,
        (day,),
        cutoff=cutoff,
        validation=validation,
        source_format="CSV",
    )
    object.__setattr__(request, "target_revision_order_policy", opt_in)
    session = _FakeSession([])
    with pytest.raises(WeatherDemandRuntimeValidationError, match="REST"):
        run_weather_demand_runtime(session, request)
    assert session.responses == []
    _assert_no_writes(session)


def test_default_runtime_still_refuses_same_receipt_rest_tie() -> None:
    day = date(2026, 10, 21)
    policy = _feature_policy()
    records = _rest_records(
        [
            _rest_row(
                gas_day=day,
                applicable_at="2026-10-21T09:20:01+00:00",
                value="100",
            ),
            _rest_row(
                gas_day=day,
                applicable_at="2026-10-21T11:20:01+00:00",
                value="101",
            ),
        ],
        date_from=day,
        date_to=day,
    )
    session = _FakeSession([records])

    with pytest.raises(DemandTargetAmbiguityError) as caught:
        run_weather_demand_runtime(
            session,
            _request(
                policy,
                (day,),
                cutoff=REST_RECEIVED,
                validation=REST_RECEIVED + timedelta(days=1),
                source_format="REST",
            ),
        )

    assert caught.value.code == "AMBIGUOUS_RECEIPT_TIE"
    assert session.responses == []
    _assert_no_writes(session)


def test_opt_in_runtime_keeps_all_revisions_and_forwards_source_clock_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    days = tuple(
        date(2026, 10, 21) - timedelta(days=offset) for offset in range(7, -1, -1)
    )
    source_rows = [
        _rest_row(
            gas_day=days[0],
            applicable_at=f"{days[0].isoformat()}T11:20:01+00:00",
            value="101",
        ),
        _rest_row(
            gas_day=days[0],
            applicable_at=f"{days[0].isoformat()}T09:20:01+00:00",
            value="100",
        ),
    ]
    source_rows.extend(
        _rest_row(
            gas_day=day,
            applicable_at=f"{day.isoformat()}T10:20:01+00:00",
            value=str(200 + index),
        )
        for index, day in enumerate(days[1:])
    )
    targets = _rest_records(
        source_rows,
        date_from=days[0],
        date_to=days[-1],
    )
    captured: dict[str, object] = {}

    def fake_fit(targets_arg, features_arg, policy_arg):
        captured["targets"] = targets_arg
        captured["features"] = features_arg
        captured["policy"] = policy_arg
        raise MissingNumpyError()

    monkeypatch.setattr(runtime, "fit_weather_demand_model", fake_fit)
    monkeypatch.setattr(
        runtime,
        "project_forecast_observation_record",
        lambda record: record,
    )
    session = _FakeSession(
        [targets]
        + [_forecast_rows(day, run_id=f"run-{day.isoformat()}") for day in days]
    )
    opt_in = RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1

    result = run_weather_demand_runtime(
        session,
        _request(
            _feature_policy(),
            days,
            cutoff=REST_RECEIVED + timedelta(days=1),
            validation=REST_RECEIVED + timedelta(days=2),
            source_format="REST",
            revision_order_policy=opt_in,
        ),
    )

    passed_targets = captured["targets"]
    assert isinstance(passed_targets, tuple)
    assert len(passed_targets) == len(targets) == 9
    assert {row.revision_id for row in passed_targets} == {
        row.record_id for row in targets
    }
    first_day = [row for row in passed_targets if row.gas_day == days[0]]
    assert [row.revision for row in first_day] == [1, 2]
    assert [row.value for row in first_day] == [100.0, 101.0]
    assert all(row.available_at == REST_RECEIVED for row in passed_targets)
    assert all(
        row.source_ref.endswith(f":{opt_in.value}") for row in passed_targets
    )
    assert result.status is WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED
    assert result.model_result is None
    assert result.target_revision_count == 9
    assert result.target_distinct_gas_days == 8
    assert result.evidence.target_revision_order_policy is opt_in
    assert result.target_revision_order_policy is opt_in
    assert result.target_availability_basis == "ACTUAL_RECEIPT_AVAILABLE_AT"
    assert set(result.evidence.target_source_refs) == {
        row.source_ref for row in passed_targets
    }
    assert result.research_only
    assert result.production_promotion is PromotionStatus.NOT_PROMOTED
    _assert_no_writes(session)


def test_validation_rejects_synthetic_basis_region_source_and_unit_mismatches() -> None:
    day = START
    policy = _feature_policy()
    with pytest.raises(WeatherDemandRuntimeSyntheticBasisError) as synthetic:
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            basis=ValidationBasis.SYNTHETIC_NOT_REAL,
        )
    assert synthetic.value.code == "SYNTHETIC_VALIDATION_BASIS_REJECTED"

    with pytest.raises(WeatherDemandRuntimeValidationError, match="source_format"):
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            source_format="XLSX",
        )
    with pytest.raises(WeatherDemandRuntimeValidationError, match="MSCM"):
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            target_unit="MWH",
        )
    with pytest.raises(WeatherDemandRuntimeValidationError, match="feature-policy hash"):
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            configs=_configs(_feature_policy(region="DE"), (day,)),
        )
    with pytest.raises(WeatherDemandRuntimeValidationError, match="point binding region"):
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            point_bindings=(_binding(region="DE"),),
        )
    mismatch = replace(
        _degree_policy(policy),
        heating_base_c=18.0,
    )
    with pytest.raises(WeatherDemandRuntimeValidationError, match="degree-day policy"):
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            degree_policy=mismatch,
        )


def test_bridge_requires_one_unique_day_and_origin_before_day_end() -> None:
    day = START
    policy = _feature_policy()
    two_days = WeatherDemandBridgeConfig(
        feature_policy=policy,
        prediction_origin=_day_start(day) - timedelta(hours=1),
        gas_days=(day, day + timedelta(days=1)),
        max_hold_minutes=240,
    )
    with pytest.raises(WeatherDemandRuntimeValidationError, match="exactly one gas day"):
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            configs=(two_days,),
        )

    duplicate = _configs(policy, (day,)) + _configs(policy, (day,))
    with pytest.raises(WeatherDemandRuntimeValidationError, match="duplicate gas days"):
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            configs=duplicate,
        )

    after_end = WeatherDemandBridgeConfig(
        feature_policy=policy,
        prediction_origin=_day_end(day),
        gas_days=(day,),
        max_hold_minutes=240,
    )
    with pytest.raises(WeatherDemandRuntimeValidationError, match="precede"):
        _request(
            policy,
            (day,),
            cutoff=_day_start(day),
            validation=_day_end(day),
            configs=(after_end,),
        )


def test_bridge_status_is_ready_for_the_synthetic_daily_mechanics() -> None:
    policy = _feature_policy()
    rows = _forecast_rows(START, run_id="run-1")

    bundle = build_weather_demand_inputs(rows, (_binding(),), _configs(policy, (START,))[0])

    assert bundle.status is WeatherDemandInputStatus.READY
    assert bundle.ready
    assert bundle.selected_vintage is not None
