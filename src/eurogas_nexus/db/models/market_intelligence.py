"""Persistence models for normalized market quotes and intraday decisions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class MarketQuoteRecord(Base):
    """Append-style normalized L1 quote from a licensed or simulated source."""

    __tablename__ = "market_quotes"
    __table_args__ = (
        Index(
            "ix_market_quotes_lookup",
            "hub",
            "product",
            "source_system",
            "observed_at_utc",
        ),
        Index("ix_market_quotes_observed_at", "observed_at_utc"),
    )

    quote_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    venue: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(128), nullable=False)
    hub: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_start_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    delivery_end_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    bid_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid_quantity_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask_quantity_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    freshness: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CompanyTsoAccessRecord(Base):
    """Effective-dated company access posture for a TSO or operator."""

    __tablename__ = "company_tso_access"
    __table_args__ = (
        Index("ix_company_tso_access_lookup", "tso", "status", "valid_from_utc"),
    )

    access_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tso: Mapped[str] = mapped_column(String(128), nullable=False)
    market_area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_to_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IntradayOpportunityRecord(Base):
    """Persisted backend decision snapshot linked to executable quote sides."""

    __tablename__ = "intraday_opportunities"
    __table_args__ = (
        Index("ix_intraday_opportunities_status_time", "status", "detected_at_utc"),
        Index(
            "ix_intraday_opportunities_route_product",
            "route_id",
            "product",
            "detected_at_utc",
        ),
    )

    opportunity_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    buy_quote_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sell_quote_id: Mapped[str] = mapped_column(String(128), nullable=False)
    route_id: Mapped[str] = mapped_column(String(128), nullable=False)
    route_name: Mapped[str] = mapped_column(String(256), nullable=False)
    buy_venue: Mapped[str] = mapped_column(String(64), nullable=False)
    sell_venue: Mapped[str] = mapped_column(String(64), nullable=False)
    buy_hub: Mapped[str] = mapped_column(String(32), nullable=False)
    sell_hub: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_start_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    delivery_end_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    comparison_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    comparison_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    buy_ask: Mapped[float] = mapped_column(Float, nullable=False)
    sell_bid: Mapped[float] = mapped_column(Float, nullable=False)
    gross_spread: Mapped[float] = mapped_column(Float, nullable=False)
    route_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    trading_cost: Mapped[float] = mapped_column(Float, nullable=False)
    risk_buffer: Mapped[float] = mapped_column(Float, nullable=False)
    net_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_quantity_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    indicative_net_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_age_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    cost_components: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    missing_inputs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    detected_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_until_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
