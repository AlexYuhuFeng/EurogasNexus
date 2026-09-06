"""Backtest experiment, event, series and attribution persistence models."""

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


class BacktestExperimentRecord(Base):
    """Lightweight grouping of related backtest runs."""

    __tablename__ = "backtest_experiments"
    __table_args__ = (Index("ix_backtest_experiments_strategy_id", "strategy_id"),)

    experiment_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategies.strategy_id"), nullable=False
    )
    base_strategy_version_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_versions.strategy_version_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    experiment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluation_period_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    run_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BacktestDecisionEventRecord(Base):
    """Normalized decision event produced by one backtest run."""

    __tablename__ = "backtest_decision_events"
    __table_args__ = (
        UniqueConstraint("run_id", "decision_sequence", name="uq_backtest_event_seq"),
        Index("ix_backtest_events_run_id", "run_id"),
        Index("ix_backtest_events_decision_time", "decision_time_utc"),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_runs.run_id"), nullable=False
    )
    experiment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_time_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    gas_day: Mapped[str] = mapped_column(String(16), nullable=False)
    gas_day_start_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    gas_day_end_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_action_for_review: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    weighted_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    day_ahead_average_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    intraday_average_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    intraday_vs_day_ahead_spread_gbp_mwh: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    allocation_targets: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    gross_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    modeled_costs_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    net_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    cumulative_net_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    ending_exposure_mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    missing_inputs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    price_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    fx_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    cost_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    resource_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    cost_trace: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    attribution: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BacktestSeriesRecord(Base):
    """Normalized cumulative net PnL / exposure series for one run."""

    __tablename__ = "backtest_series"
    __table_args__ = (
        UniqueConstraint("run_id", "decision_sequence", name="uq_backtest_series_seq"),
        Index("ix_backtest_series_run_id", "run_id"),
    )

    series_point_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_runs.run_id"), nullable=False
    )
    decision_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_time_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    gas_day: Mapped[str] = mapped_column(String(16), nullable=False)
    gross_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    modeled_costs_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    net_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    cumulative_net_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    ending_exposure_mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BacktestAttributionRecord(Base):
    """Attribution rows the current engine can support without fabrication."""

    __tablename__ = "backtest_attribution"
    __table_args__ = (
        Index("ix_backtest_attribution_run_id", "run_id"),
        Index("ix_backtest_attribution_event_id", "event_id"),
    )

    attribution_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategy_runs.run_id"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("backtest_decision_events.event_id"), nullable=False
    )
    decision_time_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    gross_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    modeled_costs_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    net_indicative_pnl_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_mwh_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
