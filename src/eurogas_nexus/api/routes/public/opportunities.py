"""Opportunities (commercial design basis 2, CP-08): claims for human review, with arithmetic.

- ``GET /api/opportunities``: the caller's list. Two lanes (must act, could act) ranked, the
  watching and cannot-evaluate groups, counts, the readiness checklist; paginated by cursor
  per bucket (a newer evaluation expires a cursor: 409), never silently truncated. Filtered
  by book scope (every book behind a row), source entitlement and the caller's dismissals.
- ``GET /api/opportunities/{opportunity_id}``: the full object, its snapshot record and
  versions.
- ``PUT /api/opportunities/{opportunity_id}/state``: the caller's own follow or dismissal.
- ``POST /api/opportunities/{opportunity_id}/case``: open a decision case with the frozen
  arithmetic (the existing case flow and its permission). Nothing else exists: no order,
  no nomination, no instruction.
- ``GET/POST /api/opportunities/evaluations``: the last runs; run one now (firm-wide).
- ``GET/PUT /api/opportunities/settings``: the thresholds (risk function to change).
- ``GET /api/opportunities/statistics``: dismissal reasons and case precision per type.

Reading needs portfolio read and sits inside the commercial boundary; a work mode or
persona grants nothing here.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.domain.opportunities.model import Lane, OpportunityType
from eurogas_nexus.security.authorization import Permission, authorize
from eurogas_nexus.security.identity import AuthenticatedPrincipal, legacy_public_token_principal

router = APIRouter(tags=["opportunities"])


def _principal(request: Request) -> AuthenticatedPrincipal:
    identity = getattr(request.state, "identity", None)
    return (
        identity
        if isinstance(identity, AuthenticatedPrincipal)
        else (legacy_public_token_principal())
    )


def _require(request: Request, permission: Permission) -> AuthenticatedPrincipal:
    principal = _principal(request)
    if not authorize(principal, permission).allowed:
        raise HTTPException(
            status_code=403, detail={"code": "permission_denied", "permission": permission.value}
        )
    return principal


def _session():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_required"})
    return get_session_factory()()


def _env(data: object, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql", "valuation-snapshot"],
            "warnings": warnings or [],
        },
    }


def _visible_row(session, principal, opportunity_id: str):
    from eurogas_nexus.application.opportunities.listing import visible_to
    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models import OpportunityRecord
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    row = session.get(OpportunityRecord, opportunity_id)
    if row is None or not visible_to(
        row, visible_book_ids(session), lambda family: row_allowed(principal, family)
    ):
        raise HTTPException(status_code=404, detail={"code": "unknown_opportunity"})
    return row


@router.get("/api/opportunities")
def list_opportunities(
    request: Request,
    lane: Lane | None = Query(default=None),
    group: Literal["watching", "blocked"] | None = Query(default=None),
    type: OpportunityType | None = Query(default=None),
    book: str | None = Query(default=None, max_length=64),
    cursor: str | None = Query(default=None, max_length=400),
    limit: int | None = Query(default=None, ge=1, le=50),
) -> dict:
    """The caller's opportunities: lanes, groups, counts and the readiness checklist.

    Raises:
        HTTPException: 409 ``cursor_expired`` when a newer evaluation replaced the list the
            cursor was cut from; 422 ``cursor_invalid``.
    """

    principal = _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.application.opportunities.listing import CursorError
    from eurogas_nexus.application.opportunities.listing import (
        list_opportunities as build,
    )

    with _session() as session:
        try:
            data = build(
                session,
                principal,
                lane=None if lane is None else lane.value,
                group=group,
                opportunity_type=None if type is None else type.value,
                book_id=book,
                cursor=cursor,
                limit=limit,
            )
        except CursorError as exc:
            status = 409 if str(exc) == "cursor_expired" else 422
            raise HTTPException(status_code=status, detail={"code": str(exc)}) from exc
    warnings = [data["banner"]] if data["banner"] else []
    return _env(data, warnings)


@router.get("/api/opportunities/evaluations")
def list_evaluations(request: Request, limit: int = Query(default=10, ge=1, le=50)) -> dict:
    """The latest evaluation runs and each evaluator's status."""

    _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.application.opportunities.service import evaluation_summary
    from eurogas_nexus.db.models import OpportunityEvaluationRecord

    with _session() as session:
        runs = (
            session.query(OpportunityEvaluationRecord)
            .order_by(OpportunityEvaluationRecord.started_at_utc.desc())
            .limit(limit)
            .all()
        )
        data = [evaluation_summary(run) for run in runs]
    return _env({"evaluations": data, "schedule": "on request; scheduled runs: later package"})


@router.post("/api/opportunities/evaluations")
def run_evaluation_now(request: Request) -> dict:
    """Evaluate now, firm-wide (the stored result is filtered per reader)."""

    principal = _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.application.opportunities.schedule import evaluate_on_demand

    with _session() as session:
        summary = evaluate_on_demand(session, principal_id=principal.principal_id)
        session.commit()
    # Evaluator internals (messages) are for the administrator alert, not the desk.
    for status in summary["evaluators"].values():
        status.pop("message", None)
    return _env(summary)


class SettingsBody(BaseModel):
    """Threshold changes (decision L5); omitted keys keep their value."""

    model_config = ConfigDict(extra="forbid")

    min_margin: float | None = None
    min_value: float | None = None
    route_cost_share: float | None = None
    max_per_lane: int | None = None
    persistence: int | None = None
    removal_after_misses: int | None = None
    material_change: float | None = None
    marks_actionable: bool | None = None
    assumption_set_id: str | None = Field(default=None, max_length=64)


@router.get("/api/opportunities/settings")
def get_settings(request: Request) -> dict:
    """The thresholds in force (minimum margin in EUR/MWh, minimum value in EUR, ...)."""

    _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.application.opportunities.settings import load_thresholds

    with _session() as session:
        return _env(load_thresholds(session).to_json())


@router.put("/api/opportunities/settings")
def put_settings(body: SettingsBody, request: Request) -> dict:
    """Change thresholds: the risk function (REVIEWER held itself); audited before/after."""

    from eurogas_nexus.security.segregation import risk_function_refusal

    principal = _principal(request)
    refusal = risk_function_refusal(principal, what="Opportunity thresholds")
    if refusal is not None:
        raise HTTPException(status_code=403, detail=refusal)
    from eurogas_nexus.application.opportunities.settings import save_thresholds
    from eurogas_nexus.domain.opportunities.controls import ThresholdError

    values: dict[str, Any] = body.model_dump(exclude_unset=True)
    with _session() as session:
        try:
            saved = save_thresholds(session, values, actor=principal.principal_id)
        except ThresholdError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "setting_invalid", "message": str(exc)}
            ) from exc
        session.commit()
    return _env(saved.to_json())


@router.get("/api/opportunities/statistics")
def get_statistics(request: Request) -> dict:
    """Dismissal reasons per type; cases opened, decided and accepted per type."""

    _require(request, Permission.REVIEW_READ)
    from eurogas_nexus.application.opportunities.actions import statistics

    with _session() as session:
        return _env(statistics(session))


@router.get("/api/opportunities/{opportunity_id}")
def get_opportunity(opportunity_id: str, request: Request) -> dict:
    """Claim, arithmetic, assumptions, falsifiers, sensitivity, checks, quality, snapshot."""

    principal = _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.application.opportunities.listing import detail

    with _session() as session:
        data = detail(session, principal, opportunity_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_opportunity"})
    return _env(data, ["Simulated inputs (demo desk)."] if data["simulated"] else [])


class StateBody(BaseModel):
    """The caller's own follow or dismissal."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["dismiss", "restore", "watch", "unwatch"]
    reason: str | None = Field(default=None, max_length=32)
    note: str = Field(default="", max_length=400)


@router.put("/api/opportunities/{opportunity_id}/state")
def put_state(opportunity_id: str, body: StateBody, request: Request) -> dict:
    """Follow, unfollow, dismiss (with a reason) or restore, for the caller only."""

    principal = _require(request, Permission.PORTFOLIO_READ)
    if principal.auth_method == "legacy_public_token":
        raise HTTPException(status_code=401, detail={"code": "named_principal_required"})
    from eurogas_nexus.application.opportunities.actions import ActionError, set_user_state

    with _session() as session:
        row = _visible_row(session, principal, opportunity_id)
        try:
            data = set_user_state(
                session,
                row,
                principal_id=principal.principal_id,
                action=body.action,
                reason=body.reason,
                note=body.note,
            )
        except ActionError as exc:
            raise HTTPException(
                status_code=exc.status, detail={"code": exc.code, **exc.detail}
            ) from exc
        session.commit()
    return _env({"opportunity_id": opportunity_id, **data})


@router.post("/api/opportunities/{opportunity_id}/case")
def open_as_case(opportunity_id: str, request: Request) -> dict:
    """Open a decision case carrying the frozen arithmetic and the snapshot reference."""

    principal = _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.application.opportunities.actions import ActionError, open_case

    with _session() as session:
        row = _visible_row(session, principal, opportunity_id)
        try:
            data = open_case(session, row, principal=principal)
        except ActionError as exc:
            raise HTTPException(
                status_code=exc.status, detail={"code": exc.code, **exc.detail}
            ) from exc
        session.commit()
    return _env(data)
