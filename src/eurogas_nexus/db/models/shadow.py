"""Shadow runtime persistence models.

Shadow research is scheduled, non-executing strategy evaluation over current
persisted evidence. Every model here is immutable evaluation/history state;
none of it can trigger an order, trade or nomination.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class StrategyShadowMonitorRecord(Base):
    """One scheduled shadow research monitor."""

    __tablename__ = "strategy_shadow_monitors"
    __table_args__ = (
        Index("ix_shadow_monitors_state_next", "state", "next_evaluation_at_utc"),
        Index("ix_shadow_monitors_strategy_id", "strategy_id"),
    )

    shadow_monitor_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategies.strategy_id"), nullable=False
    )
    strategy_version_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_versions.strategy_version_id"), nullable=False
    )
    baseline_run_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("strategy_runs.run_id"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    schedule_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_evaluation_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_evaluation_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latest_evaluation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health_state: Mapped[str] = mapped_column(String(32), nullable=False, default="OK")
    cumulative_shadow_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_exposure_mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyShadowEvaluationRecord(Base):
    """One scheduled shadow evaluation event."""

    __tablename__ = "strategy_shadow_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "shadow_monitor_id",
            "scheduled_for_utc",
            name="uq_shadow_evaluation_schedule",
        ),
        Index("ix_shadow_evaluations_monitor_time", "shadow_monitor_id", "scheduled_for_utc"),
        Index("ix_shadow_evaluations_state", "state"),
    )

    shadow_evaluation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    shadow_monitor_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_shadow_monitors.shadow_monitor_id"), nullable=False
    )
    strategy_version_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_versions.strategy_version_id"), nullable=False
    )
    scheduled_for_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_time_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="SCHEDULED")
    gas_day: Mapped[str | None] = mapped_column(String(16), nullable=True)
    gas_day_start_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    gas_day_end_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    fx_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    resource_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_systems: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    freshness_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    missing_inputs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyShadowCandidateRecord(Base):
    """Immutable candidate research observation from one evaluation."""

    __tablename__ = "strategy_shadow_candidates"
    __table_args__ = (
        Index("ix_shadow_candidates_evaluation", "shadow_evaluation_id"),
        Index("ix_shadow_candidates_decision_time", "decision_time_utc"),
    )

    candidate_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    shadow_evaluation_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_shadow_evaluations.shadow_evaluation_id"), nullable=False
    )
    shadow_monitor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    gas_day: Mapped[str] = mapped_column(String(16), nullable=False)
    candidate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    market_context: Mapped[dict] = mapped_column(JSON, nullable=False)
    hypothetical_direction: Mapped[str] = mapped_column(String(32), nullable=False)
    hypothetical_quantity_mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    expected_indicative_margin_gbp_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    expected_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    reference_price_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    all_in_cost_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_state: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_state: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    blocker_references: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyShadowRiskCheckRecord(Base):
    """One meaningful risk-control evaluation for a shadow candidate."""

    __tablename__ = "strategy_shadow_risk_checks"
    __table_args__ = (Index("ix_shadow_risk_checks_evaluation", "shadow_evaluation_id"),)

    risk_check_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    shadow_evaluation_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_shadow_evaluations.shadow_evaluation_id"), nullable=False
    )
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    explanation: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyShadowOutcomeRecord(Base):
    """Separately matured outcome; never overwrites the original candidate."""

    __tablename__ = "strategy_shadow_outcomes"
    __table_args__ = (Index("ix_shadow_outcomes_state", "state"),)

    outcome_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_shadow_candidates.candidate_id"), nullable=False
    )
    shadow_evaluation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    pnl_basis: Mapped[str] = mapped_column(String(40), nullable=False, default="MARK_TO_MODEL")
    gross_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    modeled_costs_gbp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    settlement_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    maturation_note: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    matured_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyShadowAlertRecord(Base):
    """Persisted, deduplicated shadow alert lifecycle."""

    __tablename__ = "strategy_shadow_alerts"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_shadow_alert_fingerprint"),
        Index("ix_shadow_alerts_monitor_state", "shadow_monitor_id", "state"),
    )

    alert_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    shadow_monitor_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_shadow_monitors.shadow_monitor_id"), nullable=False
    )
    shadow_evaluation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    first_seen_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    acknowledged_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyShadowDriftSnapshotRecord(Base):
    """One interpretable drift observation against an explicit baseline."""

    __tablename__ = "strategy_shadow_drift_snapshots"
    __table_args__ = (Index("ix_shadow_drift_monitor_time", "shadow_monitor_id", "created_at_utc"),)

    drift_snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    shadow_monitor_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_shadow_monitors.shadow_monitor_id"), nullable=False
    )
    baseline_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observation_window_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    explanation: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyShadowSchedulerHeartbeatRecord(Base):
    """Single-row scheduler heartbeat/observability state."""

    __tablename__ = "strategy_shadow_scheduler_heartbeat"

    heartbeat_id: Mapped[str] = mapped_column(String(64), primary_key=True, default="primary")
    last_heartbeat_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_scan_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_monitor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    oldest_overdue_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
