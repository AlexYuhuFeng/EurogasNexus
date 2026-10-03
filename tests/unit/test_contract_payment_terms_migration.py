"""Declared payment-terms carrier migration DDL round trip (SQLite, no PostgreSQL).

S2b adds the nullable ``upstream_resource_contracts.payment_terms_json`` column
through revision `0038_contract_payment_terms`. This applies the real
`upgrade()`/`downgrade()` against a throw-away SQLite database, so the
expand-only promise, the nullable carrier and the no-backfill rule are executed
rather than inspected: pre-existing rows keep ``NULL`` (no fabricated
declaration), no other column is altered, and the downgrade removes only the
carrier it added. The migration itself performs no validation and imports no
domain code; PostgreSQL applies the same DDL through the existing release
process, and no test here migrates a runtime store.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT / "alembic" / "versions" / "0038_contract_payment_terms.py"
)

_EXISTING_COLUMNS = {"contract_id", "contract_name"}


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "tests.contract_payment_terms_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply(connection, function_name: str) -> None:
    module = _migration_module()
    module.op = Operations(MigrationContext.configure(connection=connection))
    getattr(module, function_name)()


def test_the_migration_chains_to_the_revision_table_migration() -> None:
    module = _migration_module()

    assert module.revision == "0038_contract_payment_terms"
    assert module.down_revision == "0037_contract_revisions"


def test_upgrade_adds_only_the_nullable_carrier_and_downgrade_removes_it() -> None:
    """Expand-only: one nullable column added, nothing backfilled or rewritten."""

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            # A stand-in for the contract table an earlier revision created.
            connection.execute(
                text(
                    "CREATE TABLE upstream_resource_contracts"
                    " (contract_id VARCHAR(128) PRIMARY KEY,"
                    " contract_name VARCHAR(256) NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO upstream_resource_contracts (contract_id, contract_name)"
                    " VALUES ('legacy-contract-1', 'Legacy supply 2025')"
                )
            )
            tables_before = set(inspect(connection).get_table_names())

            _apply(connection, "upgrade")

            # Expand-only: no table is created, dropped or renamed.
            assert set(inspect(connection).get_table_names()) == tables_before
            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns(
                    "upstream_resource_contracts"
                )
            }
            assert set(columns) == _EXISTING_COLUMNS | {"payment_terms_json"}
            assert columns["payment_terms_json"]["nullable"] is True
            # No backfill and no fabricated declaration: the stored row keeps NULL.
            assert (
                connection.execute(
                    text(
                        "SELECT payment_terms_json FROM upstream_resource_contracts"
                        " WHERE contract_id = 'legacy-contract-1'"
                    )
                ).scalar_one()
                is None
            )
            # The column stores declaration text as-is (validation is the
            # application write path's job, never the migration's).
            connection.execute(
                text(
                    "UPDATE upstream_resource_contracts SET payment_terms_json = :text"
                    " WHERE contract_id = 'legacy-contract-1'"
                ),
                {"text": '{"items":[],"quantity_basis_reference":"invoiced"}'},
            )

            _apply(connection, "downgrade")

            columns = {
                column["name"]
                for column in inspect(connection).get_columns(
                    "upstream_resource_contracts"
                )
            }
            assert columns == _EXISTING_COLUMNS
            # The pre-existing row itself is untouched by the round trip.
            assert connection.execute(
                text(
                    "SELECT contract_name FROM upstream_resource_contracts"
                    " WHERE contract_id = 'legacy-contract-1'"
                )
            ).scalar_one() == "Legacy supply 2025"
    finally:
        engine.dispose()
