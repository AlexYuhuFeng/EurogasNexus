"""Public data-operations and source-operator endpoints.

All write/operator actions are declared OPERATOR in the permission registry
and are enforced by the release profile. The development profile keeps them
open for local testing but still records an explicit actor.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.application.dataops_observability import emit_event
from eurogas_nexus.domain.dataops.contracts import IngestionTriggerType
from eurogas_nexus.domain.ingestion.certification import (
    validate_certification_payload,
)

router = APIRouter(tags=["source-operations"])

MAX_BACKFILL_DAYS = 31


class SourceRunRequest(BaseModel):
    """Request one manual operator run."""

    reason: str = Field(default="operator-requested", max_length=512)
    dataset: str | None = Field(default=None, max_length=128)


class SourceBackfillRequest(BaseModel):
    """Request an explicit, auditable backfill window."""

    start_utc: datetime
    end_utc: datetime
    reason: str = Field(min_length=1, max_length=512)
    dry_run: bool = False


class SourceRetryRequest(BaseModel):
    """Retry one failed run as an explicit recovery run."""

    run_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="operator-retry", max_length=512)


class SourceEnabledRequest(BaseModel):
    """Enable or disable scheduler participation for one source."""

    enabled: bool
    reason: str = Field(default="operator-requested", max_length=512)


class CertificationUpsertRequest(BaseModel):
    """Record certification evidence for one source/dataset/environment."""

    dataset: str = Field(default="", max_length=128)
    environment: str = Field(default="deployment", max_length=32)
    stage: str = Field(min_length=1, max_length=32)
    checks: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=4000)
    adapter_version: str | None = Field(default=None, max_length=64)
    credential_label: str | None = Field(default=None, max_length=128)
    entitlement_scope: str | None = Field(default=None, max_length=64)
    sample_period_start_utc: datetime | None = None
    sample_period_end_utc: datetime | None = None
    tests_performed: list[str] = Field(default_factory=list)
    expires_at_utc: datetime | None = None
    evidence_ref: str | None = Field(default=None, max_length=256)


@router.get("/api/sources/{source_id}/health")
def get_source_health(source_id: str, request: Request) -> dict:
    """Return one source's backend-owned operational health."""

    _require_db()
    from eurogas_nexus.application.dataops_runtime import source_health

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            data = source_health(session, source_id=source_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")
        return _env(data, request, source="runtime-postgresql")
    except HTTPException:
        raise
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/sources/{source_id}/runs")
def get_source_runs(
    source_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List persisted ingestion runs for one source."""

    _require_db()
    from eurogas_nexus.db.repositories import dataops as dataops_repository

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            data = dataops_repository.list_source_runs(session, source_id, limit=limit)
            for row in data:
                row["issues"] = dataops_repository.list_run_issues(session, row["run_id"])
        return _env(data, request, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.post("/api/sources/{source_id}/run")
def post_source_run(source_id: str, body: SourceRunRequest, request: Request) -> dict:
    """Queue a MANUAL ingestion run (operator action, no execution here)."""

    from eurogas_nexus.application.dataops_runtime import request_operator_run

    _require_db()
    try:
        with _session() as session:
            data = request_operator_run(
                session,
                source_id=source_id,
                trigger_type=IngestionTriggerType.MANUAL,
                reason=body.reason,
            )
            session.commit()
        _emit_operator_event("run", source_id, actor=_actor(request))
        return _env(data, request, source="runtime-postgresql")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.post("/api/sources/{source_id}/backfill")
def post_source_backfill(
    source_id: str,
    body: SourceBackfillRequest,
    request: Request,
) -> dict:
    """Queue an explicit BACKFILL run; backfill never claims a live slot."""

    from eurogas_nexus.application.dataops_runtime import request_operator_run

    _require_db()
    start = _as_utc(body.start_utc)
    end = _as_utc(body.end_utc)
    if start >= end:
        raise HTTPException(status_code=422, detail="start_utc must be before end_utc.")
    if end - start > timedelta(days=MAX_BACKFILL_DAYS):
        raise HTTPException(
            status_code=422,
            detail=f"Backfill window exceeds {MAX_BACKFILL_DAYS} days.",
        )
    try:
        with _session() as session:
            data = request_operator_run(
                session,
                source_id=source_id,
                trigger_type=IngestionTriggerType.BACKFILL,
                window_start_utc=start,
                window_end_utc=end,
                reason=f"{body.reason}{' (dry-run)' if body.dry_run else ''}",
            )
            session.commit()
        _emit_operator_event("backfill", source_id, actor=_actor(request))
        return _env(data, request, source="runtime-postgresql")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.post("/api/sources/{source_id}/retry")
def post_source_retry(
    source_id: str,
    body: SourceRetryRequest,
    request: Request,
) -> dict:
    """Retry one failed run as an explicit RECOVERY run."""

    from eurogas_nexus.application.dataops_runtime import request_operator_run
    from eurogas_nexus.db.repositories import dataops as dataops_repository

    _require_db()
    try:
        with _session() as session:
            failed = dataops_repository.get_source_run(session, body.run_id)
            if failed is None or failed.source_id != source_id:
                raise HTTPException(status_code=404, detail="Failed run not found for source.")
            data = request_operator_run(
                session,
                source_id=source_id,
                trigger_type=IngestionTriggerType.RECOVERY,
                reason=body.reason,
                retry_of_run_id=body.run_id,
            )
            session.commit()
        _emit_operator_event("retry", source_id, actor=_actor(request))
        return _env(data, request, source="runtime-postgresql")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.patch("/api/sources/{source_id}/enabled")
def patch_source_enabled(
    source_id: str,
    body: SourceEnabledRequest,
    request: Request,
) -> dict:
    """Enable or disable scheduler participation for one source."""

    from eurogas_nexus.application.dataops_runtime import set_source_enabled

    _require_db()
    try:
        with _session() as session:
            data = set_source_enabled(
                session,
                source_id=source_id,
                enabled=body.enabled,
            )
            session.commit()
        _emit_operator_event(
            "enable" if body.enabled else "disable",
            source_id,
            actor=_actor(request),
        )
        return _env(data, request, source="runtime-postgresql")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/source-certifications")
def list_source_certifications(request: Request) -> dict:
    """List persisted certification records (no credential material)."""

    _require_db()
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.certification import list_certifications

        with _session() as session:
            data = list_certifications(session)
        return _env(data, request, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.post("/api/source-certifications/{source_id}/certify")
def post_source_certification(
    source_id: str,
    body: CertificationUpsertRequest,
    request: Request,
) -> dict:
    """Record certification evidence for one source (operator action)."""

    _require_db()
    provider = _provider_for_source_id(source_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")
    try:
        validate_certification_payload(
            source_system=provider,
            stage=body.stage,
            checks=body.checks,
            evidence=body.evidence,
            evaluated_by=_actor(request),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_certification", "message": str(exc)},
        ) from exc
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.certification import upsert_provider_certification

        with _session() as session:
            data = upsert_provider_certification(
                session,
                source_system=provider,
                stage=body.stage,
                checks=body.checks,
                evidence=body.evidence,
                evaluated_by=_actor(request),
                note=body.note,
                dataset=body.dataset,
                environment=body.environment,
                adapter_version=body.adapter_version,
                credential_label=body.credential_label,
                entitlement_scope=body.entitlement_scope,
                sample_period_start_utc=body.sample_period_start_utc,
                sample_period_end_utc=body.sample_period_end_utc,
                tests_performed=body.tests_performed,
                expires_at_utc=body.expires_at_utc,
                evidence_ref=body.evidence_ref,
            )
            session.commit()
        return _env(data, request, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/runtime/source-operations")
def get_runtime_source_operations(request: Request) -> dict:
    """Return scheduler/source-operations health for the runtime workspace."""

    _require_db()
    from eurogas_nexus.application.dataops_runtime import runtime_source_operations

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            data = runtime_source_operations(session)
        return _env(data, request, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/runtime/metrics")
def get_runtime_metrics(request: Request) -> dict:
    """Expose low-cardinality data-operations metrics (Prometheus text)."""

    _require_db()
    from eurogas_nexus.application.dataops_observability import prometheus_metrics

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            body = prometheus_metrics(session)
        return {
            "data": body,
            "meta": {
                "research_only": True,
                "human_review_required": False,
                "source_references": ["runtime-postgresql"],
                "content_type": "text/plain; version=0.0.4",
                "warnings": [],
            },
        }
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _provider_for_source_id(source_id: str) -> str | None:
    from eurogas_nexus.domain.dataops.registry import definition_for_source

    definition = definition_for_source(source_id)
    return definition.provider if definition is not None else None


def _require_db() -> None:
    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_required",
                "message": "RUNTIME_STORE_DATABASE_URL is required for data operations.",
            },
        )


def _session():
    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()()


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is unavailable for data operations.",
            "error_class": exc.__class__.__name__,
        },
    )


def _env(data: object, _request: Request, *, source: str) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": [],
        },
    }


def _actor(request: Request) -> str:
    value = getattr(request.state, "actor", None)
    if value:
        return str(value)
    identity = getattr(request.state, "identity", None)
    if identity is not None:
        return str(identity.principal_id)
    return "operator"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _emit_operator_event(action: str, source_id: str, *, actor: str) -> None:
    emit_event(
        event=f"source.{action}.requested",
        source_id=source_id,
        level="info",
        details={"actor": actor},
    )
