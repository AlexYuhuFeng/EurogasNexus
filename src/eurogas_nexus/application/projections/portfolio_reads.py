"""Portfolio read composition shared by the portfolio routes and projections.

This module is the single home of the portfolio loading and shaping code that
``api/routes/public/portfolio.py`` used to own privately. The existing
``/api/portfolio/*`` handlers and the Wave 5 ``PortfolioSnapshot`` projection
both call these functions, so a projection slice and the endpoint it composes
can never drift apart.

Model shapes are preserved exactly: ``ScreenOrderObservation`` and
``PortfolioPnlSnapshot`` from ``domain.market_positioning`` are the payload
contract of ``/api/portfolio/screen-orders`` and ``/api/portfolio/pnl-snapshots``.

The runtime-database decision and the ``503 runtime_db_unavailable`` translation
stay in the route (HTTP concerns); the query and the shaping live here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eurogas_nexus.domain.market_positioning import (
    PortfolioPnlSnapshot,
    ScreenOrderObservation,
)

if TYPE_CHECKING:  # pragma: no cover - import boundary: importing the API must not
    # load SQLAlchemy (tests/contract/test_db_foundation.py). Annotations are
    # strings here, so no runtime import is needed.
    from sqlalchemy.orm import Session

#: Canonical runtime tables the portfolio reads are composed from.
PORTFOLIO_TABLE_LINEAGE: tuple[str, ...] = (
    "screen_order_observations",
    "portfolio_pnl_snapshots",
)


def screen_orders(session: Session) -> list[ScreenOrderObservation]:
    """Return imported read-only screen-order observations, newest first."""

    from eurogas_nexus.db.models import ScreenOrderObservationRecord

    rows = session.query(ScreenOrderObservationRecord).order_by(
        ScreenOrderObservationRecord.observed_at_utc.desc(),
        ScreenOrderObservationRecord.venue,
    )
    return [screen_order_from_row(row) for row in rows.all()]


def pnl_snapshots(session: Session) -> list[PortfolioPnlSnapshot]:
    """Return indicative PnL snapshots, newest valuation first."""

    from eurogas_nexus.db.models import PortfolioPnlSnapshotRecord

    rows = session.query(PortfolioPnlSnapshotRecord).order_by(
        PortfolioPnlSnapshotRecord.valuation_time_utc.desc(),
        PortfolioPnlSnapshotRecord.portfolio_id,
    )
    return [pnl_snapshot_from_row(row) for row in rows.all()]


def screen_order_from_row(row: object) -> ScreenOrderObservation:
    """Shape one screen-order ORM row into its observation model."""

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


def pnl_snapshot_from_row(row: object) -> PortfolioPnlSnapshot:
    """Shape one PnL snapshot ORM row into its observation model."""

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
