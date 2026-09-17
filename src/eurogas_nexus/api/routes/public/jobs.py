"""Unified Job endpoints (Architecture V2 Wave 8 section 5).

Jobs are the shared lifecycle for ingestion, dataset builds, optimisation,
backtests, reporting and governed agent work. These endpoints are read-only apart
from cancellation, which is refused for a terminal or non-cancellable job rather
than silently ignored.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs")
def get_jobs(
    request: Request,
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    principal: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """List tracked jobs, newest first."""

    warnings: list[str] = []
    data: list = []
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.jobs import list_jobs
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = list_jobs(
                    session, status=status, kind=kind, principal=principal, limit=limit
                )
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, warnings=warnings)


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    """Read one tracked job."""

    warnings: list[str] = []
    data: dict | None = None
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.jobs import get_job as load_job
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = load_job(session, job_id)
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    if data is None and "RUNTIME_DB_NOT_CONFIGURED" not in warnings:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_job", "message": f"No job {job_id!r} is tracked."},
        )
    return _env(data, warnings=warnings)


@router.post("/api/jobs/{job_id}/cancel")
def post_cancel_job(job_id: str, request: Request) -> dict:
    """Cancel a cancellable, non-terminal job (governed operation)."""

    warnings: list[str] = []
    data: dict | None = None
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.jobs import cancel_job
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = cancel_job(session, job_id)
                session.commit()
        except ValueError as exc:
            raise _cancel_error(str(exc), job_id) from exc
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, warnings=warnings)


def _cancel_error(reason: str, job_id: str) -> HTTPException:
    if reason == "unknown_job":
        return HTTPException(
            status_code=404,
            detail={"error": "unknown_job", "message": f"No job {job_id!r} is tracked."},
        )
    if reason == "job_already_finished":
        return HTTPException(
            status_code=409,
            detail={
                "error": "job_already_finished",
                "message": "The job has already finished and cannot be cancelled.",
            },
        )
    if reason == "job_not_cancellable":
        return HTTPException(
            status_code=409,
            detail={
                "error": "job_not_cancellable",
                "message": "The job is not cancellable.",
            },
        )
    return HTTPException(
        status_code=422,
        detail={"error": reason, "message": "The job request was rejected."},
    )


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _env(data: object, *, warnings: list[str]) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": False,
            "source_references": ["job-records", "audit-events"],
            "warnings": warnings,
        },
    }
