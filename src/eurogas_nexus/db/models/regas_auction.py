"""Regas auction cases and the snapshots the desk saved of them (the regas auction desk).

``regas_auction_cases``: one row per auction the desk works: the terminal and slot, the
auction window, the cargo owner's offer, the send-out profile and the cost lines, each value
with where it came from (held in ``inputs``, a JSON document validated by
``application/regas_auction``). The row carries its book, so book isolation applies to it as to
every table with a ``book_id`` (``db/book_scope``). It closes as won, lost or lapsed with a
note; nothing is booked, bid or ordered from it (AGENTS.md rule 8).

``regas_auction_snapshots``: what the answer was when a trader acted on it: the inputs, every
price with its time and source, the result, and the valuation snapshot the prices were read
through (``valuation_snapshots``), so the desk and the remote risk function can see after the
window closes what the limit was at each point and why. Snapshots are never changed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base

CASE_STATES = ("open", "won", "lost", "lapsed")


class RegasAuctionCaseRecord(Base):
    """One regas slot auction the desk is working, and how it ended."""

    __tablename__ = "regas_auction_cases"
    __table_args__ = (
        CheckConstraint("state IN ('open', 'won', 'lost', 'lapsed')",
                        name="ck_regas_auction_cases_state"),
        Index("ix_regas_auction_cases_state", "state", "auction_closes_at_utc"),
    )

    case_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    terminal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    terminal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The cargo owner (a counterparty with a credit line, or entered by hand).
    counterparty_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    counterparty_name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False, default="open")
    auction_opens_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                                  nullable=True)
    auction_closes_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                            nullable=False)
    offer_expires_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                                  nullable=True)
    #: The capacity notice the case was opened from, when the operator's notice is held.
    notice_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: The case's inputs, each with its source (see ``application/regas_auction``).
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    closed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: For a won case: what the slot and its hedges would become in the position (the seam to
    #: booking, a later step). Recorded, never booked.
    position_seam: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class RegasAuctionSnapshotRecord(Base):
    """The answer at one moment a trader acted on it, as it was."""

    __tablename__ = "regas_auction_snapshots"
    __table_args__ = (Index("ix_regas_auction_snapshots_case", "case_id", "saved_at_utc"),)

    snapshot_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(40), nullable=False)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    saved_by: Mapped[str] = mapped_column(String(128), nullable=False)
    saved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    #: Every price read, with its time, source and class.
    prices: Mapped[list] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    #: The valuation snapshot the reads went through (``valuation_snapshots``), for replay.
    valuation_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
