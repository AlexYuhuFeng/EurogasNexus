"""Market-data licence register (one row per vendor contract or licence schedule), and the
aggregated record of who read which licensed source family (GOV-1, P6)."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class MarketDataLicenceRecord(Base):
    __tablename__ = "market_data_licences"

    licence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False)
    source_family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    licence_type: Mapped[str] = mapped_column(String(16), nullable=False)
    licensed_use: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    offices: Mapped[list | None] = mapped_column(JSON, nullable=True)
    seats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_reference: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Whether the licence permits derived figures to be redistributed outside the firm (a
    #: shareable market report). Unknown is no (migration 0064).
    redistribution_allowed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default=false()
    )
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LicensedDataUseRecord(Base):
    """How often one principal read one licensed source family on one day, through one route.

    One row per (day, principal, family, surface), counted up as requests arrive, never one
    row per request (migration 0079). ``surface`` is the route template, prefixed
    ``export:<format>`` when the rows were written to a file. This answers a vendor's
    usage declaration: who read what, how often, and what left the platform as a file.
    """

    __tablename__ = "licensed_data_use"
    __table_args__ = (
        PrimaryKeyConstraint(
            "usage_day", "principal_id", "source_family", "surface",
            name="pk_licensed_data_use",
        ),
        Index("ix_licensed_data_use_family_day", "source_family", "usage_day"),
    )

    usage_day: Mapped[date] = mapped_column(Date, nullable=False)
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_family: Mapped[str] = mapped_column(String(32), nullable=False)
    surface: Mapped[str] = mapped_column(String(160), nullable=False)
    reads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
