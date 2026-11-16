"""Migration 0064 on SQLite: the market-report record and licence redistribution, both ways."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _module():
    spec = importlib.util.spec_from_file_location("tests.migration_0064",
                                                  VERSIONS / "0064_market_reports.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_the_record_and_the_flag_and_downgrade_removes_only_them():
    module = _module()
    assert module.down_revision == "0063_resplit_power_revisions"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE market_data_licences (licence_id VARCHAR(64) "
                                "PRIMARY KEY, source_family VARCHAR(32))"))
        connection.execute(text("INSERT INTO market_data_licences VALUES ('l1', 'EEX')"))
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        names = inspect(connection).get_table_names()
        assert "market_reports" in names
        columns = {c["name"] for c in inspect(connection).get_columns("market_data_licences")}
        assert "redistribution_allowed" in columns
        # An existing licence reads as "not redistributable" (unknown is no).
        assert connection.execute(text("SELECT redistribution_allowed FROM market_data_licences"
                                       )).scalar() in (0, False)
        module.downgrade()
        assert "market_reports" not in inspect(connection).get_table_names()
        columns = {c["name"] for c in inspect(connection).get_columns("market_data_licences")}
        assert columns == {"licence_id", "source_family"}
        assert connection.execute(text("SELECT count(*) FROM market_data_licences")).scalar() == 1


def test_the_model_matches_the_migration_columns():
    from eurogas_nexus.db.models import MarketReportRecord

    module = _module()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE market_data_licences (licence_id VARCHAR(64) "
                                "PRIMARY KEY)"))
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        migrated = {c["name"] for c in inspect(connection).get_columns("market_reports")}
    assert migrated == set(MarketReportRecord.__table__.columns.keys())
