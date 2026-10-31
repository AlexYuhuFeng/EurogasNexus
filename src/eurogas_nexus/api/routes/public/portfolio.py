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

from eurogas_nexus.api.positions import (  # noqa: F401 - re-exported for older importers
    HUB_CURRENCY,
    books_by_id,
    fx_by_hub_for,
    hub_from_text,
    ladder_inputs,
    rollup,
)
from eurogas_nexus.api.routes.public.portfolio_common import (
    db_is_configured as _db_is_configured,
)
from eurogas_nexus.api.routes.public.portfolio_common import (
    db_unavailable as _db_unavailable,
)
from eurogas_nexus.api.routes.public.portfolio_common import env as _env
from eurogas_nexus.api.routes.public.portfolio_common import identity_id as _identity_id
from eurogas_nexus.api.routes.public.portfolio_common import (
    load_pnl_snapshots as _load_pnl_snapshots,
)
from eurogas_nexus.api.routes.public.portfolio_common import (
    load_screen_orders as _load_screen_orders,
)
from eurogas_nexus.api.routes.public.portfolio_common import (
    sqlalchemy_error_type as _sqlalchemy_error_type,
)
from eurogas_nexus.domain.market_positioning import (
    summarize_portfolio,
)
from eurogas_nexus.domain.ontology.markets import quote_currency

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
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
):
    """List indicative PnL snapshots for portfolio/resource/strategy context.

    ``format`` csv, xlsx or pdf returns the same snapshots as a download.
    """

    snapshots, source, warnings = _load_pnl_snapshots(_identity_id(request))
    if portfolio_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.portfolio_id == portfolio_id]
    if resource_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.resource_id == resource_id]
    if strategy_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.strategy_id == strategy_id]
    if format != "json":
        from eurogas_nexus.api.csv_export import report_response

        return report_response(
            [snapshot.model_dump(mode="json") for snapshot in snapshots],
            report="pnl-snapshots",
            format=format,
            title="P&L snapshots",
            about=[("Source", source), *[("Warning", item) for item in warnings[:20]]],
        )
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


@router.get("/api/portfolio/position-ladder")
def get_position_ladder(
    request: Request,
    months: int = Query(12, ge=1, le=36),
    group_by: str = Query("hub", pattern="^(hub|firm|legal_entity|region|business|book)$"),
    reporting_currency: str | None = Query(None, pattern="^[A-Z]{3}$"),
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
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

    from eurogas_nexus.domain.portfolio.position_ladder import ladder_report

    today = datetime.now(UTC).date()
    horizon_start = today
    horizon_end = (today.replace(day=1) + timedelta(days=32 * months)).replace(day=1) - timedelta(
        days=1
    )
    if not _db_is_configured():
        return _env(
            {"rows": [], "warnings": ["RUNTIME_DB_NOT_CONFIGURED"]},
            request,
            source="runtime-db-not-configured",
            warnings=["RUNTIME_DB_NOT_CONFIGURED"],
        )
    inputs = ladder_inputs(request, today, horizon_start, horizon_end)
    legs, warnings = inputs.legs, inputs.warnings
    marks, mark_method = inputs.marks, inputs.mark_method
    books, closes, curve, eur_rates = inputs.books, inputs.closes, inputs.curve, inputs.eur_rates
    flat_months, simulated_skipped = inputs.flat_months, inputs.simulated_skipped
    if reporting_currency is None:
        # One currency across the positions: report in it; otherwise in EUR.
        held = {quote_currency(leg.hub) for leg in legs}
        reporting_currency = held.pop() if len(held) == 1 else "EUR"
    fx_by_hub, missing_fx = fx_by_hub_for({leg.hub for leg in legs}, reporting_currency, eur_rates)
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
        payload["rollup"] = rollup(
            legs,
            books,
            group_by,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            marks=marks,
            fx_by_hub=fx_by_hub,
        )
        payload["group_by"] = group_by
    if format != "json":
        from eurogas_nexus.api.csv_export import report_response

        about = [("Horizon", f"{horizon_start.isoformat()} to {horizon_end.isoformat()}")]
        about += [("Warning", item) for item in [*warnings, *report.warnings][:20]]
        if group_by != "hub":
            rows = [{**row, "currency": reporting_currency} for row in payload["rollup"]]
            return report_response(
                rows,
                report=f"positions-by-{group_by}",
                format=format,
                title=f"Positions by {group_by.replace('_', ' ')}",
                about=about,
            )
        return report_response(
            payload["rows"],
            report="position-ladder",
            format=format,
            title="Position ladder",
            about=about,
        )
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
            books = books_by_id(session)
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


@router.get("/api/portfolio/map-situation")
def map_situation(
    request: Request,
    outage_horizon_days: int = Query(14, ge=1, le=90),
) -> dict:
    """The live map: outages, point flows, the firm's contracts, LNG cargoes and regas slots.

    实时地图态势：停运、管点流量、本公司上游合同、LNG 船货与再气化窗口，均按来源定位。

    Items are placed only where a source locates them (EIC code or point name, or the
    coordinates the vessel feed supplied); the rest are counted in ``unlocated``.
    Book-held items follow portfolio isolation; market items the caller's data scopes.
    """

    from eurogas_nexus.api.dependencies.row_entitlement import filter_rows
    from eurogas_nexus.application.map_situation import build_map_situation

    if not _db_is_configured():
        return _env({}, request, source="runtime-db-not-configured", warnings=[])
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from datetime import UTC, datetime

        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            data = build_map_situation(
                session,
                now=datetime.now(UTC),
                entitled=lambda rows: list(filter_rows(request, rows)),
                outage_horizon_days=outage_horizon_days,
            )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    warnings = [
        f"{count} {kind.replace('_', ' ')} could not be located on the map"
        for kind, count in data["unlocated"].items()
        if count
    ]
    return _env(data, request, source="runtime-postgresql:map-situation", warnings=warnings)
