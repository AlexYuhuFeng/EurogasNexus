"""Analysis Snapshot reference verification (Architecture V2 Wave 4).

A produced result that cites a reproducibility reference must cite one the
platform actually recorded. This is the single implementation of that check, so
every run path that accepts an optional ``analysis_snapshot_id`` refuses an
unknown reference with the same status codes and the same error codes:

- ``503 runtime_db_not_configured`` when a reference was supplied but no runtime
  database can verify it (fail closed: an unverifiable citation is not accepted);
- ``503 runtime_db_unavailable`` on a failed read;
- ``422 analysis_snapshot_not_found`` when no persisted snapshot carries the id.

A caller that supplies no reference is unaffected: the field is optional and
additive, so callers that do not cite a snapshot keep their previous behaviour.
"""

from __future__ import annotations

from fastapi import HTTPException


def require_known_analysis_snapshot(
    snapshot_id: str | None,
    *,
    resource: str = "route-cost",
) -> None:
    """Fail closed when a supplied Analysis Snapshot reference does not exist.

    Args:
        snapshot_id: The caller-supplied reproducibility reference, or ``None``
            when the caller supplied none.
        resource: Surface label used in the 503 message (the status codes and
            error codes are identical on every run path).

    Raises:
        HTTPException: See the module docstring for the exact refusal contract.
    """

    if not snapshot_id:
        return

    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": (
                    "An Analysis Snapshot reference cannot be verified without a "
                    "runtime database."
                ),
                "analysis_snapshot_id": snapshot_id,
            },
        )

    from sqlalchemy.exc import SQLAlchemyError

    try:
        from eurogas_nexus.db.repositories.data_platform import get_analysis_snapshot
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            known = get_analysis_snapshot(session, snapshot_id)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_unavailable",
                "message": (
                    f"Runtime database is configured but unavailable for {resource} reads."
                ),
                "error_class": exc.__class__.__name__,
            },
        ) from exc
    if known is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "analysis_snapshot_not_found",
                "message": f"No Analysis Snapshot is recorded for {snapshot_id!r}.",
                "analysis_snapshot_id": snapshot_id,
            },
        )
