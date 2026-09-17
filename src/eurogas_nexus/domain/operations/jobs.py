"""Unified Job contract (Architecture V2 08_DECISION_APPLICATION_AI.md section 5).

Long-running work in this product comes from ingestion, dataset builds,
optimisation, backtests, reporting and governed agent runs. Architecture V2 asks
those to converge on one lifecycle instead of each exposing its own run model, so a
user, an operator and the job telemetry all read the same states, the same fields
and the same failure vocabulary.

Common states: ``QUEUED``, ``RUNNING``, ``WAITING_FOR_INPUT``, ``SUCCEEDED``,
``FAILED``, ``CANCELLED``, ``EXPIRED``.

Fields: job id/type/version, principal, scope, snapshot id, input hash, progress,
status, start/finish, output refs, error code, retry/cancel, correlation id and
provenance.

Rules enforced here rather than documented only:

1. a terminal job never changes state again (a late progress write cannot resurrect
   a finished job);
2. progress never moves backwards;
3. only a cancellable, non-terminal job may be cancelled;
4. a failed job carries the stable error code from the product taxonomy, so the job
   list and the error surface cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum


class JobState(StrEnum):
    """Shared lifecycle for every long-running product operation."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class JobKind(StrEnum):
    """The work families Architecture V2 names for the shared model."""

    INGESTION = "INGESTION"
    DATASET_BUILD = "DATASET_BUILD"
    OPTIMISATION = "OPTIMISATION"
    BACKTEST = "BACKTEST"
    REPORT = "REPORT"
    AGENT_RUN = "AGENT_RUN"
    SNAPSHOT = "SNAPSHOT"


TERMINAL_JOB_STATES: frozenset[JobState] = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.EXPIRED}
)

# Allowed transitions. QUEUED may start or wait; a waiting job resumes; any active
# job may finish, fail, be cancelled or expire. Nothing leaves a terminal state.
_ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset(
        {JobState.RUNNING, JobState.WAITING_FOR_INPUT, JobState.CANCELLED, JobState.EXPIRED}
    ),
    JobState.RUNNING: frozenset(
        {
            JobState.RUNNING,
            JobState.WAITING_FOR_INPUT,
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.EXPIRED,
        }
    ),
    JobState.WAITING_FOR_INPUT: frozenset(
        {JobState.RUNNING, JobState.FAILED, JobState.CANCELLED, JobState.EXPIRED}
    ),
    JobState.SUCCEEDED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.EXPIRED: frozenset(),
}


def job_is_terminal(state: JobState) -> bool:
    """Whether the job has stopped for good."""

    return state in TERMINAL_JOB_STATES


def transition_allowed(current: JobState, target: JobState) -> bool:
    """Whether a state change is legal under the shared lifecycle."""

    return target in _ALLOWED_TRANSITIONS[current]


@dataclass(frozen=True, slots=True)
class Job:
    """One tracked operation."""

    job_id: str
    kind: JobKind
    status: JobState
    principal: str
    job_version: str = "job/v1"
    scope_refs: tuple[str, ...] = ()
    snapshot_id: str = ""
    input_hash: str = ""
    progress: float = 0.0
    created_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    output_refs: tuple[str, ...] = ()
    error_code: str = ""
    error_message: str = ""
    retryable: bool = False
    cancellable: bool = True
    correlation_id: str | None = None
    provenance: tuple[str, ...] = ()

    @property
    def terminal(self) -> bool:
        """Whether the job has stopped."""

        return job_is_terminal(self.status)

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration once both timestamps exist."""

        if not (self.started_at_utc and self.finished_at_utc):
            return None
        try:
            started = datetime.fromisoformat(self.started_at_utc)
            finished = datetime.fromisoformat(self.finished_at_utc)
        except ValueError:
            return None
        return (finished - started).total_seconds()


def job_progress(job: Job, value: float) -> Job:
    """Advance progress monotonically, never on a finished job.

    Raises:
        ValueError: the job is terminal (``job_already_finished``) or the value is
            out of range (``job_progress_out_of_range``).
    """

    if job.terminal:
        raise ValueError("job_already_finished")
    if not 0.0 <= value <= 1.0:
        raise ValueError("job_progress_out_of_range")
    if value < job.progress:
        return job
    return replace(job, progress=value)


def job_started(job: Job, *, now_utc: datetime | None = None) -> Job:
    """Move a job into RUNNING and stamp the start time."""

    if job.terminal:
        raise ValueError("job_already_finished")
    if not transition_allowed(job.status, JobState.RUNNING):
        raise ValueError("job_transition_not_allowed")
    now = _as_utc(now_utc)
    return replace(
        job,
        status=JobState.RUNNING,
        started_at_utc=job.started_at_utc or now.isoformat(),
    )


def job_succeeded(
    job: Job,
    *,
    output_refs: tuple[str, ...] = (),
    now_utc: datetime | None = None,
) -> Job:
    """Finish a job successfully."""

    return _finish(
        job,
        JobState.SUCCEEDED,
        output_refs=output_refs,
        now_utc=now_utc,
    )


def job_failed(
    job: Job,
    *,
    error_code: str,
    error_message: str = "",
    retryable: bool = False,
    now_utc: datetime | None = None,
) -> Job:
    """Fail a job with a stable taxonomy code."""

    if not (error_code or "").strip():
        raise ValueError("job_error_code_required")
    return _finish(
        job,
        JobState.FAILED,
        error_code=error_code.strip(),
        error_message=error_message,
        retryable=retryable,
        now_utc=now_utc,
    )


def job_cancelled(job: Job, *, now_utc: datetime | None = None) -> Job:
    """Cancel a job.

    Raises:
        ValueError: the job is terminal (``job_already_finished``) or not
            cancellable (``job_not_cancellable``).
    """

    if job.terminal:
        raise ValueError("job_already_finished")
    if not job.cancellable:
        raise ValueError("job_not_cancellable")
    return _finish(job, JobState.CANCELLED, now_utc=now_utc)


def _finish(
    job: Job,
    state: JobState,
    *,
    output_refs: tuple[str, ...] = (),
    error_code: str = "",
    error_message: str = "",
    retryable: bool = False,
    now_utc: datetime | None = None,
) -> Job:
    if job.terminal:
        raise ValueError("job_already_finished")
    if not transition_allowed(job.status, state):
        raise ValueError("job_transition_not_allowed")
    now = _as_utc(now_utc)
    return replace(
        job,
        status=state,
        progress=1.0 if state is JobState.SUCCEEDED else job.progress,
        finished_at_utc=now.isoformat(),
        started_at_utc=job.started_at_utc or now.isoformat(),
        output_refs=output_refs or job.output_refs,
        error_code=error_code,
        error_message=error_message,
        retryable=retryable,
        cancellable=False,
    )


def job_payload(job: Job) -> dict[str, object]:
    """API/telemetry shape: no secret, no free-form stack."""

    return {
        "job_id": job.job_id,
        "kind": job.kind.value,
        "job_version": job.job_version,
        "status": job.status.value,
        "principal": job.principal,
        "scope_refs": list(job.scope_refs),
        "snapshot_id": job.snapshot_id,
        "input_hash": job.input_hash,
        "progress": job.progress,
        "created_at_utc": job.created_at_utc,
        "started_at_utc": job.started_at_utc,
        "finished_at_utc": job.finished_at_utc,
        "duration_seconds": job.duration_seconds,
        "output_refs": list(job.output_refs),
        "error_code": job.error_code,
        "error_message": job.error_message,
        "retryable": job.retryable,
        "cancellable": job.cancellable,
        "correlation_id": job.correlation_id,
        "provenance": list(job.provenance),
    }


def _as_utc(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved.astimezone(UTC)
