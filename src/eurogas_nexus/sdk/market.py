"""SDK client for /api/market."""

import httpx
from pydantic import BaseModel


class MarketObservation(BaseModel):
    observation_id: str
    market_venue: str
    product: str
    price: float
    unit: str
    currency: str
    period_start_utc: str
    period_end_utc: str


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


def _get(url: str) -> dict:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_market_observations(base_url: str) -> list[MarketObservation]:
    return [MarketObservation(**o) for o in _get(f"{base_url}/api/market/observations")["data"]]

def fetch_fx_rates(base_url: str) -> list[FxRate]:
    return [FxRate(**f) for f in _get(f"{base_url}/api/market/fx")["data"]]

def fetch_spreads(base_url: str) -> list[MarketSpread]:
    return [MarketSpread(**s) for s in _get(f"{base_url}/api/market/spreads")["data"]]
