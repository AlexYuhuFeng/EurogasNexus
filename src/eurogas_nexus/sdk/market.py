"""SDK client for /api/v1/market."""

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
    rate: float
    observed_at_utc: str


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
    return [MarketObservation(**o) for o in _get(f"{base_url}/api/v1/market/observations")["data"]]

def fetch_fx_rates(base_url: str) -> list[FxRate]:
    return [FxRate(**f) for f in _get(f"{base_url}/api/v1/market/fx")["data"]]

def fetch_spreads(base_url: str) -> list[MarketSpread]:
    return [MarketSpread(**s) for s in _get(f"{base_url}/api/v1/market/spreads")["data"]]
