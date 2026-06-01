"""Market positioning SQLAlchemy models for read-only order/PnL observations."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class ScreenOrderObservationRecord(Base):
    """Imported external screen order state, not an order-entry record."""

    __tablename__ = "screen_order_observations"

    order_observation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    venue: Mapped[str] = mapped_column(String(64), nullable=False)
    account_label: Mapped[str] = mapped_column(String(128), nullable=False)
    external_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hub: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_code: Mapped[str] = mapped_column(String(128), nullable=False)
    delivery_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    filled_quantity_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_quantity_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    linked_strategy_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    linked_resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PortfolioPnlSnapshotRecord(Base):
    """Indicative portfolio PnL valuation snapshot."""

    __tablename__ = "portfolio_pnl_snapshots"

    pnl_snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    strategy_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    valuation_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    realized_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    cash_value_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    market_value_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    valuation_basis: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
