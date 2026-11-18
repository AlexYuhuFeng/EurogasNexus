"""Migration 0069 on SQLite: the register and the operator terms tables, both ways."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_chain_up_down_and_models_match():
    from eurogas_nexus.db.models import LngTerminalOperatorTermsRecord, LngTerminalTariffRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0069", VERSIONS / "0069_lng_terminal_tariff.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0068_installation_setup"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        found = inspect(connection)
        assert {c["name"] for c in found.get_columns("lng_terminal_tariff")} == set(
            LngTerminalTariffRecord.__table__.columns.keys()
        )
        assert {c["name"] for c in found.get_columns("lng_terminal_operator_terms")} == set(
            LngTerminalOperatorTermsRecord.__table__.columns.keys()
        )
        module.downgrade()
        assert inspect(connection).get_table_names() == []
