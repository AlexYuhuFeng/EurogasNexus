"""Append-only persistence model for National Gas NTS actual demand.

Rows are source-faithful publication revisions.  Native values remain text;
quality, provisionality, and the actual-demand role are separate concepts.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class NationalGasActualDemandRecord(Base):
    """One immutable actual-demand revision from the National Gas CSV or REST feed."""

    __tablename__ = "national_gas_actual_demand"
    __table_args__ = (
        CheckConstraint("region = 'GB_NTS'", name="ck_ng_actual_demand_region"),
        CheckConstraint("unit = 'mscm'", name="ck_ng_actual_demand_unit"),
        CheckConstraint("term IN ('D+1', 'D+6')", name="ck_ng_actual_demand_term"),
        CheckConstraint(
            "source_format IN ('CSV', 'REST')",
            name="ck_ng_actual_demand_source_format",
        ),
        CheckConstraint(
            "source_format != 'REST' OR rest_provenance IS NOT NULL",
            name="ck_ng_actual_demand_rest_provenance",
        ),
        CheckConstraint(
            "length(value_text) <= 64 AND "
            "((value_is_blank AND length(value_text) = 0) OR "
            "(NOT value_is_blank AND length(value_text) > 0))",
            name="ck_ng_actual_demand_value_text",
        ),
        CheckConstraint(
            "quality_indicator IS NULL OR "
            "(length(quality_indicator) > 0 AND length(quality_indicator) <= 8)",
            name="ck_ng_actual_demand_quality",
        ),
        Index(
            "ix_national_gas_actual_demand_series_gas_day",
            "series_key",
            "gas_day",
        ),
        Index(
            "ix_national_gas_actual_demand_published_utc",
            "published_at_utc",
        ),
    )

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_publication_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    provider_item_id: Mapped[str] = mapped_column(String(32), nullable=False)
    series_key: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(16), nullable=False)
    term: Mapped[str] = mapped_column(String(8), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    gas_day: Mapped[date] = mapped_column(Date(), nullable=False)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value_text: Mapped[str] = mapped_column(Text(), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applicable_at_raw: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at_raw: Mapped[str] = mapped_column(String(32), nullable=False)
    applicable_at_naive: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    generated_at_naive: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    quality_indicator: Mapped[str | None] = mapped_column(String(8), nullable=True)
    provisional_status: Mapped[str] = mapped_column(String(40), nullable=False)
    is_provisional: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    hash_schema: Mapped[str] = mapped_column(String(64), nullable=False)
    value_is_blank: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=text("false")
    )
    source_format: Mapped[str] = mapped_column(
        String(8), nullable=False, default="CSV", server_default="CSV"
    )
    rest_provenance: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
