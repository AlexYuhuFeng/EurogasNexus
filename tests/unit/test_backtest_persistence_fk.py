"""Regression: backtest attribution rows must reference persisted events.

CR-13 UAT found a PostgreSQL FK violation where attribution rows were flushed
before decision events because the mapper graph has no relationship dependency.
SQLite normally hides this (FK enforcement is off); this test enables FK
enforcement and proves events are persisted before attribution.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from eurogas_nexus.application.backtest_service import execute_backtest_run
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    BacktestAttributionRecord,
    BacktestDecisionEventRecord,
)
from eurogas_nexus.db.repositories import strategy_registry as repo
from eurogas_nexus.domain.backtest.contracts import (
    BacktestDecisionSchedule,
    BacktestEconomicAssumptions,
    BacktestPeriod,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.ontology.vocabulary import MissingDataPolicy
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyVersionDefinition,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record) -> None:
        dbapi_connection.execute("pragma foreign_keys=ON")

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
                        "time_window_start": "05:00",
                        "time_window_end": "05:30",
                    },
                )
            ]
        }
    )


def test_blocked_backtest_persists_events_before_attribution() -> None:
    now = datetime(2026, 9, 5, tzinfo=UTC)
    with Session(_engine()) as session:
        repo.create_strategy(
            session,
            strategy_id="uat-strategy",
            name="UAT strategy",
            description="fk regression",
            created_by="operator",
            now_utc=now,
        )
        version = repo.create_strategy_version(
            session,
            strategy_id="uat-strategy",
            definition=_definition(),
            hypothesis="regression",
            created_by="operator",
            now_utc=now,
            definition_overrides={
                "strategy_name": "UAT strategy",
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
        version = repo.freeze_strategy_version(
            session,
            strategy_version_id=version.strategy_version_id,
            frozen_by="operator",
            now_utc=now,
        )
        session.flush()

        run = execute_backtest_run(
            session,
            version=version,
            definition=BacktestRunDefinition(
                strategy_id="uat-strategy",
                strategy_version_id=version.strategy_version_id,
                period=BacktestPeriod(
                    start_utc=now - timedelta(days=5),
                    end_utc=now,
                ),
                schedule=BacktestDecisionSchedule(
                    decision_time_utc="05:00",
                    gas_day_calendar="EU-CAM-UTC-2025",
                ),
                economic_assumptions=BacktestEconomicAssumptions(
                    missing_data_policy=MissingDataPolicy.FAIL,
                ),
            ),
            requested_by="operator",
            run_id="strategy-run-1234567890abcdef123456",
            requested_at_utc=now,
        )
        session.commit()

        assert run.status == "BLOCKED"
        assert session.query(BacktestDecisionEventRecord).count() == 5
        assert session.query(BacktestAttributionRecord).count() >= 5
