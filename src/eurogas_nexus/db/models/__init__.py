"""Database models for neutral persistence metadata."""

from datetime import datetime
from typing import Literal

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.analysis import (
    AnalysisRunRecord,
    GeneratedReportRecord,
)
from eurogas_nexus.db.models.backtest import (
    BacktestAttributionRecord,
    BacktestDecisionEventRecord,
    BacktestExperimentRecord,
    BacktestSeriesRecord,
)
from eurogas_nexus.db.models.certification import ProviderCertificationRecord
from eurogas_nexus.db.models.cost_observation import CostObservationRecord
from eurogas_nexus.db.models.dataops import (
    DataOperationsHeartbeatRecord,
    IngestionRunIssueRecord,
    SourceRuntimeStateRecord,
)
from eurogas_nexus.db.models.glossary import GlossaryTermRecord
from eurogas_nexus.db.models.identity import IdentityApiKeyRecord, IdentityPrincipalRecord
from eurogas_nexus.db.models.market_intelligence import (
    CompanyTsoAccessRecord,
    IntradayOpportunityRecord,
    MarketQuoteRecord,
)
from eurogas_nexus.db.models.market_positioning import (
    PortfolioPnlSnapshotRecord,
    ScreenOrderObservationRecord,
)
from eurogas_nexus.db.models.monitoring import MonitoringAlertRecord
from eurogas_nexus.db.models.observation import (
    AuditEventRecord,
    CapacityObservationRecord,
    EntitlementDecisionRecord,
    FlowObservationRecord,
    FxObservationRecord,
    LngObservationRecord,
    MarketObservationRecord,
    ProviderCredentialRecord,
    StorageObservationRecord,
)
from eurogas_nexus.db.models.optimization import OptimizationRunRecord
from eurogas_nexus.db.models.raw_archive import RawPayloadArchiveRecord
from eurogas_nexus.db.models.reference_network import (
    NodeFacilityMapping,
    ReferenceEdge,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    ReferenceTsoAccessPoint,
    TopologyMarketMapping,
)
from eurogas_nexus.db.models.review import ReviewDecisionRecord
from eurogas_nexus.db.models.route_cost import (
    CapacityProfileRecord,
    LiveMarketMarkRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.models.shadow import (
    StrategyShadowAlertRecord,
    StrategyShadowCandidateRecord,
    StrategyShadowDriftSnapshotRecord,
    StrategyShadowEvaluationRecord,
    StrategyShadowMonitorRecord,
    StrategyShadowOutcomeRecord,
    StrategyShadowRiskCheckRecord,
    StrategyShadowSchedulerHeartbeatRecord,
)
from eurogas_nexus.db.models.storage_nomination import (
    NominationWindowMasterRecord,
    StorageFacilityMasterRecord,
    StorageInventoryObservationRecord,
)
from eurogas_nexus.db.models.strategy import (
    StrategyAlertRecord,
    StrategyAllocationTargetRecord,
    StrategyDataSnapshotRecord,
    StrategyDefinitionRecord,
    StrategyRecord,
    StrategyRunRecord,
    StrategyVersionRecord,
)

IngestionRunStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "SUCCEEDED_WITH_WARNINGS",
    "FAILED",
    "CANCELLED",
]


class IngestionRunRecord(Base):
    """SQLAlchemy model for production-shaped ingestion run metadata.

    Legacy rows written by the R33 ingestor keep their old lowercase statuses;
    CR-09 adds the structured operational columns with backward-compatible
    server defaults.
    """

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_source_started", "source_id", "started_at_utc"),
        Index("ix_ingestion_runs_status_scheduled", "status", "scheduled_for_utc"),
        Index(
            "uq_ingestion_runs_scheduled_source",
            "source_id",
            "scheduled_for_utc",
            unique=True,
            postgresql_where=text("trigger_type = 'SCHEDULED'"),
        ),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default=""
    )
    dataset: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default=""
    )
    trigger_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="MANUAL", server_default="MANUAL"
    )
    requested_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_for_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    window_start_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    window_end_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    rows_received: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rows_accepted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rows_rejected: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rows_inserted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rows_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    quality_warning_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    quality_error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(96), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adapter_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_of_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    lineage_refs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)


__all__ = [
    "StrategyShadowAlertRecord",
    "StrategyShadowCandidateRecord",
    "StrategyShadowDriftSnapshotRecord",
    "StrategyShadowEvaluationRecord",
    "StrategyShadowMonitorRecord",
    "StrategyShadowOutcomeRecord",
    "StrategyShadowRiskCheckRecord",
    "StrategyShadowSchedulerHeartbeatRecord",
    "BacktestAttributionRecord",
    "BacktestDecisionEventRecord",
    "BacktestExperimentRecord",
    "BacktestSeriesRecord",

    "AuditEventRecord",
    "DataOperationsHeartbeatRecord",
    "IngestionRunIssueRecord",
    "SourceRuntimeStateRecord",
    "AnalysisRunRecord",
    "CapacityObservationRecord",
    "CompanyTsoAccessRecord",
    "CostObservationRecord",
    "EntitlementDecisionRecord",
    "FlowObservationRecord",
    "FxObservationRecord",
    "GlossaryTermRecord",
    "GeneratedReportRecord",
    "IngestionRunRecord",
    "IngestionRunStatus",
    "IdentityApiKeyRecord",
    "IdentityPrincipalRecord",
    "IntradayOpportunityRecord",
    "LngObservationRecord",
    "CapacityProfileRecord",
    "LiveMarketMarkRecord",
    "MarketObservationRecord",
    "MarketQuoteRecord",
    "MonitoringAlertRecord",
    "NodeFacilityMapping",
    "NominationWindowMasterRecord",
    "OptimizationRunRecord",
    "PortfolioPnlSnapshotRecord",
    "ProviderCertificationRecord",
    "ProviderCredentialRecord",
    "ReferenceEdge",
    "ReferenceFacility",
    "ReferenceMarketHub",
    "ReferenceNode",
    "ReferenceTsoAccessPoint",
    "ReviewDecisionRecord",
    "RouteCandidateRecord",
    "RawPayloadArchiveRecord",
    "ScreenOrderObservationRecord",
    "StorageFacilityMasterRecord",
    "StorageInventoryObservationRecord",
    "StorageObservationRecord",
    "StrategyAlertRecord",
    "StrategyDataSnapshotRecord",
    "StrategyRecord",
    "StrategyVersionRecord",
    "StrategyAllocationTargetRecord",
    "StrategyDefinitionRecord",
    "StrategyRunRecord",
    "TsoTariffRecord",
    "TopologyMarketMapping",
    "UpstreamResourceContractRecord",
]
