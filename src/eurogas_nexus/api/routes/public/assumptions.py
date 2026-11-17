"""Assumption sets, firm marks and valuation snapshots (commercial design basis 2, CP-07).

- ``/api/assumption-sets``: the firm's named, versioned inputs. Reading needs portfolio read;
  writing a draft needs the portfolio-assumption write permission (analysts, traders);
  approving a draft needs the risk function's REVIEWER role held explicitly and a different
  person from the one who set the values (four eyes). Only an approved version is read by a
  valuation. A set owned by a book is visible and editable only with that book in scope.
- ``/api/market/firm-marks``: the customer's own marks, a grid of hub x delivery period in
  the hub's native unit. Every row says "firm's mark"; a mark is never shown as a price
  from the market.
- ``/api/market/valuation-snapshots/{snapshot_id}``: what one evaluation read, input by
  input, with class, source and as-of. Values from a source the reader is not entitled to,
  and book rows outside the reader's books, are withheld (the row stays, marked withheld).

Every write is audited without the values (``db/repositories/commercial_assumptions.py``).
Nothing here is an order, a nomination or an instruction.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.domain.valuation.assumptions import (
    ASSUMPTION_CATALOGUE,
    AssumptionError,
    validate_assumption_value,
)
from eurogas_nexus.domain.valuation.firm_marks import FirmMarkError, validate_firm_mark
from eurogas_nexus.security.authorization import Permission, authorize
from eurogas_nexus.security.identity import AuthenticatedPrincipal, legacy_public_token_principal

router = APIRouter(tags=["assumptions"])


# --------------------------------------------------------------------------- helpers


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
            status_code=403,
            detail={"code": "permission_denied", "permission": permission.value},
        )
    return principal


def _require_risk_function(principal: AuthenticatedPrincipal) -> None:
    """Approval is the risk function's: the REVIEWER role held itself, not a higher rank."""

    held = {str(principal.role or "").upper()} | {str(r).upper() for r in principal.roles or ()}
    if "REVIEWER" not in held:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "risk_function_required",
                "message": "An assumption set is approved by risk (REVIEWER role).",
            },
        )


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
            "source_references": ["runtime-postgresql"],
            "warnings": warnings or [],
        },
    }


def _visible_books(session) -> set[str] | None:
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    return visible_book_ids(session)


def _require_book(session, book_id: str | None) -> None:
    if book_id is None:
        return
    allowed = _visible_books(session)
    if allowed is not None and book_id not in allowed:
        raise HTTPException(status_code=404, detail={"code": "unknown_assumption_set"})


def _assumption_error(exc: AssumptionError) -> HTTPException:
    status = {
        "unknown_set": 404,
        "unknown_version": 404,
        "four_eyes_required": 409,
        "not_a_draft": 409,
        "set_exists": 409,
    }.get(exc.code, 422)
    return HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


# ------------------------------------------------------------------- assumption sets


class AssumptionSetCreate(BaseModel):
    """A new, empty set; its values arrive with its first version."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    book_id: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=400)


class AssumptionValueIn(BaseModel):
    """One typed value: a catalogue key, a number, its currency for money units."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(min_length=1, max_length=64)
    value: float
    currency: str | None = Field(default=None, max_length=8)
    range_low: float | None = None
    range_high: float | None = None
    note: str = Field(default="", max_length=400)


class AssumptionVersionCreate(BaseModel):
    """A draft version: the full list of values and when they apply."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    effective_from: date
    effective_to: date | None = None
    note: str = Field(default="", max_length=400)
    values: list[AssumptionValueIn] = Field(min_length=1, max_length=64)


def _catalogue() -> list[dict]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "unit": spec.unit,
            "needs_currency": spec.needs_currency,
            "low": str(spec.low),
            "high": str(spec.high),
            "used_by": spec.used_by,
        }
        for spec in ASSUMPTION_CATALOGUE.values()
    ]


@router.get("/api/assumption-sets")
def list_assumption_sets(request: Request) -> dict:
    """The sets the caller may read (organisation sets and their books' sets) and the keys a
    set may hold."""

    _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        list_assumption_sets as list_sets,
    )

    with _session() as session:
        sets = list_sets(session, _visible_books(session))
    return _env({"sets": sets, "catalogue": _catalogue()})


@router.post("/api/assumption-sets")
def create_assumption_set(body: AssumptionSetCreate, request: Request) -> dict:
    """Create a named set for the organisation or one book (portfolio-assumption write)."""

    principal = _require(request, Permission.PORTFOLIO_WRITE)
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        create_assumption_set as create_set,
    )

    with _session() as session:
        _require_book(session, body.book_id)
        try:
            payload = create_set(
                session,
                name=body.name,
                book_id=body.book_id,
                description=body.description,
                actor=principal.principal_id,
            )
        except AssumptionError as exc:
            raise _assumption_error(exc) from exc
        session.commit()
    return _env(payload)


@router.get("/api/assumption-sets/{set_id}")
def get_assumption_set(set_id: str, request: Request) -> dict:
    """One set, every version with its values, who set and who approved each."""

    _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        assumption_set_book,
    )
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        get_assumption_set as get_set,
    )

    with _session() as session:
        exists, book_id = assumption_set_book(session, set_id)
        if not exists:
            raise HTTPException(status_code=404, detail={"code": "unknown_assumption_set"})
        _require_book(session, book_id)
        payload = get_set(session, set_id)
    return _env(payload)


@router.post("/api/assumption-sets/{set_id}/versions")
def create_assumption_version(set_id: str, body: AssumptionVersionCreate, request: Request) -> dict:
    """Append a draft version holding the full list of values (portfolio-assumption write).

    Raises:
        HTTPException: 422 with the rule's code for a value outside its catalogue entry.
    """

    principal = _require(request, Permission.PORTFOLIO_WRITE)
    try:
        values = [
            validate_assumption_value(
                item.key,
                item.value,
                currency=item.currency,
                range_low=item.range_low,
                range_high=item.range_high,
                note=item.note,
            )
            for item in body.values
        ]
    except AssumptionError as exc:
        raise _assumption_error(exc) from exc
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        assumption_set_book,
    )
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        create_assumption_version as create_version,
    )

    with _session() as session:
        exists, book_id = assumption_set_book(session, set_id)
        if not exists:
            raise HTTPException(status_code=404, detail={"code": "unknown_assumption_set"})
        _require_book(session, book_id)
        try:
            payload = create_version(
                session,
                set_id=set_id,
                values=values,
                effective_from=body.effective_from,
                effective_to=body.effective_to,
                note=body.note,
                actor=principal.principal_id,
            )
        except AssumptionError as exc:
            raise _assumption_error(exc) from exc
        session.commit()
    return _env(payload)


@router.post("/api/assumption-sets/{set_id}/versions/{version}/approve")
def approve_assumption_version(set_id: str, version: int, request: Request) -> dict:
    """Approve a draft (risk function, four eyes); the earlier approved version is retired."""

    principal = _principal(request)
    _require_risk_function(principal)
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        approve_assumption_version as approve,
    )
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        assumption_set_book,
    )

    with _session() as session:
        exists, book_id = assumption_set_book(session, set_id)
        if not exists:
            raise HTTPException(status_code=404, detail={"code": "unknown_assumption_set"})
        _require_book(session, book_id)
        try:
            payload = approve(session, set_id=set_id, version=version, actor=principal.principal_id)
        except AssumptionError as exc:
            raise _assumption_error(exc) from exc
        session.commit()
    return _env(payload)


# ------------------------------------------------------------------------- firm marks


class FirmMarkIn(BaseModel):
    """One grid cell: hub, delivery period, value in the hub's native unit."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hub: str = Field(min_length=2, max_length=16)
    period: str = Field(min_length=6, max_length=16)
    value: float
    unit: str = Field(min_length=3, max_length=16)
    note: str = Field(default="", max_length=200)


class FirmMarksPut(BaseModel):
    """A grid of marks; each supersedes the current mark for its hub and period."""

    model_config = ConfigDict(extra="forbid")

    marks: list[FirmMarkIn] = Field(min_length=1, max_length=400)


@router.get("/api/market/firm-marks")
def get_firm_marks(request: Request, hub: str | None = Query(default=None, max_length=16)) -> dict:
    """The firm's marks in force, each labelled "firm's mark"."""

    _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        current_firm_marks,
        mark_payload,
    )

    with _session() as session:
        rows = [mark_payload(mark) for mark in current_firm_marks(session, hub=hub)]
    return _env(
        {
            "marks": rows,
            "statement": "These are the firm's own marks, not prices from the market.",
        }
    )


@router.put("/api/market/firm-marks")
def put_firm_marks(body: FirmMarksPut, request: Request) -> dict:
    """Store marks (portfolio-assumption write); audited without the values.

    Raises:
        HTTPException: 422 with the rule's code and the offending cell.
    """

    principal = _require(request, Permission.PORTFOLIO_WRITE)
    entries = []
    for index, cell in enumerate(body.marks):
        try:
            entries.append(
                validate_firm_mark(cell.hub, cell.period, cell.value, cell.unit, cell.note)
            )
        except FirmMarkError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code, "message": str(exc), "index": index},
            ) from exc
    cells = [(entry.hub, entry.period.label) for entry in entries]
    if len(set(cells)) != len(cells):
        raise HTTPException(status_code=422, detail={"code": "duplicate_cell"})
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        mark_payload,
    )
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        put_firm_marks as put_marks,
    )

    with _session() as session:
        stored = put_marks(session, entries, actor=principal.principal_id)
        session.commit()
        rows = [mark_payload(mark) for mark in stored]
    return _env({"marks": rows})


# ------------------------------------------------------------------- valuation snapshots


@router.get("/api/market/valuation-snapshots/{snapshot_id}")
def get_valuation_snapshot(snapshot_id: str, request: Request) -> dict:
    """What one evaluation read: every input with class, source, reference and as-of."""

    principal = _require(request, Permission.PORTFOLIO_READ)
    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.repositories.commercial_assumptions import load_snapshot

    with _session() as session:
        loaded = load_snapshot(session, snapshot_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail={"code": "unknown_snapshot"})
        allowed_books = _visible_books(session)
    meta, manifest = loaded
    inputs = []
    withheld = 0
    for item in manifest.inputs:
        row = item.to_json()
        book = item.detail.get("book_id")
        hidden = (item.source_family and not row_allowed(principal, item.source_family)) or (
            allowed_books is not None and item.kind.value == "book" and book not in allowed_books
        )
        if hidden:
            withheld += 1
            row.update({"value": None, "detail": {}, "label": "", "withheld": True})
        inputs.append(row)
    warnings = (
        [f"{withheld} input(s) withheld: outside your entitlement or books"] if withheld else []
    )
    return _env({**meta, "inputs": inputs}, warnings)
