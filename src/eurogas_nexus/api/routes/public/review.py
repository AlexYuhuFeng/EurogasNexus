"""Trader-review decision endpoints (persisted + audited)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.domain.ontology.vocabulary import ReviewDecisionValue, ReviewEntityType

router = APIRouter(tags=["review"])


class ReviewDecisionRequest(BaseModel):
    entity_type: ReviewEntityType
    entity_id: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=64)
    decision: ReviewDecisionValue
    note: str | None = Field(default=None, max_length=2000)


@router.post("/api/review/decisions")
def post_review_decision(body: ReviewDecisionRequest, request: Request) -> dict:
    """Record a trader review decision (persisted and audited)."""

    warnings: list[str] = []
    data: dict | None = None
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.review import record_review_decision
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = record_review_decision(
                    session,
                    entity_type=body.entity_type.value,
                    entity_id=body.entity_id,
                    actor=body.actor,
                    decision=body.decision.value,
                    note=body.note,
                )
                session.commit()
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, request, warnings=warnings)


@router.get("/api/review/decisions")
def get_review_decisions(
    request: Request,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List review decisions, newest first."""

    warnings: list[str] = []
    data: list = []
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.review import list_review_decisions
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = list_review_decisions(
                    session,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    limit=limit,
                )
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, request, warnings=warnings)


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _env(data: object, _request: Request, *, warnings: list[str]) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["review", "audit-events"],
            "warnings": warnings,
        },
    }
