"""SDK API client for health endpoint."""

import httpx
from pydantic import BaseModel


class HealthPayload(BaseModel):
    status: str
    service: str
    version: str
    profile: str


def fetch_health(base_url: str, timeout_seconds: float = 5.0) -> HealthPayload:
    """Fetch health payload from backend API."""

    response = httpx.get(f"{base_url.rstrip('/')}/api/health", timeout=timeout_seconds)
    response.raise_for_status()
    return HealthPayload.model_validate(response.json())
