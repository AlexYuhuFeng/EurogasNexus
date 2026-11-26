"""Credit lines and trader mandates: exposure and usage against approved limits.

``GET /api/portfolio/credit-exposure`` and ``GET /api/portfolio/mandate-usage`` read the same
legs and marks as the position ladder; the two ``PUT`` routes are the risk function's
maintenance of the approved limits (REVIEWER, audited; nobody sets their own mandate).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.positions import ladder_inputs
from eurogas_nexus.api.routes.public.portfolio_common import (
    db_is_configured as _db_is_configured,
)
from eurogas_nexus.api.routes.public.portfolio_common import db_unavailable as _db_unavailable
from eurogas_nexus.api.routes.public.portfolio_common import env as _env
from eurogas_nexus.api.routes.public.portfolio_common import identity_id as _identity_id
from eurogas_nexus.api.routes.public.portfolio_common import (
    sqlalchemy_error_type as _sqlalchemy_error_type,
)
from eurogas_nexus.application.warm_views import ViewSpec, not_json, warm_view
from eurogas_nexus.domain.ontology.markets import quote_currency
from eurogas_nexus.domain.ontology.notes import Note, declare, note

router = APIRouter(tags=["portfolio"])

NO_CASH_OUT_ASSUMPTION = declare(
    "NO_CASH_OUT_ASSUMPTION",
    "No approved cash-out premium or discount for this hub's books: the cost is not estimated "
    "on the days marked.",
)
NO_DELIVERY_HISTORY = declare(
    "NO_DELIVERY_HISTORY",
    "No delivery history for these contracts; the nomination tolerance stands in for the "
    "measured volatility. Load allocations to sharpen the plan.",
)
NO_TERMINAL_TERMS = declare(
    "NO_TERMINAL_TERMS", "No terminal terms yet; the LNG desk enters them per terminal."
)
SIMULATED_NOT_FOR_BIDS = declare(
    "SIMULATED_NOT_FOR_BIDS", "Simulated prices are never used to price a bid."
)

_FORMAT = "^(json|csv|xlsx|pdf)$"


def _horizon(today: date) -> tuple[date, date]:
    from eurogas_nexus.application.limits_service import horizon

    return horizon(today)


def _scope_note() -> list[str]:
    from eurogas_nexus.security.portfolio_scope import current_scope

    if current_scope() is None:
        return []
    return ["Computed over the books you can see; the firm-wide figure may be higher."]


def _not_configured(request: Request) -> dict:
    return _env(
        {"rows": [], "warnings": ["RUNTIME_DB_NOT_CONFIGURED"]},
        request,
        source="runtime-db-not-configured",
        warnings=["RUNTIME_DB_NOT_CONFIGURED"],
    )


def _download(rows: list[dict], *, report: str, title: str, format: str, warnings: list[str]):
    from eurogas_nexus.api.csv_export import report_response

    return report_response(
        rows,
        report=report,
        format=format,
        title=title,
        about=[("Warning", item) for item in warnings[:20]],
    )


@router.get("/api/portfolio/credit-exposure")
@warm_view(ViewSpec("portfolio.credit_exposure", max_age_seconds=60), skip=not_json)
def get_credit_exposure(request: Request, format: str = Query("json", pattern=_FORMAT)):
    """Exposure to each counterparty with an approved credit line, against its limit.

    每个交易对手的信用敞口（重置成本 + 应收款 − 抵押品）与授信额度的占用。

    Replacement exposure nets the counterparty's supply contracts and ETRM trades at the
    position ladder's marks; receivables are gas sold to them in the last ``receivable_days``
    gas days. Exchange-cleared screen trades carry no bilateral credit and are excluded.
    """

    from eurogas_nexus.application.limits_service import credit_exposure_rows

    return _limits_report(
        request, format, credit_exposure_rows, report="credit-exposure", title="Credit exposure"
    )


@router.get("/api/portfolio/mandate-usage")
@warm_view(ViewSpec("portfolio.mandate_usage", max_age_seconds=60), skip=not_json)
def get_mandate_usage(request: Request, format: str = Query("json", pattern=_FORMAT)):
    """Each trader's open positions against their mandate: size, hubs, tenor and products.

    交易员授权使用情况：净头寸、枢纽、期限与产品类型是否超出授权。
    """

    from eurogas_nexus.application.limits_service import mandate_usage_rows

    return _limits_report(
        request, format, mandate_usage_rows, report="mandate-usage", title="Trader mandates"
    )


def _limits_report(request: Request, format: str, compute, *, report: str, title: str):
    """Run a limits calculation for the caller and return it as JSON or a download."""

    from eurogas_nexus.application.caller import caller_of

    if not _db_is_configured():
        return _not_configured(request)
    today = datetime.now(UTC).date()
    try:
        result = compute(caller_of(request), today)
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc
    warnings = [*result.warnings, *_scope_note()]
    if format != "json":
        return _download(result.rows, report=report, title=title, format=format, warnings=warnings)
    from eurogas_nexus.domain.risk.method_notes import method_note

    # NUM-05: every figure says what it is and leaves out (one registry for the wording).
    if report == "credit-exposure":
        note = method_note(
            "credit_exposure",
            inputs_as_of={"positions": today.isoformat(), "marks": result.marks_as_of},
        )
    else:
        note = method_note("mandate_usage", inputs_as_of={"positions": today.isoformat()})
    rows = [{**row, "method": note} for row in result.rows]
    try:
        rows = _with_limit_provenance(report, rows)
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc
    return _env({"rows": rows, "as_of": today.isoformat()}, request, "runtime-postgresql", warnings)


def _with_limit_provenance(report: str, rows: list[dict]) -> list[dict]:
    """Each line or mandate with who set it and who approved it (P-17)."""

    from eurogas_nexus.application.maker_checker import provenance_for
    from eurogas_nexus.db.models import CreditLineRecord, TraderMandateRecord
    from eurogas_nexus.db.session import get_session_factory

    record_type, field = (
        (CreditLineRecord, "counterparty_id")
        if report == "credit-exposure"
        else (TraderMandateRecord, "mandate_id")
    )
    keys = {row.get(field) for row in rows if row.get(field)}
    if not keys:
        return rows
    column = getattr(record_type, field)
    with get_session_factory()() as session:
        records = session.query(record_type).filter(column.in_(keys)).all()
        provenance = provenance_for(
            session,
            [
                (getattr(r, field), r.updated_by, r.updated_at_utc, r.change_id)
                for r in records
            ],
        )
    return [{**row, "provenance": provenance.get(row.get(field))} for row in rows]


class CreditLineRequest(BaseModel):
    """An approved credit line: limit, collateral, and what faces the counterparty."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    legal_entity: str | None = Field(default=None, max_length=64)
    limit_amount: float = Field(ge=0)
    currency: str = Field(default="EUR", pattern="^[A-Z]{3}$")
    collateral_amount: float = Field(default=0.0, ge=0)
    rating: str | None = Field(default=None, max_length=16)
    contract_ids: list[str] = Field(default_factory=list, max_length=500)
    receivable_days: int = Field(default=50, ge=0, le=120)
    valid_until: date | None = None
    #: Unlinking every contract from a line that has some clears its exposure, so it is said
    #: out loud rather than inferred from an empty list a form forgot to fill (QA-R-01).
    unlink_contracts: bool = False
    #: Why the change is made; shown to the person who approves it (P-17).
    change_reason: str | None = Field(default=None, max_length=500)


class MandateRequest(BaseModel):
    """A trader's mandate: books, hubs, size, tenor, hedge band and instruments."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    trader: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=160)
    book_ids: list[str] = Field(default_factory=list, max_length=50)
    hubs: list[str] = Field(default_factory=list, max_length=30)
    max_net_mwh_per_month: float | None = Field(default=None, gt=0)
    max_tenor_months: int | None = Field(default=None, ge=0, le=120)
    physical_allowed: bool = True
    financial_allowed: bool = True
    valid_until: date | None = None
    min_hedge_ratio_pct: float | None = Field(default=None, ge=0, le=200)
    max_hedge_ratio_pct: float | None = Field(default=None, ge=0, le=200)
    instruments: list[str] = Field(default_factory=list, max_length=6)
    #: Why the change is made; shown to the person who approves it (P-17).
    change_reason: str | None = Field(default=None, max_length=500)


def _require_risk_function(request: Request, what: str = "Credit lines and mandates") -> None:
    """Limits are set by the risk function: REVIEWER held itself, and no front-office role.

    Roles are ranked (an ANALYST outranks a REVIEWER), and traders are analysts, so rank
    alone would let a trader set their own credit and mandate limits; a person holding both
    roles would too (segregation of duties, ``security/segregation.py``).
    """

    from eurogas_nexus.security.segregation import risk_function_refusal

    refusal = risk_function_refusal(getattr(request.state, "identity", None), what=what)
    if refusal is not None:
        raise HTTPException(status_code=403, detail=refusal)


def _change_error(exc) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.detail())


def _write(
    request: Request,
    response: Response,
    *,
    record_type,
    key: str,
    values: dict,
    action: str,
    resource: str,
    risk_only: bool = True,
    defaults: dict | None = None,
    reason: str = "",
    subject: str = "",
):
    """Create or change one reference row, or propose it for a second person's approval.

    ``values`` holds the fields the caller sent; ``defaults`` fill the rest only when the row
    is new, so a field left out of a change keeps its stored value. When four eyes is in force
    for ``action`` (P-17, default on), nothing changes yet: the change is recorded as a
    proposal with each field before and after, and the route answers 202 with it.
    """
    from eurogas_nexus.application import maker_checker
    from eurogas_nexus.application.reference_rows import json_safe, plan_row, write_row

    if risk_only:
        _require_risk_function(request)
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    actor = _identity_id(request) or "api"
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            if maker_checker.four_eyes_required(session, action):
                planned = plan_row(session, record_type, key, values, defaults)
                if not planned.created and not planned.changes:
                    return {"key": key, "created": False, "changed": [], "pending_approval": False}
                try:
                    change = maker_checker.propose_change(
                        session,
                        action=action,
                        target_key=key,
                        resource=resource,
                        subject=subject or key,
                        payload={"values": {k: json_safe(v) for k, v in planned.values.items()}},
                        before=planned.before(),
                        after=planned.after(),
                        reason=reason,
                        actor=actor,
                    )
                except maker_checker.ChangeRequestError as exc:
                    raise _change_error(exc) from exc
                session.commit()
                response.status_code = 202
                return {
                    "key": key,
                    "created": False,
                    "changed": sorted(planned.changes),
                    "pending_approval": True,
                    "change": maker_checker.describe(
                        session, change, identity=getattr(request.state, "identity", None)
                    ),
                }
            result = write_row(
                session,
                record_type=record_type,
                key=key,
                values=values,
                defaults=defaults,
                action=action,
                resource=resource,
                actor=actor,
                event_type="risk.limits" if risk_only else "desk.reference",
            )
            session.commit()
            return {**result, "pending_approval": False}
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _provenance(rows: list[tuple[str, str | None, object, str | None]]) -> dict[str, dict]:
    """Who set each figure, and who approved it when a second person did (P-17)."""

    from eurogas_nexus.application.maker_checker import provenance_for
    from eurogas_nexus.db.session import get_session_factory

    with get_session_factory()() as session:
        return provenance_for(session, rows)


@router.get("/api/portfolio/credit-lines/{counterparty_id}")
def get_credit_line(counterparty_id: str, request: Request) -> dict:
    """One stored credit line, every field, for the risk function's edit form (QA-R-01).

    The exposure row carries what the desk reads (limit, collateral, utilisation); the form
    needs the rest (aliases, linked contracts, legal entity, receivable days) so that saving
    one changed field does not send the others empty.
    """

    from eurogas_nexus.db.models import CreditLineRecord
    from eurogas_nexus.db.session import get_session_factory

    _require_risk_function(request)
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    try:
        with get_session_factory()() as session:
            row = session.get(CreditLineRecord, counterparty_id)
            if row is None:
                raise HTTPException(status_code=404, detail={"code": "credit_line_not_found"})
            line = {
                "counterparty_id": row.counterparty_id,
                "name": row.name,
                "aliases": list(row.aliases or []),
                "legal_entity": row.legal_entity,
                "limit_amount": float(row.limit_amount),
                "currency": row.currency,
                "collateral_amount": float(row.collateral_amount or 0.0),
                "rating": row.rating,
                "contract_ids": list(row.contract_ids or []),
                "receivable_days": int(row.receivable_days or 0),
                "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                "updated_by": row.updated_by,
                "updated_at_utc": row.updated_at_utc.isoformat() if row.updated_at_utc else None,
            }
            source = (row.counterparty_id, row.updated_by, row.updated_at_utc, row.change_id)
        line["provenance"] = _provenance([source])[counterparty_id]
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc
    return _env(line, request, "runtime-postgresql", [])


@router.put("/api/portfolio/credit-lines/{counterparty_id}")
def put_credit_line(
    counterparty_id: str, body: CreditLineRequest, request: Request, response: Response
) -> dict:
    """Record or change a counterparty's approved credit line (risk, audited).

    With four eyes in force (P-17, the default) the change is proposed and answers 202; it
    takes effect when a different person in the risk function approves it.
    """

    from eurogas_nexus.db.models import CreditLineRecord

    if not counterparty_id or len(counterparty_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "counterparty_id_invalid"})
    values = body.model_dump(exclude_unset=True)
    reason = values.pop("change_reason", None) or ""
    unlink = bool(values.pop("unlink_contracts", False))
    if "contract_ids" in values and not values["contract_ids"] and not unlink:
        _require_risk_function(request)
        if _db_is_configured():
            from eurogas_nexus.db.session import get_session_factory

            try:
                with get_session_factory()() as session:
                    stored = session.get(CreditLineRecord, counterparty_id)
                    linked = list(stored.contract_ids or []) if stored is not None else []
            except _sqlalchemy_error_type() as exc:
                raise _db_unavailable(exc) from exc
            if linked:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "unlink_not_confirmed",
                        "message": "This would unlink every contract from the line and clear "
                        "its exposure. Send unlink_contracts: true to do that.",
                        "linked": len(linked),
                    },
                )
    defaults = body.model_dump()
    defaults.pop("unlink_contracts", None)
    defaults.pop("change_reason", None)
    # Fields left out keep their stored value: leaving ``contract_ids`` out must not unlink the
    # contracts and clear a breach (persona review P-01). Unlinking every contract from a line
    # that has some needs ``unlink_contracts: true`` (QA-R-01).
    result = _write(
        request,
        response,
        record_type=CreditLineRecord,
        key=counterparty_id,
        values=values,
        defaults=defaults,
        action="risk.credit_line.update",
        resource=f"credit_line:{counterparty_id}",
        reason=reason,
        subject=values.get("name") or counterparty_id,
    )
    return _env(result, request, "runtime-postgresql", [])


@router.put("/api/portfolio/trader-mandates/{mandate_id}")
def put_trader_mandate(
    mandate_id: str, body: MandateRequest, request: Request, response: Response
) -> dict:
    """Record or change a trader's mandate (risk, audited; never one's own).

    With four eyes in force (P-17) the change is proposed and answers 202.
    """

    from eurogas_nexus.db.models import TraderMandateRecord

    if not mandate_id or len(mandate_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "mandate_id_invalid"})
    from eurogas_nexus.security.segregation import names_of

    if body.trader.strip().casefold() in names_of(getattr(request.state, "identity", None)):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "own_mandate",
                "message": "A trader's mandate is set by someone else (four eyes).",
            },
        )
    values = body.model_dump()
    reason = values.pop("change_reason", None) or ""
    values["hubs"] = [hub.upper() for hub in values["hubs"]]
    allowed = {"physical", "future", "forward", "swap", "option"}
    values["instruments"] = [item.casefold() for item in values["instruments"]]
    unknown = [item for item in values["instruments"] if item not in allowed]
    if unknown:
        raise HTTPException(
            status_code=422, detail={"code": "unknown_instrument", "values": unknown}
        )
    low, high = values["min_hedge_ratio_pct"], values["max_hedge_ratio_pct"]
    if low is not None and high is not None and low > high:
        raise HTTPException(status_code=422, detail={"code": "hedge_band_inverted"})
    result = _write(
        request,
        response,
        record_type=TraderMandateRecord,
        key=mandate_id,
        values=values,
        action="risk.mandate.update",
        resource=f"trader_mandate:{mandate_id}",
        reason=reason,
        subject=values["display_name"],
    )
    return _env(result, request, "runtime-postgresql", [])


# -------------------------------------------------------------------- deal hedge approvals


class HedgeApprovalRequest(BaseModel):
    """Risk's approved hedge band for one contract, with the approval's reference."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    min_hedge_ratio_pct: float | None = Field(default=None, ge=0, le=100)
    max_hedge_ratio_pct: float | None = Field(default=None, ge=0, le=100)
    approval_ref: str | None = Field(default=None, max_length=128)
    valid_until: date | None = None
    notes: str | None = Field(default=None, max_length=500)
    #: Why the change is made; shown to the person who approves it (P-17).
    change_reason: str | None = Field(default=None, max_length=500)


@router.get("/api/portfolio/hedge-approvals")
@warm_view(ViewSpec("portfolio.hedge_approvals", max_age_seconds=60))
def get_hedge_approvals(request: Request) -> dict:
    """Each approved deal's hedge band against the cover its linked trades give, by month.

    单笔合同对冲审批：风险批准的对冲比例区间与关联交易的实际覆盖。
    """

    from eurogas_nexus.domain.risk.limits import HedgeApproval, VolumeLeg, deal_hedge_usage

    if not _db_is_configured():
        return _not_configured(request)
    today = datetime.now(UTC).date()
    start, end = _horizon(today)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import HedgeApprovalRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            records = (
                session.query(HedgeApprovalRecord).order_by(HedgeApprovalRecord.contract_id).all()
            )
            session.expunge_all()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    inputs = ladder_inputs(request, today, start, end)
    linked: dict[str, list[str]] = {}
    for order in inputs.orders:
        target = getattr(order, "linked_resource_id", None)
        if target:
            linked.setdefault(str(target), []).append(order.order_observation_id)
    legs_by_ref = {leg.reference: leg for leg in inputs.legs}

    def volume(leg) -> VolumeLeg:
        return VolumeLeg(leg.reference, leg.first_gas_day, leg.last_gas_day, leg.mwh_per_day)

    rows = []
    for record in records:
        contract = legs_by_ref.get(record.contract_id)
        hedges = [
            legs_by_ref[ref] for ref in linked.get(record.contract_id, []) if ref in legs_by_ref
        ]
        row = deal_hedge_usage(
            HedgeApproval(
                contract_id=record.contract_id,
                min_hedge_ratio_pct=record.min_hedge_ratio_pct,
                max_hedge_ratio_pct=record.max_hedge_ratio_pct,
                approval_ref=record.approval_ref,
                valid_until=record.valid_until,
            ),
            [volume(contract)] if contract and contract.kind == "physical" else [],
            [volume(leg) for leg in hedges],
            today=today,
        )
        row["linked_trades"] = len(hedges)
        row["contract_found"] = contract is not None
        row["notes"] = record.notes
        row["updated_by"] = record.updated_by
        rows.append(row)
    try:
        provenance = _provenance(
            [(r.contract_id, r.updated_by, r.updated_at_utc, r.change_id) for r in records]
        )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    for row in rows:
        row["provenance"] = provenance.get(row["contract_id"])
    warnings = list(inputs.warnings)
    if any(not row["contract_found"] for row in rows):
        warnings.append("an approval names a contract that is retired or not in this book scope")
    # The contracts risk can approve a band for: identity and hub only, no commercial
    # terms, so the risk function (REVIEWER) needs no read of the contract library.
    names = {contract.contract_id: contract.contract_name for contract in inputs.contracts}
    contracts = [
        {
            "contract_id": leg.reference,
            "contract_name": names.get(leg.reference, leg.reference),
            "hub": leg.hub,
        }
        for leg in inputs.legs
        if leg.kind == "physical" and not leg.from_cargo
    ]
    for row in rows:
        row["contract_name"] = names.get(row["contract_id"], row["contract_id"])
    return _env({"rows": rows, "contracts": contracts}, request, "runtime-postgresql", warnings)


@router.put("/api/portfolio/hedge-approvals/{contract_id}")
def put_hedge_approval(
    contract_id: str, body: HedgeApprovalRequest, request: Request, response: Response
) -> dict:
    """Record or change a contract's approved hedge band (risk, audited).

    With four eyes in force (P-17) the change is proposed and answers 202.
    """

    from eurogas_nexus.db.models import HedgeApprovalRecord

    if not contract_id or len(contract_id) > 128:
        raise HTTPException(status_code=422, detail={"code": "contract_id_invalid"})
    low, high = body.min_hedge_ratio_pct, body.max_hedge_ratio_pct
    if low is None and high is None:
        raise HTTPException(status_code=422, detail={"code": "hedge_band_missing"})
    if low is not None and high is not None and low > high:
        raise HTTPException(status_code=422, detail={"code": "hedge_band_inverted"})
    values = body.model_dump()
    reason = values.pop("change_reason", None) or ""
    result = _write(
        request,
        response,
        record_type=HedgeApprovalRecord,
        key=contract_id,
        values=values,
        action="risk.hedge_approval.update",
        resource=f"hedge_approval:{contract_id}",
        reason=reason,
    )
    return _env(result, request, "runtime-postgresql", [])


# ------------------------------------------------------------------------- LNG cargo bids


class TerminalTermsRequest(BaseModel):
    """The firm's cost to land a cargo at one terminal, and the capacity it holds there."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=128)
    country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    hub: str = Field(min_length=2, max_length=16)
    regas_tariff_per_mwh: float = Field(ge=0, le=100)
    entry_tariff_per_mwh: float = Field(default=0.0, ge=0, le=100)
    fuel_retention_pct: float = Field(default=0.0, ge=0, le=10)
    port_costs_per_cargo: float = Field(default=0.0, ge=0, le=10_000_000)
    other_per_mwh: float = Field(default=0.0, ge=-100, le=100)
    extra_sailing_days: float = Field(default=0.0, ge=0, le=60)
    source_note: str = Field(min_length=1, max_length=256)
    capacity_basis: str = Field(default="spot", pattern="^(spot|long_term)$")
    variable_regas_per_mwh: float | None = Field(default=None, ge=0, le=100)
    regime: str = Field(
        default="negotiated", pattern="^(regulated_indexed|regulated|auction|negotiated)$"
    )
    fixed_per_cargo: float = Field(default=0.0, ge=0, le=10_000_000)
    source_url: str | None = Field(default=None, max_length=500)
    effective_from: str | None = Field(default=None, max_length=32)
    #: Why the change is made; shown to the person who approves it (P-17).
    change_reason: str | None = Field(default=None, max_length=500)


def _terms_row(record) -> dict:
    return {
        "terminal_id": record.terminal_id,
        "name": record.name,
        "country": record.country,
        "hub": record.hub,
        "currency": quote_currency(record.hub),
        "regas_tariff_per_mwh": record.regas_tariff_per_mwh,
        "entry_tariff_per_mwh": record.entry_tariff_per_mwh,
        "fuel_retention_pct": record.fuel_retention_pct,
        "port_costs_per_cargo": record.port_costs_per_cargo,
        "other_per_mwh": record.other_per_mwh,
        "extra_sailing_days": record.extra_sailing_days,
        "source_note": record.source_note,
        "capacity_basis": record.capacity_basis or "spot",
        "variable_regas_per_mwh": record.variable_regas_per_mwh,
        "regime": record.regime or "negotiated",
        "fixed_per_cargo": record.fixed_per_cargo or 0.0,
        "by_cargo_class": record.by_cargo_class,
        "source_url": record.source_url,
        "source_sha256": record.source_sha256,
        "effective_from": record.effective_from,
        "retrieved_at_utc": record.retrieved_at_utc.isoformat()
        if record.retrieved_at_utc
        else None,
        "updated_by": record.updated_by,
        "updated_at_utc": record.updated_at_utc.isoformat() if record.updated_at_utc else None,
    }


def _load_terms() -> list:
    from eurogas_nexus.db.models import LngTerminalTermsRecord
    from eurogas_nexus.db.session import get_session_factory

    with get_session_factory()() as session:
        rows = session.query(LngTerminalTermsRecord).order_by(LngTerminalTermsRecord.name).all()
        session.expunge_all()
        return rows


@router.get("/api/portfolio/lng-terminal-terms")
def list_lng_terminal_terms(request: Request) -> dict:
    """The firm's landing costs per regas terminal (tariffs, fuel, port, sailing days).

    公司维护的各接收站卸货成本（再气化费、入网费、燃料留存、港口费、额外航行天数）。
    """

    if not _db_is_configured():
        return _not_configured(request)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        records = _load_terms()
        rows = [_terms_row(record) for record in records]
        provenance = _provenance(
            [(r.terminal_id, r.updated_by, r.updated_at_utc, r.change_id) for r in records]
        )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    for row in rows:
        row["provenance"] = provenance.get(row["terminal_id"])
    warnings: list[str | Note] = [] if rows else [note(NO_TERMINAL_TERMS)]
    return _env({"rows": rows}, request, "runtime-postgresql", warnings)


@router.put("/api/portfolio/lng-terminal-terms/{terminal_id}")
def put_lng_terminal_terms(
    terminal_id: str, body: TerminalTermsRequest, request: Request, response: Response
) -> dict:
    """Record a terminal's landing costs (LNG desk, audited). ``source_note`` names the tariff.

    With four eyes in force (P-17) the change is proposed and answers 202; another person on
    the desk approves it.
    """

    from eurogas_nexus.db.models import LngTerminalTermsRecord
    from eurogas_nexus.domain.ontology.markets import find_market

    if not terminal_id or len(terminal_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "terminal_id_invalid"})
    values = body.model_dump()
    reason = values.pop("change_reason", None) or ""
    values["hub"] = values["hub"].upper()
    if values["source_url"] and not values["source_url"].startswith("https://"):
        raise HTTPException(status_code=422, detail={"code": "source_url_must_be_https"})
    if find_market(values["hub"]) is None:
        raise HTTPException(status_code=422, detail={"code": "unknown_hub", "hub": values["hub"]})
    result = _write(
        request,
        response,
        record_type=LngTerminalTermsRecord,
        key=terminal_id,
        values=values,
        action="lng.terminal_terms.update",
        resource=f"lng_terminal_terms:{terminal_id}",
        risk_only=False,
        reason=reason,
        subject=values["name"],
    )
    return _env(result, request, "runtime-postgresql", [])


class CargoBidBody(BaseModel):
    """A cargo to price: size in MWh or MMBtu, arrival month, margin and voyage costs."""

    model_config = ConfigDict(extra="forbid")
    cargo_mwh: float | None = Field(default=None, gt=0, le=5_000_000)
    cargo_mmbtu: float | None = Field(default=None, gt=0, le=20_000_000)
    arrival_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    target_margin_per_mwh: float = Field(default=0.0, ge=-50, le=50)
    boil_off_pct_per_day: float = Field(default=0.1, ge=0, le=1)
    charter_per_day: float = Field(default=0.0, ge=0, le=1_000_000)
    ranking_currency: str = Field(default="EUR", pattern="^[A-Z]{3}$")
    terminal_ids: list[str] = Field(default_factory=list, max_length=100)


@router.post("/api/portfolio/lng-cargo-bid")
def post_lng_cargo_bid(body: CargoBidBody, request: Request) -> dict:
    """The most the firm can bid DES for a cargo at each terminal, best first.

    LNG 船货竞价表：按接收站计算到岸（DES）最高出价、盈亏平衡价与区间，按统一币种排序。

    Hub marks for the arrival month come from the position ladder's forward curve (licensed
    quotes only; simulated prices never mark a bid); the range uses the months either side.
    Nothing is offered or sent anywhere: this prices a bid for the desk to decide.
    """

    from eurogas_nexus.domain.portfolio.lng_bid import (
        MWH_PER_MMBTU,
        CargoBidRequest,
        TerminalTerms,
        cargo_bid_sheet,
        region_ranges,
    )
    from eurogas_nexus.domain.risk.limits import fx_lookup

    if (body.cargo_mwh is None) == (body.cargo_mmbtu is None):
        raise HTTPException(
            status_code=422,
            detail={"code": "cargo_size", "message": "Give the cargo in MWh or in MMBtu."},
        )
    cargo_mwh = body.cargo_mwh or body.cargo_mmbtu * MWH_PER_MMBTU
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        records = _load_terms()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    if body.terminal_ids:
        records = [r for r in records if r.terminal_id in set(body.terminal_ids)]
    today = datetime.now(UTC).date()
    arrival = date(int(body.arrival_month[:4]), int(body.arrival_month[5:7]), 1)
    if arrival < today.replace(day=1):
        raise HTTPException(status_code=422, detail={"code": "arrival_in_the_past"})
    month_after = (arrival + timedelta(days=62)).replace(day=1) - timedelta(days=1)
    inputs = ladder_inputs(request, today, today, max(month_after, today))
    fx = fx_lookup(inputs.eur_rates)

    def spot(hub: str) -> float | None:
        series = inputs.closes.get(hub)
        return series[max(series)] if series else None

    terminals = [
        TerminalTerms(
            terminal_id=r.terminal_id,
            name=r.name,
            country=r.country,
            hub=r.hub,
            currency=quote_currency(r.hub),
            regas_tariff_per_mwh=r.regas_tariff_per_mwh,
            entry_tariff_per_mwh=r.entry_tariff_per_mwh,
            fuel_retention_pct=r.fuel_retention_pct,
            port_costs_per_cargo=r.port_costs_per_cargo,
            other_per_mwh=r.other_per_mwh,
            extra_sailing_days=r.extra_sailing_days,
            source_note=r.source_note,
            capacity_basis=r.capacity_basis or "spot",
            variable_regas_per_mwh=r.variable_regas_per_mwh,
            regime=r.regime or "negotiated",
            fixed_per_cargo=r.fixed_per_cargo or 0.0,
            by_cargo_class=r.by_cargo_class,
            effective_from=r.effective_from or "",
        )
        for r in records
    ]
    rows, warnings = cargo_bid_sheet(
        terminals,
        CargoBidRequest(
            cargo_mwh=cargo_mwh,
            arrival_month=body.arrival_month,
            target_margin_per_mwh=body.target_margin_per_mwh,
            boil_off_pct_per_day=body.boil_off_pct_per_day,
            charter_per_day=body.charter_per_day,
            ranking_currency=body.ranking_currency,
        ),
        mark=lambda hub, month: inputs.marks.get((hub, month)),
        spot=spot,
        fx=fx,
    )
    notes: list[str | Note] = list(warnings)
    if not terminals:
        notes.append(note(NO_TERMINAL_TERMS))
    if inputs.simulated_skipped:
        notes.append(note(SIMULATED_NOT_FOR_BIDS))
    return _env(
        {
            "cargo_mwh": round(cargo_mwh, 1),
            "cargo_mmbtu": round(cargo_mwh / MWH_PER_MMBTU, 0),
            "arrival_month": body.arrival_month,
            "ranking_currency": body.ranking_currency,
            "rows": rows,
            "regions": region_ranges(rows, body.ranking_currency),
        },
        request,
        "runtime-postgresql",
        notes,
    )


# --------------------------------------------------------------- day-ahead sell-down plan


@router.get("/api/portfolio/daily-balance")
@warm_view(ViewSpec("portfolio.daily_balance", max_age_seconds=60), skip=not_json)
def get_daily_balance(
    request: Request,
    hub: str = Query("NBP", min_length=2, max_length=16),
    days: int = Query(7, ge=1, le=31),
    short_premium_per_mwh: float | None = Query(None, ge=0, le=500),
    long_discount_per_mwh: float | None = Query(None, ge=0, le=500),
    flat_band_mwh: float = Query(0.0, ge=0, le=1_000_000),
) -> dict:
    """The gas balance at one hub for each coming gas day: supply, trades, what is left.

    每日平衡：逐个燃气日的实物流入流出、交易所与双边买卖、剩余敞口及不平衡结算成本（与“我的燃气日”同一口径）。

    One definition with Today's "My gas day" (``application/gas_day``): the same lines in the
    same scope. ``supply`` is the physical lines net (contracts nominated where held, else
    their quantity, capped by an outage at the source; LNG send-out from the cargo plan or the
    slot; storage and imports less offtake, injection and exports); trades are every exchange
    trade and ETRM (bilateral) deal delivering that day at the hub. The residual left open is
    cashed out by the TSO; its cost uses the approved cash-out premium or discount for the
    hub's books (``cash_out`` names the set and version), or a premium and discount given
    here, labelled as entered by hand. ``delivery_ratio`` is the contracts' measured delivery
    over the last 30 gas days, shown for reference and no longer applied
    (``delivery_ratio_applied``). Nothing is nominated or traded.
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.gas_day import gas_day_view, hub_daily_balance
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    if not _db_is_configured():
        return _not_configured(request)
    hub = hub.upper()
    now = datetime.now(UTC)
    today = date.fromisoformat(gas_day_label(now))
    gas_days = [today + timedelta(days=offset) for offset in range(days)]
    inputs = ladder_inputs(request, today, today, gas_days[-1])
    warnings: list[str | Note] = list(inputs.warnings)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ContractDeliveryRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            view = gas_day_view(session, caller_of(request), now=now, inputs=inputs,
                                days=gas_days)
            rows = hub_daily_balance(
                session, view, hub,
                short_premium=short_premium_per_mwh,
                long_discount=long_discount_per_mwh,
                flat_band_mwh=flat_band_mwh,
            )
            contract_ids = list(dict.fromkeys(
                line["ref"].split(":", 1)[1]
                for row in rows for line in row["lines"] if line["ref"].startswith("contract:")
            ))
            records = (
                session.query(ContractDeliveryRecord)
                .filter(ContractDeliveryRecord.contract_id.in_(contract_ids or [""]))
                .filter(ContractDeliveryRecord.gas_day >= today - timedelta(days=30))
                .filter(ContractDeliveryRecord.gas_day < today)
                .all()
            )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    nominated = sum(r.nominated_mwh or 0.0 for r in records if r.allocated_mwh is not None)
    allocated = sum(r.allocated_mwh or 0.0 for r in records if r.nominated_mwh is not None)
    ratio = allocated / nominated if nominated > 0 else 1.0
    if any(row["cash_out"].get("basis") == "missing" for row in rows):
        warnings.append(note(NO_CASH_OUT_ASSUMPTION))
    payload = {
        "hub": hub,
        "currency": quote_currency(hub),
        "delivery_ratio": round(ratio, 4),
        "delivery_ratio_applied": False,
        "contracts": contract_ids,
        "definition": "gas_day",
        "scope": view.scope.payload(),
        "as_of_utc": now.isoformat(),
        "days": rows,
    }
    return _env(payload, request, "runtime-postgresql", warnings)


class SellDownBody(BaseModel):
    """Tomorrow's sell-down at one hub: the prices the desk sees and the cost of a miss."""

    model_config = ConfigDict(extra="forbid")
    hub: str = Field(min_length=2, max_length=16)
    contract_ids: list[str] = Field(default_factory=list, max_length=200)
    da_price: float = Field(ge=-500, le=5000)
    wd_expected_price: float = Field(ge=-500, le=5000)
    short_penalty_per_mwh: float = Field(default=0.0, ge=0, le=500)
    long_discount_per_mwh: float = Field(default=0.0, ge=0, le=500)
    lot_mwh: float = Field(default=24.0, gt=0, le=100_000)
    history_days: int = Field(default=60, ge=14, le=365)
    #: The unit the four prices are entered in, as the desk quotes the hub (NBP in p/th);
    #: omitted, they are per MWh in the hub's currency.
    price_unit: str | None = Field(default=None, max_length=16)


@router.post("/api/portfolio/sell-down-plan")
def post_sell_down_plan(body: SellDownBody, request: Request) -> dict:
    """How much of tomorrow's supply at a hub to sell day-ahead, and how much to keep back.

    日前与日内分配：按合同实测交付波动（分配量对比提名量）求解报童问题，给出日前出售量与
    日内保留量、短缺概率与预期成本。

    Expected supply is the hub's active contracts' daily quantities corrected by their
    measured delivery bias; the uncertainty is the standard deviation of the summed daily
    deviation over ``history_days``. Without delivery history the contracts' nomination
    tolerance stands in for it, and the response says so. Nothing is nominated or sold.
    """

    import math
    from statistics import pstdev

    from eurogas_nexus.api.positions import hub_from_text
    from eurogas_nexus.application.projections.daily_closes import per_mwh_in_hub_currency
    from eurogas_nexus.domain.portfolio.sell_down import SellDownInputs, plan_sell_down

    hub = body.hub.upper()
    try:
        # The desk enters NBP in p/th; the plan prices per MWh in the hub's currency.
        body = body.model_copy(
            update={
                name: per_mwh_in_hub_currency(hub, getattr(body, name), body.price_unit)
                for name in (
                    "da_price",
                    "wd_expected_price",
                    "short_penalty_per_mwh",
                    "long_discount_per_mwh",
                )
            }
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "price_unit_invalid", "message": str(exc)}
        ) from exc
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    since = datetime.now(UTC).date() - timedelta(days=body.history_days)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ContractDeliveryRecord, UpstreamResourceContractRecord
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.security.portfolio_scope import restrict

        with get_session_factory()() as session:
            query = restrict(
                session.query(UpstreamResourceContractRecord),
                UpstreamResourceContractRecord,
                session,
            ).filter(UpstreamResourceContractRecord.retired_at_utc.is_(None))
            if body.contract_ids:
                query = query.filter(
                    UpstreamResourceContractRecord.contract_id.in_(body.contract_ids)
                )
            contracts = [
                c
                for c in query.all()
                if hub_from_text(c.delivery_point_name, session=session) == hub
            ]
            ids = [c.contract_id for c in contracts]
            records = (
                session.query(ContractDeliveryRecord)
                .filter(ContractDeliveryRecord.contract_id.in_(ids))
                .filter(ContractDeliveryRecord.gas_day >= since)
                .all()
                if ids
                else []
            )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    if not contracts:
        raise HTTPException(
            status_code=422,
            detail={"code": "no_supply_at_hub", "message": f"No active supply contracts at {hub}."},
        )
    warnings: list[str | Note] = []
    dcq = sum(float(c.delivery_quantity_mwh_per_day) for c in contracts)
    daily: dict = {}
    ratios = []
    for record in records:
        if record.nominated_mwh is None or record.allocated_mwh is None:
            continue
        daily[record.gas_day] = daily.get(record.gas_day, 0.0) + (
            record.allocated_mwh - record.nominated_mwh
        )
        if record.nominated_mwh > 0:
            ratios.append(record.allocated_mwh / record.nominated_mwh)
    if len(daily) >= 10:
        bias = sum(ratios) / len(ratios) if ratios else 1.0
        expected = dcq * bias
        sigma = pstdev(daily.values())
        basis = f"measured over {len(daily)} gas days"
    else:
        tolerance = max(float(c.nomination_tolerance_pct or 0.0) for c in contracts) / 100
        expected = dcq
        sigma = dcq * tolerance / 1.645  # the tolerance taken as a 90 % two-sided band
        basis = "contract nomination tolerance (no delivery history)"
        warnings.append(note(NO_DELIVERY_HISTORY))
    plan = plan_sell_down(
        SellDownInputs(
            expected_supply_mwh=expected,
            supply_stdev_mwh=sigma,
            da_price=body.da_price,
            wd_expected_price=body.wd_expected_price,
            short_penalty_per_mwh=body.short_penalty_per_mwh,
            long_discount_per_mwh=body.long_discount_per_mwh,
            lot_mwh=body.lot_mwh,
        )
    )
    payload = {
        "hub": hub,
        "contracts": ids,
        "dcq_mwh": round(dcq, 0),
        "expected_supply_mwh": round(expected, 0),
        "supply_stdev_mwh": round(sigma, 0),
        "volatility_basis": basis,
        "lots_day_ahead": int(math.floor(plan.sell_day_ahead_mwh / body.lot_mwh + 1e-9)),
        **plan.as_dict(),
    }
    return _env(payload, request, "runtime-postgresql", warnings)
