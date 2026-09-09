"""PostgreSQL-only isolated-schema checks for the ordering-index migration."""

from __future__ import annotations

import importlib.util
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import MarketObservationRecord
from eurogas_nexus.db.repositories.market_intelligence import (
    list_market_observations_with_source_coverage,
)

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL"),
    reason="RUNTIME_STORE_DATABASE_URL not configured; use the PostgreSQL test DB",
)


def _migration_module():
    path = ROOT / "alembic" / "versions" / "0033_market_obs_order_indexes.py"
    spec = importlib.util.spec_from_file_location("tests.market_observation_indexes_postgres", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_table(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE market_observations (
                observation_id VARCHAR(64) PRIMARY KEY,
                market_venue VARCHAR(32) NOT NULL,
                product VARCHAR(32) NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                unit VARCHAR(16) NOT NULL,
                currency VARCHAR(8) NOT NULL,
                period_start_utc TIMESTAMPTZ NOT NULL,
                period_end_utc TIMESTAMPTZ NOT NULL,
                observed_at_utc TIMESTAMPTZ NOT NULL,
                source_system VARCHAR(64) NOT NULL,
                source_reference VARCHAR(128) NOT NULL,
                source_record_id VARCHAR(128),
                freshness VARCHAR(16) NOT NULL,
                quality_score DOUBLE PRECISION NOT NULL,
                research_only BOOLEAN NOT NULL,
                metadata_json JSONB
            )
            """
        )
    )


def _apply_migration(connection, function_name: str) -> None:
    module = _migration_module()
    module.op = Operations(MigrationContext.configure(connection=connection))
    getattr(module, function_name)()


def test_market_observation_index_upgrade_downgrade_and_rowset_parity() -> None:
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    schema = f"idx_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            assert connection.scalar(text("SELECT current_schema()")) == schema
            _create_table(connection)
            assert inspect(connection).get_table_names(schema=schema) == [
                "market_observations"
            ]

            observed = datetime(2026, 9, 9, 12, tzinfo=UTC)
            with Session(bind=connection) as session:
                observations = [
                    (
                        f"idx-ice-{index}",
                        "ICE",
                        "EEX",
                        "TTF Day-Ahead",
                        observed - timedelta(minutes=index),
                    )
                    for index in range(8)
                ]
                observations.append(
                    (
                        "idx-icis-low",
                        "ICIS",
                        "EEX",
                        "TTF Day-Ahead",
                        observed - timedelta(hours=1),
                    )
                )
                for observation_id, source, venue, product, observed_at in observations:
                    session.add(
                        MarketObservationRecord(
                            observation_id=observation_id,
                            market_venue=venue,
                            product=product,
                            price=30.0,
                            unit="EUR/MWh",
                            currency="EUR",
                            period_start_utc=observed,
                            period_end_utc=observed + timedelta(hours=24),
                            observed_at_utc=observed_at,
                            source_system=source,
                            source_reference=f"test:{source}",
                            freshness="fresh",
                            quality_score=1.0,
                            research_only=True,
                            metadata_json={"hub": venue},
                        )
                    )
                session.flush()
                before = [
                    row.observation_id
                    for row in list_market_observations_with_source_coverage(
                        session, limit=4, per_source_limit=1
                    )
                ]
            assert before == [
                "idx-ice-0",
                "idx-ice-1",
                "idx-ice-2",
                "idx-icis-low",
            ]
            assert "idx-icis-low" in before

            _apply_migration(connection, "upgrade")
            indexes = {
                row["name"]
                for row in inspect(connection).get_indexes("market_observations", schema=schema)
            }
            assert "ix_market_observations_observed_venue_product" in indexes
            index_schema = connection.scalar(
                text(
                    """
                    SELECT namespace.nspname
                    FROM pg_class AS relation
                    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                    WHERE relation.relname = :index_name
                      AND namespace.nspname = :schema_name
                    """
                ),
                {
                    "index_name": "ix_market_observations_observed_venue_product",
                    "schema_name": schema,
                },
            )
            assert index_schema == schema

            with Session(bind=connection) as session:
                after = [
                    row.observation_id
                    for row in list_market_observations_with_source_coverage(
                        session, limit=4, per_source_limit=1
                    )
                ]
            assert after == before

            _apply_migration(connection, "downgrade")
            assert "ix_market_observations_observed_venue_product" not in {
                row["name"]
                for row in inspect(connection).get_indexes("market_observations", schema=schema)
            }
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
