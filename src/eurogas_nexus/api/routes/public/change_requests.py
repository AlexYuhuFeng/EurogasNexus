"""Proposed changes to limits and reference data, and their approval (P-17 maker-checker).

``GET /api/portfolio/change-requests`` lists the proposals the caller made or may decide
(``state`` pending by default, ``decided`` or ``all``), each with who proposed it, what it
changes (each field before and after), why and since when, and which writes need a second
person now. ``POST .../{change_id}/approve`` applies a proposal on a different authorised
person's word; ``.../reject`` closes it with a reason; ``.../withdraw`` is the proposer's.
Each is a governed write, audited in the same transaction (``application/maker_checker.py``).
Nothing here is an order, a nomination or an instruction.

限额与参考数据变更的提议与审批（四眼原则）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.routes.public.portfolio_common import (
    db_is_configured as _db_is_configured,
)
from eurogas_nexus.api.routes.public.portfolio_common import db_unavailable as _db_unavailable
from eurogas_nexus.api.routes.public.portfolio_common import env as _env
from eurogas_nexus.api.routes.public.portfolio_common import (
    sqlalchemy_error_type as _sqlalchemy_error_type,
)

router = APIRouter(tags=["portfolio"])


class DecisionBody(BaseModel):
    """Why a proposal is rejected or withdrawn (required to reject)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(default="", max_length=500)


def _identity(request: Request):
    identity = getattr(request.state, "identity", None)
    if identity is None or not getattr(identity, "principal_id", None):
        raise HTTPException(status_code=401, detail={"code": "named_principal_required"})
    return identity


def _require_db() -> None:
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})


@router.get("/api/portfolio/change-requests")
def list_change_requests(
    request: Request,
    state: str = Query("pending", pattern="^(pending|decided|all)$"),
    resource: str | None = Query(default=None, max_length=160),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Proposals the caller made or may decide, newest first, and the four-eyes settings.

    待审批（或已决定）的变更：提议人、变更前后、原因、时间。
    """

    from eurogas_nexus.application import maker_checker
    from eurogas_nexus.db.session import get_session_factory

    identity = _identity(request)
    _require_db()
    try:
        with get_session_factory()() as session:
            changes = maker_checker.list_changes(
                session, identity=identity, state=state, resource=resource, limit=limit
            )
            four_eyes = maker_checker.four_eyes_summary(session)
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc
    return _env({"changes": changes, "four_eyes": four_eyes}, request, "runtime-postgresql", [])


def _decide(request: Request, change_id: str, decide) -> dict:
    from eurogas_nexus.application import maker_checker
    from eurogas_nexus.db.session import get_session_factory

    identity = _identity(request)
    _require_db()
    if not change_id or len(change_id) > 40:
        raise HTTPException(status_code=404, detail={"code": "change_not_found"})
    try:
        with get_session_factory()() as session:
            try:
                change = decide(session, identity)
            except maker_checker.ChangeRequestError as exc:
                session.rollback()
                if exc.code == "four_eyes_required":
                    # The refused self-approval is a fact an auditor looks for; it changed
                    # nothing, so it is recorded best-effort.
                    from eurogas_nexus.application.audit_service import record_audit_event

                    record_audit_event(
                        event_type="governance.change_request",
                        action="change_request.self_approval_refused",
                        resource=f"change_request:{change_id}",
                        principal=str(identity.principal_id),
                        outcome="refused",
                        severity="warning",
                        detail=exc.message,
                    )
                raise HTTPException(status_code=exc.status, detail=exc.detail()) from exc
            session.commit()
            payload = maker_checker.describe(session, change, identity=identity)
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc
    return _env(payload, request, "runtime-postgresql", [])


@router.post("/api/portfolio/change-requests/{change_id}/approve")
def approve_change_request(change_id: str, request: Request) -> dict:
    """Apply a proposal: a different person with the authority to make the change approves it.

    Raises:
        HTTPException: 403 ``four_eyes_required`` for the proposer, or the approver's lack of
            authority; 404 ``change_not_found``; 409 ``change_not_pending`` or
            ``change_stale`` (the stored figures moved since the proposal).
    """

    from eurogas_nexus.application import maker_checker

    return _decide(
        request,
        change_id,
        lambda session, identity: maker_checker.approve_change(
            session, change_id, identity=identity
        ),
    )


@router.post("/api/portfolio/change-requests/{change_id}/reject")
def reject_change_request(
    change_id: str, request: Request, body: DecisionBody | None = None
) -> dict:
    """Close a proposal without applying it; the note says why (422 ``note_required``)."""

    from eurogas_nexus.application import maker_checker

    return _decide(
        request,
        change_id,
        lambda session, identity: maker_checker.reject_change(
            session, change_id, identity=identity, note=body.note if body else ""
        ),
    )


@router.post("/api/portfolio/change-requests/{change_id}/withdraw")
def withdraw_change_request(
    change_id: str, request: Request, body: DecisionBody | None = None
) -> dict:
    """The proposer takes back an open proposal (403 ``not_the_proposer`` for anyone else)."""

    from eurogas_nexus.application import maker_checker

    return _decide(
        request,
        change_id,
        lambda session, identity: maker_checker.withdraw_change(
            session, change_id, identity=identity, note=body.note if body else ""
        ),
    )
