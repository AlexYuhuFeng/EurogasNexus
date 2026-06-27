"""Market observation models for screen marks, assessed prices, FX, and units."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ObservationFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MarketObservation:
    """A single assessed market price or spread observation."""

    observation_id: str
    market_venue: str  # "TTF", "NBP", "EEX", "ICE", "PEG", etc.
    product: str  # "month-ahead", "day-ahead", "within-day", "spot"
    price: float
    unit: str  # "EUR/MWh", "GBP/MWh", "p/th", "USD/MMBtu"
    currency: str  # "EUR", "GBP", "USD"
    period_start_utc: str
    period_end_utc: str
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "operator-input"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    quality_score: float = 1.0
    commodity: str = "gas"
    market_area: str = ""
    delivery_location: str = ""
    product_code: str = ""
    contract_type: str = "assessment"  # "screen", "assessment", "index", "otc"
    price_type: str = "mid"  # "bid", "ask", "last", "settlement", "index", "mid"
    entitlement_scope: str = "internal-use"
    research_only: bool = True


@dataclass(frozen=True)
class MarketPriceMark:
    """A tradable or indicative screen mark captured from a venue/API feed."""

    mark_id: str
    venue: str  # "ICE OCM", "EEX", "Trayport", "Platts", etc.
    hub: str  # "NBP", "TTF", "THE", etc.
    product: str  # "within-day", "day-ahead", "front-month", etc.
    delivery_start_utc: str
    delivery_end_utc: str
    currency: str
    unit: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    settlement: float | None = None
    traded_volume_mwh: float | None = None
    open_interest_mwh: float | None = None
    source_system: str = "operator-input"
    source_reference: str = ""
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    quality_score: float = 1.0
    entitlement_scope: str = "internal-use"
    research_only: bool = True


@dataclass(frozen=True)
class FxObservation:
    """A single FX rate observation such as EUR/USD, EUR/GBP, or GBP/USD."""

    pair: str  # "EURUSD", "EURGBP"
    rate: float
    base_currency: str = ""
    quote_currency: str = ""
    rate_type: str = "reference"  # "reference", "spot", "fixing"
    value_date: str = ""
    observed_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_system: str = "operator-input"
    source_reference: str = ""
    freshness: ObservationFreshness = ObservationFreshness.UNKNOWN
    research_only: bool = True


@dataclass(frozen=True)
class UnitConversionRule:
    """A unit conversion rule such as MWh to MMBtu or p/th to GBP/MWh."""

    rule_id: str
    from_unit: str
    to_unit: str
    factor: float
    description: str = ""
    source_system: str = "operator-input"
