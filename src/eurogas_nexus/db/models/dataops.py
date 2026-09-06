"""CR-09 data-operations persistence models.

These tables are PostgreSQL runtime truth for the ingestion scheduler,
per-source operational state, structured run issues and the data-operations
scheduler heartbeat. They never replace the static compiled source registry;
they persist runtime state and operator decisions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class SourceRuntimeStateRecord(Base):
    """Operational state for one registered source."""

    __tablename__ = "source_runtime_states"
    __table_args__ = (
        Index("ix_source_runtime_enabled_next", "enabled", "next_run_at_utc"),
        Index("ix_source_runtime_freshness", "freshness_state", "updated_at_utc"),
        Index("ix_source_runtime_circuit", "circuit_state", "recovery_probe_at_utc"),
    )

    source_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    source_class: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    circuit_state: Mapped[str] = mapped_column(String(32), nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(96), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    activated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recovery_probe_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    freshness_state: Mapped[str] = mapped_column(String(32), nullable=False)
    source_age_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    ingestion_lag_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    pipeline_lag_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_quality_result: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_quality_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entitlement_state: Mapped[str] = mapped_column(String(32), nullable=False)
    certification_state: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schedule_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    freshness_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    retry_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    rate_limit_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    circuit_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    calendar: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class IngestionRunIssueRecord(Base):
    """One structured quality issue attached to an ingestion run."""

    __tablename__ = "ingestion_run_issues"
    __table_args__ = (
        Index("ix_ingestion_run_issues_run", "run_id", "created_at_utc"),
    )

    issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_code: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    field: Mapped[str] = mapped_column(String(128), nullable=False)
    observation_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text(), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(48), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class DataOperationsHeartbeatRecord(Base):
    """Single-row data-operations scheduler heartbeat."""

    __tablename__ = "data_operations_heartbeat"

    heartbeat_id: Mapped[str] = mapped_column(String(64), primary_key=True, default="primary")
    last_heartbeat_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_scan_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sources_scheduled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_healthy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_late: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_stale: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    certification_gaps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entitlement_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    backlog_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    oldest_overdue_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)