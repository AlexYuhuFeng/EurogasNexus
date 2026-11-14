"""Migration 0063 on SQLite: power and re-split records allowed, and a downgrade keeps them safe."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
TABLES = (
    "flow_observations",
    "capacity_observations",
    "storage_observations",
    "lng_observations",
    "power_observations",
)


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"tests.migration_{name[:4]}", VERSIONS / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _revision(connection, table: str, reason: str, revision_id: str = "rev-1") -> None:
    connection.execute(
        text(
            "INSERT INTO observation_revisions VALUES (:id, :table, 'kept', 'ENTSOE', :reason, "
            "'[]', '{}', '2026-11-13 11:15:00', '2026-11-14 01:05:00', 'a', 'b', "
            "'2026-11-14 01:05:00')"
        ),
        {"id": revision_id, "table": table, "reason": reason},
    )


@pytest.fixture
def connection():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as active:
        for table in TABLES:
            active.execute(
                text(f"CREATE TABLE {table} (observation_id VARCHAR(64) PRIMARY KEY)")
            )
            active.execute(text(f"INSERT INTO {table} VALUES ('kept')"))
        modules = [_module("0062_observation_revisions.py")]
        modules.append(_module("0063_resplit_power_revisions.py"))
        for module in modules:
            module.op = Operations(MigrationContext.configure(connection=active))
        modules[0].upgrade()
        yield active, modules[1]
    engine.dispose()


def test_chain_and_head() -> None:
    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    module = _module("0063_resplit_power_revisions.py")
    assert module.down_revision == "0062_observation_revisions"
    assert DB_SCHEMA_REVISION == module.revision == "0063_resplit_power_revisions"


def test_upgrade_allows_power_and_resplit_and_downgrade_restores_the_checks(connection):
    active, migration = connection
    with pytest.raises(IntegrityError), active.begin_nested():
        _revision(active, "power_observations", "value_changed")
    migration.upgrade()
    columns = inspect(active).get_columns("power_observations")
    column = next(c for c in columns if c["name"] == "revised_at_utc")
    assert column["nullable"] is True
    _revision(active, "power_observations", "value_changed", "rev-power")
    _revision(active, "capacity_observations", "range_resplit", "rev-resplit")
    with pytest.raises(IntegrityError), active.begin_nested():
        _revision(active, "market_observations", "value_changed", "rev-other")

    with pytest.raises(RuntimeError, match="power or re-split records"):
        migration.downgrade()
    active.execute(text("DELETE FROM observation_revisions"))
    migration.downgrade()
    assert "revised_at_utc" not in {
        c["name"] for c in inspect(active).get_columns("power_observations")
    }
    assert active.execute(text("SELECT COUNT(*) FROM power_observations")).scalar() == 1
    with pytest.raises(IntegrityError), active.begin_nested():
        _revision(active, "capacity_observations", "range_resplit")
