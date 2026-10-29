"""Real PostgreSQL acceptance for the read-only weather-demand runtime composition.

These tests own a disposable schema and persist actual ORM rows for National Gas
demand-target revisions and ECMWF forecast observations.  The production runtime,
repository queries, forecast projection, degree-day bridge/solver and frozen
NumPy fitter are called directly; none of them is mocked.

All source values are explicitly synthetic mechanics fixtures.  The forecast
rows nevertheless carry the authentic ``ecmwf-open-data-forecast-observation/v3``
provenance required by the existing projection, so the persisted-row plumbing is
exercised rather than a simplified stand-in.  They are not provider history,
accuracy evidence, model promotion or a production readiness claim.

The successful fitted-core case needs the separately reviewed optional NumPy
dependency and is skipped when it is absent.  The other cases are deliberately
independent of NumPy: they stop at missing history, SQL-origin exclusion,
no-autoflush or target-read overflow before any fit could occur.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from eurogas_nexus.application.research.weather_demand_inputs import (
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
)
from eurogas_nexus.application.research.weather_demand_runtime import (
    WeatherDemandOmissionReason,
    WeatherDemandRuntimeDiagnosticCode,
    WeatherDemandRuntimeRequest,
    WeatherDemandRuntimeStatus,
    run_weather_demand_runtime,
)
from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.db.models.research import ForecastObservationRecord
from eurogas_nexus.db.repositories.demand import DemandTargetReadOverflow
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
    ModelUseStatus,
    PromotionStatus,
    RegionLocationWeight,
    ValidationBasis,
)

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; each test uses a disposable schema.",
)

PROVIDER_ITEM = "PUBOB637"
CALENDAR = DEFAULT_GAS_DAY_CALENDAR
START = date(2026, 1, 1)
WEIGHT_EVIDENCE = "evidence://regional-weighting/synthetic-runtime-pg"
HOUR_OFFSETS = tuple(range(0, 25, 3))
# Nine explicit instant rows per gas day, above the eight-row mechanics minimum.
# Authentic v3 source-field metadata stores integral step_hours, so a literal
# eight-minute cadence cannot share one persisted forecast vintage.


def _numpy_available() -> bool:
    return importlib.util.find_spec("numpy") is not None


def _day_start(day: date) -> datetime:
    return gas_day_start_for_date(day, CALENDAR)


def _day_end(day: date) -> datetime:
    return gas_day_start_for_date(day + timedelta(days=1), CALENDAR)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _feature_policy() -> DegreeDayFeaturePolicy:
    return DegreeDayFeaturePolicy(
        region="GB_NTS",
        heating_base_c=15.5,
        cooling_base_c=22.0,
        max_gap_minutes=240,
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
) -> DemandModelPolicy:
    return DemandModelPolicy(
        target_scope=TargetScope.GB_NTS_THROUGHPUT,
        region=policy.region,
        target_unit="MSCM",
        gas_day_calendar=CALENDAR,
        training_cutoff=cutoff,
        validation_as_of=validation,
        ridge_lambda=1e-8,
        model_version="synthetic-weather-demand-runtime-postgres/v1",
        validation_basis=ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS,
        weather_features=(WeatherFeature.HDD_MEAN,),
        expected_feature_policy=policy,
        min_training_rows=8,
        min_validation_folds=3,
        min_validation_predictions=3,
        min_oos_coverage=0.5,
        min_relative_mae_improvement=0.0,
        min_fold_win_fraction=0.0,
        min_residuals_for_interval=0,
        interval_level=0.8,
        max_training_rows=100,
        max_features=16,
        max_folds=10,
    )


def _binding() -> ForecastPointBinding:
    return ForecastPointBinding(
        point_id="P1",
        series_id="S1",
        entity_id="E1",
        location_id="L1",
        region="GB_NTS",
    )


def _configs(
    policy: DegreeDayFeaturePolicy,
    days: tuple[date, ...],
) -> tuple[WeatherDemandBridgeConfig, ...]:
    return tuple(
        WeatherDemandBridgeConfig(
            feature_policy=policy,
            prediction_origin=_day_start(day) - timedelta(hours=1),
            gas_days=(day,),
            max_hold_minutes=240,
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
    source_format: str = "CSV",
    target_read_limit: int = 1_000,
) -> WeatherDemandRuntimeRequest:
    return WeatherDemandRuntimeRequest(
        model_policy=_model_policy(policy, cutoff=cutoff, validation=validation),
        degree_day_policy=_degree_policy(policy),
        bridge_configs=_configs(policy, days),
        point_bindings=(_binding(),),
        provider_item_id=PROVIDER_ITEM,
        source_format=source_format,
        target_gas_day_from=days[0],
        target_gas_day_to=days[-1],
        allow_provisional_targets=True,
        regional_weighting_evidence_ref=WEIGHT_EVIDENCE,
        target_read_limit=target_read_limit,
    )


def _temperature(day: date, offset_hours: int) -> float:
    return (
        9.0
        + 4.0 * math.sin(2.0 * math.pi * day.toordinal() / 13.0)
        + 1.5 * math.sin(2.0 * math.pi * offset_hours / 24.0)
    )


def _target_value(day: date) -> str:
    mean = math.fsum(_temperature(day, offset) for offset in HOUR_OFFSETS) / len(
        HOUR_OFFSETS
    )
    return f"{120.0 + 30.0 * max(0.0, 15.5 - mean):.3f}"


def _target_row(
    record_id: str,
    day: date,
    value_text: str,
    *,
    available_at: datetime,
    source_format: str = "CSV",
) -> NationalGasActualDemandRecord:
    start = _day_start(day)
    end = _day_end(day)
    return NationalGasActualDemandRecord(
        record_id=record_id,
        source_publication_id=f"pub-{record_id}",
        provider_item_id=PROVIDER_ITEM,
        series_key=f"national-gas:actual:GB_NTS:D+1:{source_format}",
        region="GB_NTS",
        term="D+1",
        label="Demand Actual, NTS, D+1",
        gas_day=day,
        period_start_utc=start,
        period_end_utc=end,
        value_text=value_text,
        unit="mscm",
        received_at_utc=available_at,
        available_at_utc=available_at,
        ingested_at_utc=available_at,
        published_at_utc=None,
        applicable_at_raw=day.isoformat(),
        generated_at_raw=available_at.isoformat(),
        applicable_at_naive=start.replace(tzinfo=None),
        generated_at_naive=available_at.replace(tzinfo=None),
        quality_indicator=None,
        provisional_status="PROVISIONAL_INITIAL",
        is_provisional=True,
        raw_sha256=_sha(record_id),
        source_url="https://example.test/synthetic-national-gas",
        hash_schema="national_gas_actual_demand.v1",
        value_is_blank=value_text == "",
        source_format=source_format,
        rest_provenance={"synthetic": True} if source_format == "REST" else None,
    )


def _provenance(
    *,
    observation_id: str,
    point_id: str,
    series_id: str,
    entity_id: str,
    issued: datetime,
    valid: datetime,
    available: datetime,
    temperature_c: float,
    grib_sha256: str,
    content_sha256: str,
    step_hours: int,
) -> dict[str, object]:
    run_date = issued.date().isoformat()
    valid_text = valid.isoformat()
    asset_url = (
        f"https://example.test/ecmwf/ifs/{run_date}/"
        f"{issued.hour:02d}/step-{step_hours:03d}.grib2"
    )
    source_field_version = {
        "grib_sha256": grib_sha256,
        "param_id": 167,
        "units": "K",
        "run_date": run_date,
        "cycle_hour": issued.hour,
        "step_hours": step_hours,
        "valid_at_utc": valid_text,
    }
    return {
        "schema": "ecmwf-open-data-forecast-observation/v3",
        "source_system": "ECMWF_OPEN_DATA",
        "provider": "ECMWF",
        "entity_id": entity_id,
        "grib_sha256": grib_sha256,
        "content_sha256": content_sha256,
        "grib": {"sha256": grib_sha256, "synthetic_mechanics": True},
        "source_field_version": source_field_version,
        "reference": {
            "run_date": run_date,
            "cycle_hour": issued.hour,
            "step_hours": step_hours,
            "valid_at_utc": valid_text,
            "grib_sha256": grib_sha256,
            "asset_url": asset_url,
        },
        "request": {
            "run_date": run_date,
            "cycle_hour": issued.hour,
            "step_hours": step_hours,
        },
        "run": {
            "forecast_issued_at_utc": issued.isoformat(),
            "forecast_valid_at_utc": valid_text,
            "receipt_completed_at_utc": available.isoformat(),
        },
        "availability": {"available_at_utc": available.isoformat()},
        "temporal": {
            "scope": "instant",
            "forecast_valid_start": valid_text,
            "forecast_valid_end": None,
            "database_end_representation": (
                "zero_length_interval_due_to_existing_non_null_schema"
            ),
        },
        "point": {
            "point_id": point_id,
            "temperature_celsius": temperature_c,
            "temperature_kelvin": temperature_c + 273.15,
            "represents_observing_station": False,
        },
        "binding": {
            "point_id": point_id,
            "series_id": series_id,
            "entity_id": entity_id,
        },
        "quality": {"quality_state": "FORECAST"},
        "observation_id": observation_id,
    }


def _forecast_run(
    day: date,
    *,
    label: str,
    issued: datetime,
    available: datetime,
) -> list[ForecastObservationRecord]:
    start = _day_start(day)
    rows: list[ForecastObservationRecord] = []
    for offset in HOUR_OFFSETS:
        valid = start + timedelta(hours=offset)
        step_hours = int((valid - issued).total_seconds() // 3_600)
        assert issued + timedelta(hours=step_hours) == valid
        observation_id = f"{label}-{day.isoformat()}-{offset:02d}"
        grib_sha256 = _sha(f"grib-{observation_id}")
        content_sha256 = _sha(f"content-{observation_id}")
        temperature_c = _temperature(day, offset)
        rows.append(
            ForecastObservationRecord(
                forecast_observation_id=observation_id,
                series_id="S1",
                entity_id="E1",
                forecast_issued_at=issued,
                forecast_valid_start=valid,
                forecast_valid_end=valid,
                horizon=f"{step_hours}h",
                value=temperature_c,
                unit="degC",
                source_system="ECMWF_OPEN_DATA",
                model_provider="ECMWF",
                available_at_utc=available,
                ingested_at_utc=available,
                provenance=_provenance(
                    observation_id=observation_id,
                    point_id="P1",
                    series_id="S1",
                    entity_id="E1",
                    issued=issued,
                    valid=valid,
                    available=available,
                    temperature_c=temperature_c,
                    grib_sha256=grib_sha256,
                    content_sha256=content_sha256,
                    step_hours=step_hours,
                ),
                quality_state="FORECAST",
            )
        )
    return rows


def _eligible_forecast(day: date, *, label: str) -> list[ForecastObservationRecord]:
    start = _day_start(day)
    return _forecast_run(
        day,
        label=label,
        issued=start - timedelta(hours=12),
        available=start - timedelta(hours=1),
    )


@contextmanager
def _session():
    url = make_url(_POSTGRES_URL)
    connect_args = (
        {"timeout": 5} if url.get_driver_name() == "pg8000" else {"connect_timeout": 5}
    )
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"weatherdemandruntime_{uuid4().hex}"
    schema_created = False
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            NationalGasActualDemandRecord.__table__.create(bind=connection)
            ForecastObservationRecord.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        try:
            if schema_created:
                with engine.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            engine.dispose()


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.skipif(
    not _numpy_available(),
    reason=(
        "optional NumPy is absent; the actual frozen fitter is exercised only in "
        "an environment that separately supplies the reviewed numerical dependency"
    ),
)
def test_real_orm_rows_reach_the_actual_fitted_core_with_research_evidence():
    days = tuple(START + timedelta(days=index) for index in range(21))
    policy = _feature_policy()
    cutoff = _day_start(days[14])
    validation = _day_end(days[-1]) + timedelta(hours=1)
    later_day = days[9]
    later_available = _day_start(days[15])
    targets = [
        _target_row(
            f"actual-{day.isoformat()}",
            day,
            _target_value(day),
            available_at=_day_end(day) + timedelta(hours=1),
        )
        for day in days
    ]
    targets.append(
        _target_row(
            "actual-later-revision",
            later_day,
            "999.999",
            available_at=later_available,
        )
    )
    forecast_rows = [
        row for day in days for row in _eligible_forecast(day, label=f"run-{day.isoformat()}")
    ]

    with _session() as session:
        session.add_all(targets)
        session.add_all(forecast_rows)
        session.flush()
        persisted_targets = _count(session, NationalGasActualDemandRecord)
        persisted_forecasts = _count(session, ForecastObservationRecord)

        result = run_weather_demand_runtime(
            session,
            _request(policy, days, cutoff=cutoff, validation=validation),
        )

        assert result.status is WeatherDemandRuntimeStatus.READY
        assert result.model_result is not None
        assert result.has_model
        assert result.research_only
        assert result.production_promotion is PromotionStatus.NOT_PROMOTED
        assert result.model_result.production_promotion is PromotionStatus.NOT_PROMOTED
        assert result.model_result.selected_model.use_status in {
            ModelUseStatus.UNVALIDATED_OOS_RESEARCH_OUTPUT,
            ModelUseStatus.CALENDAR_BASELINE_REFERENCE,
        }
        assert result.native_unit == "MSCM"
        assert result.source_format == "CSV"
        assert result.evidence.validation_basis is (
            ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS
        )
        assert result.evidence.training_cutoff == cutoff
        assert result.evidence.validation_as_of == validation
        assert result.evidence.regional_weighting_evidence_ref == WEIGHT_EVIDENCE
        assert result.evidence.regional_weighting_evidence_basis == (
            "CALLER_DECLARED_PROVENANCE_NOT_REVIEWED"
        )

        # Every admitted target revision is retained for per-fold resolution; the
        # later revision is genuinely unavailable at the training cutoff.
        assert result.target_revision_count == len(targets)
        assert result.target_distinct_gas_days == len(days)
        assert {"actual-later-revision"} <= set(result.evidence.target_revision_ids)
        assert len(result.target_inputs.provenance_by_record_id) == len(targets)
        assert result.target_inputs.provenance_by_record_id[
            "actual-later-revision"
        ].value_text == "999.999"
        assert "actual-later-revision" not in (
            result.model_result.baseline_model.target_revision_ids
        )
        assert later_available > cutoff
        assert result.model_result.folds
        assert later_available > min(fold.fold_origin for fold in result.model_result.folds)

        # The persisted authentic-v3 forecasts are the ones the runtime read and
        # projected; the later target revision is not evidence of a forecast run.
        assert result.feature_day_count == len(days)
        assert result.forecast_raw_count >= len(days) * len(HOUR_OFFSETS)
        assert set(result.evidence.forecast_observation_ids) == {
            row.forecast_observation_id for row in forecast_rows
        }
        assert len(result.evidence.forecast_observation_ids) == len(forecast_rows)
        assert len(result.selected_vintages) == len(days)
        assert len(result.evidence.selected_vintage_ids) == len(days)
        assert all(
            vintage_id.startswith("ECMWF/ifs/")
            for vintage_id in result.evidence.selected_vintage_ids
        )
        assert result.evidence.feature_source_refs
        assert all(
            source_ref.startswith("sha256:")
            for source_ref in result.evidence.feature_source_refs
        )

        # The core's own hashes are carried through unchanged, and its selection
        # evidence is available only at the explicit validation cutoff.
        assert result.evidence.selected_model_hash == (
            result.model_result.selected_model.model_hash
        )
        assert result.evidence.baseline_model_hash == (
            result.model_result.baseline_model.model_hash
        )
        assert result.evidence.candidate_model_hash == (
            result.model_result.candidate_model.model_hash
            if result.model_result.candidate_model is not None
            else None
        )
        assert result.evidence.model_selection_hash == result.model_result.selection_hash
        assert result.model_selection_hash == result.model_result.selection_hash
        assert result.selected_model_hash == result.model_result.selected_model.model_hash
        assert result.model_result.selection_evidence is not None
        assert result.model_result.selection_evidence.validation_as_of == validation
        assert result.model_use_label in {
            ModelUseStatus.UNVALIDATED_OOS_RESEARCH_OUTPUT.value,
            ModelUseStatus.CALENDAR_BASELINE_REFERENCE.value,
        }

        assert _count(session, NationalGasActualDemandRecord) == persisted_targets
        assert _count(session, ForecastObservationRecord) == persisted_forecasts
        assert not session.new and not session.dirty and not session.deleted


def test_later_issue_and_receipt_are_excluded_by_the_actual_sql_origin_filter():
    day = START
    start = _day_start(day)
    origin = start - timedelta(hours=1)
    eligible = _forecast_run(
        day,
        label="eligible",
        issued=origin - timedelta(hours=12),
        available=origin - timedelta(hours=1),
    )
    later_issued = origin + timedelta(hours=1)
    later_available = origin + timedelta(hours=2)
    later = _forecast_run(
        day,
        label="later",
        issued=later_issued,
        available=later_available,
    )
    target = _target_row(
        "actual-single-day",
        day,
        "123.456",
        available_at=_day_end(day) + timedelta(hours=1),
    )

    with _session() as session:
        session.add_all([target, *eligible, *later])
        session.flush()

        result = run_weather_demand_runtime(
            session,
            _request(
                _feature_policy(),
                (day,),
                cutoff=start,
                validation=_day_end(day) + timedelta(hours=1),
            ),
        )

        assert result.forecast_raw_count == len(eligible)
        assert set(result.evidence.forecast_observation_ids) == {
            row.forecast_observation_id for row in eligible
        }
        assert not (
            {row.forecast_observation_id for row in later}
            & set(result.evidence.forecast_observation_ids)
        )
        assert len(result.selected_vintages) == 1
        assert result.selected_vintages[0].issued_at == eligible[0].forecast_issued_at
        assert result.selected_vintages[0].run_id == (
            f"{eligible[0].forecast_issued_at:%Y%m%d}T"
            f"{eligible[0].forecast_issued_at.hour:02d}Z"
        )
        assert result.evidence.selected_vintage_ids
        assert result.target_revision_count == 1
        assert result.status in {
            WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY,
            WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED,
        }
        assert result.model_result is None
        assert not session.new and not session.dirty and not session.deleted


def test_missing_weather_history_is_numpy_independent_and_formats_stay_explicit():
    day = START
    with _session() as session:
        session.add_all(
            [
                _target_row(
                    "csv-row",
                    day,
                    "101.100",
                    available_at=_day_end(day) + timedelta(hours=1),
                    source_format="CSV",
                ),
                _target_row(
                    "rest-row",
                    day,
                    "202.200",
                    available_at=_day_end(day) + timedelta(hours=1),
                    source_format="REST",
                ),
            ]
        )
        session.flush()

        csv_result = run_weather_demand_runtime(
            session,
            _request(
                _feature_policy(),
                (day,),
                cutoff=_day_end(day),
                validation=_day_end(day) + timedelta(hours=1),
                source_format="CSV",
            ),
        )
        rest_result = run_weather_demand_runtime(
            session,
            _request(
                _feature_policy(),
                (day,),
                cutoff=_day_end(day),
                validation=_day_end(day) + timedelta(hours=1),
                source_format="REST",
            ),
        )

        assert csv_result.status is WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY
        assert csv_result.model_result is None
        assert csv_result.native_unit == "MSCM"
        assert csv_result.source_format == "CSV"
        assert [row.revision_id for row in csv_result.target_inputs.rows] == ["csv-row"]
        assert csv_result.target_inputs.provenance_by_record_id[
            "csv-row"
        ].source_format == "CSV"
        assert csv_result.target_inputs.provenance_by_record_id[
            "csv-row"
        ].value_text == "101.100"
        assert csv_result.evidence.target_source_refs == (
            "NATIONAL_GAS:CSV:pub-csv-row",
        )
        assert csv_result.feature_rows == ()
        assert csv_result.omitted_days
        assert csv_result.omitted_days[0].reason is (
            WeatherDemandOmissionReason.FORECAST_BRIDGE_MISSING
        )
        assert WeatherDemandRuntimeDiagnosticCode.NO_ELIGIBLE_FEATURES in {
            item.code for item in csv_result.diagnostics
        }

        assert rest_result.status is WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY
        assert rest_result.model_result is None
        assert rest_result.native_unit == "MSCM"
        assert rest_result.source_format == "REST"
        assert [row.revision_id for row in rest_result.target_inputs.rows] == ["rest-row"]
        assert rest_result.target_inputs.provenance_by_record_id[
            "rest-row"
        ].source_format == "REST"
        assert rest_result.target_inputs.provenance_by_record_id[
            "rest-row"
        ].value_text == "202.200"
        assert rest_result.evidence.target_source_refs == (
            "NATIONAL_GAS:REST:pub-rest-row",
        )

        assert "csv-row" not in rest_result.evidence.target_revision_ids
        assert "rest-row" not in csv_result.evidence.target_revision_ids
        assert _count(session, NationalGasActualDemandRecord) == 2
        assert not session.new and not session.dirty and not session.deleted


def test_runtime_reads_do_not_autoflush_pending_caller_target_write():
    day = START
    pending_day = day + timedelta(days=30)
    with _session() as session:
        session.add(
            _target_row(
                "persisted-target",
                day,
                "140.000",
                available_at=_day_end(day) + timedelta(hours=1),
            )
        )
        session.flush()
        before = _count(session, NationalGasActualDemandRecord)
        caller_transaction = session.get_transaction()
        assert caller_transaction is not None

        pending = _target_row(
            "pending-caller-target",
            pending_day,
            "150.000",
            available_at=_day_end(pending_day) + timedelta(hours=1),
        )
        session.add(pending)
        flush_events: list[str] = []

        def _on_before_flush(*_args: object, **_kwargs: object) -> None:
            flush_events.append("before_flush")

        event.listen(session, "before_flush", _on_before_flush)
        try:
            result = run_weather_demand_runtime(
                session,
                _request(
                    _feature_policy(),
                    (day,),
                    cutoff=_day_end(day),
                    validation=_day_end(day) + timedelta(hours=1),
                ),
            )
        finally:
            event.remove(session, "before_flush", _on_before_flush)

        assert result.status is WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY
        assert [row.revision_id for row in result.target_inputs.rows] == [
            "persisted-target"
        ]
        assert flush_events == []

        pending_state = inspect(pending)
        assert pending_state.pending is True
        assert pending_state.persistent is False
        assert pending_state.transient is False
        assert pending_state.detached is False
        assert pending in session.new
        assert len(session.new) == 1
        assert session.get_transaction() is caller_transaction
        assert session.in_transaction()
        assert session.is_active
        assert not session.dirty and not session.deleted

        # Count inside a test-side no_autoflush scope so this assertion cannot
        # flush the pending row it is meant to prove absent.
        with session.no_autoflush:
            stored_ids = set(
                session.scalars(select(NationalGasActualDemandRecord.record_id))
            )
            after = _count(session, NationalGasActualDemandRecord)
        assert after == before
        assert "pending-caller-target" not in stored_ids
        assert session.get_transaction() is caller_transaction
        assert pending in session.new


def test_target_read_overflow_is_surfaced_and_never_becomes_a_partial_fit():
    days = tuple(START + timedelta(days=index) for index in range(3))
    targets = [
        _target_row(
            f"overflow-{day.isoformat()}",
            day,
            "130.000",
            available_at=_day_end(day) + timedelta(hours=1),
        )
        for day in days
    ]
    with _session() as session:
        session.add_all(targets)
        session.flush()
        before = _count(session, NationalGasActualDemandRecord)

        with pytest.raises(DemandTargetReadOverflow) as caught:
            run_weather_demand_runtime(
                session,
                _request(
                    _feature_policy(),
                    days,
                    cutoff=_day_start(days[0]),
                    validation=_day_end(days[-1]) + timedelta(hours=1),
                    target_read_limit=2,
                ),
            )

        assert caught.value.code == "DEMAND_TARGET_READ_OVERFLOW"
        assert _count(session, NationalGasActualDemandRecord) == before == 3
        assert not session.new and not session.dirty and not session.deleted
        assert session.get_transaction() is not None
