"""SDK client for /api/v1/sources and /api/v1/ingestion-runs."""

import httpx
from pydantic import BaseModel


class SourceSystem(BaseModel):
    source_id: str
    source_system: str
    datasets: list[str] = []
    status: str = "registered"
    description: str = ""


class IngestionRun(BaseModel):
    run_id: str
    source_id: str
    status: str
    records_ingested: int = 0
    records_failed: int = 0
    normalization: str = "unknown"
    error_message: str | None = None


def _get(url: str, **params) -> dict:
    r = httpx.get(url, params={k: v for k, v in params.items() if v is not None}, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_sources(base_url: str) -> list[SourceSystem]:
    data = _get(f"{base_url}/api/v1/sources")
    return [SourceSystem(**s) for s in data["data"]]

def fetch_source(base_url: str, source_id: str) -> SourceSystem:
    data = _get(f"{base_url}/api/v1/sources/{source_id}")
    return SourceSystem(**data["data"])

def fetch_ingestion_runs(base_url: str, *, source_id: str | None = None) -> list[IngestionRun]:
    data = _get(f"{base_url}/api/v1/ingestion-runs", source_id=source_id)
    return [IngestionRun(**r) for r in data["data"]]
