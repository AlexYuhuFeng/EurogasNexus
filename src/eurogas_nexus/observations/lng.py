"""LNG and regas observation models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from eurogas_nexus.observations.market import ObservationFreshness


@dataclass(frozen=True)
class LngTerminal:
    """An LNG import/regas terminal."""

    terminal_id: str
    name: str
    country: str
    lat: float
    lon: float
    capacity_mcm_d: float | None = None
    storage_capacity_mcm: float | None = None
    status: str = "operational"
    source_system: str = "operator-input"


@dataclass(frozen=True)
class LngObservation:
    """A single LNG cargo or send-out observation."""

    observation_id: str
    terminal_id: str
    terminal_name: str
    observation_type: str  # "cargo_arrival", "send_out", "inventory"
    value_mcm: float | None = None
    period_start_utc: str = ""
    period_end_utc: str = ""
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "operator-input"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    research_only: bool = True
