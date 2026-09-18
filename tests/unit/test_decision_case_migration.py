"""Decision Case migration DDL round trip (SQLite, no PostgreSQL needed).

`W6-01` section 5 claims the migration is verified by applying it, and until this file
existed nothing anywhere read revision `0035`: the endpoint tests build their schema with
`Base.metadata.create_all`, which never runs the DDL a deployment actually applies. This
applies the real `upgrade()`/`downgrade()` against a throw-away SQLite database, so the
expand-only promise is executed rather than inspected.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "0035_decision_cases.py"

EXPECTED_CASE_COLUMNS = {
    "case_id",
    "objective",
    "status",
    "created_by",
    "created_at_utc",
    "updated_at_utc",
    "gas_day",
    "delivery_product",
    "hub_id",
    "portfolio_ref",
    "snapshot_id",
    "assumptions_json",
    "alternatives_json",
    "evidence_json",
    "ai_findings_json",
    "warnings_json",
}

EXPECTED_RECORD_COLUMNS = {
    "record_id",
    "case_id",
    "outcome",
    "actor",
    "note",
    "evidence_refs_json",
    "recorded_at_utc",
}


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "tests.decision_cases_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply(connection, function_name: str) -> None:
    module = _migration_module()
    module.op = Operations(MigrationContext.configure(connection=connection))
    getattr(module, function_name)()


def test_upgrade_creates_the_case_tables_and_downgrade_removes_only_them() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            # A pre-existing table standing in for an earlier revision's schema.
            connection.execute(
                text("CREATE TABLE analysis_snapshots (snapshot_id VARCHAR(64) PRIMARY KEY)")
            )
            before = set(inspect(connection).get_table_names())

            _apply(connection, "upgrade")
            after = set(inspect(connection).get_table_names())
            # Expand-only: the two new tables, and nothing else touched.
            assert after - before == {"decision_cases", "decision_case_records"}
            assert before <= after

            assert {
                column["name"] for column in inspect(connection).get_columns("decision_cases")
            } == EXPECTED_CASE_COLUMNS
            assert {
                column["name"]
                for column in inspect(connection).get_columns("decision_case_records")
            } == EXPECTED_RECORD_COLUMNS

            assert {
                row["name"] for row in inspect(connection).get_indexes("decision_cases")
            } == {
                "ix_decision_cases_status",
                "ix_decision_cases_updated_at",
                "ix_decision_cases_gas_day",
                "ix_decision_cases_created_by",
            }
            assert {
                row["name"]
                for row in inspect(connection).get_indexes("decision_case_records")
            } == {
                "ix_decision_case_records_case_id",
                "ix_decision_case_records_recorded_at",
            }

            _apply(connection, "downgrade")
            assert set(inspect(connection).get_table_names()) == before
    finally:
        engine.dispose()


def test_a_decision_record_must_name_a_case_that_exists() -> None:
    """The records table carries a real foreign key, not a convention."""

    from sqlalchemy.exc import IntegrityError

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            _apply(connection, "upgrade")
            connection.execute(
                text(
                    "INSERT INTO decision_cases (case_id, objective, status, created_by, "
                    "created_at_utc, updated_at_utc, assumptions_json, alternatives_json, "
                    "evidence_json, ai_findings_json, warnings_json) VALUES "
                    "('case-1', 'objective', 'OPEN', 'analyst-1', '2026-01-01', '2026-01-01', "
                    "'[]', '[]', '[]', '[]', '[]')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO decision_case_records (record_id, case_id, outcome, actor, "
                    "evidence_refs_json, recorded_at_utc) VALUES "
                    "('rec-1', 'case-1', 'ACCEPTED', 'trader-a', '[]', '2026-01-01')"
                )
            )
            # A record naming a case that does not exist is refused by the schema itself.
            try:
                connection.execute(
                    text(
                        "INSERT INTO decision_case_records (record_id, case_id, outcome, actor, "
                        "evidence_refs_json, recorded_at_utc) VALUES "
                        "('rec-2', 'case-missing', 'ACCEPTED', 'trader-a', '[]', '2026-01-01')"
                    )
                )
            except IntegrityError:
                pass
            else:  # pragma: no cover - only reached if the foreign key is lost
                raise AssertionError("a decision record was accepted without its case")

            assert connection.execute(
                text("SELECT count(*) FROM decision_case_records")
            ).scalar_one() == 1

            # The key is declared `ON DELETE CASCADE`, so removing the case removes the
            # records rather than leaving rows nothing can reach.
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text("DELETE FROM decision_cases WHERE case_id = 'case-1'"))
            assert connection.execute(
                text("SELECT count(*) FROM decision_case_records")
            ).scalar_one() == 0
    finally:
        engine.dispose()
