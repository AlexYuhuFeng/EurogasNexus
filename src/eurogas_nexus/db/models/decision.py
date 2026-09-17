"""Decision Case persistence model (Architecture V2 Wave 6).

Two tables: the case container itself, and its decision records as their own rows.
Records are separated because they are the audit-relevant part of the model - a
named human's conclusion, its evidence references and its timestamp - and because
a case may be reopened and decided again without losing history.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class DecisionCaseRecord(Base):
    """One decision case: objective, context, assumptions, alternatives, evidence."""

    __tablename__ = "decision_cases"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    objective: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Active Context the case was opened in.
    gas_day: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    delivery_product: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    hub_id: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    portfolio_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    # Reproducibility reference (Architecture V2 Analysis Snapshot).
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    assumptions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    alternatives_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ai_findings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class DecisionCaseDecisionRecord(Base):
    """A named human's conclusion about a case. Evidence, never approval to act."""

    __tablename__ = "decision_case_records"

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("decision_cases.case_id", ondelete="CASCADE"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
