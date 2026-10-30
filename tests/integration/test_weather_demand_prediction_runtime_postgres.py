"""Real PostgreSQL acceptance for the frozen-model prediction runtime.

The test owns a disposable UUID schema and commits synthetic mechanics rows for a
21-day training window, then invokes the existing read-only
``run_weather_demand_runtime`` to obtain an actual frozen ``DemandModelResult``.
It persists future forecast rows and calls the new prediction runtime directly;
the repository prefilter, projection, bridge, degree-day solver and core predictor
are all real, with no mocked repository or predictor.

The values are synthetic mechanics, not provider history, a real fitted provider
model, prospective accuracy, GB representativeness or promotion evidence.  NumPy
is optional and the fitted case is skipped when it is absent; registration in the
scientific CI workflow is a root follow-up.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from eurogas_nexus.application.research.weather_demand_prediction_runtime import (
    PredictionConsumptionBasis,
    WeatherDemandPredictionRequest,
    WeatherDemandPredictionStatus,
    run_weather_demand_prediction_runtime,
)
from eurogas_nexus.application.research.weather_demand_runtime import (
    WeatherDemandRuntimeStatus,
    run_weather_demand_runtime,
)
from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.db.models.research import ForecastObservationRecord
from eurogas_nexus.domain.research.weather_demand import (
    ModelKind,
    ModelUseStatus,
    PromotionStatus,
)
from tests.integration.test_weather_demand_runtime_postgres import (
    START,
    WEIGHT_EVIDENCE,
    _binding,
    _configs,
    _day_end,
    _day_start,
    _degree_policy,
    _eligible_forecast,
    _feature_policy,
    _forecast_run,
    _numpy_available,
    _target_row,
    _target_value,
)
from tests.integration.test_weather_demand_runtime_postgres import (
    _request as _training_request,
)

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = [
    pytest.mark.skipif(
        not _POSTGRES_URL.startswith("postgresql"),
        reason="Explicit PostgreSQL test URL required; this test owns a disposable schema.",
    ),
    pytest.mark.skipif(
        not _numpy_available(),
        reason=(
            "optional NumPy is absent; the actual frozen fitter is exercised only in "
            "an environment that separately supplies the reviewed numerical dependency"
        ),
    ),
]


@contextmanager
def _owned_session():
    """Yield a committed-data session whose tables live in one disposable schema."""

    url = make_url(_POSTGRES_URL)
    connect_args = (
        {"timeout": 5} if url.get_driver_name() == "pg8000" else {"connect_timeout": 5}
    )
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"weatherdemandprediction_{uuid4().hex}"
    schema_created = False
    connection = None
    session = None
    try:
        connection = engine.connect()
        with connection.begin():
            connection.execute(text("SET LOCAL statement_timeout = '20s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            NationalGasActualDemandRecord.__table__.create(bind=connection)
            ForecastObservationRecord.__table__.create(bind=connection)
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        session = Session(bind=connection, expire_on_commit=False)
        yield session
    finally:
        try:
            if session is not None:
                session.close()
            if connection is not None:
                connection.close()
            if schema_created:
                with engine.begin() as cleanup:
                    cleanup.execute(text("SET LOCAL statement_timeout = '20s'"))
                    cleanup.execute(text("SET LOCAL lock_timeout = '5s'"))
                    cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            engine.dispose()


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_committed_model_predicts_future_forecast_without_reading_target_demand():
    days = tuple(START + timedelta(days=index) for index in range(21))
    policy = _feature_policy()
    cutoff = _day_start(days[14])
    validation = _day_end(days[-1]) + timedelta(hours=1)
    targets = [
        _target_row(
            f"actual-{day.isoformat()}",
            day,
            _target_value(day),
            available_at=_day_end(day) + timedelta(hours=1),
        )
        for day in days
    ]
    training_forecasts = [
        row
        for day in days
        for row in _eligible_forecast(day, label=f"train-{day.isoformat()}")
    ]

    with _owned_session() as session:
        session.add_all(targets)
        session.add_all(training_forecasts)
        session.commit()
        assert _count(session, NationalGasActualDemandRecord) == len(targets)
        assert _count(session, ForecastObservationRecord) == len(training_forecasts)

        training = run_weather_demand_runtime(
            session,
            _training_request(policy, days, cutoff=cutoff, validation=validation),
        )
        assert training.status is WeatherDemandRuntimeStatus.READY
        assert training.model_result is not None
        model = training.model_result
        assert model.selected_model.kind is ModelKind.WEATHER_CALENDAR_RIDGE
        assert model.selected_model.use_status is (
            ModelUseStatus.UNVALIDATED_OOS_RESEARCH_OUTPUT
        )
        assert model.validation_as_of == validation
        assert model.production_promotion is PromotionStatus.NOT_PROMOTED

        # The training rows are already committed.  Future forecast rows are
        # explicit receipt evidence; the later run is ineligible at this origin.
        future_day = days[-1] + timedelta(days=2)
        future_start = _day_start(future_day)
        origin = future_start - timedelta(hours=1)
        assert origin >= model.validation_as_of
        eligible = _forecast_run(
            future_day,
            label="future-eligible",
            issued=origin - timedelta(hours=12),
            available=origin - timedelta(hours=1),
        )
        late = _forecast_run(
            future_day,
            label="future-late",
            issued=origin + timedelta(hours=1),
            available=origin + timedelta(hours=2),
        )
        session.add_all([*eligible, *late])
        session.commit()

        before = _count(session, ForecastObservationRecord)
        session.execute(text("SELECT 1"))
        caller_transaction = session.get_transaction()
        assert caller_transaction is not None
        pending = _forecast_run(
            future_day,
            label="future-pending",
            issued=origin - timedelta(hours=9),
            available=origin - timedelta(hours=3),
        )[0]
        session.add(pending)
        flush_events: list[str] = []

        def _on_before_flush(*_args: object, **_kwargs: object) -> None:
            flush_events.append("before_flush")

        event.listen(session, "before_flush", _on_before_flush)
        try:
            config = _configs(policy, (future_day,))[0]
            assert config.prediction_origin == origin
            request = WeatherDemandPredictionRequest(
                model_result=model,
                gas_day=future_day,
                prediction_origin=origin,
                degree_day_policy=_degree_policy(policy),
                bridge_config=config,
                point_bindings=(_binding(),),
                regional_weighting_evidence_ref=WEIGHT_EVIDENCE,
            )
            outcome = run_weather_demand_prediction_runtime(session, request)
        finally:
            event.remove(session, "before_flush", _on_before_flush)

        assert outcome.status is WeatherDemandPredictionStatus.READY
        assert outcome.weather_consumed
        assert outcome.baseline_reference is False
        assert outcome.evidence.consumption_basis is (
            PredictionConsumptionBasis.WEATHER_FORECAST_VINTAGE
        )
        assert outcome.prediction is not None
        assert outcome.prediction.model_kind is ModelKind.WEATHER_CALENDAR_RIDGE
        assert outcome.prediction.model_hash == model.selected_model.model_hash
        assert outcome.prediction.selection_hash == model.selection_hash
        assert outcome.prediction.forecast_vintage is not None
        assert outcome.prediction.value >= 0.0
        assert outcome.native_unit == "MSCM"
        assert outcome.request_hash == request.request_hash
        assert outcome.research_only
        assert outcome.production_promotion is PromotionStatus.NOT_PROMOTED
        assert not outcome.prospective_accuracy_claim
        assert not outcome.gb_representative_claim
        assert outcome.evidence.regional_weighting_evidence_ref == WEIGHT_EVIDENCE
        assert outcome.evidence.regional_weighting_evidence_basis == (
            "CALLER_DECLARED_PROVENANCE_NOT_REVIEWED"
        )
        assert outcome.evidence.forecast_evidence_basis.value == (
            "GENUINE_RECEIPT_AVAILABILITY"
        )

        # The SQL prefilter admits only the eligible receipt/issue vintage, while
        # the unflushed caller row remains pending and is never read.
        assert outcome.forecast_raw_count == len(eligible)
        assert set(outcome.forecast_observation_ids) == {
            row.forecast_observation_id for row in eligible
        }
        assert not (
            {row.forecast_observation_id for row in late}
            & set(outcome.forecast_observation_ids)
        )
        assert pending.forecast_observation_id not in outcome.forecast_observation_ids
        assert outcome.selected_vintage is not None
        assert outcome.selected_vintage.issued_at == eligible[0].forecast_issued_at
        assert outcome.prediction.forecast_vintage == outcome.selected_vintage

        assert flush_events == []
        pending_state = inspect(pending)
        assert pending_state.pending is True
        assert pending_state.persistent is False
        assert pending in session.new
        assert session.get_transaction() is caller_transaction
        assert session.in_transaction()
        assert session.is_active
        with session.no_autoflush:
            stored_ids = set(
                session.scalars(select(ForecastObservationRecord.forecast_observation_id))
            )
            after = _count(session, ForecastObservationRecord)
        assert after == before
        assert pending.forecast_observation_id not in stored_ids
        assert not session.dirty and not session.deleted
