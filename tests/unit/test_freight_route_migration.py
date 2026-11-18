"""Migration 0070 on SQLite: the freight route table, both ways, matching the model."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import FreightRouteRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0070", VERSIONS / "0070_freight_route.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0069_lng_terminal_tariff"
    assert DB_SCHEMA_REVISION == "0070_freight_route"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        columns = {c["name"] for c in inspect(connection).get_columns("freight_route")}
        assert columns == set(FreightRouteRecord.__table__.columns.keys())
        module.downgrade()
        assert inspect(connection).get_table_names() == []
