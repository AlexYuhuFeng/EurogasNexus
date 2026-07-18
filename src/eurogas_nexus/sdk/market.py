"""SDK client for /api/market."""

from typing import Any

from pydantic import BaseModel, Field

from eurogas_nexus.sdk._transport import SdkResult, api_url, get_envelope


class MarketObservation(BaseModel):
    observation_id: str
    market_venue: str
    product: str
    price: float
    unit: str
    currency: str
    period_start_utc: str
    period_end_utc: str
    observed_at_utc: str | None = None
    source_system: str | None = None
    source_reference: str | None = None
    source_record_id: str | None = None
    freshness: str | None = None
    quality_score: float | None = None
    research_only: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FxRate(BaseModel):
    pair: str
    base_currency: str | None = None
    quote_currency: str | None = None
    rate: float
    rate_type: str | None = None
    value_date: str | None = None
    observed_at_utc: str
    source_system: str | None = None
    source_reference: str | None = None
    freshness: str | None = None


class MarketQuote(BaseModel):
    quote_id: str
    source_system: str
    source_record_id: str | None = None
    venue: str
    instrument_id: str
    hub: str
    product: str
    delivery_start_utc: str
    delivery_end_utc: str
    bid_price: float | None = None
    ask_price: float | None = None
    last_price: float | None = None
    bid_quantity_mwh: float | None = None
    ask_quantity_mwh: float | None = None
    currency: str
    unit: str
    observed_at_utc: str
    received_at_utc: str
    source_reference: str
    freshness: str
    quality_score: float
    simulated: bool
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class IntradayOpportunity(BaseModel):
    opportunity_id: str
    scan_id: str
    opportunity_type: str
    status: str
    buy_quote_id: str
    sell_quote_id: str
    route_id: str
    route_name: str
    buy_venue: str
    sell_venue: str
    buy_hub: str
    sell_hub: str
    product: str
    delivery_start_utc: str
    delivery_end_utc: str
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
    detected_at_utc: str
    valid_until_utc: str
    simulated: bool
    human_review_required: bool


class MarketSpread(BaseModel):
    spread_id: str
    name: str
    from_venue: str
    to_venue: str
    spread_eur_mwh: float
    period: str


def fetch_market_observations(base_url: str) -> list[MarketObservation]:
    return fetch_market_observations_result(base_url).data


def fetch_market_observations_result(base_url: str) -> SdkResult[list[MarketObservation]]:
    data, meta = get_envelope(api_url(base_url, "market/observations"))
    return SdkResult([MarketObservation.model_validate(row) for row in data], meta)


def fetch_fx_rates(base_url: str) -> list[FxRate]:
    return fetch_fx_rates_result(base_url).data


def fetch_fx_rates_result(base_url: str) -> SdkResult[list[FxRate]]:
    data, meta = get_envelope(api_url(base_url, "market/fx"))
    return SdkResult([FxRate.model_validate(row) for row in data], meta)


def fetch_market_quotes(base_url: str) -> list[MarketQuote]:
    return fetch_market_quotes_result(base_url).data


def fetch_market_quotes_result(base_url: str) -> SdkResult[list[MarketQuote]]:
    data, meta = get_envelope(api_url(base_url, "market/quotes"))
    return SdkResult([MarketQuote.model_validate(row) for row in data], meta)


def fetch_intraday_opportunities(base_url: str) -> list[IntradayOpportunity]:
    return fetch_intraday_opportunities_result(base_url).data


def fetch_intraday_opportunities_result(
    base_url: str,
) -> SdkResult[list[IntradayOpportunity]]:
    data, meta = get_envelope(api_url(base_url, "market/opportunities"))
    return SdkResult([IntradayOpportunity.model_validate(row) for row in data], meta)


def fetch_spreads(base_url: str) -> list[MarketSpread]:
    return fetch_spreads_result(base_url).data


def fetch_spreads_result(base_url: str) -> SdkResult[list[MarketSpread]]:
    data, meta = get_envelope(api_url(base_url, "market/spreads"))
    return SdkResult([MarketSpread.model_validate(row) for row in data], meta)
