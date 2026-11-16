"""Generated market reports: immutable records a decision can cite (migration 0064)."""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class MarketReportRecord(Base):
    """One generated market report, written once and never updated.

    The record holds what is needed to reopen the report exactly and to say what it was
    built from: the validated plan, the audience, the full data snapshot the HTML was
    rendered from (with its hash), the rendered HTML (with its hash), the template version,
    who or what generated it and under which data scopes, the sources and licensed families
    it read, and how the model was used (which sections it reworded, each checker verdict).
    """

    __tablename__ = "market_reports"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('daily', 'weekly', 'monthly', 'situation', 'ask')",
            name="ck_market_reports_kind",
        ),
        CheckConstraint("audience IN ('internal', 'shareable')", name="ck_market_reports_audience"),
        Index("ix_market_reports_kind_created", "kind", "created_at_utc"),
        Index("ix_market_reports_generated_by", "generated_by", "created_at_utc"),
    )

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    variant: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    audience: Mapped[str] = mapped_column(String(16), nullable=False)
    headline: Mapped[str] = mapped_column(Text(), nullable=False)
    #: The validated plan: sections, hubs, countries, period, subject, question.
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: The instant the data was read as of.
    as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    html: Mapped[str] = mapped_column(Text(), nullable=False)
    html_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The principal the report ran as (a person, or a declared service principal).
    generated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    generated_by_type: Mapped[str] = mapped_column(String(16), nullable=False)
    data_scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    #: Source systems behind the figures; a reader must be entitled to every one.
    source_systems: Mapped[list] = mapped_column(JSON, nullable=False)
    licensed_families: Mapped[list] = mapped_column(JSON, nullable=False)
    #: Books behind the Our book figures; a reader must see every one.
    book_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: ``{"attempted": n, "passed": n, "sections": {key: {"ok": bool, "check": str}}}``.
    model_use: Mapped[dict] = mapped_column(JSON, nullable=False)
    #: What started it: ``{"type": "user"|"schedule"|"alert"|"outage", ...}``.
    trigger_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
