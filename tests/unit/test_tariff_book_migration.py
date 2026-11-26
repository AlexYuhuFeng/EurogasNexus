"""Migration 0083 on SQLite: the tariff book tables match the models, up and down (TAR-1)."""

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


def test_0083_is_the_head_and_expands_only():
    from eurogas_nexus.db.models import CapacityNoticeRecord, TariffVersionRecord

    module = _load("0083_tar1_tariff_book.py")
    assert module.revision == "0083_tar1_tariff_book"
    assert module.down_revision == "0082_data1_integration"
    assert DB_SCHEMA_REVISION == "0090_lng_berth_rules"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == {"tariff_versions", "capacity_notices"}
        for model in (TariffVersionRecord, CapacityNoticeRecord):
            columns = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            # TAR-2's 0088 adds tariff_versions.tariff_year.
            assert columns == set(model.__table__.columns.keys()) - {"tariff_year"}
            indexes = {i["name"] for i in inspector.get_indexes(model.__tablename__)}
            assert {i.name for i in model.__table__.indexes} <= indexes
        uniques = {u["name"] for u in inspector.get_unique_constraints("tariff_versions")}
        assert "uq_tariff_versions_key_version" in uniques
        module.downgrade()
        assert inspect(connection).get_table_names() == []
