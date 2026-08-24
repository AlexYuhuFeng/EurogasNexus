"""SDK client for /api/reference-network."""

from pydantic import BaseModel

from eurogas_nexus.sdk import _http


class NodeDTO(BaseModel):
    """One node of the European reference network.

    Attributes:
        id: Reference-network identifier of the node.
        name: Display name of the node.
        node_type: Kind of node (e.g. hub/entry/exit).
        country: ISO country code of the node.
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        capacity_boe_d: Rated capacity in barrels of oil equivalent per day;
            None when not declared.
    """

    id: str
    name: str
    node_type: str
    country: str
    lat: float
    lon: float
    capacity_boe_d: float | None = None


class EdgeDTO(BaseModel):
    """One directed edge between two reference-network nodes.

    Attributes:
        id: Reference-network identifier of the edge.
        from_node_id: Identifier of the origin node.
        to_node_id: Identifier of the destination node.
        edge_type: Kind of edge (e.g. pipeline/reverse).
        length_km: Length of the edge in kilometres; None when unknown.
    """

    id: str
    from_node_id: str
    to_node_id: str
    edge_type: str
    length_km: float | None = None


class FacilityDTO(BaseModel):
    """One facility (terminal, storage, LNG ...) of the reference network.

    Attributes:
        id: Reference-network identifier of the facility.
        name: Display name of the facility.
        facility_type: Kind of facility (e.g. lng/storage).
        country: ISO country code of the facility.
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        capacity_boe_d: Rated capacity in boe per day; None when not declared.
    """

    id: str
    name: str
    facility_type: str
    country: str
    lat: float
    lon: float
    capacity_boe_d: float | None = None


class MarketHubDTO(BaseModel):
    """One tradable market hub of the reference network.

    Attributes:
        id: Reference-network identifier of the hub.
        name: Display name of the hub.
        hub_code: Short hub code used in market data.
        country: ISO country code of the hub.
        description: Free-text description of the hub; None when absent.
    """

    id: str
    name: str
    hub_code: str
    country: str
    description: str | None = None


def _get(url: str, **params) -> dict:
    """GET one reference-network endpoint with optional query filters."""

    # 只发送非 None 参数：None 表示"未过滤"，若把 None 拼进 query-string，
    # 后端会把空值当作过滤条件，导致"不过滤"与"过滤为空"行为不一致。
    r = _http.get(url, params={k: v for k, v in params.items() if v is not None}, timeout=10)
    r.raise_for_status()
    # 不同端点的 data 形状不同（列表或单对象），解包放在各 fetch 函数内，
    # _get 只负责返回信封本身，不假设载荷形状。
    return r.json()


def fetch_nodes(
    base_url: str,
    *,
    country: str | None = None,
    node_type: str | None = None,
) -> list[NodeDTO]:
    """Fetch reference-network nodes, optionally filtered.

    Args:
        base_url: Base URL of the backend server.
        country: Only nodes in this ISO country code.
        node_type: Only nodes of this type.

    Returns:
        List of matching nodes.
    """

    data = _get(f"{base_url}/api/reference-network/nodes", country=country, node_type=node_type)
    return [NodeDTO(**n) for n in data["data"]]

def fetch_node(base_url: str, node_id: str) -> NodeDTO:
    """Fetch one reference-network node by identifier.

    Args:
        base_url: Base URL of the backend server.
        node_id: Identifier of the node to fetch.

    Returns:
        The requested node.
    """

    data = _get(f"{base_url}/api/reference-network/nodes/{node_id}")
    return NodeDTO(**data["data"])

def fetch_edges(
    base_url: str,
    *,
    from_node_id: str | None = None,
    to_node_id: str | None = None,
) -> list[EdgeDTO]:
    """Fetch reference-network edges, optionally filtered by endpoints.

    Args:
        base_url: Base URL of the backend server.
        from_node_id: Only edges starting at this node.
        to_node_id: Only edges ending at this node.

    Returns:
        List of matching edges.
    """

    url = f"{base_url}/api/reference-network/edges"
    data = _get(url, from_node_id=from_node_id, to_node_id=to_node_id)
    return [EdgeDTO(**e) for e in data["data"]]

def fetch_facilities(
    base_url: str,
    *,
    facility_type: str | None = None,
    country: str | None = None,
) -> list[FacilityDTO]:
    """Fetch reference-network facilities, optionally filtered.

    Args:
        base_url: Base URL of the backend server.
        facility_type: Only facilities of this type.
        country: Only facilities in this ISO country code.

    Returns:
        List of matching facilities.
    """

    url = f"{base_url}/api/reference-network/facilities"
    data = _get(url, facility_type=facility_type, country=country)
    return [FacilityDTO(**f) for f in data["data"]]

def fetch_market_hubs(base_url: str) -> list[MarketHubDTO]:
    """Fetch the tradable market hubs of the reference network.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        List of market hubs.
    """

    data = _get(f"{base_url}/api/reference-network/market-hubs")
    return [MarketHubDTO(**h) for h in data["data"]]
