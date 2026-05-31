"""Route-cost and contract decision-support persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class TsoTariffRecord(Base):
    __tablename__ = "tso_tariffs"

    tariff_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    tso: Mapped[str] = mapped_column(String(128), nullable=False)
    market_area: Mapped[str] = mapped_column(String(64), nullable=False)
    gas_year: Mapped[str] = mapped_column(String(16), nullable=False)
    point_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_point_name: Mapped[str] = mapped_column(String(256), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    capacity_product: Mapped[str] = mapped_column(String(32), nullable=False)
    firmness: Mapped[str] = mapped_column(String(32), nullable=False)
    tariff_value: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tariff_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_table: Mapped[str] = mapped_column(String(256), nullable=False)
    source_page: Mapped[int | None] = mapped_column(nullable=True)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UpstreamResourceContractRecord(Base):
    __tablename__ = "upstream_resource_contracts"

    contract_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    contract_name: Mapped[str] = mapped_column(String(256), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_point_name: Mapped[str] = mapped_column(String(256), nullable=False)
    gas_year: Mapped[str] = mapped_column(String(16), nullable=False)
    delivery_quantity_mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    contract_price_gbp_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    settlement_frequency: Mapped[str] = mapped_column(String(32), nullable=False)
    upstream_payment_lag_days: Mapped[int] = mapped_column(nullable=False)
    screen_sale_cash_lag_days: Mapped[int] = mapped_column(nullable=False)
    delivery_tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False)
    nomination_tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False)
    tolerance_risk_allowance_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    annual_financing_rate_pct: Mapped[float] = mapped_column(Float, nullable=False)
    owned_entry_capacity_mwh_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    owned_exit_capacity_mwh_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    allowed_exit_points: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    eligible_sale_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CapacityProfileRecord(Base):
    __tablename__ = "capacity_profiles"

    capacity_profile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(128), nullable=False)
    point_name: Mapped[str] = mapped_column(String(256), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    capacity_mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    firmness: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RouteCandidateRecord(Base):
    __tablename__ = "route_candidates"

    route_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    route_name: Mapped[str] = mapped_column(String(256), nullable=False)
    start_point_name: Mapped[str] = mapped_column(String(256), nullable=False)
    target_point_name: Mapped[str] = mapped_column(String(256), nullable=False)
    business_model: Mapped[str] = mapped_column(String(64), nullable=False)
    route_legs: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    required_entry_point_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    required_exit_point_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    required_tso_access: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_systems: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LiveMarketMarkRecord(Base):
    __tablename__ = "live_market_marks"

    mark_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    venue: Mapped[str] = mapped_column(String(64), nullable=False)
    hub: Mapped[str] = mapped_column(String(64), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    bid_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    mark_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
