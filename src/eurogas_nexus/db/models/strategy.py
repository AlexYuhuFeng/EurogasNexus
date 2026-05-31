"""Strategy-lab persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


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
    run_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
