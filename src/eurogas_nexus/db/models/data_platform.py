"""Analysis Snapshot persistence model (Architecture V2 Wave 4).

One row is the persisted descriptor of one Analysis Snapshot
(``07_DATA_PLATFORM.md`` section 6, ``02_ARCHITECTURE_CONSTITUTION.md`` rule 32).
The row stores *version references* and *declared availability*, never copied
market values: a snapshot points at the canonical rows it was taken from, so it
stays a reproducible reference rather than a second copy of the data platform.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class AnalysisSnapshotRecord(Base):
    """Persisted Analysis Snapshot descriptor.

    ``field_availability_json`` is the honesty column: it records, per
    ``07_DATA_PLATFORM.md`` section 6 field, whether the field was resolved,
    partially resolved or explicitly unavailable at creation time. A nullable
    ``*_json`` column therefore means "no implementation has ever supplied this
    field yet", not "the value was empty".
    """

    __tablename__ = "analysis_snapshots"
    __table_args__ = (
        Index("ix_analysis_snapshots_created_at", "created_at_utc"),
        Index("ix_analysis_snapshots_gas_day", "gas_day"),
        Index("ix_analysis_snapshots_created_by", "created_by"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    gas_day: Mapped[str] = mapped_column(String(10), nullable=False)
    gas_day_calendar: Mapped[str] = mapped_column(String(32), nullable=False)
    time_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    active_context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    market_data_versions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    network_capacity_version_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    portfolio_version_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    contract_resource_versions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tariff_fx_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    weather_demand_assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    manual_assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_calculation_versions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    entitlement_context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    field_availability_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    research_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    human_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
