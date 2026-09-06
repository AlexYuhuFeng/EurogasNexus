"""Temporally safe backtest engine domain package.

Import contracts/engine/temporal modules explicitly. This package init stays
empty so importing public API contracts never loads SQLAlchemy or the DB layer.
"""

from __future__ import annotations

from typing import Any

__all__: list[str] = []


def __getattr__(name: str) -> Any:
    if name in {
        "BACKTEST_ENGINE_VERSION",
        "BacktestEconomicAssumptions",
        "BacktestEvidencePool",
        "BacktestPeriod",
        "BacktestResult",
        "BacktestRunDefinition",
    }:
        from eurogas_nexus.domain.backtest import contracts

        return getattr(contracts, name)
    if name in {"build_backtest_manifest", "generate_decision_times", "run_backtest"}:
        from eurogas_nexus.domain.backtest import engine

        return getattr(engine, name)
    raise AttributeError(name)
