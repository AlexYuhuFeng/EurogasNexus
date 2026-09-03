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
    """Status of a tariff source document, best-to-worst for selection."""

    FINAL = "FINAL"
    INDICATIVE = "INDICATIVE"
    PROVISIONAL = "PROVISIONAL"
    DRAFT = "DRAFT"
    SIMULATOR_ONLY = "SIMULATOR_ONLY"


class TariffDirection(StrEnum):
    """Direction of a capacity/tariff charge at a system point."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"


class CapacityProduct(StrEnum):
    """Capacity product duration offered at interconnection points."""

    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"
    MONTHLY = "MONTHLY"
    WEEKLY = "WEEKLY"
    DAILY = "DAILY"
    WITHIN_DAY = "WITHIN_DAY"


class Firmness(StrEnum):
    """Firmness class of a capacity product or tariff."""

    FIRM = "FIRM"
    INTERRUPTIBLE = "INTERRUPTIBLE"
    BACKHAUL = "BACKHAUL"
    OFF_PEAK = "OFF_PEAK"


class PointType(StrEnum):
    """Kind of a network point in route/tariff modelling."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    BEACH = "BEACH"
    LNG_TERMINAL = "LNG_TERMINAL"
    STORAGE = "STORAGE"
    INTERCONNECTION = "INTERCONNECTION"
    VIRTUAL = "VIRTUAL"
    OFFTAKE = "OFFTAKE"


class BusinessModel(StrEnum):
    """Commercial model of a route-cost scenario."""

    VIRTUAL_HUB_SALE = "VIRTUAL_HUB_SALE"
    PHYSICAL_DELIVERY = "PHYSICAL_DELIVERY"
    STORAGE_INJECTION = "STORAGE_INJECTION"
    CROSS_BORDER_TRANSFER = "CROSS_BORDER_TRANSFER"


class DeliveryMode(StrEnum):
    """How a resource delivers or a sale is executed (physical/title)."""

    TERMINAL_TITLE_TRANSFER = "TERMINAL_TITLE_TRANSFER"
    VIRTUAL_HUB_SALE = "VIRTUAL_HUB_SALE"
    PHYSICAL_ENTRY_DELIVERY = "PHYSICAL_ENTRY_DELIVERY"
    DOWNSTREAM_PHYSICAL_DELIVERY = "DOWNSTREAM_PHYSICAL_DELIVERY"
    BORDER_TRANSFER = "BORDER_TRANSFER"
    STORAGE_INJECTION = "STORAGE_INJECTION"
    STORAGE_WITHDRAWAL = "STORAGE_WITHDRAWAL"


class SourceResourceType(StrEnum):
    """Type of an upstream source resource in the portfolio."""

    BEACH_DELIVERY = "BEACH_DELIVERY"
    LNG_REGAS = "LNG_REGAS"
    PIPELINE_IMPORT = "PIPELINE_IMPORT"
    STORAGE = "STORAGE"
    CONTRACT_POOL = "CONTRACT_POOL"


class CostComponentType(StrEnum):
    """Cost component kinds in route-cost breakdowns."""

    ENTRY_CAPACITY = "ENTRY_CAPACITY"
    EXIT_CAPACITY = "EXIT_CAPACITY"
    COMMODITY_CHARGE = "COMMODITY_CHARGE"
    BALANCING_ALLOWANCE = "BALANCING_ALLOWANCE"
    AUCTION_PREMIUM = "AUCTION_PREMIUM"
    CASHFLOW_TIMING = "CASHFLOW_TIMING"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


class AccessStatus(StrEnum):
    """Three-state TSO access evaluation.

    UNKNOWN must never be interpreted as granted: it fails closed for
    cross-zone routes until the company access list is supplied and checked.
    """

    CONFIRMED = "CONFIRMED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


class CapacityStatus(StrEnum):
    """Three-state capacity availability evaluation.

    Only NOT_REQUIRED (no network capacity needed, e.g. a same-point title
    transfer) may be treated as unlimited; UNKNOWN must fail closed.
    """

    KNOWN = "KNOWN"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class CapacityProductDuration(StrEnum):
    """Standard CAM capacity product durations.

    CAM (Regulation (EU) 2017/459) standard capacity products are yearly,
    quarterly, monthly, daily, and within-day. Day-ahead is an auction timing,
    not a capacity product (see ``AuctionTiming``).
    """

    YEARLY = "YEARLY"
    QUARTERLY = "QUARTERLY"
    MONTHLY = "MONTHLY"
    DAILY = "DAILY"
    WITHIN_DAY = "WITHIN_DAY"


class AuctionTiming(StrEnum):
    """Auction timing of capacity products (CAM Article 11)."""

    YEARLY_AUCTION = "YEARLY_AUCTION"
    QUARTERLY_AUCTION = "QUARTERLY_AUCTION"
    MONTHLY_AUCTION = "MONTHLY_AUCTION"
    DAILY_AUCTION = "DAILY_AUCTION"
    WITHIN_DAY_AUCTION = "WITHIN_DAY_AUCTION"
    DAY_AHEAD = "DAY_AHEAD"


# Non-standard capacity products kept for compatibility with legacy rows.
# They are explicitly marked as extensions so callers can flag them.
CAPACITY_PRODUCT_EXTENSIONS: frozenset[str] = frozenset({"WEEKLY"})


class StatusKind(StrEnum):
    """Unified result status semantics for optimizers and workflows.

    SUCCESS only when the outcome is complete; PARTIAL when volume or inputs
    are missing; BLOCKED when nothing could be decided; UNKNOWN when the
    evaluation did not run.
    """

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ActionKindCategory(StrEnum):
    """Action classification for governance/audit/approval rules.

    System actions need no human approval, analytical actions produce
    research outputs, decision candidates require human review before use,
    and external actions (orders, nominations) are forbidden by product
    boundary — never performed.
    """

    SYSTEM = "SYSTEM"
    ANALYTICAL = "ANALYTICAL"
    DECISION_CANDIDATE = "DECISION_CANDIDATE"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"


# --- OWL/GRM companion identifiers -----------------------------------------

GRM_ROLES: tuple[str, ...] = (
    "AllocationResponsible",
    "AreaCoordinator",
    "BalanceResponsibleParty",
    "BalancingEnergyResponsible",
    "CapacityPlatformResponsible",
    "CapacityResponsibleParty",
    "ClearingResponsible",
    "DistributionSystemOperator",
    "EnergyTradingPlatformResponsible",
    "FinalCustomer",
    "LngSystemOperator",
    "MarketInformationAggregator",
    "MeterOperator",
    "MeteredDataResponsible",
    "ProductionFacilityOperator",
    "ReconciliationResponsible",
    "StorageSystemOperator",
    "Supplier",
    "SystemOperator",
    "Trader",
    "TransmissionSystemOperator",
    "WeatherDataProvider",
)

GRM_PROCESSES: tuple[str, ...] = (
    "CapacityAllocationProcess",
    "ExchangeGasTradingProcess",
    "OtcGasTradingProcess",
    "NominationMatchingProcess",
    "MeteringProcess",
    "AllocationProcess",
    "BalancingProcess",
    "SettlementProcess",
    "RemitTransparencyProcess",
)


# --- Ontology-specific taxonomies -------------------------------------------


class MarketHub(StrEnum):
    """European virtual trading hubs / market-area price anchors.

    NOTE (Gate 2): the effective-dated DB reference master is
    ``reference_market_hubs`` (validity window, market area, supersession).
    This enum is the compatibility closure used by legacy code; historical
    codes (NCG, GASPOOL) are retained for backfill and superseded by THE per
    ``MARKET_HUB_SUPERSESSIONS``.
    """

    TTF = "TTF"
    NBP = "NBP"
    THE = "THE"
    NCG = "NCG"
    GASPOOL = "GASPOOL"
    PEG = "PEG"
    CEGH = "CEGH"
    PSV = "PSV"
    ZTP = "ZTP"


# Market-area / hub replacements: historical market areas merged into THE
# (Trading Hub Europe) when the German market areas consolidated (2021).
MARKET_HUB_SUPERSESSIONS: dict[str, str] = {
    "NCG": "THE",
    "GASPOOL": "THE",
}


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
