"""SDK client for /api/physical."""

from pydantic import BaseModel

from eurogas_nexus_sdk._transport import SdkResult, api_url, get_envelope


class FlowObservation(BaseModel):
    """One physical gas flow observation at a network point.

    Attributes:
        observation_id: Identifier of the observation.
        point_id: Reference-network identifier of the point.
        point_name: Display name of the point.
        direction: Flow direction of the observation.
        flow_mcm_d: Flow volume in million cubic metres per day.
        period_start_utc: UTC start of the observation period.
        period_end_utc: UTC end of the observation period.
        observed_at_utc: UTC time the observation was captured; None when
            unknown.
        source_system: System that produced the observation.
        source_reference: Reference of the observation in the source system.
        freshness: Freshness verdict of the observation.
        research_only: True when the observation is research-only.
    """

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
    # 观测载荷默认 research_only=True：数据来自外部源系统、未经生产确认，
    # 默认按"仅研究用途"标记，调用方须显式确认后才能用于决策。
    research_only: bool = True


class CapacityObservation(BaseModel):
    """One physical capacity observation at a network point.

    Attributes:
        observation_id: Identifier of the observation.
        point_id: Reference-network identifier of the point.
        point_name: Display name of the point.
        direction: Flow direction the capacity applies to.
        capacity_type: Kind of capacity (e.g. technical/available).
        capacity_mcm_d: Capacity in million cubic metres per day.
        original_value: Raw value as reported by the source, before conversion.
        original_unit: Unit of the raw value.
        period_start_utc: UTC start of the capacity period.
        period_end_utc: UTC end of the capacity period.
        observed_at_utc: UTC time the observation was captured; None when
            unknown.
        source_system: System that produced the observation.
        source_reference: Reference of the observation in the source system.
        freshness: Freshness verdict of the observation.
        research_only: True when the observation is research-only.
    """

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
    """One planned or unplanned outage event at a facility.

    Attributes:
        event_id: Identifier of the outage event.
        facility_id: Reference-network identifier of the facility.
        facility_name: Display name of the facility.
        event_type: Kind of outage (e.g. planned/forced).
        status: Lifecycle status of the outage event.
        start_utc: UTC start of the outage.
        end_utc: UTC end of the outage; None when still ongoing.
        capacity_impact_mcm_d: Capacity removed by the outage in mcm per day.
        description: Free-text description of the outage.
    """

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
    """Fetch physical flow observations.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        Flow observations; envelope metadata is dropped, use
        ``fetch_flows_result`` when lineage is needed.
    """

    # 与 *_result 版本成对提供：data-only 方便快速取数，_result 保留信封
    # meta（source_refs/warnings/research_only 等）供审计与治理展示。
    return fetch_flows_result(base_url).data


def fetch_flows_result(base_url: str) -> SdkResult[list[FlowObservation]]:
    """Fetch physical flow observations with envelope metadata.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        Flow observations plus backend lineage and warning metadata.
    """

    data, meta = get_envelope(api_url(base_url, "physical/flows"))
    return SdkResult([FlowObservation.model_validate(row) for row in data], meta)


def fetch_capacity(base_url: str) -> list[CapacityObservation]:
    """Fetch physical capacity observations.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        Capacity observations; use ``fetch_capacity_result`` for metadata.
    """

    return fetch_capacity_result(base_url).data


def fetch_capacity_result(base_url: str) -> SdkResult[list[CapacityObservation]]:
    """Fetch physical capacity observations with envelope metadata.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        Capacity observations plus backend lineage and warning metadata.
    """

    data, meta = get_envelope(api_url(base_url, "physical/capacity"))
    return SdkResult([CapacityObservation.model_validate(row) for row in data], meta)


def fetch_outages(base_url: str) -> list[OutageEvent]:
    """Fetch outage events.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        Outage events; use ``fetch_outages_result`` for metadata.
    """

    return fetch_outages_result(base_url).data


def fetch_outages_result(base_url: str) -> SdkResult[list[OutageEvent]]:
    """Fetch outage events with envelope metadata.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        Outage events plus backend lineage and warning metadata.
    """

    data, meta = get_envelope(api_url(base_url, "physical/outages"))
    return SdkResult([OutageEvent.model_validate(row) for row in data], meta)
