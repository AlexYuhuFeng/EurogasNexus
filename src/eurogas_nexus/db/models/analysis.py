"""Analysis and reporting persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class AnalysisRunRecord(Base):
    """Stored governed LLM/data-analysis run."""

    __tablename__ = "analysis_runs"

    analysis_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class GeneratedReportRecord(Base):
    """Stored generated report snapshot."""

    __tablename__ = "generated_reports"

    report_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_start_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_end_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    sections: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class BusinessOntologyRecord(Base):
    """Optional DB-managed business ontology entry."""

    __tablename__ = "business_ontology_terms"

    ontology_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    term: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_en: Mapped[str] = mapped_column(Text(), nullable=False)
    definition_zh_cn: Mapped[str] = mapped_column(Text(), nullable=False)
    relationships: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
