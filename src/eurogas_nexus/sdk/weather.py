"""SDK client for /api/weather."""

from pydantic import BaseModel

from eurogas_nexus.sdk import _http


class WeatherStation(BaseModel):
    """A weather station with fixed geo coordinates.

    Attributes:
        station_id: Stable identifier of the station.
        name: Display name of the station.
        country: Two-letter country code of the station.
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
    """

    station_id: str
    name: str
    country: str
    lat: float
    lon: float


class WeatherObservation(BaseModel):
    """One temperature observation reported by a station.

    Attributes:
        observation_id: Unique identifier of the observation.
        station_id: Identifier of the reporting station.
        station_name: Display name of the reporting station.
        temperature_c: Observed temperature in degrees Celsius.
        period_start_utc: Start of the observation window (ISO-8601 UTC).
        period_end_utc: End of the observation window (ISO-8601 UTC).
    """

    observation_id: str
    station_id: str
    station_name: str
    temperature_c: float
    # 时间按后端契约以 ISO-8601 字符串透传：客户端不做时区换算，
    # 避免同一时刻因本地时区不同产生歧义。
    period_start_utc: str
    period_end_utc: str


class HddCddMetric(BaseModel):
    """A heating/cooling degree-day metric for one station.

    Attributes:
        metric_id: Unique identifier of the metric.
        station_id: Identifier of the station.
        station_name: Display name of the station.
        metric_type: Metric kind (``hdd`` or ``cdd``).
        base_temperature_c: Base temperature the degree-day is computed against.
        value: Degree-day value for the period.
        period_start_utc: Start of the metric period (ISO-8601 UTC).
        period_end_utc: End of the metric period (ISO-8601 UTC).
    """

    metric_id: str
    station_id: str
    station_name: str
    metric_type: str
    # base_temperature_c 是度日基准温度（欧洲常用 18°C），不同市场口径不同，
    # 透传给展示层展示，不在 SDK 内做假设性换算。
    base_temperature_c: float
    value: float
    period_start_utc: str
    period_end_utc: str


def _get(url: str) -> dict:
    """GET a JSON envelope and return the parsed payload."""

    r = _http.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_weather_stations(base_url: str) -> list[WeatherStation]:
    """Return all weather stations.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All registered weather stations.
    """
    # 旧式客户端直接消费信封的 data 部分：{data, meta} 中的 meta 仅供审计，
    # 观测类轻量场景不建模，避免引入不必要的 SdkResult 包装。
    return [WeatherStation(**s) for s in _get(f"{base_url}/api/weather/stations")["data"]]

def fetch_weather_observations(base_url: str) -> list[WeatherObservation]:
    """Return all weather observations.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All weather observations currently exposed by the backend.
    """
    url = f"{base_url}/api/weather/observations"
    return [WeatherObservation(**o) for o in _get(url)["data"]]

def fetch_hdd_cdd(base_url: str) -> list[HddCddMetric]:
    """Return heating/cooling degree-day metrics.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All HDD/CDD metrics currently exposed by the backend.
    """
    return [HddCddMetric(**m) for m in _get(f"{base_url}/api/weather/hdd-cdd")["data"]]
