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


@dataclass(frozen=True, slots=True)
class JobRerunContract:
    """What can honestly be done with a finished job's *work*, per kind.

    Wave 8 recorded "job replay" as an open question - whether a recorded job can be re-run - and
    the answer is a property of the record, not a feature to switch on:

    - a job row is **bookkeeping about work**. It stores a *hash* of the inputs
      (``input_hash``), a scope and output *references*; it does not store the request that
      produced it. So no kind can be re-issued *from its job row*, and a contract that claimed
      otherwise would be describing something the schema cannot support - which the fitness test
      beside this module checks against the table itself.
    - where a kind's **own** record already holds what the work needs (an optimisation run's input
      snapshot, a dataset spec, an agent run's objective), the honest act is to issue a *new* run
      of that kind through the path that owns the inputs. That is a new job with a new identity,
      not a replay of the old one.
    - a new run therefore always needs **fresh authorisation** and is never assumed idempotent:
      the inputs may no longer be entitled, the deployment may have moved on, and a second run can
      produce different numbers by design.
    - recording a snapshot is the one act that can never be repeated: the second recording would
      be a *different* point in time claiming the same reference.

    Attributes:
        kind: The work family this contract answers for.
        rerun_possible: Whether new work of this kind can be issued at all with the same inputs.
        input_owner: Where those inputs actually live (table or surface), or "" when they are not
            retained anywhere.
        new_run_path: The public path that issues a new run of this kind, or "" when none exists.
        reason: Why this is the answer, in the terms an operator would ask it.
    """

    kind: JobKind
    rerun_possible: bool
    input_owner: str
    new_run_path: str
    reason: str

    @property
    def from_job_row(self) -> bool:
        """Never true: the row keeps a hash of the inputs, not the inputs."""

        return False


#: One contract per kind. A new kind must answer this question when it is declared, because the
#: fitness test beside this module fails on a kind with no contract.
JOB_RERUN_CONTRACTS: tuple[JobRerunContract, ...] = (
    JobRerunContract(
        kind=JobKind.INGESTION,
        rerun_possible=True,
        input_owner="source registry (source_id, trigger, reason)",
        new_run_path="/api/sources/{source_id}/run",
        reason=(
            "An ingestion run is defined by its source, not by a request body: queueing a new run "
            "is the operator path, and it is a new run rather than a repeat of the recorded one."
        ),
    ),
    JobRerunContract(
        kind=JobKind.DATASET_BUILD,
        rerun_possible=True,
        input_owner="research dataset spec (dataset_spec_id)",
        new_run_path="/api/research/datasets",
        reason=(
            "The build is reproducible from the stored spec, and the spec - not the job - is the "
            "input: a build after the spec changed is a different artefact under the same id."
        ),
    ),
    JobRerunContract(
        kind=JobKind.OPTIMISATION,
        rerun_possible=True,
        input_owner="optimization_runs.input_snapshot",
        new_run_path="/api/route-cost/resource-pool/optimize",
        reason=(
            "The optimisation run keeps its input snapshot, so a re-run is possible from the run "
            "row - as a new run with a new id, authorised again and compared rather than merged."
        ),
    ),
    JobRerunContract(
        kind=JobKind.BACKTEST,
        rerun_possible=True,
        input_owner="strategy run (scenario, frozen version, period)",
        new_run_path="/api/strategy-runs",
        reason=(
            "A backtest is reproducible from its frozen version and period; the engine version is "
            "recorded too, so a re-run on a newer engine is a different measurement and says so."
        ),
    ),
    JobRerunContract(
        kind=JobKind.REPORT,
        rerun_possible=True,
        input_owner="generated report row (title, selections, window)",
        new_run_path="/api/reports/portfolio",
        reason=(
            "A report can be generated again, but it is a filed artefact: the second run is a new "
            "report, and overwriting the first would destroy the evidence the job cited."
        ),
    ),
    JobRerunContract(
        kind=JobKind.AGENT_RUN,
        rerun_possible=True,
        input_owner="agent run row (objective, profile, period, frozen version)",
        new_run_path="/api/agent/research",
        reason=(
            "A research run can be repeated from its recorded objective and profile. Its findings "
            "are evidence of that run, so a repeat adds a run rather than replacing the chain."
        ),
    ),
    JobRerunContract(
        kind=JobKind.SNAPSHOT,
        rerun_possible=False,
        input_owner="",
        new_run_path="",
        reason=(
            "A snapshot records a point in time. Recording it again later would produce a "
            "different snapshot under the same reference, so it is never replayed."
        ),
    ),
)


def job_rerun_contract(kind: JobKind) -> JobRerunContract:
    """The declared answer for one kind.

    Raises:
        KeyError: the kind has no contract, which is a programming error rather than a runtime
            state: every declared kind answers this question.
    """

    for contract in JOB_RERUN_CONTRACTS:
        if contract.kind == kind:
            return contract
    raise KeyError(f"No rerun contract is declared for job kind {kind!r}.")


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
