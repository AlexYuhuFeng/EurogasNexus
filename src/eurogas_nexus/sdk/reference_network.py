"""SDK client for /api/reference-network."""

import httpx
from pydantic import BaseModel


class NodeDTO(BaseModel):
    id: str
    name: str
    node_type: str
    country: str
    lat: float
    lon: float
    capacity_boe_d: float | None = None


class EdgeDTO(BaseModel):
    id: str
    from_node_id: str
    to_node_id: str
    edge_type: str
    length_km: float | None = None


class FacilityDTO(BaseModel):
    id: str
    name: str
    facility_type: str
    country: str
    lat: float
    lon: float
    capacity_boe_d: float | None = None


class MarketHubDTO(BaseModel):
    id: str
    name: str
    hub_code: str
    country: str
    description: str | None = None


def _get(url: str, **params) -> dict:
    r = httpx.get(url, params={k: v for k, v in params.items() if v is not None}, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_nodes(
    base_url: str,
    *,
    country: str | None = None,
    node_type: str | None = None,
) -> list[NodeDTO]:
    data = _get(f"{base_url}/api/reference-network/nodes", country=country, node_type=node_type)
    return [NodeDTO(**n) for n in data["data"]]

def fetch_node(base_url: str, node_id: str) -> NodeDTO:
    data = _get(f"{base_url}/api/reference-network/nodes/{node_id}")
    return NodeDTO(**data["data"])

def fetch_edges(
    base_url: str,
    *,
    from_node_id: str | None = None,
    to_node_id: str | None = None,
) -> list[EdgeDTO]:
    url = f"{base_url}/api/reference-network/edges"
    data = _get(url, from_node_id=from_node_id, to_node_id=to_node_id)
    return [EdgeDTO(**e) for e in data["data"]]

def fetch_facilities(
    base_url: str,
    *,
    facility_type: str | None = None,
    country: str | None = None,
) -> list[FacilityDTO]:
    url = f"{base_url}/api/reference-network/facilities"
    data = _get(url, facility_type=facility_type, country=country)
    return [FacilityDTO(**f) for f in data["data"]]

def fetch_market_hubs(base_url: str) -> list[MarketHubDTO]:
    data = _get(f"{base_url}/api/reference-network/market-hubs")
    return [MarketHubDTO(**h) for h in data["data"]]
