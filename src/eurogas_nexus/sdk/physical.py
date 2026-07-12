"""SDK client for /api/physical."""

from pydantic import BaseModel

from eurogas_nexus.sdk._transport import SdkResult, api_url, get_envelope


class FlowObservation(BaseModel):
    observation_id: str
    point_id: str
    point_name: str
    direction: str
    flow_mcm_d: float
    period_start_utc: str
    period_end_utc: str
    observed_at_utc: str | None = None
    source_system: str | None = None
    source_reference: str | None = None
    freshness: str | None = None
    research_only: bool = True


class CapacityObservation(BaseModel):
    observation_id: str
    point_id: str
    point_name: str
    direction: str
    capacity_type: str
    capacity_mcm_d: float
    original_value: float | None = None
    original_unit: str | None = None
    period_start_utc: str
    period_end_utc: str
    observed_at_utc: str | None = None
    source_system: str | None = None
    source_reference: str | None = None
    freshness: str | None = None
    research_only: bool = True


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


def fetch_flows(base_url: str) -> list[FlowObservation]:
    return fetch_flows_result(base_url).data


def fetch_flows_result(base_url: str) -> SdkResult[list[FlowObservation]]:
    data, meta = get_envelope(api_url(base_url, "physical/flows"))
    return SdkResult([FlowObservation.model_validate(row) for row in data], meta)


def fetch_capacity(base_url: str) -> list[CapacityObservation]:
    return fetch_capacity_result(base_url).data


def fetch_capacity_result(base_url: str) -> SdkResult[list[CapacityObservation]]:
    data, meta = get_envelope(api_url(base_url, "physical/capacity"))
    return SdkResult([CapacityObservation.model_validate(row) for row in data], meta)


def fetch_outages(base_url: str) -> list[OutageEvent]:
    return fetch_outages_result(base_url).data


def fetch_outages_result(base_url: str) -> SdkResult[list[OutageEvent]]:
    data, meta = get_envelope(api_url(base_url, "physical/outages"))
    return SdkResult([OutageEvent.model_validate(row) for row in data], meta)
