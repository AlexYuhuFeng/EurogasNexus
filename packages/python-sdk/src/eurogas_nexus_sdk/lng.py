"""SDK client for /api/lng."""

from pydantic import BaseModel

from eurogas_nexus_sdk import _http


class LngTerminal(BaseModel):
    """An LNG regasification terminal.

    Attributes:
        terminal_id: Stable identifier of the terminal.
        name: Display name of the terminal.
        country: Two-letter country code of the terminal.
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        capacity_mcm_d: Regasification capacity in million cubic metres per day;
            None when not published.
        storage_capacity_mcm: LNG storage capacity in million cubic metres;
            None when not published.
        status: Operational status (default ``operational``).
    """

    terminal_id: str
    name: str
    country: str
    lat: float
    lon: float
    # 再气化/储罐容量并非所有终端都公开，缺失保留 None 而不是默认 0，
    # 供调用方区分"未披露"与"确实为零"。
    capacity_mcm_d: float | None = None
    storage_capacity_mcm: float | None = None
    status: str = "operational"


class LngObservation(BaseModel):
    """One LNG send-out or inventory observation.

    Attributes:
        observation_id: Unique identifier of the observation.
        terminal_id: Identifier of the terminal.
        terminal_name: Display name of the terminal.
        observation_type: Kind of observation (e.g. send-out, stock).
        value_mcm: Observed value in million cubic metres; None when absent.
        period_start_utc: Start of the observation window (ISO-8601 UTC).
        period_end_utc: End of the observation window (ISO-8601 UTC).
    """

    observation_id: str
    terminal_id: str
    terminal_name: str
    observation_type: str
    # value_mcm 的语义随 observation_type 变化（发送量或库存），
    # 缺失保留 None，避免把"缺测"误当"零流量"。
    value_mcm: float | None = None
    period_start_utc: str = ""
    period_end_utc: str = ""


def _get(url: str) -> dict:
    """GET a JSON envelope and return the parsed payload."""

    r = _http.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_lng_terminals(base_url: str) -> list[LngTerminal]:
    """Return all LNG regasification terminals.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All LNG terminals currently exposed by the backend.
    """
    return [LngTerminal(**t) for t in _get(f"{base_url}/api/lng/terminals")["data"]]

def fetch_lng_observations(base_url: str) -> list[LngObservation]:
    """Return all LNG send-out and inventory observations.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All LNG observations currently exposed by the backend.
    """
    return [LngObservation(**o) for o in _get(f"{base_url}/api/lng/observations")["data"]]
