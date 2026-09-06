"""Shadow scheduler baseline benchmark (SQLite fixture, same code path)."""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.shadow_runtime import (
    create_shadow_monitor,
    run_due_shadow_evaluations,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories import shadow as shadow_repository
from eurogas_nexus.db.repositories import strategy_registry
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyVersionDefinition,
)


def _build_fixture(engine, monitor_count: int) -> None:
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        strategy_registry.create_strategy(
            session,
            strategy_id="benchmark-shadow",
            name="Shadow benchmark",
            description="",
            created_by="operator",
            now_utc=now,
        )
        definition = StrategyVersionDefinition(
            components=[
                StrategyComponentSpec(
                    component_id="c1",
                    component_type="OCM_VS_DAY_AHEAD",
                    hubs=["NBP"],
                    extension_json={
                        "weight": 1.0,
                        "day_ahead_price_names": ["SAP"],
                        "intraday_price_names": ["ICE_OCM"],
                        "target_bar_minutes": 5,
                    },
                )
            ]
        )
        version = strategy_registry.create_strategy_version(
            session,
            strategy_id="benchmark-shadow",
            definition=definition,
            hypothesis="",
            created_by="operator",
            now_utc=now,
            definition_overrides={
                "strategy_name": "Shadow benchmark",
                "run_mode": "BACKTEST",
                "resource_contexts": [
                    {
                        "resource_id": "res-1",
                        "available_quantity_mwh_per_day": 100.0,
                        "all_in_cost_gbp_mwh": 20.0,
                    }
                ],
                "price_observations": [],
                "existing_shadow_pnl_gbp": 0.0,
                "economic_assumptions": {
                    "fill_price_policy": "NEXT_ELIGIBLE",
                    "missing_data_policy": "FAIL",
                    "cost_components": [],
                },
            },
        )
        strategy_registry.freeze_strategy_version(
            session,
            strategy_version_id=version.strategy_version_id,
            frozen_by="operator",
            now_utc=now,
        )
        for _index in range(monitor_count):
            payload = create_shadow_monitor(
                session,
                strategy_version_id=version.strategy_version_id,
                baseline_run_id=None,
                schedule_json={
                    "type": "INTERVAL",
                    "interval_seconds": 3600,
                    "missed_policy": "SKIP",
                },
                created_by="operator",
                now_utc=now,
                activate=True,
            )
            monitor = shadow_repository.get_monitor(
                session, payload["shadow_monitor_id"]
            )
            monitor.next_evaluation_at_utc = now - timedelta(seconds=1)
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monitors", type=int, default=10)
    args = parser.parse_args()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    _build_fixture(engine, args.monitors)
    now = datetime(2026, 7, 1, 10, 1, tzinfo=UTC)
    started = time.perf_counter()
    with Session(engine) as session:
        summary = run_due_shadow_evaluations(
            session, now_utc=now, limit=args.monitors
        )
        session.commit()
    elapsed = time.perf_counter() - started
    print(
        {
            "monitors": args.monitors,
            "wall_clock_seconds": round(elapsed, 4),
            "due_count": summary["due_count"],
            "claimed_count": summary["claimed_count"],
            "completed_count": summary["completed_count"],
            "blocked_count": summary["blocked_count"],
            "failed_count": summary["failed_count"],
            "duplicate_claim_count": summary["duplicate_claim_count"],
        }
    )


if __name__ == "__main__":
    main()
