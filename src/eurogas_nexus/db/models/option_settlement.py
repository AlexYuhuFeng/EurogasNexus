"""End-of-day gas option settlements with their implied volatility. Migration 0077.

One row per source, hub, contract (the underlying future's delivery period), trade date,
strike and call/put. Rows come from a licensed exchange or vendor export
(``ingestion/option_settlements.py``) or, in the demo, from the simulator
(``ingestion/simulated_option_settlements.py``, ``simulated`` true). The implied volatility
is the exchange's when it publishes one, else Black-76 solved at import; a row without one
says why in ``iv_reason``. Reads apply row-level entitlement by ``source_system`` and source
precedence per contract (``domain/market/options.choose_option_source``).

期权日终结算价及其隐含波动率；按来源族授权过滤，按合约做来源优先级选择。
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class OptionSettlementRecord(Base):
    """One option settlement (European option on a gas future)."""

    __tablename__ = "option_settlements"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "hub",
            "contract",
            "trade_date",
            "strike",
            "option_type",
            name="uq_option_settlement_key",
        ),
        CheckConstraint("option_type IN ('C', 'P')", name="ck_option_settlement_type"),
        CheckConstraint(
            "premium_style IN ('futures_style', 'premium')", name="ck_option_settlement_style"
        ),
        CheckConstraint("strike > 0", name="ck_option_settlement_strike"),
        CheckConstraint("settlement_price >= 0", name="ck_option_settlement_price"),
        Index("ix_option_settlements_hub_day", "hub", "trade_date"),
    )

    settlement_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    venue: Mapped[str] = mapped_column(String(32), nullable=False)
    hub: Mapped[str] = mapped_column(String(8), nullable=False)
    #: Delivery period of the underlying future (``Jan-27``, ``Q1-27``).
    contract: Mapped[str] = mapped_column(String(24), nullable=False)
    product_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    delivery_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: ``futures_style`` (premium margined, not discounted) or ``premium`` (paid up front).
    premium_style: Mapped[str] = mapped_column(String(16), nullable=False)
    option_type: Mapped[str] = mapped_column(String(1), nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    settlement_price: Mapped[float] = mapped_column(Float, nullable=False)
    #: Price unit of strike, settlement and underlying (the hub's native quote by default).
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    underlying_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: ``file``, ``futures_settlement`` or ``put_call_parity``.
    underlying_basis: Mapped[str | None] = mapped_column(String(24), nullable=True)
    #: Annualised, decimal (0.45 is 45 %).
    implied_vol: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: ``exchange`` (published by the source) or ``black76`` (solved at import).
    iv_basis: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Why no implied volatility exists (``at_intrinsic``, ``no_underlying``, ...).
    iv_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    forward_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    freshness: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
