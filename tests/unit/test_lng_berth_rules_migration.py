"""Migration 0092 on SQLite: the terminal berth rules table and the quote columns on
``lng_berth_calls`` match the models, up and down, and 0092 only expands."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
ADDED = {"counterparty", "quote_amount", "quote_currency", "quote_reference"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"tests.migration_{name[:4]}", VERSIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_up_down_and_model_match():
    from eurogas_nexus.db.models import LngBerthCallRecord, LngTerminalBerthRuleRecord

    lng3 = _load("0086_lng_disruption.py")
    lng4 = _load("0087_lng4_options_demurrage_outages.py")
    rules = _load("0092_lng_berth_rules.py")
    assert rules.revision == "0092_lng_berth_rules"
    assert rules.down_revision == "0091_hub_one_identity"
    assert len(rules.revision) <= 32  # alembic_version.version_num is VARCHAR(32)
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection=connection))
        lng3.op = lng4.op = rules.op = operations
        lng3.upgrade()
        lng4.upgrade()  # creates lng_berth_calls
        rules.upgrade()
        inspector = inspect(connection)
        for model in (LngBerthCallRecord, LngTerminalBerthRuleRecord):
            columns = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            assert columns == set(model.__table__.columns.keys()), model.__tablename__
        rules.downgrade()
        inspector = inspect(connection)
        assert "lng_terminal_berth_rules" not in inspector.get_table_names()
        left = {c["name"] for c in inspector.get_columns("lng_berth_calls")}
        assert not ADDED & left
        assert left == set(LngBerthCallRecord.__table__.columns.keys()) - ADDED


def test_0092_only_expands():
    """Every column 0092 adds to an existing table is nullable, and it drops or alters nothing
    on the way up."""

    source = (VERSIONS / "0092_lng_berth_rules.py").read_text(encoding="utf-8")
    upgrade = source[source.index("def upgrade") : source.index("def downgrade")]
    assert "drop_" not in upgrade and "alter_column" not in upgrade
    assert "nullable=True" in upgrade
    rules = _load("0092_lng_berth_rules.py")
    assert {(table, name) for table, name, _kind in rules._COLUMNS} == {
        ("lng_berth_calls", name) for name in ADDED
    }
