"""Background jobs: long-running work the user can leave (Architecture V2 Wave 8 jobs).

A dataset build takes 35-45 s on the demo desk; a request that holds the browser for that long
ties the user to the page. A background job instead returns its job id at once and runs the
work after the response, under the shared job lifecycle, so the user can follow it from the
notification centre (``GET /api/jobs``) and open the result when it is done.

The pattern is the repository's own (``application/functional_runs.py``): the route creates
the QUEUED job and schedules :func:`run_background_job` with FastAPI's ``BackgroundTasks``,
which runs it on the server's worker thread pool after the response is sent. Then:

1. **claim once**: the job row is locked; only a QUEUED job is started, so a duplicate
   schedule does nothing;
2. **work in its own session**: the work never commits; it reports ``step x of n`` through
   :class:`JobProgress`, which writes the step on a separate short session (visible at once)
   and checks for cancellation at every step;
3. **publish atomically**: the job row is locked in the work's session and, only if it is
   still RUNNING, the job is finished in the same transaction as the work's rows. A job
   cancelled (or failed by the sweep) in the meantime therefore never publishes a result;
4. **fail with a reason**: a failure records a stable taxonomy code and a plain reason, and
   rolls the work back, so a failed build leaves nothing half-written.

Restarts. Work runs in the API process, so a restart, crash or deploy stops it mid-way. Each
job records the process running it (``runner_id``) and a heartbeat refreshed every
:data:`HEARTBEAT_SECONDS` while it runs. :func:`fail_orphaned_jobs` fails a QUEUED or RUNNING
background job with ``JOB_INTERRUPTED`` when its process is gone (same host, process not
alive or a different boot) or its heartbeat is older than :data:`STALE_AFTER_SECONDS`. It runs
at start-up and whenever the job list is read, so the user sees "interrupted, start it again"
instead of a job that runs for ever. Jobs tracked inside a request have no heartbeat and are
never touched.
"""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from eurogas_nexus.application.jobs import _error_code, job_input_hash
from eurogas_nexus.db.models.jobs import JobRecord
from eurogas_nexus.db.repositories.jobs import (
    create_job,
    fail_job,
    finish_job,
    record_job_step,
    start_job,
)
from eurogas_nexus.domain.operations.jobs import JobState

#: How often a running job's heartbeat is refreshed.
HEARTBEAT_SECONDS = 10.0
#: A background job whose heartbeat is older than this is treated as orphaned.
STALE_AFTER_SECONDS = 90.0
#: Active (QUEUED or RUNNING) background jobs one owner may have at once.
MAX_ACTIVE_JOBS_PER_OWNER = 3
#: Code recorded on a job whose server process stopped while it ran.
JOB_INTERRUPTED = "JOB_INTERRUPTED"
#: Code of the refusal when an owner already has the maximum of active jobs.
JOB_QUEUE_LIMIT = "JOB_QUEUE_LIMIT"
#: Provenance label every background job carries.
BACKGROUND_PROVENANCE = "background-job"

_BOOT_TOKEN = uuid4().hex[:12]
_INTERRUPTED_REASON = (
    "The server restarted or stopped while this job was running, so it did not finish. "
    "Start it again."
)
_UNEXPECTED_REASON = (
    "The job stopped on an unexpected error. Start it again; if it fails again, report it."
)

SessionFactory = Callable[[], Session]


def runner_id() -> str:
    """Identity of this server process: host, pid and a token unique to this boot."""

    return f"{socket.gethostname()[:80]}:{os.getpid()}:{_BOOT_TOKEN}"


class JobCancelled(Exception):
    """The job was cancelled (or failed elsewhere) while the work was running."""


class BackgroundJobFailure(Exception):
    """A failure the work names: a stable code and a reason a user can act on."""

    def __init__(self, code: str, reason: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason
        self.retryable = retryable


class JobQueueFull(Exception):
    """The owner already has :data:`MAX_ACTIVE_JOBS_PER_OWNER` active background jobs."""

    code = JOB_QUEUE_LIMIT


@dataclass(slots=True)
class JobProgress:
    """What the work sees of its job: report steps, record outputs, notice cancellation."""

    factory: SessionFactory
    job_id: str
    total: int
    output_refs: list[str] = field(default_factory=list)
    #: The work's own session, set by the runner (see :meth:`_store_is_locked_by_work`).
    work_session: Session | None = None
    #: The last step reported, written with the result when it could not be written live.
    last_step: tuple[int, str] | None = None

    def step(self, index: int, label: str) -> None:
        """Record that the work is on step ``index`` of ``total``; stop if cancelled.

        Raises:
            JobCancelled: the job is no longer RUNNING (cancelled by the user, or failed by
                the orphan sweep), so the work must stop and publish nothing.
        """

        self.last_step = (min(index, self.total), label)
        with self.factory() as session:
            row = session.get(JobRecord, self.job_id, populate_existing=True)
            if row is None or row.status != JobState.RUNNING.value:
                raise JobCancelled(self.job_id)
            if self._store_is_locked_by_work():
                # The runner writes this step with the result instead.
                return
            try:
                record_job_step(session, self.job_id, min(index, self.total), self.total, label)
                session.commit()
            except ValueError as exc:
                session.rollback()
                if str(exc) == "job_already_finished":
                    raise JobCancelled(self.job_id) from exc
                raise

    def add_output(self, reference: str) -> None:
        """Record an artefact the work produced (published only when the job succeeds)."""

        if reference and reference not in self.output_refs:
            self.output_refs.append(reference)

    def _store_is_locked_by_work(self) -> bool:
        """Whether the work's own uncommitted writes hold the store's only write lock.

        SQLite (tests, a local single-user store) has one writer at a time: once the work has
        written, a second connection's progress write would wait for the whole job and then
        fail it. The step is then only checked for cancellation, and recorded with the result.
        PostgreSQL locks rows, so its progress is always written as it happens.
        """

        session = self.work_session
        if session is None or not session.in_transaction():
            return False
        connection = session.connection()
        if connection.dialect.name != "sqlite":
            return False
        return bool(getattr(connection.connection.dbapi_connection, "in_transaction", False))


#: The work: given its own session (never committed by the work) and its progress handle.
BackgroundWork = Callable[[Session, JobProgress], None]


def submit_background_job(
    session: Session,
    *,
    kind: str,
    principal: str,
    owner_principal_id: str | None,
    scope_refs: tuple[str, ...] = (),
    snapshot_id: str = "",
    inputs: Any = None,
    correlation_id: str | None = None,
    provenance: tuple[str, ...] = (),
    steps_total: int = 1,
    first_step_label: str = "queued",
    now_utc: datetime | None = None,
) -> dict:
    """Create the QUEUED job a background run will claim; the caller commits.

    Raises:
        JobQueueFull: the owner already has the maximum of active background jobs.
    """

    now = now_utc or datetime.now(UTC)
    if owner_principal_id is not None:
        _serialise_owner(session, owner_principal_id)
        active = (
            session.query(JobRecord.job_id)
            .filter(JobRecord.owner_principal_id == owner_principal_id)
            .filter(JobRecord.status.in_([JobState.QUEUED.value, JobState.RUNNING.value]))
            .filter(JobRecord.heartbeat_at_utc.is_not(None))
            .count()
        )
        if active >= MAX_ACTIVE_JOBS_PER_OWNER:
            raise JobQueueFull()
    payload = create_job(
        session,
        kind=kind,
        principal=principal,
        owner_principal_id=owner_principal_id,
        scope_refs=scope_refs,
        snapshot_id=snapshot_id,
        input_hash=job_input_hash(inputs) if inputs is not None else "",
        correlation_id=correlation_id,
        provenance=(*provenance, BACKGROUND_PROVENANCE),
        now_utc=now,
    )
    row = session.get(JobRecord, payload["job_id"])
    row.runner_id = runner_id()
    row.heartbeat_at_utc = now
    row.progress_step = 0
    row.progress_total = max(1, steps_total)
    row.progress_label = first_step_label
    session.flush()
    payload.update(step=0, step_total=row.progress_total, step_label=first_step_label)
    return payload


def _serialise_owner(session: Session, owner_principal_id: str) -> None:
    """Make one owner's count-then-create a single step (PR 61 review).

    Without it two requests that arrive together both count the same active jobs and both
    create one, passing the per-owner limit. On PostgreSQL a transaction-scoped advisory lock
    keyed by the owner holds the second request until the first commits (or rolls back), so it
    counts the first one's job. SQLite admits one writer at a time to the database file and the
    desktop runs one user's requests in one process, so no lock is taken there.
    """

    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"background-jobs:{owner_principal_id}"},
    )


def run_background_job(
    factory: SessionFactory,
    job_id: str,
    work: BackgroundWork,
    *,
    steps_total: int,
) -> None:
    """Claim, run and publish one background job. Never raises."""

    with factory() as session:
        row = session.get(JobRecord, job_id, with_for_update=True, populate_existing=True)
        if row is None or row.status != JobState.QUEUED.value:
            return
        start_job(session, job_id)
        row.runner_id = runner_id()
        row.heartbeat_at_utc = datetime.now(UTC)
        session.commit()

    heartbeat = _Heartbeat(factory, job_id)
    heartbeat.start()
    progress = JobProgress(factory=factory, job_id=job_id, total=max(1, steps_total))
    try:
        with factory() as work_session:
            progress.work_session = work_session
            try:
                work(work_session, progress)
                locked = work_session.get(
                    JobRecord, job_id, with_for_update=True, populate_existing=True
                )
                if locked is None or locked.status != JobState.RUNNING.value:
                    # Cancelled (or swept) while the last step ran: publish nothing.
                    work_session.rollback()
                    return
                if progress.last_step and (locked.progress_step or 0) < progress.last_step[0]:
                    step, label = progress.last_step
                    record_job_step(work_session, job_id, step, progress.total, label)
                finish_job(work_session, job_id, output_refs=tuple(progress.output_refs))
                work_session.commit()
            except JobCancelled:
                work_session.rollback()
            except BackgroundJobFailure as failure:
                work_session.rollback()
                _fail(factory, job_id, failure.code, failure.reason, retryable=failure.retryable)
            except Exception as exc:  # noqa: BLE001 - every failure must end the job honestly
                work_session.rollback()
                code, retryable = _failure_code(exc)
                _fail(factory, job_id, code, _UNEXPECTED_REASON, retryable=retryable)
    except Exception as exc:  # noqa: BLE001 - the session itself failed (store unreachable)
        _fail(factory, job_id, _failure_code(exc)[0], _UNEXPECTED_REASON, retryable=True)
    finally:
        heartbeat.stop()


def _failure_code(exc: BaseException) -> tuple[str, bool]:
    """A stable code for an unexpected failure, and whether retrying may help.

    A database error carries SQLAlchemy's own ``code`` (``e3q8``), which names the driver
    error class, not the product failure, so it is recorded as the store being unavailable.
    """

    from sqlalchemy.exc import SQLAlchemyError

    if isinstance(exc, SQLAlchemyError):
        return "runtime_db_unavailable", True
    return _error_code(exc), isinstance(exc, (TimeoutError, ConnectionError))


def fail_orphaned_jobs(session: Session, *, now_utc: datetime | None = None) -> int:
    """Fail background jobs whose server process is gone; the caller commits.

    Returns the number of jobs failed.
    """

    now = now_utc or datetime.now(UTC)
    stale_before = now - timedelta(seconds=STALE_AFTER_SECONDS)
    rows = (
        session.query(JobRecord)
        .filter(JobRecord.status.in_([JobState.QUEUED.value, JobState.RUNNING.value]))
        .filter(JobRecord.heartbeat_at_utc.is_not(None))
        .all()
    )
    failed = 0
    for row in rows:
        if not _orphaned(row, stale_before):
            continue
        try:
            locked = session.get(
                JobRecord, row.job_id, with_for_update=True, populate_existing=True
            )
            if locked is None or locked.status not in (
                JobState.QUEUED.value,
                JobState.RUNNING.value,
            ):
                continue
            if locked.status == JobState.QUEUED.value:
                start_job(session, row.job_id, now_utc=now)
            fail_job(
                session,
                row.job_id,
                error_code=JOB_INTERRUPTED,
                error_message=_INTERRUPTED_REASON,
                retryable=True,
                now_utc=now,
            )
            failed += 1
        except ValueError:
            continue
    return failed


def fail_orphaned_jobs_quietly(factory: SessionFactory | None = None) -> int:
    """Run the orphan sweep in its own session; never raises (start-up and job reads)."""

    try:
        if factory is None:
            from eurogas_nexus.db.session import get_session_factory, resolve_database_url

            if resolve_database_url() is None:
                return 0
            factory = get_session_factory()
        with factory() as session:
            count = fail_orphaned_jobs(session)
            session.commit()
            return count
    except Exception:  # noqa: BLE001 - the sweep is housekeeping, never a failure
        return 0


def _orphaned(row: JobRecord, stale_before: datetime) -> bool:
    heartbeat = row.heartbeat_at_utc
    if heartbeat is not None and heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=UTC)
    if heartbeat is not None and heartbeat < stale_before:
        return True
    recorded = (row.runner_id or "").split(":")
    if len(recorded) != 3:
        return False
    host, pid, boot = recorded
    if host != socket.gethostname()[:80]:
        return False  # another host's process: only its heartbeat can tell
    if pid == str(os.getpid()):
        return boot != _BOOT_TOKEN  # this pid, an earlier boot (a restarted container)
    return not _process_alive(pid)


def _process_alive(pid: str) -> bool:
    try:
        os.kill(int(pid), 0)
    except (ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True
    return True


def _fail(factory: SessionFactory, job_id: str, code: str, reason: str, *, retryable: bool) -> None:
    try:
        with factory() as session:
            row = session.get(JobRecord, job_id, with_for_update=True, populate_existing=True)
            if row is None or row.status != JobState.RUNNING.value:
                return
            fail_job(
                session,
                job_id,
                error_code=code or "JOB_FAILED",
                error_message=reason,
                retryable=retryable,
            )
            session.commit()
    except Exception:  # noqa: BLE001 - the sweep fails the job if even this write fails
        return


class _Heartbeat:
    """Refresh one running job's heartbeat until stopped (a daemon thread)."""

    def __init__(self, factory: SessionFactory, job_id: str) -> None:
        self._factory = factory
        self._job_id = job_id
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"job-heartbeat-{job_id}", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                with self._factory() as session:
                    row = session.get(JobRecord, self._job_id, populate_existing=True)
                    if row is None or row.status != JobState.RUNNING.value:
                        return
                    row.heartbeat_at_utc = datetime.now(UTC)
                    session.commit()
            except Exception:  # noqa: BLE001 - a missed beat only ages the heartbeat
                continue
