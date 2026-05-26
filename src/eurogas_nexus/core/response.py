"""Shared response models for API shell endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned by the import-safe health endpoint."""

    status: Literal["ok"] = "ok"
    service: str = "eurogas-nexus"
    version: str
    profile: str

