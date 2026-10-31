"""Credit lines and trader mandates: exposure and usage against approved limits.

``GET /api/portfolio/credit-exposure`` and ``GET /api/portfolio/mandate-usage`` read the same
legs and marks as the position ladder; the two ``PUT`` routes are the risk function's
maintenance of the approved limits (REVIEWER, audited; nobody sets their own mandate).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.routes.public.portfolio import (
    _db_is_configured,
    _db_unavailable,
    _env,
    _identity_id,
    _ladder_inputs,
    _sqlalchemy_error_type,
)
from eurogas_nexus.domain.ontology.markets import quote_currency

router = APIRouter(tags=["portfolio"])

_FORMAT = "^(json|csv|xlsx|pdf)$"
_HORIZON_MONTHS = 36


def _horizon(today: date) -> tuple[date, date]:
    end = (today.replace(day=1) + timedelta(days=32 * _HORIZON_MONTHS)).replace(day=1)
    return today, end - timedelta(days=1)


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
def get_credit_exposure(request: Request, format: str = Query("json", pattern=_FORMAT)):
    """Exposure to each counterparty with an approved credit line, against its limit.

    每个交易对手的信用敞口（重置成本 + 应收款 − 抵押品）与授信额度的占用。

    Replacement exposure nets the counterparty's supply contracts and ETRM trades at the
    position ladder's marks; receivables are gas sold to them in the last ``receivable_days``
    gas days. Exchange-cleared screen trades carry no bilateral credit and are excluded.
    """

    from eurogas_nexus.domain.risk.limits import (
        CounterpartyLeg,
        CreditLine,
        credit_exposure,
        fx_lookup,
    )

    if not _db_is_configured():
        return _not_configured(request)
    today = datetime.now(UTC).date()
    start, end = _horizon(today)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import CreditLineRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            lines = session.query(CreditLineRecord).order_by(CreditLineRecord.name).all()
            session.expunge_all()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    # Receivables look back before today, so read legs from the earliest look-back.
    lookback = max([line.receivable_days for line in lines] or [0])
    inputs = _ladder_inputs(request, today, start - timedelta(days=lookback), end)
    warnings = [*inputs.warnings, *_scope_note()]
    legs_by_ref = {leg.reference: leg for leg in inputs.legs}
    etrm_by_name: dict[str, list[str]] = {}
    for order in inputs.orders:
        if str(order.provider_id).upper() == "ETRM":
            etrm_by_name.setdefault(order.account_label.casefold(), []).append(
                order.order_observation_id
            )
    fx = fx_lookup(inputs.eur_rates)

    def mark(hub: str, month: str) -> float | None:
        return inputs.marks.get((hub, month))

    rows: list[dict] = []
    for record in lines:
        names = {record.name, record.counterparty_id, *(record.aliases or [])}
        references = [*(record.contract_ids or [])]
        for name in names:
            references += etrm_by_name.get(str(name).casefold(), [])
        legs = []
        for reference in dict.fromkeys(references):
            leg = legs_by_ref.get(reference)
            if leg is None:
                continue
            legs.append(
                CounterpartyLeg(
                    reference=reference,
                    kind="supply_contract" if leg.kind == "physical" else "otc_trade",
                    hub=leg.hub,
                    currency=quote_currency(leg.hub),
                    first_gas_day=leg.first_gas_day,
                    last_gas_day=leg.last_gas_day,
                    mwh_per_day=leg.mwh_per_day,
                    price=leg.price,
                )
            )
        line = CreditLine(
            counterparty_id=record.counterparty_id,
            name=record.name,
            limit_amount=float(record.limit_amount),
            currency=record.currency,
            collateral_amount=float(record.collateral_amount or 0.0),
            receivable_days=int(record.receivable_days or 0),
            valid_until=record.valid_until,
            legal_entity=record.legal_entity,
            rating=record.rating,
        )
        rows.append(credit_exposure(line, legs, today=today, mark=mark, fx=fx).as_row())
    if not lines:
        warnings.append("No credit lines are recorded; risk adds them under Portfolio > Limits.")
    if format != "json":
        return _download(
            rows,
            report="credit-exposure",
            title="Credit exposure",
            format=format,
            warnings=warnings,
        )
    return _env({"rows": rows, "as_of": today.isoformat()}, request, "runtime-postgresql", warnings)


@router.get("/api/portfolio/mandate-usage")
def get_mandate_usage(request: Request, format: str = Query("json", pattern=_FORMAT)):
    """Each trader's open positions against their mandate: size, hubs, tenor and products.

    交易员授权使用情况：净头寸、枢纽、期限与产品类型是否超出授权。
    """

    from eurogas_nexus.domain.risk.limits import Mandate, MandateLeg, mandate_usage

    if not _db_is_configured():
        return _not_configured(request)
    today = datetime.now(UTC).date()
    start, end = _horizon(today)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import TraderMandateRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            records = session.query(TraderMandateRecord).order_by(TraderMandateRecord.trader).all()
            session.expunge_all()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    inputs = _ladder_inputs(request, today, start, end)
    accounts = {
        order.order_observation_id: order.account_label
        for order in inputs.orders
        if str(order.provider_id).upper() != "ETRM"
    }
    legs = [
        MandateLeg(
            reference=leg.reference,
            kind=leg.kind,
            hub=leg.hub,
            book_id=leg.book_id,
            account=accounts.get(leg.reference, ""),
            first_gas_day=leg.first_gas_day,
            last_gas_day=leg.last_gas_day,
            mwh_per_day=leg.mwh_per_day,
        )
        for leg in inputs.legs
    ]
    rows = []
    for record in records:
        mandate = Mandate(
            mandate_id=record.mandate_id,
            trader=record.trader,
            display_name=record.display_name,
            book_ids=tuple(record.book_ids or ()),
            hubs=tuple(record.hubs or ()),
            max_net_mwh_per_month=record.max_net_mwh_per_month,
            max_tenor_months=record.max_tenor_months,
            physical_allowed=bool(record.physical_allowed),
            financial_allowed=bool(record.financial_allowed),
            valid_until=record.valid_until,
        )
        rows.append(mandate_usage(mandate, legs, today=today).as_row())
    warnings = [*inputs.warnings, *_scope_note()]
    if not records:
        warnings.append("No trader mandates are recorded; risk adds them under Portfolio > Limits.")
    if format != "json":
        return _download(
            rows,
            report="mandate-usage",
            title="Trader mandates",
            format=format,
            warnings=warnings,
        )
    return _env({"rows": rows, "as_of": today.isoformat()}, request, "runtime-postgresql", warnings)


class CreditLineRequest(BaseModel):
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


class MandateRequest(BaseModel):
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


def _require_risk_function(request: Request) -> None:
    """Limits are set by the risk function: an explicit REVIEWER role, not a higher rank.

    Roles are ranked (an ANALYST outranks a REVIEWER), and traders are analysts, so rank
    alone would let a trader set their own credit and mandate limits. The writer must hold
    REVIEWER itself, as the risk and middle-office personas do.
    """

    identity = getattr(request.state, "identity", None)
    held = {str(getattr(identity, "role", "") or "").upper()}
    held |= {str(role).upper() for role in (getattr(identity, "roles", ()) or ())}
    if "REVIEWER" not in held:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "risk_function_required",
                "message": "Credit lines and mandates are maintained by risk (REVIEWER role).",
            },
        )


def _write(
    request: Request,
    *,
    record_type,
    key: str,
    values: dict,
    action: str,
    resource: str,
    risk_only: bool = True,
):
    if risk_only:
        _require_risk_function(request)
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    actor = _identity_id(request) or "api"
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.audit import record_audit_event
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            row = session.get(record_type, key)
            created = row is None
            if row is None:
                row = record_type(**{record_type.__mapper__.primary_key[0].key: key})
                session.add(row)
            for name, value in values.items():
                setattr(row, name, value)
            row.updated_by = actor
            row.updated_at_utc = datetime.now(UTC)
            record_audit_event(
                session,
                event_type="risk.limits" if risk_only else "desk.reference",
                principal=actor,
                action=action,
                resource=resource,
                outcome="created" if created else "updated",
                severity="info",
                detail=", ".join(f"{k}={v}" for k, v in values.items() if k != "aliases")[:500],
            )
            session.commit()
            return {"key": key, "created": created, "updated_by": actor}
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.put("/api/portfolio/credit-lines/{counterparty_id}")
def put_credit_line(counterparty_id: str, body: CreditLineRequest, request: Request) -> dict:
    """Record or change a counterparty's approved credit line (risk, audited)."""

    from eurogas_nexus.db.models import CreditLineRecord

    if not counterparty_id or len(counterparty_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "counterparty_id_invalid"})
    result = _write(
        request,
        record_type=CreditLineRecord,
        key=counterparty_id,
        values=body.model_dump(),
        action="risk.credit_line.update",
        resource=f"credit_line:{counterparty_id}",
    )
    return _env(result, request, "runtime-postgresql", [])


@router.put("/api/portfolio/trader-mandates/{mandate_id}")
def put_trader_mandate(mandate_id: str, body: MandateRequest, request: Request) -> dict:
    """Record or change a trader's mandate (risk, audited; never one's own)."""

    from eurogas_nexus.db.models import TraderMandateRecord

    if not mandate_id or len(mandate_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "mandate_id_invalid"})
    actor = _identity_id(request)
    if actor and actor.casefold() == body.trader.casefold():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "own_mandate",
                "message": "A trader's mandate is set by someone else (four eyes).",
            },
        )
    values = body.model_dump()
    values["hubs"] = [hub.upper() for hub in values["hubs"]]
    result = _write(
        request,
        record_type=TraderMandateRecord,
        key=mandate_id,
        values=values,
        action="risk.mandate.update",
        resource=f"trader_mandate:{mandate_id}",
    )
    return _env(result, request, "runtime-postgresql", [])


# ------------------------------------------------------------------------- LNG cargo bids


class TerminalTermsRequest(BaseModel):
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
        rows = [_terms_row(record) for record in _load_terms()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    warnings = [] if rows else ["No terminal terms yet; the LNG desk enters them per terminal."]
    return _env({"rows": rows}, request, "runtime-postgresql", warnings)


@router.put("/api/portfolio/lng-terminal-terms/{terminal_id}")
def put_lng_terminal_terms(terminal_id: str, body: TerminalTermsRequest, request: Request) -> dict:
    """Record a terminal's landing costs (LNG desk, audited). ``source_note`` names the tariff."""

    from eurogas_nexus.db.models import LngTerminalTermsRecord
    from eurogas_nexus.domain.ontology.markets import find_market

    if not terminal_id or len(terminal_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "terminal_id_invalid"})
    values = body.model_dump()
    values["hub"] = values["hub"].upper()
    if find_market(values["hub"]) is None:
        raise HTTPException(status_code=422, detail={"code": "unknown_hub", "hub": values["hub"]})
    result = _write(
        request,
        record_type=LngTerminalTermsRecord,
        key=terminal_id,
        values=values,
        action="lng.terminal_terms.update",
        resource=f"lng_terminal_terms:{terminal_id}",
        risk_only=False,
    )
    return _env(result, request, "runtime-postgresql", [])


class CargoBidBody(BaseModel):
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
    inputs = _ladder_inputs(request, today, today, max(month_after, today))
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
    if not terminals:
        warnings.append("No terminal terms yet; the LNG desk enters them per terminal.")
    if inputs.simulated_skipped:
        warnings.append("Simulated prices are never used to price a bid.")
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
        warnings,
    )
