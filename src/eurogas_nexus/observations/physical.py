"""Physical flow, capacity, and outage observation models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from eurogas_nexus.observations.market import ObservationFreshness


@dataclass(frozen=True)
class FlowObservation:
    """A single physical flow observation at an interconnection point."""

    observation_id: str
    point_id: str  # reference node ID
    point_name: str
    direction: str  # "entry", "exit"
    flow_mcm_d: float  # million cubic meters per day
    period_start_utc: str
    period_end_utc: str
    tso: str = ""
    country: str = ""
    interconnection_point_code: str = ""
    flow_status: str = "actual"  # "actual", "nomination", "allocation", "forecast"
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "synthetic-fixture"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    research_only: bool = True


@dataclass(frozen=True)
class CapacityObservation:
    """A single capacity observation (technical or booked)."""

    observation_id: str
    point_id: str
    point_name: str
    capacity_type: str  # "technical", "booked", "available"
    capacity_mcm_d: float
    period_start_utc: str
    period_end_utc: str
    direction: str = ""
    tso: str = ""
    country: str = ""
    firmness: str = "firm"
    product: str = "day"
    booking_platform: str = ""
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "synthetic-fixture"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    research_only: bool = True


@dataclass(frozen=True)
class OutageEvent:
    """A single infrastructure outage or maintenance event."""

    event_id: str
    facility_id: str
    facility_name: str
    event_type: str  # "planned", "unplanned", "maintenance"
    status: str  # "active", "resolved", "scheduled"
    start_utc: str
    end_utc: str | None = None
    affected_point_id: str = ""
    affected_point_name: str = ""
    tso: str = ""
    country: str = ""
    direction: str = ""
    capacity_impact_mcm_d: float = 0.0
    description: str = ""
    source_system: str = "synthetic-fixture"
    source_reference: str = ""
    research_only: bool = True
