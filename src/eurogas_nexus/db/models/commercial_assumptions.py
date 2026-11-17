"""Assumption sets, firm marks and valuation snapshots (commercial design basis 2, J.3).

- ``assumption_sets`` / ``assumption_set_versions`` / ``assumption_values``: the firm's
  named, versioned inputs (financing rate, load factor, fuel where not published, storage
  fees, freight and LNG figures). Values change only by a new version; a version is read by
  a valuation only once a second person approved it.
- ``firm_marks``: the customer's own price marks per hub and delivery period, in the hub's
  native unit, append-only (a new mark supersedes the previous one; both stay for replay).
  There is no class column: a firm mark is always read as class ``firm_mark``.
- ``valuation_snapshots`` / ``valuation_snapshot_inputs``: what one evaluation read, input
  by input, with class, source and as-of, so the evaluation replays to identical figures.

Decimal columns (``Numeric``) hold the figures exactly; nothing is stored in a column whose
name carries a currency.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base

DECIMAL = Numeric(28, 10, asdecimal=True)


class AssumptionSetRecord(Base):
    """A named assumption set, owned by the organisation or by one book."""

    __tablename__ = "assumption_sets"
    __table_args__ = (UniqueConstraint("name", "book_id", name="uq_assumption_sets_name_book"),)

    set_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    #: ``NULL``: the organisation's set; otherwise the book it belongs to.
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssumptionSetVersionRecord(Base):
    """One version of a set: draft, approved (readable by valuations) or retired."""

    __tablename__ = "assumption_set_versions"
    __table_args__ = (
        UniqueConstraint("set_id", "version", name="uq_assumption_set_versions_set_version"),
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    set_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assumption_sets.set_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_state: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    values_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssumptionValueRecord(Base):
    """One typed value of one version."""

    __tablename__ = "assumption_values"

    version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("assumption_set_versions.version_id", ondelete="CASCADE"),
        primary_key=True,
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    range_low: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    range_high: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    note: Mapped[str] = mapped_column(String(400), nullable=False, default="")


class FirmMarkRecord(Base):
    """One firm mark; the latest unsuperseded row per hub and period is current."""

    __tablename__ = "firm_marks"
    __table_args__ = (Index("ix_firm_marks_hub_period", "hub", "period_label", "entered_at_utc"),)

    mark_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    period_label: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    note: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    entered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    entered_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ValuationSnapshotRecord(Base):
    """One evaluation's input record: the version line of each input set."""

    __tablename__ = "valuation_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    demo_desk: Mapped[bool] = mapped_column(Boolean, nullable=False)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_class: Mapped[str] = mapped_column(String(16), nullable=False)
    fx_method: Mapped[str] = mapped_column(String(16), nullable=False)
    assumption_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    curve_as_of_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fx_as_of_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rates_as_of_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    book_as_of_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tariff_documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False)
    inputs_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class ValuationSnapshotInputRecord(Base):
    """One input of one snapshot, in reading order."""

    __tablename__ = "valuation_snapshot_inputs"

    snapshot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("valuation_snapshots.snapshot_id", ondelete="CASCADE"),
        primary_key=True,
    )
    input_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    input_class: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Decimal text, so a replay reads back exactly the figure the evaluation used.
    value_text: Mapped[str | None] = mapped_column(String(48), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    as_of_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
