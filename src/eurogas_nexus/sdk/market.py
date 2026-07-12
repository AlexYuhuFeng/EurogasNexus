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


def fetch_spreads(base_url: str) -> list[MarketSpread]:
    return fetch_spreads_result(base_url).data


def fetch_spreads_result(base_url: str) -> SdkResult[list[MarketSpread]]:
    data, meta = get_envelope(api_url(base_url, "market/spreads"))
    return SdkResult([MarketSpread.model_validate(row) for row in data], meta)
