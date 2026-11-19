"""Tracked strategies (shadow run on the Spreads StrategySpec): paper only, never an order.

``strategy_tracks``: one saved StrategySpec per row, owned by the principal who saved it, with
its mode (``daily`` on new closes, ``intraday`` on arriving quotes), the intraday rule and the
paper book's state. ``strategy_track_events``: what happened, append-only: signals, paper
fills and refusals, liquidity gates, and equity marks (throttled).

Nothing in either table can place, route or nominate anything.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class StrategyTrackRecord(Base):
    __tablename__ = "strategy_tracks"
    __table_args__ = (
        Index("ix_strategy_tracks_owner", "owner_principal_id", "state"),
        Index("ix_strategy_tracks_mode_state", "mode", "state"),
    )

    track_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_principal_id: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # daily | intraday
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    spec_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    rule_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    #: Instrument keys (``HUB|product``) this track listens to, for the on-arrival lookup.
    instruments: Mapped[list] = mapped_column(JSON, nullable=False)
    book_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_evaluated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signal_changed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class StrategyTrackEventRecord(Base):
    __tablename__ = "strategy_track_events"
    __table_args__ = (Index("ix_strategy_track_events_track", "track_id", "at_utc"),)

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    track_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("strategy_tracks.track_id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
