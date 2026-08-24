"""Optimization run persistence models (Gate 3 evidence trail)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class OptimizationRunRecord(Base):
    """Immutable input/output snapshot of one optimization run.

    Every /api/optimization/* run persists what was decided from what inputs
    so evidence can be reconstructed later (Gate 3).
    """

    __tablename__ = "optimization_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    optimization_type: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_context: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
