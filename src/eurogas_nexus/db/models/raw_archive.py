"""Raw payload archive model (raw -> canonical lineage)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class RawPayloadArchiveRecord(Base):
    """Immutable raw provider payload kept for lineage and replay.

    Normalized rows carry ``source_reference`` values that resolve to these
    archives, so the raw -> canonical transformation is auditable (Gate 4).
    """

    __tablename__ = "raw_payload_archives"

    archive_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    payload_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
