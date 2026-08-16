"""Controlled vocabulary — the enumerable, machine-checkable values.

This is the canonical home for every finite value a domain model accepts. It
adopts the runtime enum values already used by the route-cost domain (exact
strings preserved) and adds the ontology-specific taxonomies. The strict values
let deterministic engines and LLM validation resolve to the same finite set.
"""

from __future__ import annotations

from enum import StrEnum

# --- Runtime route-cost enums (values preserved verbatim) -------------------


class TariffStatus(StrEnum):
    FINAL = "FINAL"
    INDICATIVE = "INDICATIVE"
    PROVISIONAL = "PROVISIONAL"
    DRAFT = "DRAFT"
    SIMULATOR_ONLY = "SIMULATOR_ONLY"


class TariffDirection(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class CapacityProduct(StrEnum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"
    MONTHLY = "MONTHLY"
    WEEKLY = "WEEKLY"
    DAILY = "DAILY"
    WITHIN_DAY = "WITHIN_DAY"


class Firmness(StrEnum):
    FIRM = "FIRM"
    INTERRUPTIBLE = "INTERRUPTIBLE"
    BACKHAUL = "BACKHAUL"
    OFF_PEAK = "OFF_PEAK"


class PointType(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    BEACH = "BEACH"
    LNG_TERMINAL = "LNG_TERMINAL"
    STORAGE = "STORAGE"
    INTERCONNECTION = "INTERCONNECTION"
    VIRTUAL = "VIRTUAL"
    OFFTAKE = "OFFTAKE"


class BusinessModel(StrEnum):
    VIRTUAL_HUB_SALE = "VIRTUAL_HUB_SALE"
    PHYSICAL_DELIVERY = "PHYSICAL_DELIVERY"
    STORAGE_INJECTION = "STORAGE_INJECTION"
    CROSS_BORDER_TRANSFER = "CROSS_BORDER_TRANSFER"


class DeliveryMode(StrEnum):
    TERMINAL_TITLE_TRANSFER = "TERMINAL_TITLE_TRANSFER"
    VIRTUAL_HUB_SALE = "VIRTUAL_HUB_SALE"
    PHYSICAL_ENTRY_DELIVERY = "PHYSICAL_ENTRY_DELIVERY"
    DOWNSTREAM_PHYSICAL_DELIVERY = "DOWNSTREAM_PHYSICAL_DELIVERY"
    BORDER_TRANSFER = "BORDER_TRANSFER"
    STORAGE_INJECTION = "STORAGE_INJECTION"
    STORAGE_WITHDRAWAL = "STORAGE_WITHDRAWAL"


class SourceResourceType(StrEnum):
    BEACH_DELIVERY = "BEACH_DELIVERY"
    LNG_REGAS = "LNG_REGAS"
    PIPELINE_IMPORT = "PIPELINE_IMPORT"
    STORAGE = "STORAGE"
    CONTRACT_POOL = "CONTRACT_POOL"


class CostComponentType(StrEnum):
    ENTRY_CAPACITY = "ENTRY_CAPACITY"
    EXIT_CAPACITY = "EXIT_CAPACITY"
    COMMODITY_CHARGE = "COMMODITY_CHARGE"
    BALANCING_ALLOWANCE = "BALANCING_ALLOWANCE"
    AUCTION_PREMIUM = "AUCTION_PREMIUM"
    CASHFLOW_TIMING = "CASHFLOW_TIMING"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


# --- Ontology-specific taxonomies -------------------------------------------


class MarketHub(StrEnum):
    """European virtual trading hubs / market-area price anchors."""

    TTF = "TTF"
    NBP = "NBP"
    THE = "THE"
    NCG = "NCG"
    GASPOOL = "GASPOOL"
    PEG = "PEG"
    CEGH = "CEGH"
    PSV = "PSV"
    ZTP = "ZTP"


class NodeType(StrEnum):
    """Reference-network node kinds."""

    HUB = "hub"
    INTERCONNECTION = "interconnection"
    ENTRY_POINT = "entry_point"
    EXIT_POINT = "exit_point"
    LNG = "lng"
    STORAGE = "storage"
    CITY_GATE = "city_gate"
    PRODUCTION = "production"


class EdgeType(StrEnum):
    """Reference-network edge kinds."""

    PIPELINE = "pipeline"
    VIRTUAL = "virtual"
    CORRIDOR = "corridor"


class FacilityType(StrEnum):
    """Reference-facility kinds."""

    LNG_TERMINAL = "lng_terminal"
    STORAGE = "storage"
    REGAS = "regas"
    COMPRESSOR = "compressor"
    METERING = "metering"
    BORDER_POINT = "border_point"


class ProductTenor(StrEnum):
    """Temporal granularity of a gas product."""

    DAY_AHEAD = "day-ahead"
    WITHIN_DAY = "within-day"
    INTRADAY = "intraday"
    WEEKEND = "weekend"
    MONTH = "month"
    QUARTER = "quarter"
    SEASON = "season"
    YEAR = "year"


class ProductKind(StrEnum):
    """Instrument kind."""

    SPOT = "spot"
    FORWARD = "forward"
    FUTURES = "futures"
    OPTIONS = "options"


class PriceType(StrEnum):
    """Price side or derived-price kind."""

    BID = "bid"
    ASK = "ask"
    LAST = "last"
    MID = "mid"
    SETTLEMENT = "settlement"
    ASSESSMENT = "assessment"
    INDEX = "index"


class PriceDataKind(StrEnum):
    """Distinguishes assessment/derived data from executable screen marks."""

    MARKET_OBSERVATION = "market_observation"
    LIVE_MARKET_MARK = "live_market_mark"
    MARKET_QUOTE = "market_quote"


class CapacityScope(StrEnum):
    """Capacity availability bucket."""

    TECHNICAL = "technical"
    BOOKED = "booked"
    AVAILABLE = "available"


class FlowKind(StrEnum):
    """Nature of a flow observation."""

    ACTUAL = "actual"
    NOMINATION = "nomination"
    ALLOCATION = "allocation"
    FORECAST = "forecast"


class Currency(StrEnum):
    """Supported settlement currencies (FX-convertible)."""

    GBP = "GBP"
    EUR = "EUR"
    USD = "USD"


class StrategyRunMode(StrEnum):
    """Strategy-lab run mode."""

    BACKTEST = "BACKTEST"
    SHADOW_RUN = "SHADOW_RUN"
    LIVE_MONITOR = "LIVE_MONITOR"


class StrategyComponentType(StrEnum):
    """Strategy-lab component family."""

    OCM_VS_DAY_AHEAD = "OCM_VS_DAY_AHEAD"
    MEAN_REVERSION = "MEAN_REVERSION"
    BEST_BUCKETS = "BEST_BUCKETS"
    SCORING = "SCORING"
    WEIGHTED_COMBINATION = "WEIGHTED_COMBINATION"


class CandidateAction(StrEnum):
    """Trader-review recommendation produced by a strategy/optimizer run."""

    REVIEW_STRATEGY_OUTPUT = "REVIEW_STRATEGY_OUTPUT"
    REVIEW_BLOCKED_STRATEGY = "REVIEW_BLOCKED_STRATEGY"
    REVIEW_PARTIAL_STRATEGY = "REVIEW_PARTIAL_STRATEGY"
    REVIEW_HIGHER_OCM_ALLOCATION = "REVIEW_HIGHER_OCM_ALLOCATION"
    REVIEW_HIGHER_DAY_AHEAD_ALLOCATION = "REVIEW_HIGHER_DAY_AHEAD_ALLOCATION"
    REVIEW_BALANCED_ALLOCATION = "REVIEW_BALANCED_ALLOCATION"


class ReviewDecisionValue(StrEnum):
    """Trader review outcome for a decision-support artifact."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_ATTENTION = "needs_attention"


class ReviewEntityType(StrEnum):
    """Artifact kinds that can carry a trader review decision."""

    INTRADAY_OPPORTUNITY = "intraday_opportunity"
    STRATEGY_RUN = "strategy_run"
    GENERATED_REPORT = "generated_report"
