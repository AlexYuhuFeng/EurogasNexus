"""Unified Data Platform public routes (Architecture V2 Wave 4).

Three additive read/write surfaces under the stable ``/api`` prefix:

- ``GET /api/data-products`` - the declared Data Product catalogue with the
  per-principal entitlement verdict and the freshness/provenance summary a
  business user may see (``07_DATA_PLATFORM.md`` section 3). It never returns
  API keys, secret values, scheduler internals or retry traces; those belong to
  the operator posture in section 4, already served by the Source Center.
- ``POST /api/analysis-snapshots`` - record an Analysis Snapshot from the
  current Active Context (section 6).
- ``GET /api/analysis-snapshots`` / ``GET /api/analysis-snapshots/{id}`` - read
  recent snapshots and one snapshot by its reproducibility reference.

Entitlement is evaluated per principal with the existing fail-closed helpers. A
product whose required family the caller is not entitled to is reported as
``restricted`` with no provenance block: it is never omitted and never rendered
as a measured zero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.dependencies.row_entitlement import current_principal
from eurogas_nexus.domain.data_platform.snapshots import (
    ACTIVE_CONTEXT_KEYS,
    UNSUPPORTED_ACTIVE_CONTEXT_KEYS,
)

router = APIRouter(tags=["data-platform"])

_MAX_ASSUMPTION_ITEMS = 50
_MAX_ASSUMPTION_KEY_LENGTH = 64
_MAX_ASSUMPTION_VALUE_LENGTH = 512


def _job_principal(request: Request) -> str:
    """The principal a tracked run is attributed to.

    The compatibility deployment token's identifier is not expressible in the principal
    vocabulary, so the job records the acting principal's name - the convention the
    dataset-build, optimisation, report and agent-run paths already follow.
    """

    identity = getattr(request.state, "identity", None)
    return identity.name if identity is not None else "public-api"


class AnalysisSnapshotCreateRequest(BaseModel):
    """Request body for recording an Analysis Snapshot.

    Attributes:
        as_of_utc: Instant the analysis context is valid as of; defaults to the
            creation time.
        active_context: Active Context values to record with the snapshot.
        manual_assumptions: Operator-supplied assumptions for this analysis.
    """

    model_config = ConfigDict(extra="forbid")

    as_of_utc: datetime | None = None
    active_context: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    manual_assumptions: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


@router.get("/api/data-products")
def list_data_products(request: Request) -> dict:
    """Return the declared Data Product catalogue for the calling principal.

    Returns:
        Enveloped catalogue. Each product carries its availability state, time
        basis, declared sources, serving surfaces, entitlement verdict and - only
        when the principal is entitled - a freshness/provenance summary.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` when the runtime database is
            configured but the provenance read fails.
    """

    principal = current_principal(request)
    catalogue, source, warnings = _catalogue_with_provenance(principal)
    return _env(catalogue, source=source, warnings=warnings)


@router.post("/api/analysis-snapshots")
def create_analysis_snapshot(body: AnalysisSnapshotCreateRequest, request: Request) -> dict:
    """Record an Analysis Snapshot and return its reproducibility reference.

    Returns:
        Enveloped descriptor payload, including ``snapshot_id`` and
        ``content_hash``. Every ``07_DATA_PLATFORM.md`` section 6 field is either
        resolved from runtime data or explicitly marked unavailable.

    Raises:
        HTTPException: 422 ``active_context_key_unsupported`` when the request
            names a context key the backend cannot express; 503
            ``runtime_db_not_configured`` when no runtime database is available.
    """

    _reject_unsupported_context_keys(body.active_context)
    _reject_oversized_assumptions(body.manual_assumptions)

    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": (
                    "An Analysis Snapshot is persisted evidence; a runtime database is "
                    "required to record one."
                ),
            },
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.application.data_platform_snapshots import build_analysis_snapshot
        from eurogas_nexus.application.jobs import track_job
        from eurogas_nexus.db.repositories.data_platform import create_analysis_snapshot
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            # Architecture V2 Wave 8: recording a snapshot is a run of its own family, so it is
            # tracked like every other one - the snapshot family is declared by
            # `JOB_RERUN_CONTRACTS` (it is the one family a re-run contract says is never
            # re-issued), and `/api/jobs` is where a run's artefacts are read back. The job row
            # commits in this session, with the snapshot it describes.
            with track_job(
                session,
                kind="SNAPSHOT",
                principal=_job_principal(request),
                # The scope a snapshot run has is the Active Context it froze, recorded as the
                # context's own references rather than invented.
                scope_refs=tuple(
                    f"{key.upper()}:{value}"
                    for key, value in sorted(body.active_context.items())
                ),
                inputs={
                    "as_of_utc": body.as_of_utc.isoformat() if body.as_of_utc else "",
                    "active_context": dict(body.active_context),
                    "manual_assumptions": dict(body.manual_assumptions or {}),
                },
                correlation_id=getattr(request.state, "request_id", None),
                provenance=("data-platform", "analysis-snapshot"),
            ) as job:
                descriptor = build_analysis_snapshot(
                    current_principal(request),
                    session=session,
                    active_context=body.active_context,
                    manual_assumptions=body.manual_assumptions,
                    as_of_utc=body.as_of_utc,
                )
                payload = create_analysis_snapshot(session, descriptor)
                job.add_output(f"analysis_snapshot:{payload['snapshot_id']}")
            session.commit()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    return _env(
        payload,
        source="runtime-postgresql",
        warnings=list(payload["warnings"]),
    )


@router.get("/api/analysis-snapshots")
def list_analysis_snapshots(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    gas_day: str | None = Query(default=None),
    created_by: str | None = Query(default=None),
) -> dict:
    """List recent Analysis Snapshots, newest first.

    Returns:
        Enveloped descriptor payloads.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` when the runtime database is
            configured but the read fails.
    """

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; no Analysis Snapshot can be listed."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.data_platform import list_analysis_snapshots
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = list_analysis_snapshots(
                session,
                limit=limit,
                gas_day=gas_day,
                created_by=created_by,
            )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    return _env(rows, source="runtime-postgresql")


@router.get("/api/analysis-snapshots/{snapshot_id}")
def get_analysis_snapshot(snapshot_id: str, request: Request) -> dict:
    """Return one Analysis Snapshot by its reproducibility reference.

    Returns:
        Enveloped descriptor payload.

    Raises:
        HTTPException: 404 when no snapshot carries that id; 503
            ``runtime_db_unavailable`` when the runtime database is configured but
            the read fails.
    """

    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": "A runtime database is required to read an Analysis Snapshot.",
            },
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.data_platform import get_analysis_snapshot
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            payload = get_analysis_snapshot(session, snapshot_id)
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "analysis_snapshot_not_found",
                "message": f"No Analysis Snapshot is recorded for {snapshot_id!r}.",
            },
        )
    return _env(payload, source="runtime-postgresql", warnings=list(payload["warnings"]))


def _catalogue_with_provenance(principal: Any) -> tuple[dict, str, list[str]]:
    """Build the catalogue with a runtime provenance read when one is available.

    Returns:
        ``(catalogue, source_label, warnings)``. A configured-but-unavailable
        database degrades to a catalogue without provenance rather than failing
        the read: the declared contract stays visible and every affected product
        reports ``UNKNOWN`` freshness instead of a fabricated zero.
    """

    if not _db_is_configured():
        return (
            _catalogue(principal, session=None),
            "runtime-db-not-configured",
            ["Runtime DB is not configured; freshness summaries are unavailable."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            catalogue = _catalogue(principal, session=session)
        return catalogue, "runtime-postgresql", []
    except sqlalchemy_error:
        return (
            _catalogue(principal, session=None),
            "runtime-db-not-configured",
            ["Runtime DB is configured but unavailable; freshness is UNKNOWN."],
        )


def _catalogue(principal: Any, *, session: Any) -> dict:
    """Build the catalogue through the application service (deferred import)."""

    from eurogas_nexus.application.data_products import build_data_product_catalogue

    return build_data_product_catalogue(principal, session=session)


def _reject_unsupported_context_keys(active_context: dict[str, Any]) -> None:
    """Fail closed on Active Context keys the backend cannot express."""

    unsupported = sorted(set(active_context) - set(ACTIVE_CONTEXT_KEYS))
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "active_context_key_unsupported",
                "message": (
                    "These Active Context keys are not expressible by the backend yet and "
                    "are refused rather than silently dropped."
                ),
                "unsupported_keys": unsupported,
                "declared_unsupported_dimensions": list(UNSUPPORTED_ACTIVE_CONTEXT_KEYS),
            },
        )


def _reject_oversized_assumptions(manual_assumptions: dict[str, Any]) -> None:
    """Bound the manual-assumption payload so a snapshot stays a descriptor."""

    if len(manual_assumptions) > _MAX_ASSUMPTION_ITEMS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "manual_assumptions_too_many",
                "message": f"At most {_MAX_ASSUMPTION_ITEMS} manual assumptions are accepted.",
            },
        )
    for key, value in manual_assumptions.items():
        if len(key) > _MAX_ASSUMPTION_KEY_LENGTH:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "manual_assumption_key_too_long",
                    "message": f"Assumption key exceeds {_MAX_ASSUMPTION_KEY_LENGTH} characters.",
                },
            )
        if isinstance(value, str) and len(value) > _MAX_ASSUMPTION_VALUE_LENGTH:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "manual_assumption_value_too_long",
                    "message": (
                        f"Assumption value exceeds {_MAX_ASSUMPTION_VALUE_LENGTH} characters."
                    ),
                },
            )


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for data-platform reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _env(data: object, *, source: str, warnings: list[str] | None = None) -> dict:
    """Envelope with research-only markers and de-duplicated warnings."""

    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "lineage": [source],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }
