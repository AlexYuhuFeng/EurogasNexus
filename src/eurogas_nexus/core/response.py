"""Shared response models for API shell endpoints."""

from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned by the import-safe health endpoint."""

    status: Literal["ok"] = "ok"
    service: str = "eurogas-nexus"
    version: str
    profile: str
    #: Whether this deployment identifies its callers (architecture finding C5, owner decision D1).
    #: `enforced` is the default in every profile: a caller that presents nothing is refused.
    #: `anonymous_allowed` is a deployment's own, explicit choice
    #: (`EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS`) to trust its network, and it is reported rather
    #: than assumed - an operator can always see which of the two this deployment is.
    #: `not_installed` remains declared for a profile that installs no authentication at all; no
    #: shipped profile does since D1.
    authentication: Literal[
        "enforced", "anonymous_allowed", "not_installed"
    ] = "enforced"
    #: The server's own time when it answered: a client compares it with its clock (deal and
    #: price ordering, the ages on screen), allowing for the round trip.
    server_time_utc: str | None = None
    #: The server clock's check (application/clock_check.py): ``state`` ok, warning, unknown
    #: or checking; ``offset_seconds`` against NTP; ``synchronised``; ``threshold_seconds``.
    clock: dict[str, Any] | None = None

