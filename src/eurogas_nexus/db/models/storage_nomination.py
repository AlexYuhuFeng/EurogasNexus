"""Storage and nomination master-data persistence models (R34A)."""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class StorageFacilityMasterRecord(Base):
    """DB-owned storage facility parameters for runtime dispatch assessment."""

    __tablename__ = "storage_facility_masters"

    facility_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    market_hub: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    minimum_inventory_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_inventory_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_injection_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_withdrawal_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    injection_efficiency: Mapped[float] = mapped_column(Float, nullable=False)
    withdrawal_efficiency: Mapped[float] = mapped_column(Float, nullable=False)
    injection_cost_gbp_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    withdrawal_cost_gbp_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    terminal_inventory_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_from_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StorageInventoryObservationRecord(Base):
    """Latest DB-owned storage inventory observation (as-of composition)."""

    __tablename__ = "storage_inventory_observations"

    observation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    facility_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("storage_facility_masters.facility_id"),
        nullable=False,
    )
    inventory_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class NominationWindowMasterRecord(Base):
    """DB-owned nomination/renomination window rules."""

    __tablename__ = "nomination_window_masters"

    window_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    opens_at: Mapped[time] = mapped_column(Time, nullable=False)
    closes_at: Mapped[time] = mapped_column(Time, nullable=False)
    maximum_change_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_from_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
