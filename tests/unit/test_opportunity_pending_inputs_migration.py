"""Migration 0071 on SQLite: the pending evaluation inputs table, both ways, matching the model."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import OpportunityPendingInputRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0071", VERSIONS / "0071_opportunity_pending_inputs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0070_freight_route"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        columns = {c["name"] for c in inspect(connection).get_columns("opportunity_pending_inputs")}
        assert columns == set(OpportunityPendingInputRecord.__table__.columns.keys())
        module.downgrade()
        assert inspect(connection).get_table_names() == []
