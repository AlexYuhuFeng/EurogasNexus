"""Reviewed public transmission tariffs an administrator enters (four eyes). Migration 0075.

ENTSOG does not publish every leg route pricing needs (National Gas's charges, GTS's exit to
BBL, LNG and Norwegian landing entries ...). An administrator enters the operator's published
charge with where it was read; a second person reviews it. The entry is mirrored into the
tariff register (``tso_tariffs``, ``tariff_id`` ``entry-<entry_id>``) so route pricing reads
it like any other row: a candidate as indicative, a reviewed entry with the operator's own
status. An ingested published row for the same leg and period retires it.
"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class TsoTariffEntryRecord(Base):
    """One operator-published transmission charge, as an administrator entered it."""

    __tablename__ = "tso_tariff_entry"
    __table_args__ = (
        CheckConstraint(
            "state IN ('CANDIDATE', 'REVIEWED', 'RETIRED', 'WITHDRAWN')",
            name="ck_tso_tariff_entry_state",
        ),
        CheckConstraint("direction IN ('ENTRY', 'EXIT')", name="ck_tso_tariff_entry_direction"),
        CheckConstraint(
            "published_status IN ('FINAL', 'INDICATIVE')", name="ck_tso_tariff_entry_status"
        ),
        Index("ix_tso_tariff_entry_leg", "point_id", "direction", "capacity_product"),
    )

    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    operator_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tso: Mapped[str] = mapped_column(String(128), nullable=False)
    point_id: Mapped[str] = mapped_column(String(128), nullable=False)
    point_name: Mapped[str] = mapped_column(String(256), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    market_area: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    capacity_product: Mapped[str] = mapped_column(String(32), nullable=False)
    firmness: Mapped[str] = mapped_column(String(32), nullable=False)
    tariff_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    #: The last gas day the charge applies (inclusive).
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    gas_year: Mapped[str] = mapped_column(String(16), nullable=False)
    #: What the operator published the figure as.
    published_status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    published_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: Where in the document the figure is (page, table, row).
    source_location: Mapped[str] = mapped_column(String(256), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    closed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
