"""Migration 0094 on SQLite: the option settlements table matches its model, up and down."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import OptionSettlementRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0094", VERSIONS / "0094_option_settlements.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0094_option_settlements"
    assert module.down_revision == "0093_timescale_optional"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        columns = {c["name"] for c in inspector.get_columns("option_settlements")}
        assert columns == set(OptionSettlementRecord.__table__.columns.keys())
        indexes = {i["name"] for i in inspector.get_indexes("option_settlements")}
        assert "ix_option_settlements_hub_day" in indexes
        module.downgrade()
        assert "option_settlements" not in inspect(connection).get_table_names()
