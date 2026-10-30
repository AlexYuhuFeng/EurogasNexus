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


_HUB_CODES = ("NBP", "TTF", "THE", "PEG", "ZTP", "PSV", "PVB", "CEGH", "ZEE")
_HUB_CURRENCY = {"NBP": "GBP"}


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


@router.get("/api/portfolio/position-ladder")
def get_position_ladder(
    request: Request,
    months: int = Query(12, ge=1, le=36),
) -> dict:
    """Physical and financial positions by hub and delivery month, MtM and indicative VaR.

    按枢纽与交割月份汇总实物与金融头寸，附盯市价值与历史模拟 VaR（指示性）。

    Physical legs are the stored upstream contracts (daily contract quantity over their gas
    year, hub from the delivery point); financial legs are filled screen trades (buy long,
    sell short) spread over their delivery days. Marks are the latest entitled daily close
    per hub, applied flat across months; legs in a currency other than the hub's mark are
    left unvalued.
    """

    from datetime import UTC, datetime, timedelta

    from eurogas_nexus.api.routes.public.spread_lab import _daily_rows
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
            contracts = session.query(UpstreamResourceContractRecord).all()
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
    marks = {}
    for hub, series in closes.items():
        if series:
            latest = series[max(series)]
            month = horizon_start
            while month <= horizon_end:
                marks[(hub, f"{month.year:04d}-{month.month:02d}")] = latest
                month = (month.replace(day=1) + timedelta(days=32)).replace(day=1)
    report = ladder_report(
        legs,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        marks=marks,
        daily_closes_by_hub=closes,
    )
    if marks:
        warnings.append("Marks are the latest daily close per hub applied flat across months.")
    if simulated_skipped:
        warnings.append(
            "Simulated prices are not used for marks or VaR; connect or import licensed prices."
        )
    payload = report.as_dict()
    payload["horizon"] = {"start": horizon_start.isoformat(), "end": horizon_end.isoformat()}
    payload["legs"] = {
        "physical": sum(1 for leg in legs if leg.kind == "physical"),
        "financial": sum(1 for leg in legs if leg.kind == "financial"),
    }
    return _env(
        payload, request, source="runtime-postgresql", warnings=[*warnings, *report.warnings]
    )
