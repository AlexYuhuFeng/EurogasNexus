"""Background job runner tests (application/background_jobs.py).

A background job returns at once and runs its work after the response. These tests pin what
makes that safe to leave: the work is claimed once, publishes its rows and its SUCCEEDED
outcome in one transaction, publishes nothing when cancelled or failed, records a stable code
and a plain reason on failure, and a job whose server process stopped is failed with
``JOB_INTERRUPTED`` instead of running for ever.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eurogas_nexus.application import background_jobs as bg
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import JobRecord
from eurogas_nexus.db.repositories.jobs import cancel_job, create_job, get_job


@pytest.fixture()
def factory(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'bg.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _submit(factory, **overrides) -> str:
    spec = {
        "kind": "DATASET_BUILD",
        "principal": "analyst.one",
        "owner_principal_id": None,
        "inputs": {"dataset_spec_id": "spec-1"},
        "steps_total": 3,
    }
    spec.update(overrides)
    with factory() as session:
        job = bg.submit_background_job(session, **spec)
        session.commit()
    assert job["status"] == "QUEUED"
    assert (job["step"], job["step_total"], job["step_label"]) == (0, spec["steps_total"], "queued")
    return str(job["job_id"])


def _artefact(session, marker: str) -> None:
    """A row the work writes: it must land only when the job succeeds."""

    create_job(session, kind="REPORT", principal=marker)


def _artefacts(factory, marker: str) -> int:
    with factory() as session:
        return session.query(JobRecord).filter(JobRecord.principal == marker).count()


def _job(factory, job_id: str) -> dict:
    with factory() as session:
        payload = get_job(session, job_id)
    assert payload is not None
    return payload


def test_a_job_runs_its_steps_and_publishes_with_its_rows(factory) -> None:
    job_id = _submit(factory)
    seen: list[dict] = []

    def work(session, progress) -> None:
        for index, label in enumerate(("a.one", "a.two", "a.three"), start=1):
            progress.step(index, label)
            seen.append(_job(factory, job_id))
        _artefact(session, "artefact-ok")
        progress.add_output("dataset_snapshot:snap-1")

    bg.run_background_job(factory, job_id, work, steps_total=3)

    assert [(row["step"], row["step_label"]) for row in seen] == [
        (1, "a.one"),
        (2, "a.two"),
        (3, "a.three"),
    ]
    assert seen[1]["status"] == "RUNNING" and seen[1]["progress"] == pytest.approx(1 / 3)
    done = _job(factory, job_id)
    assert done["status"] == "SUCCEEDED" and done["progress"] == 1.0
    assert done["output_refs"] == ["dataset_snapshot:snap-1"]
    assert "background-job" in done["provenance"]
    assert _artefacts(factory, "artefact-ok") == 1


def test_a_named_failure_records_its_code_and_reason_and_rolls_back(factory) -> None:
    job_id = _submit(factory)

    def work(session, progress) -> None:
        progress.step(1, "a.one")
        _artefact(session, "artefact-failed")
        raise bg.BackgroundJobFailure("dataset_no_observations", "No observations matched.")

    bg.run_background_job(factory, job_id, work, steps_total=3)

    failed = _job(factory, job_id)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "dataset_no_observations"
    assert failed["error_message"] == "No observations matched."
    assert failed["output_refs"] == []
    assert _artefacts(factory, "artefact-failed") == 0


def test_an_unexpected_error_fails_with_a_stable_code_and_a_plain_reason(factory) -> None:
    job_id = _submit(factory)

    def work(session, progress) -> None:
        raise KeyError("column")

    bg.run_background_job(factory, job_id, work, steps_total=3)

    failed = _job(factory, job_id)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "JOB_FAILED"
    assert "unexpected error" in failed["error_message"]
    assert "KeyError" not in failed["error_message"]


def test_cancelling_stops_the_work_at_the_next_step_and_publishes_nothing(factory) -> None:
    job_id = _submit(factory)
    reached: list[int] = []

    def work(session, progress) -> None:
        progress.step(1, "a.one")
        reached.append(1)
        with factory() as other:
            cancel_job(other, job_id)
            other.commit()
        _artefact(session, "artefact-cancelled")
        progress.step(2, "a.two")
        reached.append(2)

    bg.run_background_job(factory, job_id, work, steps_total=3)

    assert reached == [1]
    cancelled = _job(factory, job_id)
    assert cancelled["status"] == "CANCELLED"
    assert _artefacts(factory, "artefact-cancelled") == 0


def test_a_cancel_during_the_last_step_still_publishes_nothing(factory) -> None:
    job_id = _submit(factory)

    def work(session, progress) -> None:
        progress.step(3, "a.three")
        # SQLite allows one writer, so the cancel lands before the work writes its row; on
        # PostgreSQL the two transactions run side by side and the outcome is the same.
        with factory() as other:
            cancel_job(other, job_id)
            other.commit()
        _artefact(session, "artefact-late")
        progress.add_output("dataset_snapshot:late")

    bg.run_background_job(factory, job_id, work, steps_total=3)

    cancelled = _job(factory, job_id)
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["output_refs"] == []
    assert _artefacts(factory, "artefact-late") == 0


def test_a_job_is_claimed_once(factory) -> None:
    job_id = _submit(factory)
    runs: list[str] = []

    def work(session, progress) -> None:
        runs.append(job_id)

    bg.run_background_job(factory, job_id, work, steps_total=3)
    bg.run_background_job(factory, job_id, work, steps_total=3)

    assert runs == [job_id]


def test_an_owner_may_have_three_active_background_jobs(factory) -> None:
    from eurogas_nexus.db.repositories.identity import create_identity_principal

    with factory() as session:
        owner = create_identity_principal(
            session, name="owner.one", display_name="Owner", role="ANALYST"
        ).principal_id
        session.commit()
    for _ in range(bg.MAX_ACTIVE_JOBS_PER_OWNER):
        _submit(factory, owner_principal_id=owner)
    with pytest.raises(bg.JobQueueFull), factory() as session:
        bg.submit_background_job(
            session,
            kind="DATASET_BUILD",
            principal="owner",
            owner_principal_id=owner,
            steps_total=3,
        )


def _set_runner(factory, job_id: str, *, runner: str, heartbeat: datetime) -> None:
    with factory() as session:
        row = session.get(JobRecord, job_id)
        row.runner_id = runner
        row.heartbeat_at_utc = heartbeat
        session.commit()


def test_a_store_failure_is_recorded_as_the_store_not_as_a_driver_code(factory) -> None:
    from sqlalchemy.exc import OperationalError

    job_id = _submit(factory)

    def work(session, progress) -> None:
        raise OperationalError("SELECT 1", {}, Exception("database is locked"))

    bg.run_background_job(factory, job_id, work, steps_total=3)

    failed = _job(factory, job_id)
    assert failed["error_code"] == "runtime_db_unavailable"
    assert failed["retryable"] is True


def test_the_sweep_fails_jobs_whose_process_is_gone_and_keeps_live_ones(factory) -> None:
    now = datetime.now(UTC)
    host = bg.runner_id().split(":")[0]
    stale = _submit(factory)
    _set_runner(factory, stale, runner="other-host:1:x", heartbeat=now - timedelta(minutes=5))
    earlier_boot = _submit(factory)
    _set_runner(factory, earlier_boot, runner=f"{host}:{os.getpid()}:oldboot", heartbeat=now)
    dead_pid = _submit(factory)
    _set_runner(factory, dead_pid, runner=f"{host}:999999999:x", heartbeat=now)
    live_here = _submit(factory)  # this process, this boot, fresh heartbeat
    live_elsewhere = _submit(factory)
    _set_runner(factory, live_elsewhere, runner="other-host:1:x", heartbeat=now)
    with factory() as session:
        request_scoped = create_job(session, kind="REPORT", principal="request")["job_id"]
        session.commit()

    assert bg.fail_orphaned_jobs_quietly(factory) == 3

    for job_id in (stale, earlier_boot, dead_pid):
        failed = _job(factory, job_id)
        assert failed["status"] == "FAILED"
        assert failed["error_code"] == bg.JOB_INTERRUPTED
        assert failed["retryable"] is True
        assert "Start it again" in failed["error_message"]
    assert _job(factory, live_here)["status"] == "QUEUED"
    assert _job(factory, live_elsewhere)["status"] == "QUEUED"
    assert _job(factory, request_scoped)["status"] == "QUEUED"


def test_a_swept_job_does_not_publish_when_its_work_comes_back(factory) -> None:
    job_id = _submit(factory)

    def work(session, progress) -> None:
        progress.step(1, "a.one")
        _set_runner(
            factory,
            job_id,
            runner="other-host:1:x",
            heartbeat=datetime.now(UTC) - timedelta(minutes=5),
        )
        bg.fail_orphaned_jobs_quietly(factory)
        _artefact(session, "artefact-swept")

    bg.run_background_job(factory, job_id, work, steps_total=3)

    assert _job(factory, job_id)["error_code"] == bg.JOB_INTERRUPTED
    assert _artefacts(factory, "artefact-swept") == 0
