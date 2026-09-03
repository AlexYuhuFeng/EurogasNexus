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
    capacity_mwh_per_day: float | None = None
    direction: str = ""
    firmness: str = "firm"
    capacity_product: str = "day"
    contract_type: str = "capacity"
    settlement_frequency: str = ""
    payment_lag_days: int | None = None
    tolerance_pct: float | None = None
    overrun_charge_rule: str = ""
    start_utc: str = ""
    end_utc: str = ""
    status: str = "active"  # "active", "expiring", "expired"
    counterparty: str = ""
    notes: str = ""
    source_system: str = "operator-input"
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
    business_model: str = ""  # "virtual_hub_sale", "physical_delivery", "storage_cycle"
    required_capacity_products: list[str] = field(default_factory=list)
    required_market_marks: list[str] = field(default_factory=list)
    required_physical_signals: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    notes: str = ""
    source_system: str = "operator-input"
    research_only: bool = True
