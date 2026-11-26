"""Migration 0087 on SQLite: step progress, runner and heartbeat columns on ``job_records``."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
NEW_COLUMNS = {
    "progress_step",
    "progress_total",
    "progress_label",
    "runner_id",
    "heartbeat_at_utc",
}


def test_chain_up_down_and_model_match():
    from eurogas_nexus.db.models import JobRecord

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0090_jobs", VERSIONS / "0090_job_progress_steps.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0090_job_progress_steps"
    assert module.down_revision == "0089_alert_reader_state"
    table = JobRecord.__table__
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        before = table.to_metadata(type(table.metadata)())
        for name in NEW_COLUMNS:
            before._columns.remove(before.c[name])  # noqa: SLF001
        before.foreign_keys.clear()
        for constraint in list(before.constraints):
            if constraint.__class__.__name__ == "ForeignKeyConstraint":
                before.constraints.discard(constraint)
        before.create(connection)
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        names = {c["name"] for c in inspect(connection).get_columns(table.name)}
        assert names == set(table.columns.keys())
        module.downgrade()
        names = {c["name"] for c in inspect(connection).get_columns(table.name)}
        assert not names & NEW_COLUMNS
