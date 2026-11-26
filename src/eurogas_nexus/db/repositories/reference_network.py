"""Read-only repositories for reference network domain models.

参考网络域的只读仓储：DTO 数据类（领域安全载荷）、仓储协议（供测试
与依赖注入）与 SQLAlchemy 适配器。所有适配器只做查询映射，不写库。
"""

from dataclasses import dataclass, replace
from typing import Protocol

from sqlalchemy import or_
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.reference_network import (
    REFERENCE_RETIRED_QUALITY,
    ReferenceEdge,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    ReferenceTsoAccessPoint,
)
from eurogas_nexus.reference_data.network_adjacency import (
    RETIRED_TRADING_POINTS,
    trading_point_country,
)
from eurogas_nexus.reference_data.network_bundle import (
    BUNDLE_EDGE_SOURCE,
    shipped_reference_edges,
    shipped_zone_nodes,
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
    source_system: str | None = None
    source_dataset: str | None = None
    source_reference: str | None = None
    source_record_id: str | None = None
    data_quality: str | None = None
    metadata_json: dict | None = None


@dataclass(frozen=True)
class EdgeDTO:
    """Domain-safe reference edge payload."""

    id: str
    from_node_id: str
    to_node_id: str
    edge_type: str
    length_km: float | None = None
    source_system: str | None = None
    source_dataset: str | None = None
    source_reference: str | None = None
    source_record_id: str | None = None
    data_quality: str | None = None
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
    source_system: str | None = None
    source_dataset: str | None = None
    source_reference: str | None = None
    source_record_id: str | None = None
    data_quality: str | None = None
    metadata_json: dict | None = None


@dataclass(frozen=True)
class MarketHubDTO:
    """Domain-safe market hub payload (effective-dated DB reference master)."""

    id: str
    name: str
    hub_code: str
    country: str
    market_area: str | None = None
    valid_from_utc: str | None = None
    valid_to_utc: str | None = None
    superseded_by_hub_id: str | None = None
    description: str | None = None
    source_system: str | None = None
    source_dataset: str | None = None
    source_reference: str | None = None
    source_record_id: str | None = None
    data_quality: str | None = None
    metadata_json: dict | None = None


@dataclass(frozen=True)
class TsoAccessPointDTO:
    """Domain-safe TSO access point payload."""

    access_id: str
    point_id: str | None
    point_key: str
    point_name: str
    country: str
    operator_key: str
    operator_name: str
    tso_eic_code: str | None
    direction: str
    adjacent_country: str | None
    adjacent_operator_key: str | None
    connected_operators: str | None
    booking_platform: str | None
    booking_platform_url: str | None
    annual_contracts_available: bool
    monthly_contracts_available: bool
    daily_contracts_available: bool
    day_ahead_contracts_available: bool
    is_cam_relevant: bool
    is_cmp_relevant: bool
    last_update_utc: str | None
    source_system: str
    source_dataset: str
    source_reference: str
    source_record_id: str
    data_quality: str
    metadata_json: dict | None = None


# --- Repository protocols ----------------------------------------------------


class NodeRepository(Protocol):
    """Read-only repository for reference nodes."""

    def list_all(
        self,
        *,
        country: str | None = None,
        node_type: str | None = None,
    ) -> list[NodeDTO]:
        """List nodes, optionally filtered by country and node type."""

        ...

    def get_by_id(self, node_id: str) -> NodeDTO | None:
        """Fetch one node by id (None when absent)."""

        ...


class EdgeRepository(Protocol):
    """Read-only repository for reference edges."""

    def list_all(
        self,
        *,
        from_node_id: str | None = None,
        to_node_id: str | None = None,
    ) -> list[EdgeDTO]:
        """List edges, optionally filtered by endpoint node ids."""

        ...

    def get_by_id(self, edge_id: str) -> EdgeDTO | None:
        """Fetch one edge by id (None when absent)."""

        ...


class FacilityRepository(Protocol):
    """Read-only repository for reference facilities."""

    def list_all(
        self,
        *,
        facility_type: str | None = None,
        country: str | None = None,
    ) -> list[FacilityDTO]:
        """List facilities, optionally filtered by type and country."""

        ...

    def get_by_id(self, facility_id: str) -> FacilityDTO | None:
        """Fetch one facility by id (None when absent)."""

        ...


class MarketHubRepository(Protocol):
    """Read-only repository for market hubs."""

    def list_all(self) -> list[MarketHubDTO]:
        """List all market hubs."""

        ...

    def get_by_id(self, hub_id: str) -> MarketHubDTO | None:
        """Fetch one hub by id (None when absent)."""

        ...


class TsoAccessPointRepository(Protocol):
    """Read-only repository for source-owned TSO access metadata."""

    def list_all(
        self,
        *,
        point_id: str | None = None,
        country: str | None = None,
        operator_key: str | None = None,
        direction: str | None = None,
    ) -> list[TsoAccessPointDTO]:
        """List TSO access points, optionally filtered."""

        ...


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
        """List nodes from the runtime DB, optionally filtered.

        Args:
            country: Country filter, or None.
            node_type: Node type filter, or None.

        Returns:
            NodeDTO list.
        """

        q = self._session.query(ReferenceNode).filter(_current(ReferenceNode))
        if country is not None:
            q = q.filter(ReferenceNode.country == country)
        if node_type is not None:
            q = q.filter(ReferenceNode.node_type == node_type)
        stored = [
            _served_node(row)
            for row in q.all()
            if str(row.source_record_id or "") not in RETIRED_TRADING_POINTS
        ]
        return stored + [
            node
            for node in self._shipped_zone_nodes()
            if (country is None or node.country == country)
            and (node_type is None or node.node_type == node_type)
        ]

    def _shipped_zone_nodes(self) -> list[NodeDTO]:
        """Market-area nodes of the shipped bundle the store does not hold as current rows.

        A live ENTSOG read holds connection points only; the zones ENTSOG publishes no trading
        point for (``shipped_zone_nodes``) come from the bundle, so their adjacency is drawn.
        """

        return _missing_zone_nodes(self._session)

    def get_by_id(self, node_id: str) -> NodeDTO | None:
        """Fetch one node by id.

        Args:
            node_id: Node id.

        Returns:
            NodeDTO, or None when absent.
        """

        row = self._session.get(ReferenceNode, node_id)
        if row is not None and str(row.source_record_id or "") not in RETIRED_TRADING_POINTS:
            return _served_node(row)
        return next((node for node in self._shipped_zone_nodes() if node.id == node_id), None)


def _served_node(row: ReferenceNode) -> NodeDTO:
    """A stored node as read, with a trading point's country taken from its zone.

    A store read before the live normaliser set it holds ENTSOG trading points as country
    "EU" (TTF, OTE, GTF ...); the zone ENTSOG files each under gives the country.
    """

    dto = _node_to_dto(row)
    if row.node_type == "hub" and (row.country or "EU") == "EU":
        country = trading_point_country(str(row.source_record_id or ""))
        if country:
            return replace(dto, country=country)
    return dto


def _missing_zone_nodes(session: Session) -> list[NodeDTO]:
    """The shipped zone nodes a store holding ENTSOG reference points lacks (none when empty)."""

    held = {
        node_id
        for (node_id,) in session.query(ReferenceNode.id)
        .filter(_current(ReferenceNode), ReferenceNode.source_system == "ENTSOG")
        .all()
    }
    if not held:
        return []
    return [NodeDTO(**row) for row in shipped_zone_nodes() if row["id"] not in held]


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
        """List edges from the runtime DB, optionally filtered by endpoints.

        Args:
            from_node_id: Source endpoint filter, or None.
            to_node_id: Target endpoint filter, or None.

        Returns:
            EdgeDTO list.
        """

        q = self._session.query(ReferenceEdge).filter(
            or_(
                ReferenceEdge.source_system.is_(None),
                ReferenceEdge.source_system != BUNDLE_EDGE_SOURCE,
            )
        )
        if from_node_id is not None:
            q = q.filter(ReferenceEdge.from_node_id == from_node_id)
        if to_node_id is not None:
            q = q.filter(ReferenceEdge.to_node_id == to_node_id)
        stored = [_edge_to_dto(row) for row in q.all()]
        return stored + [
            edge
            for edge in self._shipped_edges()
            if (from_node_id is None or edge.from_node_id == from_node_id)
            and (to_node_id is None or edge.to_node_id == to_node_id)
        ]

    def _shipped_edges(self) -> list[EdgeDTO]:
        """The reference bundle's edges between nodes this store holds.

        Zone links and market-area adjacency come from the shipped bundle on every store, the
        same graph route pricing walks (``shipped_reference_edges``), whether the store was
        seeded from the bundle or holds a live ENTSOG read. Stored copies are not read.
        """

        held = {
            node_id
            for (node_id,) in self._session.query(ReferenceNode.id)
            .filter(_current(ReferenceNode))
            .all()
        } | {node.id for node in _missing_zone_nodes(self._session)}
        return [
            EdgeDTO(**row)
            for row in shipped_reference_edges()
            if row["from_node_id"] in held and row["to_node_id"] in held
        ]

    def get_by_id(self, edge_id: str) -> EdgeDTO | None:
        """Fetch one edge by id.

        Args:
            edge_id: Edge id.

        Returns:
            EdgeDTO, or None when absent.
        """

        row = self._session.get(ReferenceEdge, edge_id)
        if row is not None and row.source_system != BUNDLE_EDGE_SOURCE:
            return _edge_to_dto(row)
        return next((edge for edge in self._shipped_edges() if edge.id == edge_id), None)


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
        """List facilities from the runtime DB, optionally filtered.

        Args:
            facility_type: Facility type filter, or None.
            country: Country filter, or None.

        Returns:
            FacilityDTO list.
        """

        q = self._session.query(ReferenceFacility).filter(_current(ReferenceFacility))
        if facility_type is not None:
            q = q.filter(ReferenceFacility.facility_type == facility_type)
        if country is not None:
            q = q.filter(ReferenceFacility.country == country)
        return [_facility_to_dto(row) for row in q.all()]

    def get_by_id(self, facility_id: str) -> FacilityDTO | None:
        """Fetch one facility by id.

        Args:
            facility_id: Facility id.

        Returns:
            FacilityDTO, or None when absent.
        """

        row = self._session.get(ReferenceFacility, facility_id)
        return _facility_to_dto(row) if row else None


class SqlAlchemyMarketHubRepository:
    """SQLAlchemy adapter for market hub reads."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[MarketHubDTO]:
        """List all market hubs from the runtime DB.

        Returns:
            MarketHubDTO list.
        """

        rows = (
            self._session.query(ReferenceMarketHub).filter(_current(ReferenceMarketHub)).all()
        )
        return [_hub_to_dto(row) for row in rows]

    def get_by_id(self, hub_id: str) -> MarketHubDTO | None:
        """Fetch one hub by id.

        Args:
            hub_id: Hub id.

        Returns:
            MarketHubDTO, or None when absent.
        """

        row = self._session.get(ReferenceMarketHub, hub_id)
        return _hub_to_dto(row) if row else None


class SqlAlchemyTsoAccessPointRepository:
    """SQLAlchemy adapter for TSO access metadata reads."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(
        self,
        *,
        point_id: str | None = None,
        country: str | None = None,
        operator_key: str | None = None,
        direction: str | None = None,
    ) -> list[TsoAccessPointDTO]:
        """List TSO access points from the runtime DB, optionally filtered.

        Args:
            point_id: Point id filter, or None.
            country: Country filter, or None.
            operator_key: Operator key filter, or None.
            direction: Direction filter, or None.

        Returns:
            TsoAccessPointDTO list.
        """

        q = self._session.query(ReferenceTsoAccessPoint).filter(
            _current(ReferenceTsoAccessPoint)
        )
        if point_id is not None:
            q = q.filter(ReferenceTsoAccessPoint.point_id == point_id)
        if country is not None:
            q = q.filter(ReferenceTsoAccessPoint.country == country)
        if operator_key is not None:
            q = q.filter(ReferenceTsoAccessPoint.operator_key == operator_key)
        if direction is not None:
            q = q.filter(ReferenceTsoAccessPoint.direction == direction)
        return [_tso_access_to_dto(row) for row in q.all()]


# --- Row-to-DTO helpers ------------------------------------------------------


def _current(model):
    """Leave out source rows the provider no longer publishes (kept for history, by id)."""

    return or_(model.data_quality.is_(None), model.data_quality != REFERENCE_RETIRED_QUALITY)


def _node_to_dto(row: ReferenceNode) -> NodeDTO:
    return NodeDTO(
        id=row.id,
        name=row.name,
        node_type=row.node_type,
        country=row.country,
        lat=row.lat,
        lon=row.lon,
        capacity_boe_d=row.capacity_boe_d,
        source_system=row.source_system,
        source_dataset=row.source_dataset,
        source_reference=row.source_reference,
        source_record_id=row.source_record_id,
        data_quality=row.data_quality,
        metadata_json=row.metadata_json,
    )


def _edge_to_dto(row: ReferenceEdge) -> EdgeDTO:
    return EdgeDTO(
        id=row.id,
        from_node_id=row.from_node_id,
        to_node_id=row.to_node_id,
        edge_type=row.edge_type,
        length_km=row.length_km,
        source_system=row.source_system,
        source_dataset=row.source_dataset,
        source_reference=row.source_reference,
        source_record_id=row.source_record_id,
        data_quality=row.data_quality,
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
        source_system=row.source_system,
        source_dataset=row.source_dataset,
        source_reference=row.source_reference,
        source_record_id=row.source_record_id,
        data_quality=row.data_quality,
        metadata_json=row.metadata_json,
    )


def _iso_or_none(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _hub_to_dto(row: ReferenceMarketHub) -> MarketHubDTO:
    return MarketHubDTO(
        id=row.id,
        name=row.name,
        hub_code=row.hub_code,
        country=row.country,
        market_area=row.market_area,
        valid_from_utc=_iso_or_none(row.valid_from_utc),
        valid_to_utc=_iso_or_none(row.valid_to_utc),
        superseded_by_hub_id=row.superseded_by_hub_id,
        description=row.description,
        source_system=row.source_system,
        source_dataset=row.source_dataset,
        source_reference=row.source_reference,
        source_record_id=row.source_record_id,
        data_quality=row.data_quality,
        metadata_json=row.metadata_json,
    )


def _tso_access_to_dto(row: ReferenceTsoAccessPoint) -> TsoAccessPointDTO:
    return TsoAccessPointDTO(
        access_id=row.access_id,
        point_id=row.point_id,
        point_key=row.point_key,
        point_name=row.point_name,
        country=row.country,
        operator_key=row.operator_key,
        operator_name=row.operator_name,
        tso_eic_code=row.tso_eic_code,
        direction=row.direction,
        adjacent_country=row.adjacent_country,
        adjacent_operator_key=row.adjacent_operator_key,
        connected_operators=row.connected_operators,
        booking_platform=row.booking_platform,
        booking_platform_url=row.booking_platform_url,
        annual_contracts_available=row.annual_contracts_available,
        monthly_contracts_available=row.monthly_contracts_available,
        daily_contracts_available=row.daily_contracts_available,
        day_ahead_contracts_available=row.day_ahead_contracts_available,
        is_cam_relevant=row.is_cam_relevant,
        is_cmp_relevant=row.is_cmp_relevant,
        last_update_utc=row.last_update_utc.isoformat() if row.last_update_utc else None,
        source_system=row.source_system,
        source_dataset=row.source_dataset,
        source_reference=row.source_reference,
        source_record_id=row.source_record_id,
        data_quality=row.data_quality,
        metadata_json=row.metadata_json,
    )
