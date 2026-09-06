"""Strategy-lab persistence models."""

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


class StrategyRecord(Base):
    """Long-lived versioned strategy research identity."""

    __tablename__ = "strategies"

    strategy_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="RESEARCH")
    current_version_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyVersionRecord(Base):
    """Immutable semantic version of a strategy."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version_number", name="uq_strategy_version_number"),
        Index("ix_strategy_versions_strategy_id", "strategy_id"),
    )

    strategy_version_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategies.strategy_id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    hypothesis: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    frozen_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyDataSnapshotRecord(Base):
    """Evidence-bundle reference for reproducible strategy runs."""

    __tablename__ = "strategy_data_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    data_cutoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    fx_observation_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    resource_snapshot_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_systems: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    row_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quality_state: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyDefinitionRecord(Base):
    """Configured paper strategy definition."""

    __tablename__ = "strategy_definitions"

    strategy_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(256), nullable=False)
    strategy_family: Mapped[str] = mapped_column(String(64), nullable=False)
    supported_run_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    resource_filter: Mapped[dict] = mapped_column(JSON, nullable=False)
    components: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    risk_control: Mapped[dict] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategyRunRecord(Base):
    """Stored backtest, shadow-run, or live-monitor evaluation snapshot."""

    __tablename__ = "strategy_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("strategy_versions.strategy_version_id"), nullable=True
    )
    run_type: Mapped[str | None] = mapped_column(String(32), nullable=True, default="EVALUATION")
    run_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluation_start_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evaluation_end_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_cutoff_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dataset_snapshot_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("strategy_data_snapshots.snapshot_id"), nullable=True
    )
    manifest_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    manifest_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    backtest_engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    application_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    git_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    run_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deterministic_seed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    missing_inputs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class StrategyAllocationTargetRecord(Base):
    """Paper allocation target created by a strategy run."""

    __tablename__ = "strategy_allocation_targets"

    target_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market_bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    target_allocation_pct: Mapped[float] = mapped_column(Float, nullable=False)
    target_quantity_mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    reference_price_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_margin_gbp_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategyAlertRecord(Base):
    """Alert emitted by a backtest, shadow-run, or live-monitor strategy process."""

    __tablename__ = "strategy_alerts"

    alert_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message_en: Mapped[str] = mapped_column(Text(), nullable=False)
    message_zh_cn: Mapped[str] = mapped_column(Text(), nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
