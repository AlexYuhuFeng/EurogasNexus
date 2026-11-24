"""Migration 0065 on SQLite: the local-credential table, both ways, matching the model."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _module():
    spec = importlib.util.spec_from_file_location(
        "tests.migration_0065", VERSIONS / "0065_local_accounts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _principals(connection) -> None:
    connection.execute(
        text("CREATE TABLE identity_principals (principal_id VARCHAR(80) PRIMARY KEY)")
    )
    connection.execute(text("INSERT INTO identity_principals VALUES ('p1')"))


def test_chain_and_head():
    module = _module()
    assert module.revision == "0065_local_accounts"
    assert module.down_revision == "0064_market_reports"
    assert DB_SCHEMA_REVISION == "0079_licensed_data_use"


def test_upgrade_creates_the_table_and_downgrade_removes_only_it():
    module = _module()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        _principals(connection)
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        assert "identity_local_credentials" in inspect(connection).get_table_names()
        module.downgrade()
        assert inspect(connection).get_table_names() == ["identity_principals"]
        assert connection.execute(text("SELECT count(*) FROM identity_principals")).scalar() == 1


def test_the_model_matches_the_migration_and_stores_nothing_reversible():
    from eurogas_nexus.db.models import IdentityLocalCredentialRecord

    module = _module()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        _principals(connection)
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        migrated = {c["name"] for c in inspect(connection).get_columns(
            "identity_local_credentials")}
    assert migrated == set(IdentityLocalCredentialRecord.__table__.columns.keys())
    # Only a derivation, its salt and parameters, and a token digest: no "password" column.
    assert not {name for name in migrated if name in {"password", "plaintext", "secret"}}
