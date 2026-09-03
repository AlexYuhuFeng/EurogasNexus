"""SDK client for /api/cost-observations."""

from __future__ import annotations

from pydantic import BaseModel, Field

from eurogas_nexus_sdk import _http


class CostObservationDTO(BaseModel):
    """One time-windowed cost observation."""

    observation_id: str
    scope_type: str
    scope_id: str
    observation_type: str
    value: float
    currency: str
    unit: str
    direction: str | None = None
    capacity_product: str | None = None
    firmness: str | None = None
    gas_year: str | None = None
    effective_from_utc: str
    effective_to_utc: str | None = None
    source_system: str
    source_reference: str
    entitlement_scope: list[str] = Field(default_factory=list)
    status: str
    manual_review_required: bool = True


class CostResolutionDTO(BaseModel):
    """Applicable-cost resolution result."""

    scope_type: str
    scope_id: str
    as_of_utc: str
    selected: CostObservationDTO | None = None
    alternatives: list[CostObservationDTO] = Field(default_factory=list)
    fallback_used: bool = False
    entitlement_scopes: list[str] = Field(default_factory=list)


def fetch_cost_observations(
    base_url: str,
    *,
    scope_type: str | None = None,
    scope_id: str | None = None,
    as_of: str | None = None,
) -> list[CostObservationDTO]:
    """Return active cost observations for a scope."""

    url = f"{base_url}/api/cost-observations/values"
    params = {}
    if scope_type:
        params["scope_type"] = scope_type
    if scope_id:
        params["scope_id"] = scope_id
    if as_of:
        params["as_of"] = as_of
    response = _http.get(url, params=params, timeout=10)
    response.raise_for_status()
    return [CostObservationDTO(**row) for row in response.json()["data"]]


def resolve_cost_observation(
    base_url: str,
    *,
    scope_type: str,
    scope_id: str,
    as_of: str,
    entitlement_scope: list[str] | None = None,
) -> CostResolutionDTO:
    """Resolve the applicable cost with entitlement priority."""

    url = f"{base_url}/api/cost-observations/applicable"
    params = {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "as_of": as_of,
        "entitlement_scope": entitlement_scope or [],
    }
    response = _http.get(url, params=params, timeout=10)
    response.raise_for_status()
    return CostResolutionDTO(**response.json()["data"])
