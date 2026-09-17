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
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
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
