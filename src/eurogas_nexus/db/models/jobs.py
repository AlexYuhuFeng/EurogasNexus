"""Unified Job persistence model (Architecture V2 Wave 8)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class JobRecord(Base):
    """One tracked long-running operation (ingestion, build, optimisation, agent)."""

    __tablename__ = "job_records"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    job_version: Mapped[str] = mapped_column(String(16), nullable=False, default="job/v1")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    principal: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancellable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provenance_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
