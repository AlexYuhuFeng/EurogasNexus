"""Weather station, observation, and HDD/CDD metric models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from eurogas_nexus.observations.market import ObservationFreshness


@dataclass(frozen=True)
class WeatherStation:
    """A weather observation station."""

    station_id: str
    name: str
    country: str
    lat: float
    lon: float
    source_system: str = "operator-input"


@dataclass(frozen=True)
class WeatherObservation:
    """A single temperature observation."""

    observation_id: str
    station_id: str
    station_name: str
    temperature_c: float
    period_start_utc: str
    period_end_utc: str
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "operator-input"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    research_only: bool = True


@dataclass(frozen=True)
class HddCddMetric:
    """Heating Degree Days (HDD) or Cooling Degree Days (CDD) metric."""

    metric_id: str
    station_id: str
    station_name: str
    metric_type: str  # "HDD" or "CDD"
    base_temperature_c: float  # typically 15.5 for HDD, 18.0 for CDD
    value: float
    period_start_utc: str
    period_end_utc: str
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "operator-input"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    research_only: bool = True
