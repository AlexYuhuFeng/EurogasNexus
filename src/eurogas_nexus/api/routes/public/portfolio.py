"""Read-only portfolio, screen-order, and PnL observation routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

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
    summary = summarize_portfolio(orders, snapshots)
    source = (
        "runtime-postgresql"
        if {order_source, pnl_source} == {"runtime-postgresql"}
        else "runtime-db-not-configured"
    )
    return _env(
        summary.model_dump(mode="json"),
        request,
        source=source,
        warnings=[*order_warnings, *pnl_warnings],
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
        from eurogas_nexus.db.models import ScreenOrderObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(ScreenOrderObservationRecord).order_by(
                ScreenOrderObservationRecord.observed_at_utc.desc(),
                ScreenOrderObservationRecord.venue,
            )
            return [_screen_order_from_row(row) for row in rows.all()], "runtime-postgresql", []
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
        from eurogas_nexus.db.models import PortfolioPnlSnapshotRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(PortfolioPnlSnapshotRecord).order_by(
                PortfolioPnlSnapshotRecord.valuation_time_utc.desc(),
                PortfolioPnlSnapshotRecord.portfolio_id,
            )
            return [_pnl_snapshot_from_row(row) for row in rows.all()], "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _screen_order_from_row(row) -> ScreenOrderObservation:
    return ScreenOrderObservation(
        order_observation_id=row.order_observation_id,
        provider_id=row.provider_id,
        venue=row.venue,
        account_label=row.account_label,
        external_order_id=row.external_order_id,
        side=row.side,
        order_type=row.order_type,
        hub=row.hub,
        product=row.product,
        contract_code=row.contract_code,
        delivery_start_utc=row.delivery_start_utc.isoformat(),
        delivery_end_utc=row.delivery_end_utc.isoformat(),
        price=row.price,
        currency=row.currency,
        unit=row.unit,
        quantity_mwh=row.quantity_mwh,
        filled_quantity_mwh=row.filled_quantity_mwh,
        remaining_quantity_mwh=row.remaining_quantity_mwh,
        status=row.status,
        observed_at_utc=row.observed_at_utc.isoformat(),
        source_system=row.source_system,
        source_reference=row.source_reference,
        linked_strategy_id=row.linked_strategy_id,
        linked_resource_id=row.linked_resource_id,
        research_only=row.research_only,
        human_review_required=row.human_review_required,
    )


def _pnl_snapshot_from_row(row) -> PortfolioPnlSnapshot:
    return PortfolioPnlSnapshot(
        pnl_snapshot_id=row.pnl_snapshot_id,
        portfolio_id=row.portfolio_id,
        resource_id=row.resource_id,
        strategy_id=row.strategy_id,
        valuation_time_utc=row.valuation_time_utc.isoformat(),
        realized_pnl_gbp=row.realized_pnl_gbp,
        unrealized_pnl_gbp=row.unrealized_pnl_gbp,
        indicative_pnl_gbp=row.indicative_pnl_gbp,
        cash_value_gbp=row.cash_value_gbp,
        market_value_gbp=row.market_value_gbp,
        quantity_mwh=row.quantity_mwh,
        valuation_basis=row.valuation_basis,
        source_system=row.source_system,
        source_reference=row.source_reference,
        warnings=row.warnings,
        research_only=row.research_only,
        human_review_required=row.human_review_required,
    )


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


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
