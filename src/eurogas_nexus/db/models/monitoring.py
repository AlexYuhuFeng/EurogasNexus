"""Persistence model for normalized monitoring alerts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class MonitoringAlertRecord(Base):
    """A deduplicated decision-support alert with optional LLM enrichment."""

    __tablename__ = "monitoring_alerts"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_monitoring_alerts_fingerprint"),
        Index("ix_monitoring_alerts_status_time", "status", "detected_at_utc"),
        Index(
            "ix_monitoring_alerts_category_severity",
            "category",
            "severity",
            "updated_at_utc",
        ),
    )

    alert_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(96), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    title_en: Mapped[str] = mapped_column(String(256), nullable=False)
    title_zh_cn: Mapped[str] = mapped_column(String(256), nullable=False)
    message_en: Mapped[str] = mapped_column(Text(), nullable=False)
    message_zh_cn: Mapped[str] = mapped_column(Text(), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detected_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    llm_provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    llm_status: Mapped[str] = mapped_column(String(64), nullable=False)
    llm_summary_en: Mapped[str | None] = mapped_column(Text(), nullable=True)
    llm_summary_zh_cn: Mapped[str | None] = mapped_column(Text(), nullable=True)
    llm_last_attempt_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
