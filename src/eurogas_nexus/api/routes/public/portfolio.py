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

    orders, source, warnings = _load_screen_orders()
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

    snapshots, source, warnings = _load_pnl_snapshots()
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

    orders, order_source, order_warnings = _load_screen_orders()
    snapshots, pnl_source, pnl_warnings = _load_pnl_snapshots()
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


def _load_screen_orders() -> tuple[list[ScreenOrderObservation], str, list[str]]:
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
            return screen_orders(session), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _load_pnl_snapshots() -> tuple[list[PortfolioPnlSnapshot], str, list[str]]:
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
            return pnl_snapshots(session), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


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
