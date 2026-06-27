"""SDK client for /api/physical."""

import httpx
from pydantic import BaseModel


class FlowObservation(BaseModel):
    observation_id: str
    point_id: str
    point_name: str
    direction: str
    flow_mcm_d: float
    period_start_utc: str
    period_end_utc: str


class CapacityObservation(BaseModel):
    observation_id: str
    point_id: str
    point_name: str
    capacity_type: str
    capacity_mcm_d: float
    period_start_utc: str
    period_end_utc: str


class OutageEvent(BaseModel):
    event_id: str
    facility_id: str
    facility_name: str
    event_type: str
    status: str
    start_utc: str
    end_utc: str | None = None
    capacity_impact_mcm_d: float = 0.0
    description: str = ""


def _get(url: str) -> dict:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_flows(base_url: str) -> list[FlowObservation]:
    return [FlowObservation(**f) for f in _get(f"{base_url}/api/physical/flows")["data"]]

def fetch_capacity(base_url: str) -> list[CapacityObservation]:
    return [CapacityObservation(**c) for c in _get(f"{base_url}/api/physical/capacity")["data"]]

def fetch_outages(base_url: str) -> list[OutageEvent]:
    return [OutageEvent(**o) for o in _get(f"{base_url}/api/physical/outages")["data"]]
