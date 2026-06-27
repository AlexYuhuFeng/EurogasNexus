"""Reference network models populated from source-owned topology metadata."""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class ReferenceNode(Base):
    """A point on the European gas reference network."""

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
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_dataset: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_dataset: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_dataset: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_dataset: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ReferenceTsoAccessPoint(Base):
    """Source-owned TSO access metadata for a network point and direction."""

    __tablename__ = "reference_tso_access_points"

    access_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    point_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("reference_nodes.id"), nullable=True
    )
    point_key: Mapped[str] = mapped_column(String(64), nullable=False)
    point_name: Mapped[str] = mapped_column(String(256), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    operator_key: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(256), nullable=False)
    tso_eic_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    adjacent_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    adjacent_operator_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connected_operators: Mapped[str | None] = mapped_column(Text(), nullable=True)
    booking_platform: Mapped[str | None] = mapped_column(String(128), nullable=True)
    booking_platform_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    annual_contracts_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    monthly_contracts_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    daily_contracts_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    day_ahead_contracts_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_cam_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_cmp_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_update_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    data_quality: Mapped[str] = mapped_column(String(32), nullable=False)
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
