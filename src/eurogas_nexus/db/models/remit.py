"""REMIT urgent market messages (gas facility unavailability), one row per message version."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class RemitUmmRecord(Base):
    """One version of one UMM as published on an inside-information platform.

    Versions are kept, not overwritten, so the history of a revised outage stays readable;
    readers take the latest version per ``message_id``.
    """

    __tablename__ = "remit_umm_messages"
    __table_args__ = (
        Index("ix_remit_umm_messages_message_version", "message_id", "version"),
        Index("ix_remit_umm_messages_event_stop", "event_stop_utc"),
    )

    record_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_status: Mapped[str] = mapped_column(String(16), nullable=False)
    unavailability_type: Mapped[str] = mapped_column(String(16), nullable=False)
    event_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_stop_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    asset_name: Mapped[str] = mapped_column(String(160), nullable=False)
    asset_eic: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    balancing_zone: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    technical_capacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_capacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unavailable_capacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unavailable_mcm_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    unavailable_gwh_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    market_participant: Mapped[str] = mapped_column(String(160), nullable=False)
    remarks: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="REMIT")
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    ingested_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
