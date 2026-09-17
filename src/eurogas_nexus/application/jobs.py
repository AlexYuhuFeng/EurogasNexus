"""Job tracking for long-running operations (Architecture V2 Wave 8).

The unified Job contract only earns its keep if existing work registers into it.
:func:`track_job` is the single seam: a handler wraps the work it already does, the
tracker creates the job, records success with the artefacts it produced or failure
with a stable taxonomy code, and never changes what the handler returns or raises.

Design notes:

- the job row is written in the **caller's session**, so a job cannot claim an
  outcome the surrounding transaction did not commit;
- a failure inside the tracker never replaces the original error: the job is
  finished as FAILED best-effort and the exception propagates unchanged;
- deployment without a configured runtime store is not an error for callers that
  merely *run* work: tracking is skipped and the work proceeds.

:func:`run_tracked_job` is the same seam for work that has no session of its own
(a pure computation such as the resource-pool optimisation): it opens a tracking
session, records the outcome and returns exactly what the work returned.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.db.repositories.jobs import (
    create_job,
    fail_job,
    finish_job,
    start_job,
)


@dataclass(slots=True)
class JobHandle:
    """The tracker's view of the job being run."""

    job_id: str
    kind: str
    principal: str
    output_refs: list[str]

    def add_output(self, reference: str) -> None:
        """Record an artefact the operation produced."""

        if reference and reference not in self.output_refs:
            self.output_refs.append(reference)


def job_input_hash(payload: Any) -> str:
    """Stable hash of the inputs a job ran with, for reproducibility."""

    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@contextmanager
def track_job(
    session: Session | None,
    *,
    kind: str,
    principal: str,
    scope_refs: tuple[str, ...] = (),
    snapshot_id: str = "",
    inputs: Any = None,
    correlation_id: str | None = None,
    provenance: tuple[str, ...] = (),
) -> Iterator[JobHandle]:
    """Run work under the shared job lifecycle.

    Yields a handle whose ``add_output`` records produced artefacts. On an
    exception the job is failed with ``error_code`` taken from the exception's
    ``code``/``error`` attribute when present, otherwise the taxonomy fallback for
    the failure family, and the exception is re-raised untouched.
    """

    if session is None:
        # No runtime store: run the work untracked rather than refusing it.
        yield JobHandle(job_id="", kind=kind, principal=principal, output_refs=[])
        return

    job = create_job(
        session,
        kind=kind,
        principal=principal,
        scope_refs=scope_refs,
        snapshot_id=snapshot_id,
        input_hash=job_input_hash(inputs) if inputs is not None else "",
        correlation_id=correlation_id,
        provenance=provenance,
    )
    handle = JobHandle(
        job_id=str(job["job_id"]), kind=kind, principal=principal, output_refs=[]
    )
    start_job(session, handle.job_id)
    try:
        yield handle
    except BaseException as exc:  # noqa: BLE001 - the original error must propagate
        _fail_quietly(session, handle.job_id, exc)
        raise
    finish_job(session, handle.job_id, output_refs=tuple(handle.output_refs))


def _fail_quietly(session: Session, job_id: str, exc: BaseException) -> None:
    """Mark the job failed without ever masking the original exception."""

    try:
        fail_job(
            session,
            job_id,
            error_code=_error_code(exc),
            error_message=exc.__class__.__name__,
            retryable=isinstance(exc, (TimeoutError, ConnectionError)),
        )
    except Exception:  # noqa: BLE001 - tracking must not break the real failure path
        return


def _error_code(exc: BaseException) -> str:
    """A stable code for the failure: the exception's own, or a family fallback."""

    for attribute in ("code", "error", "error_code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        for key in ("error", "code"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    from eurogas_nexus.domain.operations.error_taxonomy import code_for_status

    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return code_for_status(status)
    return "JOB_FAILED"


def run_tracked_job(
    work: Callable[[JobHandle], Any],
    *,
    kind: str,
    principal: str,
    scope_refs: tuple[str, ...] = (),
    snapshot_id: str = "",
    inputs: Any = None,
    correlation_id: str | None = None,
    provenance: tuple[str, ...] = (),
) -> Any:
    """Run work that has no session of its own under the shared job lifecycle.

    Some long-running paths only compute: the resource-pool optimisation reads
    its inputs from the request body and writes nothing, so it has no session to
    write its job row in. This opens one, tracks the work and commits the job row
    once the outcome is known, so the run still appears in ``/api/jobs``.

    The guarantees are the ones :func:`track_job` already gives a caller:

    - a deployment without a runtime store runs the work untracked rather than
      refusing it;
    - a store that cannot even accept the job (configured but unreachable, or
      migrated without ``job_records``) also runs the work untracked, so tracking
      never turns a computation into a failure;
    - the caller's own return value is returned unchanged and the caller's own
      exception propagates untouched, with the FAILED outcome the tracker
      recorded committed best-effort first;
    - the job row is written only after the work's outcome is known.

    Args:
        work: The operation, receiving the :class:`JobHandle` to record artefacts
            on.
        kind: Job kind (a :class:`~eurogas_nexus.domain.operations.jobs.JobKind`
            value).
        principal: Principal the run is attributed to.
        scope_refs: References the run is scoped to.
        snapshot_id: The Analysis Snapshot the run was computed against, when the
            caller cited one.
        inputs: The run's inputs, hashed for reproducibility.
        correlation_id: Request correlation id, when one is available.
        provenance: Free-form provenance labels.

    Returns:
        Whatever ``work`` returns.
    """

    spec = {
        "kind": kind,
        "principal": principal,
        "scope_refs": scope_refs,
        "snapshot_id": snapshot_id,
        "inputs": inputs,
        "correlation_id": correlation_id,
        "provenance": provenance,
    }
    session = _open_tracking_session()
    if session is None:
        return work(_untracked_handle(kind=kind, principal=principal))

    tracker = track_job(session, **spec)
    try:
        try:
            handle = tracker.__enter__()
        except Exception:  # noqa: BLE001 - tracking must not change the outcome
            # The store cannot accept the job at all: run the work untracked.
            return work(_untracked_handle(kind=kind, principal=principal))
        try:
            result = work(handle)
        except BaseException as exc:  # noqa: BLE001 - the original error propagates
            # Exiting records FAILED with the exception's stable code; the row is
            # then committed so /api/jobs shows the failure that did happen.
            _exit_tracking_quietly(tracker, exc)
            _commit_quietly(session)
            raise
        _finish_tracking_quietly(session, tracker, handle)
        _commit_quietly(session)
        return result
    finally:
        _close_quietly(session)


def _untracked_handle(*, kind: str, principal: str) -> JobHandle:
    """Return the handle used when no job row can be written."""

    return JobHandle(job_id="", kind=kind, principal=principal, output_refs=[])


def _open_tracking_session() -> Session | None:
    """Open a session for job tracking, or ``None`` when none is available."""

    try:
        from eurogas_nexus.db.session import get_session_factory

        return get_session_factory()()
    except Exception:  # noqa: BLE001 - tracking is best effort, never fatal
        return None


def _exit_tracking_quietly(tracker: Any, exc: BaseException) -> None:
    """Exit the tracker on a failure, keeping the caller's exception propagating."""

    try:
        tracker.__exit__(type(exc), exc, exc.__traceback__)
    except BaseException:  # noqa: BLE001 - never mask the caller's own failure
        return


def _finish_tracking_quietly(session: Session, tracker: Any, handle: JobHandle) -> None:
    """Finish the job on success, failing it quietly if it cannot be finished."""

    try:
        tracker.__exit__(None, None, None)
    except BaseException as exc:  # noqa: BLE001 - the work itself did succeed
        # Never leave a job stuck in RUNNING: a terminal, honest outcome beats a
        # silent one, and the caller's successful result is returned regardless.
        _fail_quietly(session, handle.job_id, exc)


def _commit_quietly(session: Session) -> None:
    """Commit the job outcome, rolling back when the store refuses it."""

    try:
        session.commit()
    except Exception:  # noqa: BLE001 - a lost job row must not fail the run
        try:
            session.rollback()
        except Exception:  # noqa: BLE001 - the session is already unusable
            return


def _close_quietly(session: Session) -> None:
    """Close a tracking session without raising."""

    try:
        session.close()
    except Exception:  # noqa: BLE001 - closing must never mask an outcome
        return
