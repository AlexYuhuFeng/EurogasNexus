"""Migration 0077 on SQLite: the market event outbox tables match the models, up and down."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import MarketEventDeliveryRecord, MarketEventRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0077", VERSIONS / "0077_market_event_outbox.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0076_gas_day_nominations"
    assert DB_SCHEMA_REVISION == "0079_licensed_data_use"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        for model in (MarketEventRecord, MarketEventDeliveryRecord):
            columns = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            assert columns == set(model.__table__.columns.keys())
            indexes = {i["name"] for i in inspector.get_indexes(model.__tablename__)}
            assert {i.name for i in model.__table__.indexes} <= indexes
        uniques = {u["name"] for u in inspector.get_unique_constraints("market_events")}
        assert "uq_market_events_key_revision" in uniques
        module.downgrade()
        assert inspect(connection).get_table_names() == []
