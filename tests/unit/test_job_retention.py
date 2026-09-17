"""Job-record retention tests (Architecture V2 Wave 8).

The unified job model is the record of what a deployment ran, so retention has to be bounded
without ever deleting work in progress or the work itself. These tests pin that:

- only terminal rows past the window are eligible, and an active row is kept however old it is;
- a dry run counts and changes nothing, and running the real prune twice is idempotent;
- the window is the operator's, with no default, and nonsense values are refused;
- the script refuses to do anything without an explicit window or a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.job_retention import (
    MAX_JOB_RETENTION_DAYS,
    MIN_JOB_RETENTION_DAYS,
    prune_expired_job_records,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import JobRecord
from eurogas_nexus.domain.operations.jobs import JobState

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _job(job_id: str, *, age_days: int, status: JobState) -> JobRecord:
    created = NOW - timedelta(days=age_days)
    return JobRecord(
        job_id=job_id,
        kind="REPORT",
        status=status.value,
        principal="public-api",
        scope_refs_json=[],
        snapshot_id="",
        input_hash="hash",
        progress=1.0,
        created_at_utc=created,
        started_at_utc=created,
        finished_at_utc=created if status in {JobState.SUCCEEDED, JobState.FAILED} else None,
        output_refs_json=["generated_report:report-1"] if status == JobState.SUCCEEDED else [],
        error_code="",
        error_message=None,
        retryable=False,
        cancellable=True,
        correlation_id=None,
        provenance_json=[],
    )


def _session(tmp_path) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'jobs.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_a_dry_run_counts_what_would_go_and_changes_nothing(tmp_path) -> None:
    with _session(tmp_path) as session:
        session.add(_job("old-ok", age_days=400, status=JobState.SUCCEEDED))
        session.add(_job("recent-ok", age_days=10, status=JobState.SUCCEEDED))
        session.commit()

        summary = prune_expired_job_records(session, retention_days=180, now_utc=NOW)

        assert summary["dry_run"] is True
        assert summary["jobs_eligible"] == 1
        assert summary["jobs_deleted"] == 0
        assert session.query(JobRecord).count() == 2
        assert summary["oldest_job_created_at_utc"] == (NOW - timedelta(days=400)).isoformat()


def test_only_terminal_rows_past_the_window_are_deleted(tmp_path) -> None:
    with _session(tmp_path) as session:
        session.add(_job("old-ok", age_days=400, status=JobState.SUCCEEDED))
        session.add(_job("old-failed", age_days=400, status=JobState.FAILED))
        session.add(_job("old-cancelled", age_days=400, status=JobState.CANCELLED))
        session.add(_job("old-expired", age_days=400, status=JobState.EXPIRED))
        session.add(_job("old-running", age_days=400, status=JobState.RUNNING))
        session.add(_job("old-queued", age_days=400, status=JobState.QUEUED))
        session.add(_job("old-waiting", age_days=400, status=JobState.WAITING_FOR_INPUT))
        session.add(_job("recent-ok", age_days=5, status=JobState.SUCCEEDED))
        session.commit()

        summary = prune_expired_job_records(
            session, retention_days=180, now_utc=NOW, dry_run=False
        )

        assert summary["jobs_deleted"] == 4
        assert summary["jobs_eligible"] == 4
        # Work that has not finished is never history, whatever its age: the row is what the
        # cancel endpoint acts on, so it is reported for recovery instead of deleted.
        assert summary["active_jobs_retained"] == 3
        assert {row.job_id for row in session.query(JobRecord).all()} == {
            "old-running",
            "old-queued",
            "old-waiting",
            "recent-ok",
        }


def test_pruning_is_idempotent_and_leaves_the_work_it_referenced(tmp_path) -> None:
    with _session(tmp_path) as session:
        session.add(_job("old-ok", age_days=400, status=JobState.SUCCEEDED))
        session.commit()

        first = prune_expired_job_records(
            session, retention_days=180, now_utc=NOW, dry_run=False
        )
        second = prune_expired_job_records(
            session, retention_days=180, now_utc=NOW, dry_run=False
        )

        assert first["jobs_deleted"] == 1
        assert second["jobs_deleted"] == 0
        assert second["jobs_eligible"] == 0
        assert second["oldest_job_created_at_utc"] is None


def test_the_window_is_the_operators_and_nonsense_is_refused(tmp_path) -> None:
    with _session(tmp_path) as session:
        for value in (0, -1, MAX_JOB_RETENTION_DAYS + 1):
            with pytest.raises(ValueError, match="retention_days must be between"):
                # No default exists to fall back on: a retention window is a decision, and a
                # value that cannot be meant is refused rather than rounded into one.
                prune_expired_job_records(session, retention_days=value, now_utc=NOW)
        assert MIN_JOB_RETENTION_DAYS == 1


def test_the_script_requires_a_window_and_a_database(tmp_path, monkeypatch) -> None:
    import scripts.ops.prune_job_records as script

    # Without --retention-days the run is refused before anything is opened.
    with pytest.raises(SystemExit):
        script.main([])

    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    assert script.main(["--retention-days", "180"]) == 2


def test_the_script_prunes_with_an_explicit_window(tmp_path, monkeypatch, capsys) -> None:
    import scripts.ops.prune_job_records as script

    database_url = f"sqlite+pysqlite:///{(tmp_path / 'script.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(database_url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    with Session(create_engine(database_url, future=True)) as session:
        session.add(_job("old-ok", age_days=400, status=JobState.SUCCEEDED))
        session.add(_job("old-running", age_days=400, status=JobState.RUNNING))
        session.commit()

    # Dry-run is the default: the rows are counted, not removed.
    assert script.main(["--retention-days", "180"]) == 0
    assert "dry-run" in capsys.readouterr().out
    with Session(create_engine(database_url, future=True)) as session:
        assert session.query(JobRecord).count() == 2

    assert script.main(["--retention-days", "180", "--commit"]) == 0
    output = capsys.readouterr().out
    assert "committed" in output
    # The stale active row is reported with the recovery script to run, not deleted.
    assert "recover_stale_jobs.py" in output
    with Session(create_engine(database_url, future=True)) as session:
        assert {row.job_id for row in session.query(JobRecord).all()} == {"old-running"}
