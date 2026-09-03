"""SDK client for /api/market."""

from typing import Any

from pydantic import BaseModel, Field

from eurogas_nexus_sdk._transport import SdkResult, api_url, get_envelope


class MarketObservation(BaseModel):
    """One observed market price point published by a reporting venue.

    Attributes:
        observation_id: Unique identifier of the observation.
        market_venue: Venue or exchange that published the price.
        product: Product identifier (e.g., gas day or month-ahead).
        price: Observed price in ``currency`` per ``unit``.
        unit: Volume unit the price applies to (e.g., MWh).
        currency: ISO currency code of ``price``.
        period_start_utc: Delivery/valuation period start (ISO 8601).
        period_end_utc: Delivery/valuation period end (ISO 8601).
        observed_at_utc: Publication time of the price; None when unknown.
        source_system: Originating system name; None when unknown.
        source_reference: External reference for the source record.
        source_record_id: Identifier of the record in the source system.
        freshness: Source-certified freshness status; None when not assessed.
        quality_score: Data quality score in [0, 1]; None when not assessed.
        research_only: Whether the observation is restricted to research use.
        metadata_json: Free-form metadata carried from the source payload.
    """

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
    """One foreign-exchange rate observation used for price conversion.

    Attributes:
        pair: Currency pair identifier (e.g., ``GBP/EUR``).
        base_currency: ISO code of the base currency; None when implied by pair.
        quote_currency: ISO code of the quote currency; None when implied by pair.
        rate: Exchange rate of ``base_currency`` in ``quote_currency``.
        rate_type: Type of rate (e.g., spot, reference); None when unknown.
        value_date: Date the rate applies to; None when not applicable.
        observed_at_utc: Publication time of the rate (ISO 8601).
        source_system: Originating system name; None when unknown.
        source_reference: External reference for the source record.
        freshness: Source-certified freshness status; None when not assessed.
    """

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
    """One bid/ask quote captured from a trading venue.

    Attributes:
        quote_id: Unique identifier of the quote.
        source_system: Originating system name.
        source_record_id: Identifier of the record in the source system.
        venue: Venue that published the quote.
        instrument_id: Traded instrument identifier on the venue.
        hub: Delivery hub the quote refers to.
        product: Product identifier (e.g., day-ahead, month-ahead).
        delivery_start_utc: Delivery period start (ISO 8601).
        delivery_end_utc: Delivery period end (ISO 8601).
        bid_price: Best bid price; None when no bid exists.
        ask_price: Best ask price; None when no ask exists.
        last_price: Last traded price; None when not available.
        bid_quantity_mwh: Volume available at the bid; None when unknown.
        ask_quantity_mwh: Volume available at the ask; None when unknown.
        currency: ISO currency code of the prices.
        unit: Volume unit of the prices and quantities (e.g., MWh).
        observed_at_utc: Venue-side observation time (ISO 8601).
        received_at_utc: Time the quote was received by the platform (ISO 8601).
        source_reference: External reference for the source record.
        freshness: Source-certified freshness status.
        quality_score: Data quality score in [0, 1].
        simulated: Whether the quote is simulated rather than live.
        metadata_json: Free-form metadata carried from the source payload.
    """

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
    """One detected intraday arbitrage opportunity between two venues.

    Decision-support output: carries assumptions, missing inputs, and
    warnings alongside the economics so reviewers can judge the detection.

    Attributes:
        opportunity_id: Unique identifier of the opportunity.
        scan_id: Identifier of the scan run that detected it.
        opportunity_type: Type of opportunity (e.g., venue arbitrage).
        status: Lifecycle status of the opportunity.
        buy_quote_id: Quote id used for the buy side.
        sell_quote_id: Quote id used for the sell side.
        route_id: Identifier of the transport route between the venues.
        route_name: Human-readable name of the route.
        buy_venue: Venue of the buy side.
        sell_venue: Venue of the sell side.
        buy_hub: Delivery hub of the buy side.
        sell_hub: Delivery hub of the sell side.
        product: Product identifier traded on both sides.
        delivery_start_utc: Delivery period start (ISO 8601).
        delivery_end_utc: Delivery period end (ISO 8601).
        comparison_currency: Currency used for the spread comparison.
        comparison_unit: Volume unit used for the spread comparison.
        buy_ask: Ask price on the buy side.
        sell_bid: Bid price on the sell side.
        gross_spread: Raw spread before costs (sell_bid minus buy_ask).
        route_cost: Estimated transport cost per unit; None when unavailable.
        trading_cost: Estimated trading cost per unit.
        risk_buffer: Risk margin subtracted from the gross spread.
        net_margin: Net margin after all costs; None when not computed.
        max_quantity_mwh: Maximum executable volume; None when unknown.
        indicative_net_value: Indicative total value of the opportunity; None
            when not computable.
        quote_age_seconds: Age of the underlying quotes in seconds.
        confidence_score: Confidence of the detection in [0, 1].
        cost_components: Breakdown of the cost estimates.
        source_refs: References to the underlying source records.
        assumptions: Assumptions the detection relies on.
        missing_inputs: Inputs that were missing during detection.
        warnings: Non-blocking warnings about the opportunity.
        detected_at_utc: Detection time (ISO 8601).
        valid_until_utc: Time until which the opportunity is considered valid.
        simulated: Whether the opportunity comes from a simulation.
        human_review_required: Whether the opportunity needs human review.
    """

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
    """One derived price spread between two hubs.

    Attributes:
        spread_id: Unique identifier of the spread.
        name: Human-readable name of the spread.
        from_venue: Venue of the from side.
        to_venue: Venue of the to side.
        from_hub: Hub of the from side.
        to_hub: Hub of the to side.
        spread_eur_mwh: Spread value in EUR per MWh.
        period: Period the spread refers to (e.g., gas day).
    """

    spread_id: str
    name: str
    from_venue: str
    to_venue: str
    from_hub: str
    to_hub: str
    spread_eur_mwh: float
    period: str


class NormalizedMarketObservation(BaseModel):
    """A market observation normalized to a common hub/tenor schema.

    Attributes:
        observation_id: Unique identifier of the observation.
        market_venue: Venue or exchange that published the price.
        product: Product identifier in the original schema.
        price: Observed price in ``currency`` per ``unit``.
        unit: Volume unit of ``price``.
        currency: ISO currency code of ``price``.
        period_start_utc: Delivery/valuation period start (ISO 8601).
        period_end_utc: Delivery/valuation period end (ISO 8601).
        observed_at_utc: Publication time of the price; None when unknown.
        source_system: Originating system name; None when unknown.
        source_reference: External reference for the source record.
        source_record_id: Identifier of the record in the source system.
        freshness: Source-certified freshness status; None when not assessed.
        quality_score: Data quality score in [0, 1]; None when not assessed.
        research_only: Whether the observation is restricted to research use.
        metadata_json: Free-form metadata carried from the source payload.
        hub: Canonical hub the observation is mapped to.
        tenor: Canonical delivery tenor (e.g., day-ahead).
        is_gas_price: Whether the observation is a gas price rather than
            another product type.
        price_gbp_mwh: Price converted to GBP per MWh; None when conversion
            is not available.
    """

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
    hub: str
    tenor: str
    is_gas_price: bool
    price_gbp_mwh: float | None = None


def fetch_market_observations(base_url: str) -> list[MarketObservation]:
    """Fetch market observations, returning only the payload data.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        The observation list; response metadata (source references, warnings)
        is dropped.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    # 薄封装只取 .data：meta 里的来源引用与警告大多数调用方用不到，
    # 需要溯源/审计时改用 fetch_market_observations_result。
    return fetch_market_observations_result(base_url).data


def fetch_market_observations_result(base_url: str) -> SdkResult[list[MarketObservation]]:
    """Fetch market observations together with backend response metadata.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        An SdkResult whose data holds the observations and whose meta carries
        the backend envelope (source references, warnings, research-only and
        human-review flags).

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    data, meta = get_envelope(api_url(base_url, "market/observations"))
    # 同时保留 data 与 meta：meta 携带 source_references/warnings 等审计与
    # 人工复核所需信息；只要结果数据的调用方请使用不带 _result 的变体。
    return SdkResult([MarketObservation.model_validate(row) for row in data], meta)


def fetch_fx_rates(base_url: str) -> list[FxRate]:
    """Fetch foreign-exchange rates, returning only the payload data.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        The rate list; response metadata is dropped.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    return fetch_fx_rates_result(base_url).data


def fetch_fx_rates_result(base_url: str) -> SdkResult[list[FxRate]]:
    """Fetch foreign-exchange rates together with backend response metadata.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        An SdkResult whose data holds the rates and whose meta carries the
        backend envelope.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    data, meta = get_envelope(api_url(base_url, "market/fx"))
    return SdkResult([FxRate.model_validate(row) for row in data], meta)


def fetch_market_quotes(base_url: str) -> list[MarketQuote]:
    """Fetch market quotes, returning only the payload data.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        The quote list; response metadata is dropped.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    return fetch_market_quotes_result(base_url).data


def fetch_market_quotes_result(base_url: str) -> SdkResult[list[MarketQuote]]:
    """Fetch market quotes together with backend response metadata.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        An SdkResult whose data holds the quotes and whose meta carries the
        backend envelope.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    data, meta = get_envelope(api_url(base_url, "market/quotes"))
    return SdkResult([MarketQuote.model_validate(row) for row in data], meta)


def fetch_intraday_opportunities(base_url: str) -> list[IntradayOpportunity]:
    """Fetch intraday opportunities, returning only the payload data.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        The opportunity list; response metadata is dropped.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    return fetch_intraday_opportunities_result(base_url).data


def fetch_intraday_opportunities_result(
    base_url: str,
) -> SdkResult[list[IntradayOpportunity]]:
    """Fetch intraday opportunities together with backend response metadata.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        An SdkResult whose data holds the opportunities and whose meta carries
        the backend envelope.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    data, meta = get_envelope(api_url(base_url, "market/opportunities"))
    return SdkResult([IntradayOpportunity.model_validate(row) for row in data], meta)


def fetch_spreads(base_url: str) -> list[MarketSpread]:
    """Fetch market spreads, returning only the payload data.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        The spread list; response metadata is dropped.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    return fetch_spreads_result(base_url).data


def fetch_spreads_result(base_url: str) -> SdkResult[list[MarketSpread]]:
    """Fetch market spreads together with backend response metadata.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        An SdkResult whose data holds the spreads and whose meta carries the
        backend envelope.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    data, meta = get_envelope(api_url(base_url, "market/spreads"))
    return SdkResult([MarketSpread.model_validate(row) for row in data], meta)


def fetch_normalized_market_observations(
    base_url: str,
) -> list[NormalizedMarketObservation]:
    """Fetch normalized market observations, returning only the payload data.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        The normalized observation list; response metadata is dropped.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    return fetch_normalized_market_observations_result(base_url).data


def fetch_normalized_market_observations_result(
    base_url: str,
) -> SdkResult[list[NormalizedMarketObservation]]:
    """Fetch normalized observations together with backend response metadata.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        An SdkResult whose data holds the normalized observations and whose
        meta carries the backend envelope.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    data, meta = get_envelope(api_url(base_url, "market/normalized"))
    return SdkResult(
        [NormalizedMarketObservation.model_validate(row) for row in data], meta
    )
