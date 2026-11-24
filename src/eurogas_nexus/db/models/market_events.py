"""The market event outbox (M4, ADR Decision 28).

- ``market_events``: append-only canonical events. One row per revision of an event; a
  revision never overwrites the one it supersedes. ``seq`` orders the log for delivery and
  replay. ``(event_key, revision)`` and ``event_id`` are unique, so a replayed source history
  cannot write a second copy.
- ``market_event_deliveries``: one row per event and consumer, written in the publisher's
  transaction (the transactional outbox): its status (``pending``, ``processed``,
  ``superseded``, ``failed`` awaiting retry, ``dead`` after the last attempt), attempts, the
  next attempt time, the processing and notification times and the consumer's result.

PostgreSQL is the only store; there is no broker. ``LISTEN/NOTIFY`` only wakes a worker
early, the tables are the truth.

DATA-1: ``writer_txid`` is the writing transaction's id (PostgreSQL fills it by default,
migration ``0082_data1_integration``); the change feed orders by it and ``seq`` so a reader
never skips an event committed after one it has already read.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base

#: BIGINT on PostgreSQL, the SQLite rowid alias in tests (only INTEGER autoincrements there).
SEQ = BigInteger().with_variant(Integer(), "sqlite")


class MarketEventRecord(Base):
    """One revision of one canonical market event."""

    __tablename__ = "market_events"
    __table_args__ = (
        UniqueConstraint("event_key", "revision", name="uq_market_events_key_revision"),
        Index("ix_market_events_subject", "subject_key", "ingested_at_utc"),
        Index("ix_market_events_source", "source_id", "ingested_at_utc"),
        Index("ix_market_events_feed", "writer_txid", "seq"),
    )

    seq: Mapped[int] = mapped_column(SEQ, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_key: Mapped[str] = mapped_column(String(40), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(160), nullable=False)
    input_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    dependency_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    market_time_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingested_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The writing transaction (PostgreSQL default ``pg_current_xact_id()``; NULL on SQLite
    #: and for rows written before migration 0082). Never set by code.
    writer_txid: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, server_default=FetchedValue()
    )


class MarketEventDeliveryRecord(Base):
    """One consumer's processing of one event revision."""

    __tablename__ = "market_event_deliveries"
    __table_args__ = (
        Index("ix_market_event_deliveries_due", "consumer", "status", "available_at_utc"),
    )

    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_seq: Mapped[int] = mapped_column(
        SEQ, ForeignKey("market_events.seq", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notified_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


__all__ = ["MarketEventDeliveryRecord", "MarketEventRecord"]
