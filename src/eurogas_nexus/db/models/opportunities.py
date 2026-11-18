"""The opportunity store (commercial design basis 2, J.3).

- ``opportunities``: one current record per dedupe key (type, legs, delivery period, books),
  with its lifecycle fields; re-evaluation updates it, never duplicates it.
- ``opportunity_versions``: the frozen object at each version (a material change or a state
  change makes a version); a case opened from an opportunity points at one of these.
- ``opportunity_legs`` / ``opportunity_checks``: the current version's arithmetic and checks,
  queryable.
- ``opportunity_dependencies``: the input keys each record read (``hub:TTF:2027-01``,
  ``tariff:...``, ``contract:<id>``), stored from the first release so an outbox event can
  re-evaluate only what depends on it.
- ``opportunity_user_states``: a person's dismissal (with its reason) or follow, per key.
- ``opportunity_evaluations``: each evaluation run, its snapshot and each evaluator's status.
- ``opportunity_settings``: the organisation's thresholds (decision L5).

Money is a value column plus a currency column; no column name carries a currency.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base

DECIMAL = Numeric(28, 10, asdecimal=True)


class OpportunityRecord(Base):
    """The current state of one opportunity key."""

    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_state_lane", "state", "lane"),
        Index("ix_opportunities_expires", "expires_at_utc"),
    )

    opportunity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opp_key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    lane: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    assessed_state: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The figure the current version was cut on; a move of 20 % from it is material.
    version_basis: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    claim_key: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    headline_value: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    headline_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    value_amount: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    value_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    #: The value in the threshold/reporting currency, when it could be converted.
    reporting_value: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    reporting_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    volume_value: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    period_label: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    quality_class: Mapped[str] = mapped_column(String(16), nullable=False)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    book_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_families: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    blocker_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_seen_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_evaluated_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_changed_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consecutive_seen: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_missed: Mapped[int] = mapped_column(Integer, nullable=False)
    surfaced: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluator: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(16), nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    converted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    converted_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OpportunityVersionRecord(Base):
    """The frozen object at one version."""

    __tablename__ = "opportunity_versions"

    opportunity_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class OpportunityLegRecord(Base):
    """One arithmetic row of the current version."""

    __tablename__ = "opportunity_legs"

    opportunity_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_value: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rate_value: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    rate_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fx_value: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    fx_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contribution_value: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    subtotal_value: Mapped[Decimal | None] = mapped_column(DECIMAL, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    as_of_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OpportunityCheckRecord(Base):
    """One check of the current version."""

    __tablename__ = "opportunity_checks"

    opportunity_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    figure: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class OpportunityDependencyRecord(Base):
    """One input key a record depends on."""

    __tablename__ = "opportunity_dependencies"
    __table_args__ = (Index("ix_opportunity_dependencies_input_key", "input_key"),)

    opportunity_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("opportunities.opportunity_id", ondelete="CASCADE"),
        primary_key=True,
    )
    input_key: Mapped[str] = mapped_column(String(160), primary_key=True)


class OpportunityUserStateRecord(Base):
    """A person's dismissal or follow of one key, at the version it was made on."""

    __tablename__ = "opportunity_user_states"
    __table_args__ = (Index("ix_opportunity_user_states_key", "opp_key"),)

    principal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opp_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    at_version: Mapped[int] = mapped_column(Integer, nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityEvaluationRecord(Base):
    """One evaluation run."""

    __tablename__ = "opportunity_evaluations"
    __table_args__ = (Index("ix_opportunity_evaluations_started", "started_at_utc"),)

    evaluation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    demo_desk: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evaluators_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    counts_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class OpportunitySettingRecord(Base):
    """One organisation setting of the opportunity controls."""

    __tablename__ = "opportunity_settings"

    setting_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
