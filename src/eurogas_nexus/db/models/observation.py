"""Observation domain SQLAlchemy models."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class MarketObservationRecord(Base):
    __tablename__ = "market_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market_venue: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FxObservationRecord(Base):
    __tablename__ = "fx_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pair: Mapped[str] = mapped_column(String(16), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    rate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_date: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FlowObservationRecord(Base):
    __tablename__ = "flow_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    point_id: Mapped[str] = mapped_column(String(64), nullable=False)
    point_name: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    flow_mcm_d: Mapped[float] = mapped_column(Float, nullable=False)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)


class StorageObservationRecord(Base):
    __tablename__ = "storage_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_dataset: Mapped[str] = mapped_column(String(16), nullable=False)
    facility_id: Mapped[str] = mapped_column(String(64), nullable=False)
    facility_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    inventory_twh: Mapped[float | None] = mapped_column(Float, nullable=True)
    working_capacity_twh: Mapped[float | None] = mapped_column(Float, nullable=True)
    fill_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    injection_twh_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    withdrawal_twh_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)


class LngObservationRecord(Base):
    __tablename__ = "lng_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_dataset: Mapped[str] = mapped_column(String(16), nullable=False)
    terminal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    terminal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    inventory_twh: Mapped[float | None] = mapped_column(Float, nullable=True)
    send_out_twh_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    dtmi_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    principal: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(String, nullable=False)
    event_ts_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class EntitlementDecisionRecord(Base):
    __tablename__ = "entitlement_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    evaluated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ProviderCredentialRecord(Base):
    __tablename__ = "provider_credentials"

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text(), nullable=False)
    redacted_preview: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_tested_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
