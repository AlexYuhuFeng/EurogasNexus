"""Decision Case endpoints (Architecture V2 Wave 6).

A Decision Case collects the objective, context, assumptions, alternatives,
evidence and human review that lead to a Decision Record. The record is evidence
and rationale, never approval to execute: nothing here enters orders, routes them,
submits nominations or settles.

Two rules the endpoints enforce rather than document:

- the **actor is the authenticated identity**, never a body field, so the record
  names who actually decided;
- a case **cannot be decided without evidence**: the refusal lists the blockers,
  and the backend - not the client - owns that decision.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.domain.decision import DecisionAssumptionSource, DecisionEvidenceKind
from eurogas_nexus.domain.ontology.vocabulary import ReviewDecisionValue
from eurogas_nexus.security.identity import AuthenticatedPrincipal, legacy_public_token_principal

router = APIRouter(tags=["decision"])


class DecisionCaseCreateRequest(BaseModel):
    """Open a decision case in the current Active Context."""

    objective: str = Field(min_length=1, max_length=500)
    gas_day: str = Field(default="", max_length=16)
    delivery_product: str = Field(default="", max_length=32)
    hub_id: str = Field(default="", max_length=16)
    portfolio_ref: str = Field(default="", max_length=128)
    snapshot_id: str = Field(default="", max_length=64)


class DecisionCaseEvidenceRequest(BaseModel):
    """Attach one evidence reference to a case."""

    kind: DecisionEvidenceKind
    ref: str = Field(min_length=1, max_length=128)
    label: str = Field(default="", max_length=200)
    as_of_utc: str = Field(default="", max_length=40)
    snapshot_id: str = Field(default="", max_length=64)


class DecisionCaseAssumptionRequest(BaseModel):
    """One bounded assumption the alternatives were evaluated under."""

    key: str = Field(min_length=1, max_length=80)
    value: str = Field(default="", max_length=200)
    source: DecisionAssumptionSource = DecisionAssumptionSource.MANUAL
    note: str = Field(default="", max_length=400)


class DecisionCaseRecordRequest(BaseModel):
    """Record the human decision. The actor comes from the authenticated identity."""

    outcome: ReviewDecisionValue
    note: str = Field(default="", max_length=2000)


@router.post("/api/decision-cases")
def post_decision_case(body: DecisionCaseCreateRequest, request: Request) -> dict:
    """Open a decision case (governed write)."""

    principal = _actor(request)
    warnings: list[str] = []
    data: dict | None = None
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.decision import create_decision_case
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = create_decision_case(
                    session,
                    objective=body.objective,
                    created_by=principal.name,
                    gas_day=body.gas_day,
                    delivery_product=body.delivery_product,
                    hub_id=body.hub_id,
                    portfolio_ref=body.portfolio_ref,
                    snapshot_id=body.snapshot_id,
                )
                session.commit()
        except ValueError as exc:
            raise _validation_error(str(exc)) from exc
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, warnings=warnings)


@router.get("/api/decision-cases")
def get_decision_cases(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """List decision cases, newest first, as compact summaries."""

    warnings: list[str] = []
    data: list = []
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.decision import list_decision_cases
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = list_decision_cases(session, status=status, limit=limit)
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, warnings=warnings)


@router.get("/api/decision-cases/{case_id}")
def get_decision_case(case_id: str, request: Request) -> dict:
    """Read one decision case with its evidence, assumptions and records."""

    warnings: list[str] = []
    data: dict | None = None
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.decision import get_decision_case as load_case
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = load_case(session, case_id)
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    if data is None and "RUNTIME_DB_NOT_CONFIGURED" not in warnings:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_decision_case", "message": f"No decision case {case_id!r}."},
        )
    return _env(data, warnings=warnings)


@router.post("/api/decision-cases/{case_id}/evidence")
def post_decision_case_evidence(
    case_id: str, body: DecisionCaseEvidenceRequest, request: Request
) -> dict:
    """Attach evidence to a case. The first evidence moves it from DRAFT to OPEN."""

    warnings: list[str] = []
    data: dict | None = None
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.decision import attach_evidence
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = attach_evidence(
                    session,
                    case_id=case_id,
                    kind=body.kind.value,
                    ref=body.ref,
                    label=body.label,
                    as_of_utc=body.as_of_utc,
                    snapshot_id=body.snapshot_id,
                )
                session.commit()
        except ValueError as exc:
            raise _case_error(str(exc), case_id) from exc
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, warnings=warnings)


@router.post("/api/decision-cases/{case_id}/decisions")
def post_decision_case_decision(
    case_id: str, body: DecisionCaseRecordRequest, request: Request
) -> dict:
    """Record the human decision on a case (reviewer-gated)."""

    principal = _actor(request)
    warnings: list[str] = []
    data: dict | None = None
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.decision import record_case_decision
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = record_case_decision(
                    session,
                    case_id=case_id,
                    outcome=body.outcome.value,
                    actor=principal.name,
                    note=body.note,
                )
                session.commit()
        except ValueError as exc:
            raise _case_error(str(exc), case_id) from exc
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, warnings=warnings)


@router.post("/api/decision-cases/{case_id}/reopen")
def post_decision_case_reopen(case_id: str, request: Request) -> dict:
    """Reopen a decided case, preserving every record (reviewer-gated)."""

    principal = _actor(request)
    warnings: list[str] = []
    data: dict | None = None
    if not _db_is_configured():
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            from eurogas_nexus.db.repositories.decision import reopen_decision_case
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                data = reopen_decision_case(
                    session, case_id=case_id, actor=principal.name
                )
                session.commit()
        except ValueError as exc:
            raise _case_error(str(exc), case_id) from exc
        except _sqlalchemy_error_type():
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return _env(data, warnings=warnings)


def _actor(request: Request) -> AuthenticatedPrincipal:
    """The authenticated identity, never a caller-supplied actor string."""

    identity = getattr(request.state, "identity", None)
    if isinstance(identity, AuthenticatedPrincipal):
        return identity
    return legacy_public_token_principal()


def _validation_error(reason: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"error": reason, "message": "The decision case payload is incomplete."},
    )


def _case_error(reason: str, case_id: str) -> HTTPException:
    """Translate a repository refusal into the right status code.

    ``case_not_decidable`` carries its blocker codes and is a conflict with the
    current case state, not a client mistake in the request body.
    """

    if reason.startswith("unknown_decision_case"):
        return HTTPException(
            status_code=404,
            detail={"error": "unknown_decision_case", "message": f"No decision case {case_id!r}."},
        )
    if reason.startswith("case_not_decidable"):
        return HTTPException(
            status_code=409,
            detail={
                "error": "case_not_decidable",
                "message": "The case cannot be decided yet.",
                "blockers": reason.split(":", 1)[1].split(",") if ":" in reason else [],
            },
        )
    return HTTPException(
        status_code=422,
        detail={"error": reason, "message": "The decision case request was rejected."},
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
            "human_review_required": True,
            "source_references": ["decision-cases", "audit-events"],
            "warnings": warnings,
        },
    }
