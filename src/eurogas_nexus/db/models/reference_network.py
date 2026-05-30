"""Reference network domain models — synthetic geometry, topology, and market mapping."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class ReferenceNode(Base):
    """A point on the European gas reference network (synthetic fixture only)."""

    __tablename__ = "reference_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "entry_point", "interconnection", "hub", "city_gate", "lng", "storage", "production"
    country: Mapped[str] = mapped_column(String(2), nullable=False)  # ISO 3166-1 alpha-2
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    capacity_boe_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ReferenceEdge(Base):
    """A directional connection between two reference nodes."""

    __tablename__ = "reference_edges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    from_node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reference_nodes.id"), nullable=False
    )
    to_node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reference_nodes.id"), nullable=False
    )
    edge_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "pipeline", "virtual", "corridor"
    length_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ReferenceFacility(Base):
    """A physical or commercial facility on the reference network."""

    __tablename__ = "reference_facilities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    facility_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "lng_terminal", "storage", "regas", "compressor", "metering", "border_point"
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    capacity_boe_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ReferenceMarketHub(Base):
    """A market trading hub abstraction (TTF, NBP, PEG, etc.)."""

    __tablename__ = "reference_market_hubs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    hub_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class NodeFacilityMapping(Base):
    """Explicit mapping between a node and a facility with confidence and eligibility."""

    __tablename__ = "node_facility_mappings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reference_nodes.id"), nullable=False
    )
    facility_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reference_facilities.id"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    eligibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default="research_candidate"
    )  # "research_candidate", "confirmed", "ineligible"
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class TopologyMarketMapping(Base):
    """Explicit mapping between a topology node and a market hub with confidence."""

    __tablename__ = "topology_market_mappings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reference_nodes.id"), nullable=False
    )
    market_hub_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reference_market_hubs.id"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    eligibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default="research_candidate"
    )  # "research_candidate", "confirmed", "ineligible"
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
