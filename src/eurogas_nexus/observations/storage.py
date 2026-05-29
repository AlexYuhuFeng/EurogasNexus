"""Storage site and observation models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from eurogas_nexus.observations.market import ObservationFreshness


@dataclass(frozen=True)
class StorageSite:
    """An underground gas storage site."""

    site_id: str
    name: str
    country: str
    lat: float
    lon: float
    working_capacity_mcm: float | None = None
    injection_rate_mcm_d: float | None = None
    withdrawal_rate_mcm_d: float | None = None
    status: str = "operational"
    source_system: str = "synthetic-fixture"


@dataclass(frozen=True)
class StorageObservation:
    """A single storage fill-level or injection/withdrawal observation."""

    observation_id: str
    site_id: str
    site_name: str
    observation_type: str  # "fill_level", "injection", "withdrawal"
    fill_pct: float | None = None  # 0-100
    volume_mcm: float | None = None
    period_start_utc: str = ""
    period_end_utc: str = ""
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "synthetic-fixture"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    research_only: bool = True
