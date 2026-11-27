"""Deals captured from exchange exports and by hand, the files they came from, the day's close.

``captured_deals`` keeps every version of a deal (one row per version): a repeated export of
the same trade adds nothing, a correction or a cancellation adds a version and marks the
earlier one superseded; nothing is deleted. Money and volume are exact decimals. Each row
says where it came from (file and line, or entered by hand, by whom). These are the desk's
own record of the day's trades before the ETRM close; the ETRM stays the official record.

``deal_day_closes`` records that a business day was closed for a book: who closed it, when,
and the end-of-day differences they acknowledged, with the figures the daily pack used.
``daily_packs`` holds the files of a pack queued for e-mail until it is sent.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class DealImportFileRecord(Base):
    """One export file received (upload or watched folder) and what it gave."""

    __tablename__ = "deal_import_files"

    file_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    format_name: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The book the file was imported into (rows may name their own).
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)  # upload | folder
    received_by: Mapped[str] = mapped_column(String(128), nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_amended: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_cancelled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_unreadable: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DealImportProblemRecord(Base):
    """A row of an export that could not be read, with the reason (shown, never dropped)."""

    __tablename__ = "deal_import_problems"
    __table_args__ = (Index("ix_deal_import_problems_day", "business_date"),)

    problem_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    line: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(48), nullable=True)
    raw_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_row: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The day the file was received (a row that could not be read has no trade date).
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Set when a later file or a manual entry supplied the deal (the row is then history).
    resolved_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                              nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


class CapturedDealRecord(Base):
    """One version of one captured deal; the newest unsuperseded version is current."""

    __tablename__ = "captured_deals"
    __table_args__ = (
        UniqueConstraint("deal_key", "version", name="uq_captured_deals_version"),
        Index("ix_captured_deals_day", "trade_date", "superseded_at_utc"),
        Index("ix_captured_deals_key", "deal_key"),
    )

    version_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    deal_key: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # live | cancelled
    venue: Mapped[str] = mapped_column(String(32), nullable=False)
    venue_trade_id: Mapped[str] = mapped_column(String(128), nullable=False)
    leg_id: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                            nullable=True)
    trader: Mapped[str] = mapped_column(String(128), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    cleared: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    product: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_start: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_end: Mapped[date] = mapped_column(Date, nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    volume_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    total_mwh: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    price_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    physical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    instrument: Mapped[str] = mapped_column(String(16), nullable=False)
    fees: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    fee_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin: Mapped[str] = mapped_column(String(8), nullable=False)  # file | manual
    file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: The fields a person typed for a manual deal (rule 19: the result says so).
    entered_by_hand: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    entered_by: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                               nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class DealDayCloseRecord(Base):
    """A business day closed for one book, with the differences a named person acknowledged."""

    __tablename__ = "deal_day_closes"
    __table_args__ = (Index("ix_deal_day_closes_day", "business_date", "book_id"),)

    close_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    closed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    closed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    etrm_file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    etrm_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Every difference listed at the close, each with its acknowledgement.
    differences: Mapped[list] = mapped_column(JSON, nullable=False)
    #: Per deal key, the deal's value at the close's marks (decimal text), for the next day's
    #: P&L; and the day's P&L by trader and hub (decimal text).
    figures: Mapped[dict] = mapped_column(JSON, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    superseded_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                               nullable=True)


class DealPositionKindRecord(Base):
    """A person's choice that a captured deal counts as physical or financial (entered by hand).

    Overrides the rule file (``reference_data/desk/position_kinds.toml``) for that deal key in
    every version; a later choice supersedes it and the earlier one is kept.
    """

    __tablename__ = "deal_position_kinds"
    __table_args__ = (Index("ix_deal_position_kinds_key", "deal_key", "superseded_at_utc"),)

    choice_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    deal_key: Mapped[str] = mapped_column(String(200), nullable=False)
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # physical | financial
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    entered_by: Mapped[str] = mapped_column(String(128), nullable=False)
    entered_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                               nullable=True)


class DailyPackRecord(Base):
    """The files of one daily pack queued for e-mail (attached when the outbox row is sent)."""

    __tablename__ = "daily_packs"

    pack_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    notification_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # management | risk
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)  # click | schedule
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The books the pack's figures cover (the generating person's or the service's scope).
    scope_note: Mapped[str] = mapped_column(String(500), nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False)
    pdf: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    xlsx: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sent_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
