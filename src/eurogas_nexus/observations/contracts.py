"""Capacity contract and route eligibility context models."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapacityContract:
    """A research-view capacity contract record.

    NOT an ETRM, booking, or nomination record. Research context only.
    """

    contract_id: str
    route_name: str
    from_node_id: str
    to_node_id: str
    capacity_boe_d: float
    unit: str = "boe/d"
    start_utc: str = ""
    end_utc: str = ""
    status: str = "active"  # "active", "expiring", "expired"
    counterparty: str = ""
    notes: str = ""
    source_system: str = "synthetic-fixture"
    research_only: bool = True
    human_review_required: bool = True


@dataclass(frozen=True)
class RouteEligibility:
    """Whether a route corridor is eligible for research scenario evaluation."""

    route_id: str
    from_node_id: str
    to_node_id: str
    eligibility: str  # "research_candidate", "confirmed", "ineligible"
    confidence: float  # 0.0 - 1.0
    constraints: list[str] = field(default_factory=list)
    notes: str = ""
    source_system: str = "synthetic-fixture"
    research_only: bool = True
