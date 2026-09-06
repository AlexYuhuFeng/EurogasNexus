"""CR-04 backtest engine baseline benchmark (in-memory representative data).

This script measures the pure engine loop for 30-day and 365-day daily
evaluations. It intentionally does not set a performance target before the
baseline is measured.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from eurogas_nexus.domain.backtest.contracts import (
    BacktestDecisionSchedule,
    BacktestEconomicAssumptions,
    BacktestEvidencePool,
    BacktestObservation,
    BacktestPeriod,
    BacktestResourceEvidence,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.backtest.engine import run_backtest
from eurogas_nexus.domain.ontology.vocabulary import TemporalIntegrityStatus


def _version(days: int) -> SimpleNamespace:
    return SimpleNamespace(
        strategy_version_id="benchmark-version",
        strategy_id="benchmark-strategy",
        version_number=1,
        content_hash="sha256:benchmark",
        definition_json={
            "strategy_name": "Benchmark NBP OCM vs DA",
            "components": [
                {
                    "component_id": "c1",
                    "component_type": "OCM_VS_DAY_AHEAD",
                    "hubs": ["NBP"],
                    "extension_json": {
                        "weight": 1.0,
                        "day_ahead_price_names": ["SAP"],
                        "intraday_price_names": ["ICE_OCM"],
                        "positive_spread_threshold_gbp_mwh": 0.0,
                        "negative_spread_threshold_gbp_mwh": 0.0,
                        "target_bar_minutes": 5,
                        "time_window_start": "05:00",
                        "time_window_end": "05:30",
                    },
                }
            ],
            "risk_controls": {
                "max_ocm_allocation_pct": 80.0,
                "min_day_ahead_allocation_pct": 10.0,
                "require_tso_access": False,
            },
            "resource_contexts": [
                {
                    "resource_id": "res-1",
                    "available_quantity_mwh_per_day": 100.0,
                    "all_in_cost_gbp_mwh": 20.0,
                }
            ],
            "run_mode": "BACKTEST",
            "parameter_values": {},
        },
    )


def _pool(days: int) -> BacktestEvidencePool:
    rows = []
    for day in range(days):
        observed = datetime(2026, 1, 1, 4, 30, tzinfo=UTC) + timedelta(days=day)
        rows.extend(
            [
                BacktestObservation(
                    observation_id=f"ice-{day}",
                    source_system="ICE_OCM",
                    venue="ICE OCM",
                    hub="NBP",
                    product="NBP within-day",
                    tenor="within-day",
                    price_name="ICE_OCM",
                    price=30.0 + (day % 20) * 0.1,
                    currency="GBP",
                    unit="MWh",
                    observed_at_utc=observed,
                    received_at_utc=observed,
                    delivery_start_utc=observed,
                    delivery_end_utc=observed + timedelta(hours=24),
                    bar_minutes=5,
                    price_type="mid",
                    source_reference=f"ice:{day}",
                    temporal_integrity=TemporalIntegrityStatus.VERIFIED,
                ),
                BacktestObservation(
                    observation_id=f"sap-{day}",
                    source_system="SAP",
                    venue="SAP",
                    hub="NBP",
                    product="NBP day-ahead",
                    tenor="day-ahead",
                    price_name="SAP",
                    price=25.0 + (day % 20) * 0.08,
                    currency="GBP",
                    unit="MWh",
                    observed_at_utc=observed,
                    received_at_utc=observed,
                    delivery_start_utc=observed + timedelta(hours=24),
                    delivery_end_utc=observed + timedelta(hours=48),
                    price_type="assessment",
                    source_reference=f"sap:{day}",
                    temporal_integrity=TemporalIntegrityStatus.VERIFIED,
                ),
            ]
        )
    return BacktestEvidencePool(
        observations=rows,
        resources=[
            BacktestResourceEvidence(
                resource_id="res-1",
                available_quantity_mwh_per_day=100.0,
                all_in_cost_gbp_mwh=20.0,
            )
        ],
    )


def _run(days: int) -> dict:
    definition = BacktestRunDefinition(
        strategy_version_id="benchmark-version",
        period=BacktestPeriod(
            start_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            end_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
            + timedelta(days=days),
        ),
        schedule=BacktestDecisionSchedule(decision_time_utc="05:00"),
        economic_assumptions=BacktestEconomicAssumptions(),
    )
    started = time.perf_counter()
    result = run_backtest(
        version=_version(days),
        pool=_pool(days),
        definition=definition,
        run_id=f"benchmark-{days}d",
        requested_by="operator",
    )
    elapsed = time.perf_counter() - started
    return {
        "days": days,
        "wall_clock_seconds": round(elapsed, 4),
        "evaluation_events": len(result.events),
        "candidate_decisions": result.metrics.candidate_decision_count,
        "blocked_decisions": result.metrics.blocked_decision_count,
        "status": result.status,
    }


def main() -> None:
    print("CR-04 backtest engine baseline (in-memory domain pool)")
    print("environment: CPython, no database queries, Windows 11 local dev")
    for days in (30, 365):
        print(_run(days))


if __name__ == "__main__":
    main()
