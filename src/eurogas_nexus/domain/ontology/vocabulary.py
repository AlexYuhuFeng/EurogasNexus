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


# --- LNG cargo and terminal semantics --------------------------------------
#
# These are gas/energy stage and measurement semantics, so their reviewed home
# is this canonical ontology vocabulary. The original research and terminal
# modules re-export these exact classes so existing imports, API/SDK contracts
# and model-version strings remain unchanged. Reference-contract control codes
# (review, lookup, error and source-change status) deliberately stay with the
# terminal-reference contract; see docs/architecture/LNG_VOCABULARY_OWNERSHIP.md.


class LngEnergyStageKind(StrEnum):
    """Declared kind of one explicit LNG cargo energy stage."""

    CARGO_TRANSFER = "cargo_transfer"
    SHIPPING = "shipping"
    STORAGE = "storage"
    REGASIFICATION = "regasification"
    OTHER = "other"


class LngDownstreamChargeBasis(StrEnum):
    """Declared nature of one economics-only downstream charge.

    Only ``INVOICED_CASH`` may become a cash expense. ``IN_KIND`` and
    ``UNKNOWN`` are explicit declarations that must not be silently monetized;
    in-kind energy belongs in the explicit energy stages instead.
    """

    INVOICED_CASH = "invoiced_cash"
    IN_KIND = "in_kind"
    UNKNOWN = "unknown"


class QuantityBasis(StrEnum):
    """Distinct measurement bases. No member is converted into another."""

    LIQUID_LNG_M3_PER_HOUR = "LIQUID_LNG_M3_PER_HOUR"
    ACTUAL_GAS_M3_PER_HOUR = "ACTUAL_GAS_M3_PER_HOUR"
    NORMAL_GAS_NM3_PER_HOUR = "NORMAL_GAS_NM3_PER_HOUR"
    ENERGY_MWH_PER_HOUR = "ENERGY_MWH_PER_HOUR"
    ENERGY_GWH_PER_DAY = "ENERGY_GWH_PER_DAY"
    DURATION_HOURS = "DURATION_HOURS"
    TANK_CAPACITY_PERCENT_PER_DAY = "TANK_CAPACITY_PERCENT_PER_DAY"
    CARGO_ENERGY_PERCENT = "CARGO_ENERGY_PERCENT"
    MONEY_PER_ENERGY = "MONEY_PER_ENERGY"


class FactParameter(StrEnum):
    """Terminal fact parameters with deliberately narrow basis compatibility."""

    VESSEL_UNLOADING_MAX_RATE = "VESSEL_UNLOADING_MAX_RATE"
    VESSEL_UNLOADING_RATE = "VESSEL_UNLOADING_RATE"
    UNLOADING_RATE = "UNLOADING_RATE"
    SENDOUT_CAPACITY = "SENDOUT_CAPACITY"
    MINIMUM_SENDOUT_RATE = "MINIMUM_SENDOUT_RATE"
    REGASIFICATION_CAPACITY = "REGASIFICATION_CAPACITY"
    TANK_EVAPORATION_RATE = "TANK_EVAPORATION_RATE"
    EVAPORATION_RATE = "EVAPORATION_RATE"
    CARGO_ENERGY_LOSS_RATE = "CARGO_ENERGY_LOSS_RATE"
    RETAINED_FUEL_RATE = "RETAINED_FUEL_RATE"
    VESSEL_DISCHARGE_DURATION = "VESSEL_DISCHARGE_DURATION"
    TERMINAL_FEE = "TERMINAL_FEE"


# --- Contract payment-term vocabulary (S2a declared-rule representation) ----
#
# Parent design review for the S2a unit: explicit payment terms are evidence
# supplied by the operator, never a market default and never a legal
# conclusion. These finite vocabularies name what a declared rule may say.
# None of them supplies an anchor fact (invoice, delivery or meter date),
# resolves a date, or asserts a market/contract calendar: a rule may not be
# used for valuation until the required anchor facts and calendar versions
# exist and a resolver has been reviewed. The single implementation lives in
# ``domain/route_cost/payment_terms.py``; this is the reviewed vocabulary it
# consumes, not a parallel taxonomy.


class PaymentAnchorEvent(StrEnum):
    """Reviewed anchor events a declared payment rule may reference.

    The event names *which* contractual fact the operator declared (for
    example the invoice date); it never supplies the fact itself, so no
    invoice, delivery-period or meter-read date is inferred or defaulted.
    """

    INVOICE_DATE = "INVOICE_DATE"
    DELIVERY_PERIOD_START = "DELIVERY_PERIOD_START"
    DELIVERY_PERIOD_END = "DELIVERY_PERIOD_END"
    METER_READ_DATE = "METER_READ_DATE"


class PaymentOffsetDayKind(StrEnum):
    """Whether a declared anchor offset counts calendar or business days.

    A business-day count requires an explicit calendar reference on the rule;
    no counting convention is defaulted.
    """

    CALENDAR_DAYS = "CALENDAR_DAYS"
    BUSINESS_DAYS = "BUSINESS_DAYS"


class BusinessDayConvention(StrEnum):
    """Explicit business-day adjustment convention of a declared rule.

    ``NONE`` means the declared date is used exactly as stated and is never
    rolled; the other values roll onto a business day of the rule's explicit
    calendar reference. No convention is defaulted.
    """

    NONE = "NONE"
    FOLLOWING = "FOLLOWING"
    MODIFIED_FOLLOWING = "MODIFIED_FOLLOWING"
    PRECEDING = "PRECEDING"


class PaymentDateSpecificationKind(StrEnum):
    """Discriminator of a declared payment date specification.

    Exactly one shape applies per schedule item: an operator-stated final
    payable date, or a rule anchored to a reviewed event.
    """

    EXPLICIT_DATE = "EXPLICIT_DATE"
    ANCHORED_RULE = "ANCHORED_RULE"


class PaymentFlowDirection(StrEnum):
    """Declared direction of one payment item's money flow.

    Defined from the contract-holder/reporting entity's perspective:
    ``INFLOW`` is money received, ``OUTFLOW`` is money paid out. The direction
    is stated per item and never inferred from the cash-flow category; a
    refund or reimbursement can reverse the category's usual sign, so future
    composition must validate any signed amount against this explicit
    declaration rather than deriving a sign from the category.
    """

    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"


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


# --- Weather-to-demand semantics (RFC-0003 phase C) -------------------------
#
# These finite vocabularies name the weather evidence, demand targets and
# degree-day features consumed by the pure weather-to-demand research core.
# They are gas/data semantics, not research-lifecycle states, so their canonical
# home is this ontology vocabulary. ``domain/research/weather_demand.py`` imports
# and re-exports these exact classes, preserving existing public imports, enum
# identity and serialized values.


class TemperatureInputType(StrEnum):
    """Whether a temperature value is a forecast vintage or realized evidence."""

    FORECAST_VINTAGE = "FORECAST_VINTAGE"
    REALIZED_OBSERVATION = "REALIZED_OBSERVATION"


class TargetScope(StrEnum):
    """Supported actual-target scope; no implicit cross-region aggregation."""

    GB_NTS_THROUGHPUT = "GB_NTS_THROUGHPUT"
    REGION = "REGION"


class DemandTargetQuality(StrEnum):
    """Native target quality preserved from the source revision."""

    ACTUAL = "ACTUAL"
    ESTIMATED = "ESTIMATED"
    PROVISIONAL = "PROVISIONAL"
    ALLOCATED = "ALLOCATED"


class WeatherFeature(StrEnum):
    """Weather columns that a demand candidate may use explicitly."""

    HDD_MEAN = "HDD_MEAN"
    CDD_MEAN = "CDD_MEAN"
    HDD_INTEGRAL = "HDD_INTEGRAL"
    CDD_INTEGRAL = "CDD_INTEGRAL"


class TemperatureDerivationMethod(StrEnum):
    """How an interval mean was produced, kept separate from degree-day math.

    ``PROVIDER_INTERVAL_MEAN`` means the provider supplied a mean over the whole
    valid interval. ``EXPLICIT_DERIVED_HOLD`` means a single value was explicitly
    held across the interval by a derivation step. The weather-to-demand core
    performs no instant-to-mean conversion; a future adapter that does must label
    its output.
    """

    PROVIDER_INTERVAL_MEAN = "PROVIDER_INTERVAL_MEAN"
    EXPLICIT_DERIVED_HOLD = "EXPLICIT_DERIVED_HOLD"


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

GRM_INTERACTION_PROPERTIES: dict[str, tuple[str, str]] = {
    # property: (rdfs:domain role, rdfs:range role or commodity class)
    "providesAllocationData": ("GasMarketRole", "GasMarketRole"),
    "providesMatchingResults": ("GasMarketRole", "GasMarketRole"),
    "providesMeteredData": ("GasMarketRole", "GasMarketRole"),
    "providesValidatedMeteredData": ("MeteredDataResponsible", "MarketInformationAggregator"),
    "providesWeatherData": ("WeatherDataProvider", "GasMarketRole"),
    "providesNominationAndMatchingData": ("GasMarketRole", "GasMarketRole"),
    "submitsBidsOrOffers": ("Trader", "EnergyTradingPlatformResponsible"),
    "reportsTradeData": ("Trader", "MarketInformationAggregator"),
    "providesTradeInformation": ("EnergyTradingPlatformResponsible", "ClearingResponsible"),
    "confirmsExecutedTrades": ("EnergyTradingPlatformResponsible", "Trader"),
    "nominatesConcludedTrades": ("EnergyTradingPlatformResponsible", "BalanceResponsibleParty"),
    "purchasesCapacityFrom": ("CapacityResponsibleParty", "CapacityPlatformResponsible"),
    "allocatesCapacityTo": ("CapacityPlatformResponsible", "CapacityResponsibleParty"),
    "offersAvailableCapacity": ("TransmissionSystemOperator", "CapacityPlatformResponsible"),
    "commissionsBalancingEnergy": ("AreaCoordinator", "BalancingEnergyResponsible"),
    "suppliesGasTo": ("Supplier", "FinalCustomer"),
    "tradesGas": ("Trader", "GasCommodity"),
    "transportsGas": ("CapacityResponsibleParty", "GasCommodity"),
}

# Sub-property relationships emitted by scripts/ontology/generate_grm_ttl.py.
GRM_INTERACTION_SUBPROPERTIES: dict[str, str] = {
    "providesValidatedMeteredData": "providesMeteredData",
}

GRM_BOUNDARY_CLASSES: tuple[str, ...] = ("DecisionSupportOutput",)

# GRM commodity view. Values use the OWL/Turtle prefixed notation emitted by
# scripts/ontology/generate_grm_ttl.py; they are rendered with the ``saref:``
# prefix and the local ``:`` prefix respectively.
GRM_COMMODITY_TAXONOMY: dict[str, tuple[str, ...]] = {
    "GasCommodity": (
        "saref:EnergyCommodity",
        "saref:NaturalResourceCommodity",
    ),
    "LngCommodity": (":GasCommodity",),
    "GasMarketServiceCommodity": ("saref:Commodity",),
    "StorageServiceCommodity": (":GasMarketServiceCommodity",),
    "CapacityCommodity": (":GasMarketServiceCommodity",),
    "BalanceServiceCommodity": (":GasMarketServiceCommodity",),
}

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


class StrategyLifecycleStatus(StrEnum):
    """Lifecycle status of a long-lived strategy research identity."""

    RESEARCH = "RESEARCH"
    RETIRED = "RETIRED"


class StrategyVersionStatus(StrEnum):
    """Mutability status of one semantic strategy version."""

    DRAFT = "DRAFT"
    FROZEN = "FROZEN"
    RETIRED = "RETIRED"


class StrategyRunType(StrEnum):
    """Executable kind of a strategy run."""

    EVALUATION = "EVALUATION"
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    SCENARIO = "SCENARIO"


class StrategyRunStatus(StrEnum):
    """Execution status of a strategy run."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StrategyEvidenceTargetRole(StrEnum):
    """What one declared strategy price leg is evidence *of*.

    The role is declared, never inferred from a series name: a deliverable
    quote and a published assessment are different evidence even when they
    carry the same product label.
    """

    DELIVERY_PRICE = "DELIVERY_PRICE"
    REFERENCE_LEVEL = "REFERENCE_LEVEL"


class StrategyEvidenceTargetBasis(StrEnum):
    """How one declared evidence target resolves to a delivery interval.

    ``EXPLICIT_INTERVAL`` states the interval's UTC endpoints directly.

    ``GAS_DAY`` rolls the target relative to the decision gas day using an
    explicit canonical calendar and an explicit offset: ``0`` is the gas day
    containing the decision time, ``1`` the following gas day. The interval is
    resolved through the canonical gas-day calendar, never by adding 24 hours,
    so DST 23/25-hour days are correct. Month/quarter tenor rolls need their own
    convention validation and are added by a later slice; they are refused
    rather than guessed.
    """

    EXPLICIT_INTERVAL = "EXPLICIT_INTERVAL"
    GAS_DAY = "GAS_DAY"


class ParameterType(StrEnum):
    """Primitive type of a strategy parameter."""

    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    DURATION = "DURATION"
    PERCENTAGE = "PERCENTAGE"


class TemporalIntegrityStatus(StrEnum):
    """Historical availability classification for one evidence row."""

    VERIFIED = "VERIFIED"
    APPROXIMATE = "APPROXIMATE"
    INSUFFICIENT = "INSUFFICIENT"


class BacktestOutcomeStatus(StrEnum):
    """Research outcome of one backtest decision event."""

    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class BacktestIssueSeverity(StrEnum):
    """Severity of one data-quality/economic issue."""

    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class MissingDataPolicy(StrEnum):
    """Policy for absent required price series at a decision time."""

    FAIL = "FAIL"
    SKIP_DECISION = "SKIP_DECISION"
    CARRY_FORWARD_WITH_MAX_AGE = "CARRY_FORWARD_WITH_MAX_AGE"
    USE_APPROVED_FALLBACK_SOURCE = "USE_APPROVED_FALLBACK_SOURCE"


class FillPricePolicy(StrEnum):
    """Historical price selection policy."""

    MID = "MID"
    BID = "BID"
    ASK = "ASK"
    LAST = "LAST"
    ASSESSMENT = "ASSESSMENT"
    NEXT_ELIGIBLE = "NEXT_ELIGIBLE"


class CostTreatment(StrEnum):
    """How one backtest cost component is treated."""

    KNOWN_COST = "KNOWN_COST"
    MODELED_COST = "MODELED_COST"
    EXCLUDED = "EXCLUDED"
    UNAVAILABLE = "UNAVAILABLE"
    RESOURCE_DEFINED = "RESOURCE_DEFINED"


class DecisionClockBasis(StrEnum):
    """Decision-clock scheduling basis."""

    GAS_DAY = "GAS_DAY"
    FIXED_UTC = "FIXED_UTC"


class ExperimentType(StrEnum):
    """Research experiment grouping type."""

    SINGLE_RUN = "SINGLE_RUN"
    PARAMETER_COMPARISON = "PARAMETER_COMPARISON"
    WALK_FORWARD = "WALK_FORWARD"


class ShadowMonitorState(StrEnum):
    """Lifecycle state of a scheduled shadow research monitor."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    RETIRED = "RETIRED"


class ShadowScheduleType(StrEnum):
    """Supported typed shadow evaluation schedule."""

    INTERVAL = "INTERVAL"
    DAILY_AT = "DAILY_AT"


class ShadowMissedPolicy(StrEnum):
    """Policy for evaluations missed while offline."""

    SKIP = "SKIP"
    RUN_LATEST_ONLY = "RUN_LATEST_ONLY"
    CATCH_UP_LIMITED = "CATCH_UP_LIMITED"


class ShadowEvaluationState(StrEnum):
    """Execution/outcome state of one shadow evaluation."""

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ShadowFreshness(StrEnum):
    """Freshness classification of one required evidence family."""

    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    RESTRICTED = "RESTRICTED"
    UNAVAILABLE = "UNAVAILABLE"


class ShadowAlertState(StrEnum):
    """Lifecycle state of a shadow alert."""

    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class ShadowAlertSeverity(StrEnum):
    """Compact shadow alert severity vocabulary."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ShadowDriftState(StrEnum):
    """Interpretable drift classification."""

    NORMAL = "NORMAL"
    WATCH = "WATCH"
    MATERIAL = "MATERIAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ShadowOutcomeState(StrEnum):
    """Maturation state of one shadow candidate outcome."""

    OPEN = "OPEN"
    MATURED = "MATURED"
    UNRESOLVED = "UNRESOLVED"
    INVALIDATED = "INVALIDATED"


class ShadowPnlBasis(StrEnum):
    """Basis of one shadow indicative PnL outcome."""

    MARK_TO_MODEL = "MARK_TO_MODEL"
    REALIZED_SHADOW_INDICATIVE = "REALIZED_SHADOW_INDICATIVE"
    UNRESOLVED = "UNRESOLVED"


class ShadowFailureClass(StrEnum):
    """Failure classification for retry policy."""

    DATA_BLOCKER = "DATA_BLOCKER"
    DOMAIN_BLOCKER = "DOMAIN_BLOCKER"
    TRANSIENT_INFRASTRUCTURE = "TRANSIENT_INFRASTRUCTURE"
    PERMANENT_CONFIGURATION = "PERMANENT_CONFIGURATION"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ShadowRiskState(StrEnum):
    """State of one persisted shadow risk check."""

    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


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
    AGENT_REVIEW_PACK = "agent_review_pack"


class DecisionCaseStatus(StrEnum):
    """Lifecycle of an Architecture V2 Decision Case.

    A case collects objective, context, assumptions, alternatives, evidence and
    human review, and ends in a Decision Record. The record is evidence and
    rationale, never approval to execute anything.
    """

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    DECIDED = "DECIDED"
    REOPENED = "REOPENED"
    RETIRED = "RETIRED"


class DecisionEvidenceKind(StrEnum):
    """Product artefacts a Decision Case may cite as evidence."""

    MARKET_CONTEXT = "MARKET_CONTEXT"
    PORTFOLIO_SNAPSHOT = "PORTFOLIO_SNAPSHOT"
    SCENARIO = "SCENARIO"
    OPTIMIZATION = "OPTIMIZATION"
    ROUTE_RECOMMENDATION = "ROUTE_RECOMMENDATION"
    BACKTEST = "BACKTEST"
    STRATEGY_RUN = "STRATEGY_RUN"
    RESEARCH_DATASET = "RESEARCH_DATASET"
    AGENT_RUN = "AGENT_RUN"
    REVIEW_CONTEXT = "REVIEW_CONTEXT"
    #: A governed AI *interpretation* - the Copilot's Ask, Explain, Compare, Challenge or
    #: Draft run. The Decision Case chain names an "AI Findings/Challenge" stage, so citing
    #: one is part of the record; it stays interpretation, never a numeric authority, and the
    #: case still needs a human decision.
    AI_ANALYSIS = "AI_ANALYSIS"
    MANUAL = "MANUAL"


class DecisionAssumptionSource(StrEnum):
    """Where a Decision Case assumption came from, so a reader can weigh it."""

    BACKEND = "BACKEND"
    MARKET_DATA = "MARKET_DATA"
    CONTRACT = "CONTRACT"
    MANUAL = "MANUAL"
    AI_DRAFT = "AI_DRAFT"


def coerce_review_entity_type(value: str) -> ReviewEntityType:
    """Resolve one review artifact kind, failing closed on unknown values.

    将评审对象类型解析为受控词表值；未知类型一律拒绝，不做兜底映射。

    Args:
        value: Candidate review entity kind.

    Returns:
        The matching :class:`ReviewEntityType` member.

    Raises:
        ValueError: The value is not a known review artifact kind.
    """

    try:
        return ReviewEntityType(value)
    except ValueError as exc:
        known = ", ".join(sorted(item.value for item in ReviewEntityType))
        raise ValueError(
            f"unknown review entity type {value!r}; expected one of: {known}"
        ) from exc
