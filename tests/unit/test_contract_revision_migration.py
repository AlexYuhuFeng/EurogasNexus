"""Contract-revision migration DDL round trip (SQLite, no PostgreSQL needed).

S1b adds revision storage through revision `0037_contract_revisions`. This
applies the real `upgrade()`/`downgrade()` against a throw-away SQLite
database, so the expand-only promise, the exact storage columns, the
per-contract revision-number uniqueness and the `ON DELETE RESTRICT` contract
FK are executed rather than inspected. It also asserts the storage has no
invented lifecycle or validity columns: no status, no current pointer and no
effective dates exist in this slice.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "0037_contract_revisions.py"

EXPECTED_REVISION_COLUMNS = {
    "contract_revision_id",
    "contract_id",
    "revision_number",
    "schema_version",
    "capture_origin",
    "snapshot_json",
    "display_metadata_json",
    "content_hash",
    "recorded_at_utc",
    "recorded_by",
}

_REVISION_INSERT = (
    "INSERT INTO upstream_contract_revisions (contract_revision_id, contract_id,"
    " revision_number, schema_version, capture_origin, snapshot_json,"
    " display_metadata_json, content_hash, recorded_at_utc, recorded_by) VALUES"
    " (:revision_id, :contract_id, :revision_number, 'upstream-contract-revision/v1',"
    " 'legacy_capture', '{}', '{\"contract_name\": \"TTF supply 2025\"}',"
    " 'sha256:x', '2026-10-01 09:00:00', 'trader-a')"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "tests.contract_revision_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply(connection, function_name: str) -> None:
    module = _migration_module()
    module.op = Operations(MigrationContext.configure(connection=connection))
    getattr(module, function_name)()


def test_upgrade_creates_only_the_revision_table_and_downgrade_removes_it() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            # A stand-in for the earlier revision's contract table this FK names.
            connection.execute(
                text(
                    "CREATE TABLE upstream_resource_contracts"
                    " (contract_id VARCHAR(128) PRIMARY KEY)"
                )
            )
            before = set(inspect(connection).get_table_names())

            _apply(connection, "upgrade")
            after = set(inspect(connection).get_table_names())
            # Expand-only: one new table, nothing existing touched.
            assert after - before == {"upstream_contract_revisions"}
            assert before <= after

            columns = {
                column["name"]
                for column in inspect(connection).get_columns("upstream_contract_revisions")
            }
            assert columns == EXPECTED_REVISION_COLUMNS

            assert {
                row["name"]
                for row in inspect(connection).get_indexes("upstream_contract_revisions")
            } == {"ix_upstream_contract_revisions_contract"}

            unique = {
                row["name"]: tuple(row["column_names"])
                for row in inspect(connection).get_unique_constraints(
                    "upstream_contract_revisions"
                )
            }
            assert unique == {
                "uq_upstream_contract_revision_number": ("contract_id", "revision_number")
            }

            foreign_keys = inspect(connection).get_foreign_keys(
                "upstream_contract_revisions"
            )
            assert len(foreign_keys) == 1
            assert foreign_keys[0]["referred_table"] == "upstream_resource_contracts"
            assert foreign_keys[0]["constrained_columns"] == ["contract_id"]
            assert foreign_keys[0]["options"].get("ondelete") == "RESTRICT"

            _apply(connection, "downgrade")
            assert set(inspect(connection).get_table_names()) == before
    finally:
        engine.dispose()


def test_revisions_require_a_contract_and_are_unique_per_contract_number() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            _apply(connection, "upgrade")
            connection.execute(
                text(
                    "CREATE TABLE upstream_resource_contracts"
                    " (contract_id VARCHAR(128) PRIMARY KEY)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO upstream_resource_contracts (contract_id) VALUES ('contract-1')"
                )
            )
            connection.execute(
                text(_REVISION_INSERT),
                {
                    "revision_id": "revision-1",
                    "contract_id": "contract-1",
                    "revision_number": 1,
                },
            )

            # A contract cannot have two captured revisions with one number.
            try:
                connection.execute(
                    text(_REVISION_INSERT),
                    {
                        "revision_id": "revision-2",
                        "contract_id": "contract-1",
                        "revision_number": 1,
                    },
                )
            except IntegrityError:
                pass
            else:  # pragma: no cover - only reached if the unique key is lost
                raise AssertionError("a duplicate contract revision number was accepted")

            # A revision must name a stored contract.
            try:
                connection.execute(
                    text(_REVISION_INSERT),
                    {
                        "revision_id": "revision-3",
                        "contract_id": "contract-missing",
                        "revision_number": 1,
                    },
                )
            except IntegrityError:
                pass
            else:  # pragma: no cover - only reached if the foreign key is lost
                raise AssertionError("a revision was accepted without its contract")

            # ON DELETE RESTRICT: captured evidence cannot be orphaned by deleting
            # the mutable contract row.
            try:
                connection.execute(
                    text("DELETE FROM upstream_resource_contracts WHERE contract_id = 'contract-1'")
                )
            except IntegrityError:
                pass
            else:  # pragma: no cover - only reached if RESTRICT is lost
                raise AssertionError("a captured contract revision was orphaned")

            assert connection.execute(
                text("SELECT count(*) FROM upstream_contract_revisions")
            ).scalar_one() == 1
    finally:
        engine.dispose()
