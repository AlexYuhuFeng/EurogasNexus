"""Contracts for the market observation ordering-index milestone."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from eurogas_nexus.db.models import MarketObservationRecord

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_INDEXES = {
    "ix_market_observations_observed_venue_product":
        "CREATE INDEX ix_market_observations_observed_venue_product ON market_observations "
        "(observed_at_utc DESC, market_venue, product)",
}


def _migration_module():
    path = ROOT / "alembic" / "versions" / "0033_market_obs_order_indexes.py"
    spec = importlib.util.spec_from_file_location("tests.market_observation_indexes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_from_actual_head_and_declares_only_ordering_indexes() -> None:
    migration = _migration_module()

    assert migration.revision == "0033_market_obs_order_indexes"
    assert len(migration.revision) <= 32
    assert migration.down_revision == "0032_agent_capability_layer"
    assert set(EXPECTED_INDEXES) == {"ix_market_observations_observed_venue_product"}


def test_orm_metadata_matches_postgresql_index_ordering() -> None:
    indexes = {
        index.name: index
        for index in MarketObservationRecord.__table__.indexes
        if index.name in EXPECTED_INDEXES
    }

    assert set(indexes) == set(EXPECTED_INDEXES)
    for name, expected_sql in EXPECTED_INDEXES.items():
        sql = str(CreateIndex(indexes[name]).compile(dialect=postgresql.dialect()))
        assert sql == expected_sql
