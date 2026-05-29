"""Database models for neutral persistence metadata."""

from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.observation import (
    AuditEventRecord,
    EntitlementDecisionRecord,
    FlowObservationRecord,
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
    "EntitlementDecisionRecord",
    "FlowObservationRecord",
    "IngestionRunRecord",
    "IngestionRunStatus",
    "LngObservationRecord",
    "MarketObservationRecord",
    "NodeFacilityMapping",
    "ProviderCredentialRecord",
    "ReferenceEdge",
    "ReferenceFacility",
    "ReferenceMarketHub",
    "ReferenceNode",
    "StorageObservationRecord",
    "TopologyMarketMapping",
]
