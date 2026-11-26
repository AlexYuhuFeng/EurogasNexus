"""The gated upgrade on PostgreSQL: backup gate, plan, timeouts, audit, non-blocking index.

Runs when ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` is set (the PostgreSQL CI job). Each test uses
its own scratch database, created and dropped here.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="needs EUROGAS_NEXUS_TEST_POSTGRES_URL (the PostgreSQL CI job)",
)


@pytest.fixture()
def scratch_url(monkeypatch):
    name = f"p1c_upgrade_{uuid.uuid4().hex[:10]}"
    admin = create_engine(_POSTGRES_URL, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(_POSTGRES_URL).set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    yield url
    with admin.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name "
                "AND pid <> pg_backend_pid()"
            ),
            {"name": name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    admin.dispose()


def _upgrade(url: str, **kwargs) -> tuple[int, list[str]]:
    from eurogas_nexus.application.database_upgrade import run_upgrade

    lines: list[str] = []
    code = run_upgrade(url, emit=lines.append, **kwargs)
    return code, lines


def _audit(url: str) -> list[tuple[str, str, str]]:
    engine = create_engine(url, future=True)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT principal, action, outcome FROM audit_events "
                "WHERE source_system = 'database-upgrade' ORDER BY event_ts_utc, event_id"
            )
        ).all()
    engine.dispose()
    return [tuple(row) for row in rows]


def _alembic(url: str, target: str, direction: str = "downgrade") -> None:
    from alembic import command
    from eurogas_nexus.application.database_upgrade import alembic_config

    getattr(command, direction)(alembic_config(url), target)


def test_fresh_store_needs_no_backup_and_is_audited(scratch_url) -> None:
    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    code, lines = _upgrade(scratch_url, operator="Ops Tester")
    assert code == 0, lines
    assert any("empty store" in line for line in lines)
    assert any("can be undone: no: going back means restoring the backup" in line for line in lines)
    assert lines[-1].startswith(f"upgraded to {DB_SCHEMA_REVISION}")
    # The audit table did not exist before the run, so only the outcome is recorded.
    assert _audit(scratch_url) == [("Ops Tester", "database.upgrade", "succeeded")]
    code, lines = _upgrade(scratch_url, operator="Ops Tester")
    assert code == 0 and any("up to date" in line for line in lines)


def test_pending_upgrade_refuses_without_a_recent_backup(scratch_url) -> None:
    from eurogas_nexus.application.database_upgrade import record_backup

    assert _upgrade(scratch_url, operator="Ops Tester")[0] == 0
    _alembic(scratch_url, "0092_lng_berth_rules")
    code, lines = _upgrade(scratch_url, operator="Ops Tester")
    assert code == 2
    assert any(line.startswith("REFUSED: no backup recorded") for line in lines)
    assert any("0093_timescale_optional" in line for line in lines)
    assert any("nothing to undo" in line for line in lines)  # 0093 is a no-op downgrade

    engine = create_engine(scratch_url, future=True)
    with Session(engine) as session:
        record_backup(
            session,
            operator="Backup Bot",
            reference="old-dump",
            kind="pg_dump",
            now_utc=datetime.now(UTC) - timedelta(hours=30),
        )
        session.commit()
    assert _upgrade(scratch_url, operator="Ops Tester")[0] == 2  # 30 h old: too old
    with Session(engine) as session:
        record_backup(session, operator="Backup Bot", reference="fresh-dump", kind="pg_dump")
        session.commit()
    engine.dispose()
    code, lines = _upgrade(scratch_url, operator="Ops Tester")
    assert code == 0, lines
    assert any("backup fresh-dump (pg_dump)" in line for line in lines)
    assert _audit(scratch_url)[-2:] == [
        ("Ops Tester", "database.upgrade", "started"),
        ("Ops Tester", "database.upgrade", "succeeded"),
    ]


def test_override_is_recorded(scratch_url) -> None:
    assert _upgrade(scratch_url, operator="Ops Tester")[0] == 0
    _alembic(scratch_url, "0093_timescale_optional")
    code, lines = _upgrade(
        scratch_url, operator="Ops Tester", override_reason="storage snapshot taken by DBA"
    )
    assert code == 0, lines
    engine = create_engine(scratch_url, future=True)
    with engine.connect() as connection:
        detail = connection.execute(
            text(
                "SELECT detail FROM audit_events WHERE action = 'database.upgrade' "
                "AND outcome = 'succeeded' ORDER BY event_ts_utc DESC LIMIT 1"
            )
        ).scalar()
    engine.dispose()
    assert "overridden: storage snapshot taken by DBA" in detail


def test_lock_timeout_fails_the_upgrade_instead_of_queueing(scratch_url) -> None:
    """A reader holding a lock: the ALTER gives up after lock_timeout, nothing is half-done."""

    assert _upgrade(scratch_url, operator="Ops Tester")[0] == 0
    _alembic(scratch_url, "0089_alert_reader_state")
    holder = create_engine(scratch_url, future=True)
    connection = holder.connect()
    transaction = connection.begin()
    connection.execute(text("LOCK TABLE job_records IN ACCESS SHARE MODE"))
    started = datetime.now(UTC)
    try:
        code, lines = _upgrade(
            scratch_url, operator="Ops Tester", override_reason="test", lock_timeout="1s"
        )
    finally:
        transaction.rollback()
        connection.close()
        holder.dispose()
    assert code == 1, lines
    assert (datetime.now(UTC) - started).total_seconds() < 60
    assert any("lock_timeout" in line for line in lines)
    assert _audit(scratch_url)[-1] == ("Ops Tester", "database.upgrade", "failed")
    from eurogas_nexus.application.database_upgrade import alembic_config, build_plan

    engine = create_engine(scratch_url, future=True)
    plan = build_plan(engine, alembic_config(scratch_url))
    engine.dispose()
    assert plan.current == "0089_alert_reader_state"  # rolled back as a whole


def test_create_index_nonblocking_builds_a_valid_index_concurrently(scratch_url) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from eurogas_nexus.db.migration_rules import create_index_nonblocking

    engine = create_engine(scratch_url, future=True)
    with engine.connect() as connection:
        connection.execute(text("CREATE TABLE big_rows (id int, hub text)"))
        connection.commit()
        # As env.py runs a migration: inside the migration transaction, which a concurrent
        # build cannot run in; the helper steps out of it (autocommit block) and back.
        context = MigrationContext.configure(connection)
        with context.begin_transaction(), Operations.context(context):
            create_index_nonblocking("ix_big_rows_hub", "big_rows", ["hub"])
            create_index_nonblocking("ix_big_rows_hub", "big_rows", ["hub"])  # idempotent
        valid = connection.execute(
            text(
                "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = 'ix_big_rows_hub'"
            )
        ).scalar()
    engine.dispose()
    assert valid is True
