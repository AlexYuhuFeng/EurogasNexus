"""Read-only repositories for reference network domain models."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.reference_network import (
    ReferenceEdge,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
)

# --- Domain-safe dataclasses -------------------------------------------------


@dataclass(frozen=True)
class NodeDTO:
    """Domain-safe reference node payload."""

    id: str
    name: str
    node_type: str
    country: str
    lat: float
    lon: float
    capacity_boe_d: float | None = None
    metadata_json: dict | None = None


@dataclass(frozen=True)
class EdgeDTO:
    """Domain-safe reference edge payload."""

    id: str
    from_node_id: str
    to_node_id: str
    edge_type: str
    length_km: float | None = None
    metadata_json: dict | None = None


@dataclass(frozen=True)
class FacilityDTO:
    """Domain-safe reference facility payload."""

    id: str
    name: str
    facility_type: str
    country: str
    lat: float
    lon: float
    capacity_boe_d: float | None = None
    metadata_json: dict | None = None


@dataclass(frozen=True)
class MarketHubDTO:
    """Domain-safe market hub payload."""

    id: str
    name: str
    hub_code: str
    country: str
    description: str | None = None
    metadata_json: dict | None = None


# --- Repository protocols ----------------------------------------------------


class NodeRepository(Protocol):
    """Read-only repository for reference nodes."""

    def list_all(
        self,
        *,
        country: str | None = None,
        node_type: str | None = None,
    ) -> list[NodeDTO]: ...
    def get_by_id(self, node_id: str) -> NodeDTO | None: ...


class EdgeRepository(Protocol):
    """Read-only repository for reference edges."""

    def list_all(
        self,
        *,
        from_node_id: str | None = None,
        to_node_id: str | None = None,
    ) -> list[EdgeDTO]: ...
    def get_by_id(self, edge_id: str) -> EdgeDTO | None: ...


class FacilityRepository(Protocol):
    """Read-only repository for reference facilities."""

    def list_all(
        self,
        *,
        facility_type: str | None = None,
        country: str | None = None,
    ) -> list[FacilityDTO]: ...
    def get_by_id(self, facility_id: str) -> FacilityDTO | None: ...


class MarketHubRepository(Protocol):
    """Read-only repository for market hubs."""

    def list_all(self) -> list[MarketHubDTO]: ...
    def get_by_id(self, hub_id: str) -> MarketHubDTO | None: ...


# --- SQLAlchemy adapters -----------------------------------------------------


class SqlAlchemyNodeRepository:
    """SQLAlchemy adapter for reference node reads."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(
        self,
        *,
        country: str | None = None,
        node_type: str | None = None,
    ) -> list[NodeDTO]:
        q = self._session.query(ReferenceNode)
        if country is not None:
            q = q.filter(ReferenceNode.country == country)
        if node_type is not None:
            q = q.filter(ReferenceNode.node_type == node_type)
        return [_node_to_dto(row) for row in q.all()]

    def get_by_id(self, node_id: str) -> NodeDTO | None:
        row = self._session.get(ReferenceNode, node_id)
        return _node_to_dto(row) if row else None


class SqlAlchemyEdgeRepository:
    """SQLAlchemy adapter for reference edge reads."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(
        self,
        *,
        from_node_id: str | None = None,
        to_node_id: str | None = None,
    ) -> list[EdgeDTO]:
        q = self._session.query(ReferenceEdge)
        if from_node_id is not None:
            q = q.filter(ReferenceEdge.from_node_id == from_node_id)
        if to_node_id is not None:
            q = q.filter(ReferenceEdge.to_node_id == to_node_id)
        return [_edge_to_dto(row) for row in q.all()]

    def get_by_id(self, edge_id: str) -> EdgeDTO | None:
        row = self._session.get(ReferenceEdge, edge_id)
        return _edge_to_dto(row) if row else None


class SqlAlchemyFacilityRepository:
    """SQLAlchemy adapter for reference facility reads."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(
        self,
        *,
        facility_type: str | None = None,
        country: str | None = None,
    ) -> list[FacilityDTO]:
        q = self._session.query(ReferenceFacility)
        if facility_type is not None:
            q = q.filter(ReferenceFacility.facility_type == facility_type)
        if country is not None:
            q = q.filter(ReferenceFacility.country == country)
        return [_facility_to_dto(row) for row in q.all()]

    def get_by_id(self, facility_id: str) -> FacilityDTO | None:
        row = self._session.get(ReferenceFacility, facility_id)
        return _facility_to_dto(row) if row else None


class SqlAlchemyMarketHubRepository:
    """SQLAlchemy adapter for market hub reads."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[MarketHubDTO]:
        rows = self._session.query(ReferenceMarketHub).all()
        return [_hub_to_dto(row) for row in rows]

    def get_by_id(self, hub_id: str) -> MarketHubDTO | None:
        row = self._session.get(ReferenceMarketHub, hub_id)
        return _hub_to_dto(row) if row else None


# --- Row-to-DTO helpers ------------------------------------------------------


def _node_to_dto(row: ReferenceNode) -> NodeDTO:
    return NodeDTO(
        id=row.id,
        name=row.name,
        node_type=row.node_type,
        country=row.country,
        lat=row.lat,
        lon=row.lon,
        capacity_boe_d=row.capacity_boe_d,
        metadata_json=row.metadata_json,
    )


def _edge_to_dto(row: ReferenceEdge) -> EdgeDTO:
    return EdgeDTO(
        id=row.id,
        from_node_id=row.from_node_id,
        to_node_id=row.to_node_id,
        edge_type=row.edge_type,
        length_km=row.length_km,
        metadata_json=row.metadata_json,
    )


def _facility_to_dto(row: ReferenceFacility) -> FacilityDTO:
    return FacilityDTO(
        id=row.id,
        name=row.name,
        facility_type=row.facility_type,
        country=row.country,
        lat=row.lat,
        lon=row.lon,
        capacity_boe_d=row.capacity_boe_d,
        metadata_json=row.metadata_json,
    )


def _hub_to_dto(row: ReferenceMarketHub) -> MarketHubDTO:
    return MarketHubDTO(
        id=row.id,
        name=row.name,
        hub_code=row.hub_code,
        country=row.country,
        description=row.description,
        metadata_json=row.metadata_json,
    )
