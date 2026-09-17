"""Shared response models for API shell endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned by the import-safe health endpoint."""

    status: Literal["ok"] = "ok"
    service: str = "eurogas-nexus"
    version: str
    profile: str
    #: Whether this profile installs app-wide authentication (architecture finding C5).
    #: `not_installed` is a documented posture of the development and internal profiles, not
    #: an error - but it is the difference between a deployment that identifies its callers
    #: and one that trusts the network, so it is reported rather than assumed.
    authentication: Literal["enforced", "not_installed"] = "not_installed"

