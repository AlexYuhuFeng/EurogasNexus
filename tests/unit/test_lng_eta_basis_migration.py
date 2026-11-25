"""Migration 0080 on SQLite: the ETA basis columns match the model, up and down."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
ADDED = {"eta_basis", "eta_confidence", "eta_source", "eta_recorded_at_utc"}


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import LngCargoRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0080", VERSIONS / "0080_lng_eta_basis.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0079_licensed_data_use"
    assert DB_SCHEMA_REVISION == "0083_tar1_tariff_book"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    before = sa.MetaData()
    sa.Table(
        "lng_cargoes",
        before,
        *[
            column._copy()
            for column in LngCargoRecord.__table__.columns
            if column.name not in ADDED
        ],
    )
    with engine.begin() as connection:
        before.create_all(connection)
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        columns = {c["name"] for c in inspect(connection).get_columns("lng_cargoes")}
        assert columns == set(LngCargoRecord.__table__.columns.keys())
        module.downgrade()
        columns = {c["name"] for c in inspect(connection).get_columns("lng_cargoes")}
        assert columns.isdisjoint(ADDED) and "eta_utc" in columns
