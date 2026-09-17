"""Unified Job contract tests (Architecture V2 Wave 8 section 5).

The shared lifecycle exists so ingestion, dataset builds, optimisation, backtests,
reporting and agent work cannot each invent their own run model. These tests pin
the rules that make it trustworthy: terminal jobs stay terminal, progress never
moves backwards, cancellation is explicit, and a failure carries a stable code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.domain.operations.jobs import (
    TERMINAL_JOB_STATES,
    Job,
    JobKind,
    JobState,
    job_cancelled,
    job_failed,
    job_is_terminal,
    job_payload,
    job_progress,
    job_started,
    job_succeeded,
    transition_allowed,
)

NOW = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)


def _job(**overrides: object) -> Job:
    base: dict[str, object] = {
        "job_id": "job-1",
        "kind": JobKind.DATASET_BUILD,
        "status": JobState.QUEUED,
        "principal": "analyst.one",
    }
    base.update(overrides)
    return Job(**base)  # type: ignore[arg-type]


def test_the_lifecycle_covers_every_state_v2_names() -> None:
    assert {state.value for state in JobState} == {
        "QUEUED",
        "RUNNING",
        "WAITING_FOR_INPUT",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "EXPIRED",
    }
    assert {kind.value for kind in JobKind} == {
        "INGESTION",
        "DATASET_BUILD",
        "OPTIMISATION",
        "BACKTEST",
        "REPORT",
        "AGENT_RUN",
        "SNAPSHOT",
    }
    assert TERMINAL_JOB_STATES == {
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.EXPIRED,
    }


def test_a_job_runs_to_success_and_stamps_its_duration() -> None:
    job = job_started(_job(), now_utc=NOW)
    assert job.status is JobState.RUNNING
    assert job.started_at_utc == NOW.isoformat()

    job = job_progress(job, 0.4)
    assert job.progress == 0.4

    finished = job_succeeded(job, output_refs=("dataset_snapshot:ds-1",), now_utc=NOW + timedelta(seconds=30))
    assert finished.status is JobState.SUCCEEDED
    assert finished.progress == 1.0
    assert finished.output_refs == ("dataset_snapshot:ds-1",)
    assert finished.cancellable is False
    assert finished.duration_seconds == 30.0
    assert finished.terminal is True


def test_a_terminal_job_never_moves_again() -> None:
    finished = job_succeeded(job_started(_job(), now_utc=NOW), now_utc=NOW)

    for move in (
        lambda: job_started(finished, now_utc=NOW),
        lambda: job_progress(finished, 0.5),
        lambda: job_failed(finished, error_code="JOB_FAILED", now_utc=NOW),
        lambda: job_cancelled(finished, now_utc=NOW),
    ):
        with pytest.raises(ValueError) as excinfo:
            move()
        assert "job_already_finished" in str(excinfo.value)

    for state in TERMINAL_JOB_STATES:
        assert transition_allowed(state, JobState.RUNNING) is False
        assert job_is_terminal(state) is True


def test_progress_never_moves_backwards_and_stays_in_range() -> None:
    job = job_progress(job_started(_job(), now_utc=NOW), 0.6)

    assert job_progress(job, 0.2).progress == 0.6
    assert job_progress(job, 0.6).progress == 0.6

    with pytest.raises(ValueError) as excinfo:
        job_progress(job, 1.4)
    assert "job_progress_out_of_range" in str(excinfo.value)


def test_cancellation_is_explicit_and_bounded() -> None:
    cancellable = job_started(_job(), now_utc=NOW)
    cancelled = job_cancelled(cancellable, now_utc=NOW)
    assert cancelled.status is JobState.CANCELLED
    assert cancelled.cancellable is False

    protected = job_started(_job(cancellable=False), now_utc=NOW)
    with pytest.raises(ValueError) as excinfo:
        job_cancelled(protected, now_utc=NOW)
    assert "job_not_cancellable" in str(excinfo.value)


def test_a_failure_requires_a_stable_code() -> None:
    running = job_started(_job(), now_utc=NOW)

    with pytest.raises(ValueError) as excinfo:
        job_failed(running, error_code="   ")
    assert "job_error_code_required" in str(excinfo.value)

    failed = job_failed(
        running,
        error_code="runtime_db_unavailable",
        error_message="OperationalError",
        retryable=True,
        now_utc=NOW,
    )
    assert failed.status is JobState.FAILED
    assert failed.error_code == "runtime_db_unavailable"
    assert failed.retryable is True
    assert failed.terminal is True


def test_a_waiting_job_can_resume_but_not_jump_to_success() -> None:
    waiting = Job(
        job_id="job-2",
        kind=JobKind.AGENT_RUN,
        status=JobState.WAITING_FOR_INPUT,
        principal="analyst.one",
    )
    assert transition_allowed(JobState.WAITING_FOR_INPUT, JobState.RUNNING) is True
    assert transition_allowed(JobState.WAITING_FOR_INPUT, JobState.SUCCEEDED) is False
    assert transition_allowed(JobState.QUEUED, JobState.SUCCEEDED) is False

    with pytest.raises(ValueError) as excinfo:
        job_succeeded(waiting, now_utc=NOW)
    assert "job_transition_not_allowed" in str(excinfo.value)


def test_the_payload_is_telemetry_safe() -> None:
    job = job_failed(
        job_started(_job(input_hash="abc", correlation_id="corr-1"), now_utc=NOW),
        error_code="JOB_FAILED",
        error_message="ValueError",
        now_utc=NOW,
    )
    payload = job_payload(job)

    assert set(payload) == {
        "job_id",
        "kind",
        "job_version",
        "status",
        "principal",
        "scope_refs",
        "snapshot_id",
        "input_hash",
        "progress",
        "created_at_utc",
        "started_at_utc",
        "finished_at_utc",
        "duration_seconds",
        "output_refs",
        "error_code",
        "error_message",
        "retryable",
        "cancellable",
        "correlation_id",
        "provenance",
    }
    assert payload["kind"] == "DATASET_BUILD"
    assert payload["status"] == "FAILED"
    assert payload["job_version"] == "job/v1"
    assert payload["correlation_id"] == "corr-1"
    assert payload["input_hash"] == "abc"


# ---------------------------------------------------------------------------
# run_tracked_job: the seam for work that has no session of its own
# ---------------------------------------------------------------------------


def _runtime_store(tmp_path, monkeypatch, name: str, *, with_jobs: bool = True) -> str:
    """Point the runtime store at a SQLite database, optionally without jobs."""

    from sqlalchemy import create_engine

    from eurogas_nexus.db.base import Base

    database_url = f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine(database_url, future=True)
    tables = None
    if not with_jobs:
        tables = [table for table in Base.metadata.sorted_tables if table.name != "job_records"]
    Base.metadata.create_all(engine, tables=tables)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def test_run_tracked_job_records_a_successful_computation(tmp_path, monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.application.jobs import run_tracked_job
    from eurogas_nexus.db.repositories.jobs import list_jobs

    database_url = _runtime_store(tmp_path, monkeypatch, "tracked.sqlite")

    result = run_tracked_job(
        lambda handle: {"allocated": 6000},
        kind="OPTIMISATION",
        principal="analyst.one",
        scope_refs=("PORTFOLIO:pool-1",),
        snapshot_id="asnap-1",
        inputs={"portfolio_id": "pool-1"},
        correlation_id="corr-7",
        provenance=("route-cost-resource-pool",),
    )

    assert result == {"allocated": 6000}
    with Session(create_engine(database_url, future=True)) as session:
        rows = list_jobs(session, kind="OPTIMISATION")
    assert len(rows) == 1
    assert rows[0]["status"] == "SUCCEEDED"
    assert rows[0]["scope_refs"] == ["PORTFOLIO:pool-1"]
    assert rows[0]["snapshot_id"] == "asnap-1"
    assert rows[0]["correlation_id"] == "corr-7"
    assert rows[0]["provenance"] == ["route-cost-resource-pool"]


def test_run_tracked_job_commits_a_failure_and_reraises(tmp_path, monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.application.jobs import run_tracked_job
    from eurogas_nexus.db.repositories.jobs import list_jobs

    database_url = _runtime_store(tmp_path, monkeypatch, "tracked-failed.sqlite")

    class Boom(RuntimeError):
        code = "OPTIMIZATION_INFEASIBLE"

    def _work(handle) -> None:
        raise Boom("no feasible allocation")

    with pytest.raises(Boom):
        run_tracked_job(_work, kind="OPTIMISATION", principal="analyst.one")

    with Session(create_engine(database_url, future=True)) as session:
        rows = list_jobs(session, kind="OPTIMISATION")
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["error_code"] == "OPTIMIZATION_INFEASIBLE"
    assert rows[0]["error_message"] == "Boom"


def test_run_tracked_job_runs_untracked_without_a_runtime_store(monkeypatch) -> None:
    from eurogas_nexus.application.jobs import run_tracked_job

    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    seen: list[str] = []
    result = run_tracked_job(
        lambda handle: seen.append(handle.job_id) or "done",
        kind="OPTIMISATION",
        principal="analyst.one",
    )

    assert result == "done"
    assert seen == [""]


def test_run_tracked_job_runs_untracked_when_the_store_cannot_accept_the_job(
    tmp_path, monkeypatch
) -> None:
    from eurogas_nexus.application.jobs import run_tracked_job

    # The store is configured but carries no job table: tracking is skipped
    # rather than turning a computation into a failure.
    _runtime_store(tmp_path, monkeypatch, "no-jobs.sqlite", with_jobs=False)

    result = run_tracked_job(
        lambda handle: "computed",
        kind="OPTIMISATION",
        principal="analyst.one",
    )

    assert result == "computed"
