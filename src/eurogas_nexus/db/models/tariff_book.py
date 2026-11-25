"""The tariff book: every version of every public tariff, and capacity notices (TAR-1).

Migration ``0083_tar1_tariff_book``, ADR Decision 34.

``tariff_versions`` is append-only except for one column: when a newer version of the same
``tariff_key`` is recorded, the version before it gets ``superseded_at_utc``. A read "as of T"
takes, per key, the version recorded at or before T and not superseded by T. The registers
route pricing reads (``tso_tariffs``, ``lng_terminal_tariff``) stay as they are; this table is
their history.

``capacity_notices`` holds upcoming capacity windows: standard auctions (rule-derived from the
CAM network code), LNG slot offers and secondary-capacity windows imported from a publisher's
own notice. One row per notice key; a changed notice updates the row and counts a revision.
Notices publish no market event: they change no price an evaluator reads, and the capacity
event class carries a 24-hour staleness expectation a monthly calendar would trip.

TAR-1：费率版本表（只追加，仅回填被取代时间）与容量通知表（拍卖、LNG 窗口、二级容量）。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class TariffVersionRecord(Base):
    """One version of one public tariff, as its publisher stated it."""

    __tablename__ = "tariff_versions"
    __table_args__ = (
        UniqueConstraint("tariff_key", "version", name="uq_tariff_versions_key_version"),
        CheckConstraint("status IN ('INDICATIVE', 'FINAL')", name="ck_tariff_versions_status"),
        CheckConstraint(
            "change_kind IN ('first', 'revised', 'status_change', 'withdrawn')",
            name="ck_tariff_versions_change_kind",
        ),
        Index("ix_tariff_versions_current", "superseded_at_utc", "publisher_id"),
        Index("ix_tariff_versions_facility", "facility_id", "period_from"),
        Index("ix_tariff_versions_recorded", "recorded_at_utc"),
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tariff_key: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: ``INDICATIVE->FINAL`` or ``FINAL->INDICATIVE`` when the status changed, else NULL.
    status_change: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publisher_id: Mapped[str] = mapped_column(String(64), nullable=False)
    facility_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    facility_id: Mapped[str] = mapped_column(String(128), nullable=False)
    facility_name: Mapped[str] = mapped_column(String(256), nullable=False)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    market_area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    product: Mapped[str] = mapped_column(String(32), nullable=False)
    duration: Mapped[str | None] = mapped_column(String(16), nullable=True)
    firmness: Mapped[str | None] = mapped_column(String(16), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    by_class: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    status_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: When this platform first held this content (the as-of boundary).
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: When the next version of the same key was recorded; NULL while current.
    superseded_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The ``tariff.changed`` market event this version published.
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CapacityNoticeRecord(Base):
    """One upcoming capacity window: an auction, an LNG slot offer, a secondary window."""

    __tablename__ = "capacity_notices"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('auction', 'lng_slot', 'secondary_capacity')",
            name="ck_capacity_notices_kind",
        ),
        CheckConstraint("basis IN ('rule_derived', 'published')", name="ck_capacity_notices_basis"),
        Index("ix_capacity_notices_opens", "opens_at_utc"),
        Index("ix_capacity_notices_publisher", "publisher_id", "kind"),
    )

    notice_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    publisher_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    #: ``rule_derived`` (computed from the network code) or ``published`` (the publisher's own).
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    facility_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    facility_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    facility_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    product: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    opens_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offers_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    offers_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: open, cancelled (a published notice the publisher withdrew).
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
