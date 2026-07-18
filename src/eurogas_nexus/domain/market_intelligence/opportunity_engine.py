"""Pure intraday spread evaluation using executable quote sides."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, Field


class AccessStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    DENIED = "DENIED"


class OpportunityStatus(StrEnum):
    ACTIONABLE_REVIEW = "ACTIONABLE_REVIEW"
    WATCH = "WATCH"
    BLOCKED = "BLOCKED"


class MarketQuote(BaseModel):
    quote_id: str
    source_system: str
    venue: str
    instrument_id: str
    hub: str
    product: str
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    bid_price: float | None = None
    ask_price: float | None = None
    last_price: float | None = None
    bid_quantity_mwh: float | None = None
    ask_quantity_mwh: float | None = None
    currency: str
    unit: str = "MWh"
    observed_at_utc: datetime
    received_at_utc: datetime
    source_reference: str
    freshness: str
    quality_score: float = Field(ge=0, le=1)
    simulated: bool = False
    metadata_json: dict = Field(default_factory=dict)


class FxRate(BaseModel):
    base_currency: str
    quote_currency: str
    rate: float = Field(gt=0)
    observed_at_utc: datetime
    source_reference: str


class RouteEconomics(BaseModel):
    route_id: str
    route_name: str
    from_hub: str
    to_hub: str
    total_cost: float | None = None
    currency: str = "EUR"
    unit: str = "MWh"
    available_capacity_mwh: float | None = None
    access_status: AccessStatus = AccessStatus.UNCONFIRMED
    required_tso_access: list[str] = Field(default_factory=list)
    cost_components: list[dict] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OpportunityScanPolicy(BaseModel):
    comparison_currency: str = "EUR"
    quote_max_age_seconds: float = Field(default=30.0, gt=0)
    quote_future_tolerance_seconds: float = Field(default=2.0, ge=0)
    trading_cost_per_mwh: float = Field(default=0.02, ge=0)
    risk_buffer_per_mwh: float = Field(default=0.03, ge=0)
    minimum_net_margin_per_mwh: float = Field(default=0.05, ge=0)
    validity_seconds: float = Field(default=15.0, gt=0)


class IntradayOpportunity(BaseModel):
    opportunity_id: str
    scan_id: str
    opportunity_type: str = "CROSS_HUB_TRANSPORT_SPREAD"
    status: OpportunityStatus
    buy_quote_id: str
    sell_quote_id: str
    route_id: str
    route_name: str
    buy_venue: str
    sell_venue: str
    buy_hub: str
    sell_hub: str
    product: str
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    comparison_currency: str
    comparison_unit: str
    buy_ask: float
    sell_bid: float
    gross_spread: float
    route_cost: float | None = None
    trading_cost: float
    risk_buffer: float
    net_margin: float | None = None
    max_quantity_mwh: float | None = None
    indicative_net_value: float | None = None
    quote_age_seconds: float
    confidence_score: float
    cost_components: list[dict] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    detected_at_utc: datetime
    valid_until_utc: datetime
    simulated: bool
    human_review_required: bool = True


def evaluate_route_opportunity(
    buy_quote: MarketQuote,
    sell_quote: MarketQuote,
    route: RouteEconomics,
    *,
    scan_id: str,
    detected_at_utc: datetime,
    fx_rates: list[FxRate] | None = None,
    policy: OpportunityScanPolicy | None = None,
) -> IntradayOpportunity | None:
    """Evaluate one route without creating any order or execution instruction."""

    policy = policy or OpportunityScanPolicy()
    detected_at = _as_utc(detected_at_utc)
    if not _quotes_match_route_and_delivery(buy_quote, sell_quote, route):
        return None
    if buy_quote.ask_price is None or sell_quote.bid_price is None:
        return None

    fx_rates = fx_rates or []
    missing_inputs = [*route.missing_inputs]
    warnings = [*route.warnings]
    assumptions = [
        "BUY_SIDE_USES_VISIBLE_ASK",
        "SELL_SIDE_USES_VISIBLE_BID",
        "NO_SIMULTANEOUS_FILL_GUARANTEE",
        "HUMAN_REVIEW_BEFORE_EXTERNAL_ACTION",
    ]

    buy_ask = _convert_price(
        buy_quote.ask_price,
        buy_quote.currency,
        policy.comparison_currency,
        fx_rates,
    )
    sell_bid = _convert_price(
        sell_quote.bid_price,
        sell_quote.currency,
        policy.comparison_currency,
        fx_rates,
    )
    if buy_ask is None:
        missing_inputs.append(f"FX_RATE_MISSING:{buy_quote.currency}:{policy.comparison_currency}")
    if sell_bid is None:
        missing_inputs.append(f"FX_RATE_MISSING:{sell_quote.currency}:{policy.comparison_currency}")
    if buy_ask is None or sell_bid is None:
        return None

    gross_spread = round(sell_bid - buy_ask, 4)
    if gross_spread <= 0:
        return None

    route_cost = None
    if route.total_cost is None:
        missing_inputs.append("ROUTE_COST_MISSING")
    else:
        route_cost = _convert_price(
            route.total_cost,
            route.currency,
            policy.comparison_currency,
            fx_rates,
        )
        if route_cost is None:
            missing_inputs.append(
                f"ROUTE_COST_FX_MISSING:{route.currency}:{policy.comparison_currency}"
            )

    if buy_quote.ask_quantity_mwh is None or buy_quote.ask_quantity_mwh <= 0:
        missing_inputs.append("BUY_VISIBLE_DEPTH_MISSING")
    if sell_quote.bid_quantity_mwh is None or sell_quote.bid_quantity_mwh <= 0:
        missing_inputs.append("SELL_VISIBLE_DEPTH_MISSING")
    if route.available_capacity_mwh is None or route.available_capacity_mwh <= 0:
        missing_inputs.append("ROUTE_AVAILABLE_CAPACITY_MISSING")
    if route.access_status == AccessStatus.DENIED:
        missing_inputs.append("TSO_ACCESS_DENIED")
    elif route.access_status == AccessStatus.UNCONFIRMED:
        missing_inputs.append("TSO_ACCESS_UNCONFIRMED")

    buy_age_raw = (detected_at - _as_utc(buy_quote.observed_at_utc)).total_seconds()
    sell_age_raw = (detected_at - _as_utc(sell_quote.observed_at_utc)).total_seconds()
    if min(buy_age_raw, sell_age_raw) < -policy.quote_future_tolerance_seconds:
        missing_inputs.append("QUOTE_EVENT_TIME_IN_FUTURE")
    buy_age = max(buy_age_raw, 0.0)
    sell_age = max(sell_age_raw, 0.0)
    quote_age = round(max(buy_age, sell_age), 3)
    if quote_age > policy.quote_max_age_seconds:
        missing_inputs.append("QUOTE_STALE")

    net_margin = None
    if route_cost is not None:
        net_margin = round(
            gross_spread
            - route_cost
            - policy.trading_cost_per_mwh
            - policy.risk_buffer_per_mwh,
            4,
        )

    max_quantity = _max_quantity(buy_quote, sell_quote, route)
    indicative_value = (
        round(net_margin * max_quantity, 2)
        if net_margin is not None and max_quantity is not None
        else None
    )

    status = OpportunityStatus.BLOCKED if missing_inputs else OpportunityStatus.WATCH
    if (
        not missing_inputs
        and net_margin is not None
        and net_margin >= policy.minimum_net_margin_per_mwh
    ):
        status = OpportunityStatus.ACTIONABLE_REVIEW
    elif net_margin is not None and net_margin < policy.minimum_net_margin_per_mwh:
        warnings.append("NET_MARGIN_BELOW_ALERT_THRESHOLD")

    confidence = min(buy_quote.quality_score, sell_quote.quality_score)
    if missing_inputs:
        confidence *= 0.5
    if buy_quote.simulated or sell_quote.simulated:
        warnings.append("SIMULATED_MARKET_DATA")
        confidence *= 0.85

    opportunity_key = sha256(
        f"{route.route_id}:{buy_quote.quote_id}:{sell_quote.quote_id}".encode()
    ).hexdigest()[:32]
    return IntradayOpportunity(
        opportunity_id=f"opp-{opportunity_key}",
        scan_id=scan_id,
        status=status,
        buy_quote_id=buy_quote.quote_id,
        sell_quote_id=sell_quote.quote_id,
        route_id=route.route_id,
        route_name=route.route_name,
        buy_venue=buy_quote.venue,
        sell_venue=sell_quote.venue,
        buy_hub=buy_quote.hub,
        sell_hub=sell_quote.hub,
        product=buy_quote.product,
        delivery_start_utc=buy_quote.delivery_start_utc,
        delivery_end_utc=buy_quote.delivery_end_utc,
        comparison_currency=policy.comparison_currency,
        comparison_unit=f"{policy.comparison_currency}/MWh",
        buy_ask=round(buy_ask, 4),
        sell_bid=round(sell_bid, 4),
        gross_spread=gross_spread,
        route_cost=round(route_cost, 4) if route_cost is not None else None,
        trading_cost=policy.trading_cost_per_mwh,
        risk_buffer=policy.risk_buffer_per_mwh,
        net_margin=net_margin,
        max_quantity_mwh=max_quantity,
        indicative_net_value=indicative_value,
        quote_age_seconds=quote_age,
        confidence_score=round(max(min(confidence, 1.0), 0.0), 4),
        cost_components=route.cost_components,
        source_refs=_unique(
            [
                buy_quote.source_reference,
                sell_quote.source_reference,
                *route.source_refs,
                *[rate.source_reference for rate in fx_rates],
            ]
        ),
        assumptions=assumptions,
        missing_inputs=_unique(missing_inputs),
        warnings=_unique(warnings),
        detected_at_utc=detected_at,
        valid_until_utc=detected_at + timedelta(seconds=policy.validity_seconds),
        simulated=buy_quote.simulated or sell_quote.simulated,
        human_review_required=True,
    )


def _quotes_match_route_and_delivery(
    buy_quote: MarketQuote,
    sell_quote: MarketQuote,
    route: RouteEconomics,
) -> bool:
    return (
        buy_quote.hub.strip().upper() == route.from_hub.strip().upper()
        and sell_quote.hub.strip().upper() == route.to_hub.strip().upper()
        and buy_quote.product.strip().lower() == sell_quote.product.strip().lower()
        and _as_utc(buy_quote.delivery_start_utc)
        == _as_utc(sell_quote.delivery_start_utc)
        and _as_utc(buy_quote.delivery_end_utc) == _as_utc(sell_quote.delivery_end_utc)
        and buy_quote.unit.strip().upper() == "MWH"
        and sell_quote.unit.strip().upper() == "MWH"
    )


def _convert_price(
    value: float,
    from_currency: str,
    to_currency: str,
    fx_rates: list[FxRate],
) -> float | None:
    source = from_currency.strip().upper()
    target = to_currency.strip().upper()
    if source == target:
        return value
    for rate in sorted(fx_rates, key=lambda item: item.observed_at_utc, reverse=True):
        base = rate.base_currency.strip().upper()
        quote = rate.quote_currency.strip().upper()
        if base == source and quote == target:
            return value * rate.rate
        if base == target and quote == source:
            return value / rate.rate
    return None


def _max_quantity(
    buy_quote: MarketQuote,
    sell_quote: MarketQuote,
    route: RouteEconomics,
) -> float | None:
    values = [
        buy_quote.ask_quantity_mwh,
        sell_quote.bid_quantity_mwh,
        route.available_capacity_mwh,
    ]
    if any(value is None or value <= 0 for value in values):
        return None
    return round(min(float(value) for value in values if value is not None), 4)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
