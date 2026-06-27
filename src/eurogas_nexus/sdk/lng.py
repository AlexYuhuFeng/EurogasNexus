"""SDK client for /api/lng."""

import httpx
from pydantic import BaseModel


class LngTerminal(BaseModel):
    terminal_id: str
    name: str
    country: str
    lat: float
    lon: float
    capacity_mcm_d: float | None = None
    storage_capacity_mcm: float | None = None
    status: str = "operational"


class LngObservation(BaseModel):
    observation_id: str
    terminal_id: str
    terminal_name: str
    observation_type: str
    value_mcm: float | None = None
    period_start_utc: str = ""
    period_end_utc: str = ""


def _get(url: str) -> dict:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_lng_terminals(base_url: str) -> list[LngTerminal]:
    return [LngTerminal(**t) for t in _get(f"{base_url}/api/lng/terminals")["data"]]

def fetch_lng_observations(base_url: str) -> list[LngObservation]:
    return [LngObservation(**o) for o in _get(f"{base_url}/api/lng/observations")["data"]]
