"""SDK client for /api/v1/weather."""

import httpx
from pydantic import BaseModel


class WeatherStation(BaseModel):
    station_id: str
    name: str
    country: str
    lat: float
    lon: float


class WeatherObservation(BaseModel):
    observation_id: str
    station_id: str
    station_name: str
    temperature_c: float
    period_start_utc: str
    period_end_utc: str


class HddCddMetric(BaseModel):
    metric_id: str
    station_id: str
    station_name: str
    metric_type: str
    base_temperature_c: float
    value: float
    period_start_utc: str
    period_end_utc: str


def _get(url: str) -> dict:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_weather_stations(base_url: str) -> list[WeatherStation]:
    return [WeatherStation(**s) for s in _get(f"{base_url}/api/v1/weather/stations")["data"]]

def fetch_weather_observations(base_url: str) -> list[WeatherObservation]:
    url = f"{base_url}/api/v1/weather/observations"
    return [WeatherObservation(**o) for o in _get(url)["data"]]

def fetch_hdd_cdd(base_url: str) -> list[HddCddMetric]:
    return [HddCddMetric(**m) for m in _get(f"{base_url}/api/v1/weather/hdd-cdd")["data"]]
