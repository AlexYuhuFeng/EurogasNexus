"""SDK client for /api/storage."""

import httpx
from pydantic import BaseModel


class StorageSite(BaseModel):
    site_id: str
    name: str
    country: str
    lat: float
    lon: float
    working_capacity_mcm: float | None = None
    status: str = "operational"


class StorageObservation(BaseModel):
    observation_id: str
    site_id: str
    site_name: str
    observation_type: str
    fill_pct: float | None = None
    volume_mcm: float | None = None
    period_start_utc: str = ""
    period_end_utc: str = ""


def _get(url: str) -> dict:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_storage_sites(base_url: str) -> list[StorageSite]:
    return [StorageSite(**s) for s in _get(f"{base_url}/api/storage/sites")["data"]]

def fetch_storage_observations(base_url: str) -> list[StorageObservation]:
    url = f"{base_url}/api/storage/observations"
    return [StorageObservation(**o) for o in _get(url)["data"]]
