"""Historical-boundary guard for professional backtest runs.

BACKTEST_ENGINE_SPEC section 1 answers what a frozen strategy would have done over
a *historical* period. The pure domain engine has no wall clock, so the application
service is the boundary that knows a window has not happened yet: it must refuse
``period.end_utc > requested_at`` before writing an evidence snapshot or a run row.

These tests pin that boundary, including the injected request clock and the
allowed equality case, and prove the refusal leaves no run/snapshot artefact.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.backtest_service import execute_backtest_run
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import StrategyDataSnapshotRecord, StrategyRunRecord
from eurogas_nexus.db.repositories import strategy_registry as repo
from eurogas_nexus.domain.backtest.contracts import (
    BacktestEconomicAssumptions,
    BacktestPeriod,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.ontology.vocabulary import MissingDataPolicy
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyEvidenceTarget,
    StrategyVersionDefinition,
)

REQUESTED_AT = datetime(2026, 10, 7, 16, 0, tzinfo=UTC)


def _target(leg_id: str, name: str, tenor: str) -> StrategyEvidenceTarget:
    """A rolling current-gas-day declaration; it never expires."""

    return StrategyEvidenceTarget.model_validate(
        {
            "leg_id": leg_id,
            "price_names": [name],
            "role": "DELIVERY_PRICE",
            "hub": "NBP",
            "tenor": tenor,
            "price_basis": "MID",
            "target_basis": "GAS_DAY",
            "calendar_id": "EU-CAM-UTC-2025",
            "gas_day_offset": 0,
        }
    )


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _definition() -> StrategyVersionDefinition:
    return StrategyVersionDefinition.model_validate(
        {
            "components": [
                StrategyComponentSpec(
                    component_id="ocm-da",
                    component_type="OCM_VS_DAY_AHEAD",
                    hubs=["NBP"],
                    extension_json={
                        "weight": 1.0,
                        "day_ahead_price_names": ["SAP"],
                        "intraday_price_names": ["ICE_OCM"],
                        "positive_spread_threshold_gbp_mwh": 0.0,
                        "negative_spread_threshold_gbp_mwh": 0.0,
                        "target_bar_minutes": 5,
                    },
                    evidence_targets=[
                        _target("day_ahead", "SAP", "day-ahead"),
                        _target("intraday", "ICE_OCM", "within-day"),
                    ],
                )
            ]
        }
    )


def _frozen_version(session: Session):
    created = datetime(2026, 9, 5, tzinfo=UTC)
    repo.create_strategy(
        session,
        strategy_id="boundary-strategy",
        name="Boundary strategy",
        description="future-window guard",
        created_by="operator",
        now_utc=created,
    )
    version = repo.create_strategy_version(
        session,
        strategy_id="boundary-strategy",
        definition=_definition(),
        hypothesis="guard",
        created_by="operator",
        now_utc=created,
        definition_overrides={
            "strategy_name": "Boundary strategy",
            "run_mode": "BACKTEST",
            "resource_contexts": [
                {
                    "resource_id": "r1",
                    "resource_name": "Resource 1",
                    "available_quantity_mwh_per_day": 100.0,
                    "all_in_cost_gbp_mwh": 20.0,
                    "required_tso_access": [],
                }
            ],
            "price_observations": [],
            "existing_shadow_pnl_gbp": 0.0,
        },
    )
    frozen = repo.freeze_strategy_version(
        session,
        strategy_version_id=version.strategy_version_id,
        frozen_by="operator",
        now_utc=created,
    )
    session.flush()
    return frozen


def _run_definition(start: datetime, end: datetime) -> BacktestRunDefinition:
    return BacktestRunDefinition(
        strategy_version_id="unused",
        period=BacktestPeriod(start_utc=start, end_utc=end),
        economic_assumptions=BacktestEconomicAssumptions(
            missing_data_policy=MissingDataPolicy.FAIL,
        ),
    )


def test_future_period_end_is_refused_with_no_run_or_snapshot_write() -> None:
    with Session(_engine()) as session:
        version = _frozen_version(session)
        future_end = REQUESTED_AT + timedelta(days=3)

        with pytest.raises(ValueError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=_run_definition(REQUESTED_AT - timedelta(days=1), future_end),
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        message = str(refused.value)
        assert "after the request time" in message
        assert future_end.isoformat() in message
        # The refusal happens before any persistence the run would produce.
        assert session.query(StrategyRunRecord).count() == 0
        assert session.query(StrategyDataSnapshotRecord).count() == 0


def test_period_end_equal_to_the_request_instant_is_allowed() -> None:
    with Session(_engine()) as session:
        version = _frozen_version(session)

        run = execute_backtest_run(
            session,
            version=version,
            definition=_run_definition(REQUESTED_AT - timedelta(days=1), REQUESTED_AT),
            requested_by="operator",
            requested_at_utc=REQUESTED_AT,
        )

        assert run.evaluation_end_utc.replace(tzinfo=UTC) == REQUESTED_AT
        assert session.query(StrategyRunRecord).count() == 1
        assert session.query(StrategyDataSnapshotRecord).count() == 1


def test_period_ending_before_the_request_instant_is_allowed() -> None:
    with Session(_engine()) as session:
        version = _frozen_version(session)

        run = execute_backtest_run(
            session,
            version=version,
            definition=_run_definition(
                REQUESTED_AT - timedelta(days=3), REQUESTED_AT - timedelta(days=1)
            ),
            requested_by="operator",
            requested_at_utc=REQUESTED_AT,
        )

        assert run.evaluation_end_utc.replace(tzinfo=UTC) == REQUESTED_AT - timedelta(
            days=1
        )


def test_the_guard_reads_the_injected_request_clock_not_the_wall_clock() -> None:
    # A window that is future relative to the machine clock is still admissible
    # when the service is invoked with a request instant after it: the rule is
    # "was this historical when the request was made", and the clock is injected.
    injected = datetime(2030, 1, 1, tzinfo=UTC)
    with Session(_engine()) as session:
        version = _frozen_version(session)

        run = execute_backtest_run(
            session,
            version=version,
            definition=_run_definition(
                injected - timedelta(days=2), injected - timedelta(days=1)
            ),
            requested_by="operator",
            requested_at_utc=injected,
        )

        assert run.evaluation_end_utc.replace(tzinfo=UTC) == injected - timedelta(days=1)
