"""Database models for neutral persistence metadata."""

from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.analysis import (
    AnalysisRunRecord,
    BusinessOntologyRecord,
    GeneratedReportRecord,
)
from eurogas_nexus.db.models.glossary import GlossaryTermRecord
from eurogas_nexus.db.models.observation import (
    AuditEventRecord,
    EntitlementDecisionRecord,
    FlowObservationRecord,
    FxObservationRecord,
    LngObservationRecord,
    MarketObservationRecord,
    ProviderCredentialRecord,
    StorageObservationRecord,
)
from eurogas_nexus.db.models.reference_network import (
    NodeFacilityMapping,
    ReferenceEdge,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    TopologyMarketMapping,
)
from eurogas_nexus.db.models.route_cost import (
    CapacityProfileRecord,
    LiveMarketMarkRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.models.strategy import (
    StrategyAlertRecord,
    StrategyAllocationTargetRecord,
    StrategyDefinitionRecord,
    StrategyRunRecord,
)

IngestionRunStatus = Literal["queued", "running", "succeeded", "failed"]


class IngestionRunRecord(Base):
    """SQLAlchemy model for ingestion run metadata."""

    __tablename__ = "ingestion_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)


__all__ = [
    "AuditEventRecord",
    "AnalysisRunRecord",
    "BusinessOntologyRecord",
    "EntitlementDecisionRecord",
    "FlowObservationRecord",
    "FxObservationRecord",
    "GlossaryTermRecord",
    "GeneratedReportRecord",
    "IngestionRunRecord",
    "IngestionRunStatus",
    "LngObservationRecord",
    "CapacityProfileRecord",
    "LiveMarketMarkRecord",
    "MarketObservationRecord",
    "NodeFacilityMapping",
    "ProviderCredentialRecord",
    "ReferenceEdge",
    "ReferenceFacility",
    "ReferenceMarketHub",
    "ReferenceNode",
    "RouteCandidateRecord",
    "StorageObservationRecord",
    "StrategyAlertRecord",
    "StrategyAllocationTargetRecord",
    "StrategyDefinitionRecord",
    "StrategyRunRecord",
    "TsoTariffRecord",
    "TopologyMarketMapping",
    "UpstreamResourceContractRecord",
]
