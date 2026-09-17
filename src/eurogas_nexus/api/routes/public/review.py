"""Trader-review decision endpoints (persisted + audited).

A trader review decision is a governance act, so the record and the audit event name the
actor. That actor is the **authenticated identity**, never the request body: W0-03 C13 found
this path taking its actor from a free-text field and repeating it as the audit event's
principal, so a caller could attribute a decision to somebody who never made it. The rule now
lives in :mod:`eurogas_nexus.api.dependencies.acting_actor`, and a caller that still sends an
``actor`` is told its claim was not used rather than silently overruled.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.api.dependencies.acting_actor import acting_actor
from eurogas_nexus.domain.ontology.vocabulary import ReviewDecisionValue, ReviewEntityType

router = APIRouter(tags=["review"])


class ReviewDecisionRequest(BaseModel):
    """One trader review decision payload.

    Attributes:
        entity_type: Artifact kind under review.
        entity_id: Artifact id (1-128 chars).
        actor: Retained for backward compatibility with callers that still send it.
            The platform records the authenticated identity instead and never uses
            this field as the actor; a value that disagrees is reported as a warning
            (``ACTOR_CLAIM_IGNORED``) rather than believed.
        decision: ACCEPTED / REJECTED / NEEDS_ATTENTION.
        note: Optional review note (max 2000 chars).
    """

    entity_type: ReviewEntityType
    entity_id: str = Field(min_length=1, max_length=128)
    actor: str | None = Field(default=None, max_length=64)
    decision: ReviewDecisionValue
    note: str | None = Field(default=None, max_length=2000)


@router.post("/api/review/decisions")
def post_review_decision(body: ReviewDecisionRequest, request: Request) -> dict:
    """Record a trader review decision (persisted and audited).

    The decision and its audit event are attributed to the authenticated identity. A body
    that claims a different actor is recorded under the identity, and the envelope carries a
    warning naming the ignored claim, so a caller learns the decision is not filed under the
    name it typed.
    """

    warnings: list[str] = []
    claimed_actor = (body.actor or "").strip()
    actor = acting_actor(request).name
    if claimed_actor and claimed_actor != actor:
        warnings.append(f"ACTOR_CLAIM_IGNORED:{claimed_actor}")

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
                    actor=actor,
                    decision=body.decision.value,
                    note=body.note,
                )
                session.commit()
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    _record_audit_decision(
        body=body,
        actor=actor,
        persisted=data is not None,
        request_id=getattr(request.state, "request_id", None),
    )
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


def _record_audit_decision(
    *,
    body: ReviewDecisionRequest,
    actor: str,
    persisted: bool,
    request_id: str | None,
) -> None:
    """Append a review-decision audit event under the acting identity (best-effort)."""

    from eurogas_nexus.application.audit_service import record_audit_event

    record_audit_event(
        event_type="governance.action",
        action="review.decision.record",
        resource=f"{body.entity_type.value}:{body.entity_id}",
        principal=actor,
        outcome=body.decision.value,
        severity="info",
        detail=f"persisted={persisted}; note={bool(body.note)}",
        source_system="review",
        request_id=request_id,
    )


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
