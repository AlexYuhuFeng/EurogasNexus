"""Observation domain SQLAlchemy models.

观测域模型：市场/汇率/流量/容量/储气/LNG 观测与审计、授权、凭据记录。
所有观测行都携带 source_reference 溯源、freshness 与 research_only
标记（fail-closed 数据纪律的落库形态）。
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class MarketObservationRecord(Base):
    """A market price observation (assessment/index/settlement row).

    对应表 ``market_observations``；metadata_json 承载 hub/tenor 等
    规范化辅助字段。
    """

    __tablename__ = "market_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market_venue: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class FxObservationRecord(Base):
    """An FX reference observation (e.g. ECB eurofxref row).

    对应表 ``fx_observations``；用于跨币种换算的 as-of 汇率。
    """

    __tablename__ = "fx_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pair: Mapped[str] = mapped_column(String(16), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    rate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_date: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class FlowObservationRecord(Base):
    """A physical flow observation at a network point.

    对应表 ``flow_observations``；``kind`` 标记性质
    （actual/nomination/allocation/forecast，Gate 2 语义）。
    """

    __tablename__ = "flow_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    point_id: Mapped[str] = mapped_column(String(64), nullable=False)
    point_name: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="actual"
    )  # "actual" | "nomination" | "allocation" | "forecast"
    flow_mcm_d: Mapped[float] = mapped_column(Float, nullable=False)
    original_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CapacityObservationRecord(Base):
    """A capacity observation at a network point (ENTSOG style).

    对应表 ``capacity_observations``；capacity_type 区分容量种类。
    """

    __tablename__ = "capacity_observations"

    observation_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    point_id: Mapped[str] = mapped_column(String(64), nullable=False)
    point_name: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    capacity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity_mcm_d: Mapped[float] = mapped_column(Float, nullable=False)
    original_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class StorageObservationRecord(Base):
    """A storage facility observation (GIE AGSI style).

    对应表 ``storage_observations``；库存/工作气量/注采率按设施日粒度。
    """

    __tablename__ = "storage_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_dataset: Mapped[str] = mapped_column(String(16), nullable=False)
    facility_id: Mapped[str] = mapped_column(String(64), nullable=False)
    facility_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    inventory_twh: Mapped[float | None] = mapped_column(Float, nullable=True)
    working_capacity_twh: Mapped[float | None] = mapped_column(Float, nullable=True)
    fill_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    injection_twh_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    withdrawal_twh_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class LngObservationRecord(Base):
    """An LNG terminal observation (GIE ALSI style).

    对应表 ``lng_observations``；库存/外输/DTMI 按终端日粒度。
    """

    __tablename__ = "lng_observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_dataset: Mapped[str] = mapped_column(String(16), nullable=False)
    terminal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    terminal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    inventory_twh: Mapped[float | None] = mapped_column(Float, nullable=True)
    send_out_twh_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    dtmi_twh: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AuditEventRecord(Base):
    """One audit event row (who did what, when, with what outcome).

    对应表 ``audit_events``；全链路审计的持久化载体。
    """

    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    principal: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(String, nullable=False)
    event_ts_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class EntitlementDecisionRecord(Base):
    """One persisted entitlement decision (fail-closed audit trail).

    对应表 ``entitlement_decisions``；每次授权裁决留痕。
    """

    __tablename__ = "entitlement_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    evaluated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ProviderCredentialRecord(Base):
    """One stored provider credential (encrypted at rest).

    对应表 ``provider_credentials``；仅存加密载荷与脱敏预览，
    明文密钥永不落库。
    """

    __tablename__ = "provider_credentials"

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text(), nullable=False)
    redacted_preview: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_tested_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
