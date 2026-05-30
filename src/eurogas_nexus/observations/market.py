"""Market observation models — prices, spreads, FX, unit conversion."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ObservationFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MarketObservation:
    """A single market price or spread observation."""

    observation_id: str
    market_venue: str  # "TTF", "NBP", "EEX", "ICE", "PEG", etc.
    product: str  # "month-ahead", "day-ahead", "within-day", "spot"
    price: float
    unit: str  # "EUR/MWh", "p/th", "USD/MMBtu"
    currency: str  # "EUR", "GBP", "USD"
    period_start_utc: str
    period_end_utc: str
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "synthetic-fixture"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    quality_score: float = 1.0
    research_only: bool = True


@dataclass(frozen=True)
class FxObservation:
    """A single FX rate observation (e.g., EUR/USD, EUR/GBP)."""

    pair: str  # "EURUSD", "EURGBP"
    rate: float
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "synthetic-fixture"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    research_only: bool = True


@dataclass(frozen=True)
class UnitConversionRule:
    """A unit conversion rule (e.g., MWh to MMBtu, p/th to EUR/MWh)."""

    rule_id: str
    from_unit: str
    to_unit: str
    factor: float
    description: str = ""
    source_system: str = "synthetic-fixture"
