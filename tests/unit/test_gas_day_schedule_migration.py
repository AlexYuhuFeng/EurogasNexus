"""Migration 0074 on SQLite: the gas-day schedule and delegations, both ways, matching the model."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import GasDayDelegationRecord, GasDayScheduleLineRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0074", VERSIONS / "0074_gas_day_schedule.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0073_contract_kinds"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        for model in (GasDayScheduleLineRecord, GasDayDelegationRecord):
            columns = {c["name"] for c in inspect(connection).get_columns(model.__tablename__)}
            assert columns == set(model.__table__.columns.keys())
        module.downgrade()
        assert inspect(connection).get_table_names() == []
