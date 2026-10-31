"""Read-only portfolio, screen-order, and PnL observation routes.

The loading and shaping code lives in
``eurogas_nexus.application.projections.portfolio_reads`` so the Wave 5
PortfolioSnapshot projection composes exactly these reads instead of
re-implementing them. This module keeps the HTTP concerns: the runtime-database
guard, the ``503 runtime_db_unavailable`` translation and the response envelope.
Every response field of every endpoint below is unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.application.projections.market_reads import runtime_db_configured
from eurogas_nexus.application.projections.portfolio_reads import (
    pnl_snapshots,
    screen_orders,
)
from eurogas_nexus.domain.market_positioning import (
    PortfolioPnlSnapshot,
    ScreenOrderObservation,
    summarize_portfolio,
)
from eurogas_nexus.domain.ontology.markets import european_gas_hubs, quote_currency

router = APIRouter(tags=["portfolio"])


@router.get("/api/portfolio/screen-orders")
def list_screen_orders(
    request: Request,
    provider_id: str | None = Query(None),
    venue: str | None = Query(None),
    status: str | None = Query(None),
) -> dict:
    """List imported read-only external screen order observations."""

    orders, source, warnings = _load_screen_orders(_identity_id(request))
    if provider_id:
        orders = [order for order in orders if order.provider_id == provider_id]
    if venue:
        venue_key = venue.casefold()
        orders = [order for order in orders if order.venue.casefold() == venue_key]
    if status:
        status_key = status.casefold()
        orders = [order for order in orders if order.status.casefold() == status_key]
    return _env([order.model_dump(mode="json") for order in orders], request, source, warnings)


@router.get("/api/portfolio/pnl-snapshots")
def list_pnl_snapshots(
    request: Request,
    portfolio_id: str | None = Query(None),
    resource_id: str | None = Query(None),
    strategy_id: str | None = Query(None),
) -> dict:
    """List indicative PnL snapshots for portfolio/resource/strategy context."""

    snapshots, source, warnings = _load_pnl_snapshots(_identity_id(request))
    if portfolio_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.portfolio_id == portfolio_id]
    if resource_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.resource_id == resource_id]
    if strategy_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.strategy_id == strategy_id]
    return _env(
        [snapshot.model_dump(mode="json") for snapshot in snapshots],
        request,
        source,
        warnings,
    )


@router.get("/api/portfolio/live-summary")
def get_live_summary(
    request: Request,
    portfolio_id: str | None = Query(None),
) -> dict:
    """Return a cockpit summary of latest imported order/PnL observations."""

    orders, order_source, order_warnings = _load_screen_orders(_identity_id(request))
    snapshots, pnl_source, pnl_warnings = _load_pnl_snapshots(_identity_id(request))
    if portfolio_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.portfolio_id == portfolio_id]
    # No snapshot evidence (unconfigured runtime, degraded read, empty table, or
    # a filter that matched nothing) is carried through as an explicit unknown:
    # summarize_portfolio returns None aggregates plus VALUATION_EVIDENCE_MISSING
    # and latest_valuation_time_utc=None. The route must not fill those in with 0,
    # which would present a missing measurement as a measured zero
    # (UX01-EXPOSURE-001, "never fabricate evidence").
    summary = summarize_portfolio(orders, snapshots)
    source = (
        "runtime-postgresql"
        if {order_source, pnl_source} == {"runtime-postgresql"}
        else "runtime-db-not-configured"
    )
    # The summary's own warnings (notably VALUATION_EVIDENCE_MISSING) are
    # domain facts about the returned data, so they are surfaced in the envelope
    # meta alongside the loader warnings instead of being dropped. This informs
    # consumers why the GBP totals are null; it never substitutes a number for
    # the missing evidence.
    return _env(
        summary.model_dump(mode="json"),
        request,
        source=source,
        warnings=[*order_warnings, *pnl_warnings, *summary.warnings],
    )


def _load_screen_orders(
    principal_id: str | None = None,
) -> tuple[list[ScreenOrderObservation], str, list[str]]:
    if not _db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["RUNTIME_DB_NOT_CONFIGURED"],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return screen_orders(session, principal_id=principal_id), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _load_pnl_snapshots(
    principal_id: str | None = None,
) -> tuple[list[PortfolioPnlSnapshot], str, list[str]]:
    if not _db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["RUNTIME_DB_NOT_CONFIGURED"],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return pnl_snapshots(session, principal_id=principal_id), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _identity_id(request: Request) -> str | None:
    return getattr(getattr(request.state, "identity", None), "principal_id", None)


def _db_is_configured() -> bool:
    return runtime_db_configured()


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for portfolio reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _env(data: object, _request: Request, source: str, warnings: list[str]) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings)),
        },
    }


_HUB_CODES = european_gas_hubs()
_HUB_CURRENCY = {code: quote_currency(code) for code in _HUB_CODES}
_CURVE_QUOTE_LOOKBACK_DAYS = 10


def _curve_quotes(request: Request, date_from, date_to) -> list:
    """Latest entitled, non-simulated quote per hub and delivery window, for the curve.

    Only quotes in the hub's own currency are used (NBP in GBP, continental hubs in EUR).
    A window that starts on the 1st and lasts 28 to 31 days is read as that whole month,
    so a month-ahead quote with a gas-day-aligned end prices its month.
    """

    from datetime import UTC, datetime, time, timedelta

    from sqlalchemy import func

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.market.forward_curve import CurveQuote

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with get_session_factory()() as session:
            naive = session.get_bind().dialect.name == "sqlite"

            def bound(day):
                moment = datetime.combine(day, time.min, tzinfo=UTC)
                return moment.replace(tzinfo=None) if naive else moment

            records = (
                session.query(
                    MarketObservationRecord.product,
                    MarketObservationRecord.price,
                    MarketObservationRecord.currency,
                    MarketObservationRecord.period_start_utc,
                    MarketObservationRecord.period_end_utc,
                    MarketObservationRecord.observed_at_utc,
                    MarketObservationRecord.source_system,
                    MarketObservationRecord.metadata_json,
                )
                .filter(func.upper(MarketObservationRecord.unit).like("%MWH%"))
                .filter(MarketObservationRecord.observed_at_utc >= bound(date_from))
                .filter(
                    MarketObservationRecord.observed_at_utc < bound(date_to + timedelta(days=1))
                )
                .order_by(MarketObservationRecord.observed_at_utc)
                .limit(20_000)
                .all()
            )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    rows = []
    for record in records:
        metadata = record.metadata_json or {}
        if metadata.get("simulated") or record.source_system.endswith("_Sim"):
            continue
        hub = str(metadata.get("hub") or record.product.split(" ")[0]).upper()
        if (record.currency or "").upper() != _HUB_CURRENCY.get(hub, "EUR"):
            continue
        rows.append(
            {
                "hub": hub,
                "label": str(metadata.get("tenor") or record.product),
                "first": record.period_start_utc.date(),
                "end": record.period_end_utc.date(),
                "price": float(record.price),
                "source_system": record.source_system,
            }
        )
    latest: dict[tuple, dict] = {}
    for row in filter_entitled_rows(current_principal(request), rows, source_key="source_system"):
        first, end = row["first"], row["end"]
        if first.day == 1 and 28 <= (end - first).days <= 31:
            end = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        latest[(row["hub"], first, end)] = row  # ordered by time: the last one wins
    return [
        CurveQuote(
            hub, first, end, row["price"], label=row["label"], reference=row["source_system"]
        )
        for (hub, first, end), row in latest.items()
    ]


def _hub_from_text(text: str, default: str = "NBP") -> str:
    upper = (text or "").upper()
    return next((hub for hub in _HUB_CODES if hub in upper), default)


def _gas_year_window(label: str, horizon_end) -> tuple | None:
    """``2026/27``, ``GY-26``, ``2026`` or ``2025+`` (open-ended) as first/last gas day."""

    import re
    from datetime import date, timedelta

    match = re.search(r"(\d{4})|GY-?(\d{2})", (label or "").upper())
    if not match:
        return None
    year = int(match.group(1)) if match.group(1) else 2000 + int(match.group(2))
    first = date(year, 10, 1)
    last = horizon_end if label.strip().endswith("+") else date(year + 1, 10, 1) - timedelta(days=1)
    return first, last


def _books(session) -> dict:
    """Books the caller may see (all of them unless portfolio isolation restricts)."""

    from eurogas_nexus.db.models import TradingBookRecord
    from eurogas_nexus.domain.portfolio.books import Book
    from eurogas_nexus.security.portfolio_scope import restrict

    return {
        row.book_id: Book(
            book_id=row.book_id,
            name=row.name,
            legal_entity=row.legal_entity,
            region=row.region,
            business=row.business,
            base_currency=row.base_currency,
            commodities=tuple(row.commodities or ()),
            active=row.active,
        )
        for row in restrict(session.query(TradingBookRecord), TradingBookRecord, session).all()
    }


def _order_books(session) -> dict[str, str]:
    from eurogas_nexus.db.models import ScreenOrderObservationRecord

    return {
        order_id: book_id
        for order_id, book_id in session.query(
            ScreenOrderObservationRecord.order_observation_id,
            ScreenOrderObservationRecord.book_id,
        )
        .filter(ScreenOrderObservationRecord.book_id.is_not(None))
        .all()
    }


def _ecb_rates(session) -> dict[str, float]:
    """Latest ECB reference rate per currency, units of currency per EUR (EUR itself is 1)."""

    from eurogas_nexus.db.models import FxObservationRecord

    rates: dict[str, tuple[str, float]] = {}
    for quote, value_date, rate in (
        session.query(
            FxObservationRecord.quote_currency,
            FxObservationRecord.value_date,
            FxObservationRecord.rate,
        )
        .filter(FxObservationRecord.base_currency == "EUR")
        .filter(FxObservationRecord.source_system == "ECB")
        .all()
    ):
        held = rates.get(quote)
        if rate and (held is None or value_date > held[0]):
            rates[quote] = (value_date, float(rate))
    return {"EUR": 1.0, **{quote: rate for quote, (_d, rate) in rates.items()}}


def _fx_by_hub(hubs, reporting_currency: str, eur_rates: dict[str, float]):
    """Multiplier from each hub's quote currency into the reporting currency (shared FX table)."""

    from datetime import date

    from eurogas_nexus.domain.ontology.currency import FxTable

    table = FxTable.from_pivot_map(eur_rates, as_of=date.today(), source="ECB")
    fx: dict[str, float] = {}
    missing: set[str] = set()
    for hub in hubs:
        currency = quote_currency(hub)
        if table.has(currency, reporting_currency):
            fx[hub] = table.rate(currency, reporting_currency)
        else:
            missing.add(currency)
    return fx, missing


def _rollup(legs, books, level, *, horizon_start, horizon_end, marks, fx_by_hub) -> list[dict]:
    """Totals per group at ``level`` (firm, legal entity, region, business or book)."""

    from eurogas_nexus.domain.portfolio.books import group_key
    from eurogas_nexus.domain.portfolio.position_ladder import build_ladder, mark_to_market

    groups: dict[str, list] = {}
    for leg in legs:
        groups.setdefault(group_key(leg.book_id, books, level), []).append(leg)
    rollup = []
    for key, members in sorted(groups.items()):
        rows = build_ladder(members, horizon_start=horizon_start, horizon_end=horizon_end)
        physical = sum(row.physical_mwh for row in rows)
        financial = sum(row.financial_mwh for row in rows)
        value, _missing = mark_to_market(
            members,
            marks,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            fx_by_hub=fx_by_hub,
        )
        rollup.append(
            {
                "group": key,
                "level": level,
                "physical_mwh": round(physical, 1),
                "financial_mwh": round(financial, 1),
                "net_mwh": round(physical + financial, 1),
                "hedge_ratio": None if abs(physical) < 1e-9 else round(-financial / physical, 4),
                "mark_to_market": None if value is None else round(value, 2),
                "legs": len(members),
            }
        )
    return rollup


@router.get("/api/portfolio/position-ladder")
def get_position_ladder(
    request: Request,
    months: int = Query(12, ge=1, le=36),
    group_by: str = Query("hub", pattern="^(hub|firm|legal_entity|region|business|book)$"),
    reporting_currency: str | None = Query(None, pattern="^[A-Z]{3}$"),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    """Physical and financial positions by hub and delivery month, MtM and indicative VaR.

    按枢纽与交割月份汇总实物与金融头寸，附盯市价值与历史模拟 VaR（指示性）。

    Physical legs are the stored upstream contracts (daily contract quantity over their gas
    year, hub from the delivery point); financial legs are filled screen trades (buy long,
    sell short) spread over their delivery days. Marks come from a monthly forward curve
    built from the latest entitled quotes (months, quarters, seasons, years); a month the
    curve does not reach falls back to the hub's latest daily close, and the warnings say
    so. Legs in a currency other than the hub's mark are left unvalued.
    """

    from datetime import UTC, datetime, timedelta

    from eurogas_nexus.api.routes.public.spread_lab import _daily_rows
    from eurogas_nexus.domain.market.forward_curve import build_forward_curve
    from eurogas_nexus.domain.portfolio.position_ladder import PositionLeg, ladder_report

    today = datetime.now(UTC).date()
    horizon_start = today
    horizon_end = (today.replace(day=1) + timedelta(days=32 * months)).replace(day=1) - timedelta(
        days=1
    )
    legs: list[PositionLeg] = []
    warnings: list[str] = []
    if not _db_is_configured():
        return _env(
            {"rows": [], "warnings": ["RUNTIME_DB_NOT_CONFIGURED"]},
            request,
            source="runtime-db-not-configured",
            warnings=["RUNTIME_DB_NOT_CONFIGURED"],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            from eurogas_nexus.security.portfolio_scope import restrict

            contracts = restrict(
                session.query(UpstreamResourceContractRecord),
                UpstreamResourceContractRecord,
                session,
            ).all()
            books = _books(session)
            order_books = _order_books(session)
            eur_rates = _ecb_rates(session)
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    for contract in contracts:
        window = _gas_year_window(contract.gas_year, horizon_end)
        if window is None:
            warnings.append(
                f"contract {contract.contract_id}: gas year {contract.gas_year!r} not understood"
            )
            continue
        hub = _hub_from_text(contract.delivery_point_name)
        legs.append(
            PositionLeg(
                kind="physical",
                hub=hub,
                first_gas_day=window[0],
                last_gas_day=window[1],
                mwh_per_day=float(contract.delivery_quantity_mwh_per_day),
                # Contract prices are stored in GBP/MWh; they value only against a GBP mark.
                price=float(contract.contract_price_gbp_mwh)
                if _HUB_CURRENCY.get(hub) == "GBP"
                else None,
                reference=contract.contract_id,
                book_id=contract.book_id or "",
            )
        )
    orders, _source, order_warnings = _load_screen_orders(_identity_id(request))
    warnings += order_warnings
    for order in orders:
        filled = float(order.filled_quantity_mwh or 0.0)
        if filled <= 0:
            continue
        start_at, end_at = (
            value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            for value in (order.delivery_start_utc, order.delivery_end_utc)
        )
        # Delivery windows run gas day start to gas day start (05:00/06:00 UTC), so the number
        # of gas days is the whole days between them, not the calendar date of the end.
        first = start_at.date()
        days = max(1, round((end_at - start_at).total_seconds() / 86_400))
        last = first + timedelta(days=days - 1)
        sign = 1.0 if str(order.side).lower() in {"buy", "bid", "b"} else -1.0
        hub = order.hub.upper()
        currency_matches = (order.currency or "").upper() == _HUB_CURRENCY.get(hub, "EUR")
        legs.append(
            PositionLeg(
                kind="financial",
                hub=hub,
                first_gas_day=first,
                last_gas_day=last,
                mwh_per_day=sign * filled / days,
                price=float(order.price) if currency_matches else None,
                reference=order.order_observation_id,
                book_id=order_books.get(order.order_observation_id, ""),
            )
        )
    closes: dict[str, dict] = {}
    simulated_skipped = 0
    for row in _daily_rows(request, today - timedelta(days=400), today):
        if row["simulated"]:
            # A simulated price must not become a mark or a risk figure (AGENTS.md rule 17).
            simulated_skipped += 1
            continue
        tenor = row["tenor"]
        if tenor not in {"month-ahead", "day-ahead"}:
            continue
        # Prefer month-ahead closes; day-ahead fills hubs without a month-ahead series.
        series = closes.setdefault(row["hub"], {})
        if tenor == "month-ahead" or row["day"] not in series:
            series[row["day"]] = row["price"]
    curve = build_forward_curve(
        _curve_quotes(request, today - timedelta(days=_CURVE_QUOTE_LOOKBACK_DAYS), today),
        first_month=horizon_start,
    )
    marks = curve.marks()
    mark_method = {(point.hub, point.month): point.method for point in curve.points}
    flat_months = 0
    for hub, series in closes.items():
        if series:
            latest = series[max(series)]
            month = horizon_start
            while month <= horizon_end:
                key = (hub, f"{month.year:04d}-{month.month:02d}")
                if key not in marks:
                    marks[key] = latest
                    mark_method[key] = "flat"
                    flat_months += 1
                month = (month.replace(day=1) + timedelta(days=32)).replace(day=1)
    if reporting_currency is None:
        # One currency across the positions: report in it; otherwise in EUR.
        held = {quote_currency(leg.hub) for leg in legs}
        reporting_currency = held.pop() if len(held) == 1 else "EUR"
    fx_by_hub, missing_fx = _fx_by_hub({leg.hub for leg in legs}, reporting_currency, eur_rates)
    if missing_fx:
        warnings.append(
            f"No ECB rate to {reporting_currency} for {', '.join(sorted(missing_fx))}; "
            "positions in those currencies are not valued."
        )
    report = ladder_report(
        legs,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        marks=marks,
        daily_closes_by_hub=closes,
        fx_by_hub=fx_by_hub,
        reporting_currency=reporting_currency,
    )
    if flat_months:
        warnings.append(
            f"{flat_months} hub-months have no curve quote and are marked flat at the hub's "
            "latest daily close."
        )
    warnings += curve.warnings
    if simulated_skipped:
        warnings.append(
            "Simulated prices are not used for marks or VaR; connect or import licensed prices."
        )
    payload = report.as_dict()
    for row in payload["rows"]:
        key = (row["hub"], row["month"])
        row["mark"] = round(marks[key], 4) if key in marks else None
        row["mark_method"] = mark_method.get(key)
    payload["curve"] = curve.as_dict()["points"]
    payload["horizon"] = {"start": horizon_start.isoformat(), "end": horizon_end.isoformat()}
    payload["legs"] = {
        "physical": sum(1 for leg in legs if leg.kind == "physical"),
        "financial": sum(1 for leg in legs if leg.kind == "financial"),
    }
    if group_by != "hub":
        payload["rollup"] = _rollup(
            legs,
            books,
            group_by,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            marks=marks,
            fx_by_hub=fx_by_hub,
        )
        payload["group_by"] = group_by
    if format == "csv":
        from eurogas_nexus.api.csv_export import csv_response

        if group_by != "hub":
            rows = [{**row, "currency": reporting_currency} for row in payload["rollup"]]
            return csv_response(rows, report=f"positions-by-{group_by}")
        return csv_response(payload["rows"], report="position-ladder")
    return _env(
        payload, request, source="runtime-postgresql", warnings=[*warnings, *report.warnings]
    )


class BookRequest(BaseModel):
    """A trading book and the contracts and screen trades to hold in it."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=128)
    legal_entity: str = Field(min_length=1, max_length=64)
    region: str = Field(pattern="^(europe|north_america|asia|global)$")
    business: str = Field(min_length=1, max_length=128)
    base_currency: str = Field(default="EUR", pattern="^[A-Z]{3}$")
    commodities: list[str] = Field(default_factory=list, max_length=8)
    active: bool = True
    #: Contracts and screen trades to hold in this book (moved from any other book).
    contract_ids: list[str] = Field(default_factory=list, max_length=5000)
    order_ids: list[str] = Field(default_factory=list, max_length=20000)


@router.get("/api/portfolio/books")
def list_books(request: Request) -> dict:
    """Trading books and their hierarchy: legal entity, region, business, book.

    交易账簿及其层级（法人实体、区域、业务、账簿），用于组合汇总。
    """

    from eurogas_nexus.domain.portfolio.books import hierarchy

    if not _db_is_configured():
        return _env([], request, source="runtime-db-not-configured", warnings=[])
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from sqlalchemy import func

        from eurogas_nexus.db.models import (
            ScreenOrderObservationRecord,
            UpstreamResourceContractRecord,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            books = _books(session)
            contracts = dict(
                session.query(UpstreamResourceContractRecord.book_id, func.count()).group_by(
                    UpstreamResourceContractRecord.book_id
                )
            )
            orders = dict(
                session.query(ScreenOrderObservationRecord.book_id, func.count()).group_by(
                    ScreenOrderObservationRecord.book_id
                )
            )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    rows = [
        {
            "book_id": book.book_id,
            "name": book.name,
            "legal_entity": book.legal_entity,
            "region": book.region,
            "business": book.business,
            "base_currency": book.base_currency,
            "commodities": list(book.commodities),
            "active": book.active,
            "contracts": contracts.get(book.book_id, 0),
            "orders": orders.get(book.book_id, 0),
        }
        for book in sorted(books.values(), key=lambda b: b.book_id)
    ]
    unassigned = {"contracts": contracts.get(None, 0), "orders": orders.get(None, 0)}
    return _env(
        {"books": rows, "hierarchy": hierarchy(books.values()), "unassigned": unassigned},
        request,
        source="runtime-postgresql",
        warnings=[],
    )


@router.put("/api/portfolio/books/{book_id}")
def put_book(book_id: str, body: BookRequest, request: Request) -> dict:
    """Define a book and assign contracts and screen trades to it (operator, audited)."""

    from datetime import UTC, datetime

    from eurogas_nexus.domain.ontology.markets import Commodity

    if not book_id or len(book_id) > 64 or book_id.upper() == "UNASSIGNED":
        raise HTTPException(status_code=422, detail={"code": "book_id_invalid"})
    unknown = [c for c in body.commodities if c not in {m.value for m in Commodity}]
    if unknown:
        raise HTTPException(
            status_code=422, detail={"code": "unknown_commodity", "values": unknown}
        )
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})
    actor = _identity_id(request) or "api"
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import (
            ScreenOrderObservationRecord,
            TradingBookRecord,
            UpstreamResourceContractRecord,
        )
        from eurogas_nexus.db.repositories.audit import record_audit_event
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            from eurogas_nexus.security.portfolio_scope import current_scope, restrict

            row = session.get(TradingBookRecord, book_id)
            scope = current_scope()
            if scope is not None and not (
                scope.allows(book_id, body.legal_entity, body.region)
                and (row is None or scope.allows(row.book_id, row.legal_entity, row.region))
            ):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "book_outside_scope",
                        "message": "Books can be defined only in your legal entity or region.",
                    },
                )
            created = row is None
            if row is None:
                row = TradingBookRecord(book_id=book_id)
                session.add(row)
            row.name = body.name
            row.legal_entity = body.legal_entity
            row.region = body.region
            row.business = body.business
            row.base_currency = body.base_currency
            row.commodities = body.commodities or None
            row.active = body.active
            row.updated_by = actor
            row.updated_at_utc = datetime.now(UTC)
            moved_contracts = moved_orders = 0
            if body.contract_ids:
                moved_contracts = (
                    restrict(
                        session.query(UpstreamResourceContractRecord),
                        UpstreamResourceContractRecord,
                        session,
                    )
                    .filter(UpstreamResourceContractRecord.contract_id.in_(body.contract_ids))
                    .update({"book_id": book_id}, synchronize_session=False)
                )
            if body.order_ids:
                moved_orders = (
                    restrict(
                        session.query(ScreenOrderObservationRecord),
                        ScreenOrderObservationRecord,
                        session,
                    )
                    .filter(ScreenOrderObservationRecord.order_observation_id.in_(body.order_ids))
                    .update({"book_id": book_id}, synchronize_session=False)
                )
            record_audit_event(
                session,
                event_type="portfolio.book",
                principal=actor,
                action="portfolio.book.update",
                resource=f"trading_book:{book_id}",
                outcome="created" if created else "updated",
                severity="info",
                detail=f"contracts={moved_contracts} orders={moved_orders}",
                source_system="portfolio-api",
                now_utc=datetime.now(UTC),
            )
            session.commit()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    return _env(
        {
            "book_id": book_id,
            "created": created,
            "contracts_assigned": moved_contracts,
            "orders_assigned": moved_orders,
        },
        request,
        source="runtime-postgresql",
        warnings=[],
    )
