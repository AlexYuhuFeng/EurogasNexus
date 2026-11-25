"""Migrations 0077 and 0082 on SQLite: the market event outbox tables match the models, up
and down (0082 adds the change feed's ``writer_txid`` and its index, and the ERP reference
table ``erp_references``, DATA-1)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"tests.migration_{name[:4]}", VERSIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import (
        ErpReferenceRecord,
        MarketEventDeliveryRecord,
        MarketEventRecord,
    )

    module = _load("0077_market_event_outbox.py")
    feed = _load("0082_data1_integration.py")
    assert module.down_revision == "0076_gas_day_nominations"
    assert DB_SCHEMA_REVISION == "0087_lng4_options_demurrage_outages"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        feed.op = module.op
        module.upgrade()
        columns = {c["name"] for c in inspect(connection).get_columns("market_events")}
        assert "writer_txid" not in columns
        feed.upgrade()
        inspector = inspect(connection)
        for model in (MarketEventRecord, MarketEventDeliveryRecord, ErpReferenceRecord):
            columns = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            assert columns == set(model.__table__.columns.keys())
            indexes = {i["name"] for i in inspector.get_indexes(model.__tablename__)}
            assert {i.name for i in model.__table__.indexes} <= indexes
        uniques = {u["name"] for u in inspector.get_unique_constraints("market_events")}
        assert "uq_market_events_key_revision" in uniques
        feed.downgrade()
        columns = {c["name"] for c in inspect(connection).get_columns("market_events")}
        assert "writer_txid" not in columns and "seq" in columns
        assert "erp_references" not in inspect(connection).get_table_names()
        module.downgrade()
        assert inspect(connection).get_table_names() == []
