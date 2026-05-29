"""SDK client for /api/v1/contracts."""

import httpx
from pydantic import BaseModel


class CapacityContract(BaseModel):
    contract_id: str
    route_name: str
    from_node_id: str
    to_node_id: str
    capacity_boe_d: float
    unit: str = "boe/d"
    start_utc: str = ""
    end_utc: str = ""
    status: str = "active"


class RouteEligibility(BaseModel):
    route_id: str
    from_node_id: str
    to_node_id: str
    eligibility: str
    confidence: float
    constraints: list[str] = []


def _get(url: str) -> dict:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_capacity_contracts(base_url: str) -> list[CapacityContract]:
    return [CapacityContract(**c) for c in _get(f"{base_url}/api/v1/contracts/capacity")["data"]]

def fetch_route_eligibility(base_url: str) -> list[RouteEligibility]:
    return [RouteEligibility(**r) for r in _get(f"{base_url}/api/v1/contracts/routes")["data"]]
