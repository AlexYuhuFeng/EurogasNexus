"""Internal operator routes for provider certification evidence."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from eurogas_nexus.domain.ingestion.certification import validate_certification_payload
from eurogas_nexus.security.internal_api import (
    InternalApiAuthError,
    validate_internal_operator_headers,
)

router = APIRouter(prefix="/sources", tags=["internal-sources"])


class CertificationUpsertRequest(BaseModel):
    source_system: str
    stage: str
    checks: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


@router.post("/certification")
def upsert_source_certification(
    body: CertificationUpsertRequest,
    request: Request,
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None,
        alias="X-Eurogas-Internal-Token",
    ),
) -> dict:
    """Record provider certification evidence (simulated-to-live gate).

    Fail closed: unknown stages, missing required checks, and an unconfigured
    runtime DB all reject the write.
    """

    try:
        principal = validate_internal_operator_headers(
            token=x_eurogas_internal_token,
            principal=x_eurogas_principal,
        )
    except InternalApiAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    try:
        validate_certification_payload(
            source_system=body.source_system,
            stage=body.stage,
            checks=body.checks,
            evidence=body.evidence,
            evaluated_by=principal,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_certification", "message": str(exc)},
        ) from exc

    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_required",
                "message": "RUNTIME_STORE_DATABASE_URL is required for certification writes.",
            },
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.certification import upsert_provider_certification
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            result = upsert_provider_certification(
                session,
                source_system=body.source_system,
                stage=body.stage,
                checks=body.checks,
                evidence=body.evidence,
                evaluated_by=principal,
                note=body.note,
            )
            session.commit()
        return _env(result, request)
    except sqlalchemy_error as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_unavailable",
                "message": "Runtime database is unavailable for certification writes.",
                "error_class": exc.__class__.__name__,
            },
        ) from exc


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _env(data: object, _request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": [],
        },
    }
