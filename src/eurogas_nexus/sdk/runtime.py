"""SDK client for /api/v1/runtime status routes."""

import httpx
from pydantic import BaseModel


class RuntimeConnectivity(BaseModel):
    ok: bool
    error: str | None = None


class RuntimeDbStatus(BaseModel):
    database_url_present: bool
    redacted_database_url: str | None = None
    connectivity: RuntimeConnectivity
    alembic_revision: str | None = None
    required_tables: list[str]
    missing_tables: list[str]
    warnings: list[str]


def fetch_runtime_db_status(base_url: str) -> RuntimeDbStatus:
    response = httpx.get(f"{base_url}/api/v1/runtime/db", timeout=10)
    response.raise_for_status()
    return RuntimeDbStatus(**response.json()["data"])
