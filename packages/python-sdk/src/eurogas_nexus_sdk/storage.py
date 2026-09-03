"""SDK client for /api/storage."""

from pydantic import BaseModel

from eurogas_nexus_sdk import _http


class StorageSite(BaseModel):
    """A gas storage site with capacity characteristics.

    Attributes:
        site_id: Stable identifier of the site.
        name: Display name of the site.
        country: Two-letter country code of the site.
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        working_capacity_mcm: Working gas capacity in million cubic metres;
            None when not published for this site.
        status: Operational status (default ``operational``).
    """

    site_id: str
    name: str
    country: str
    lat: float
    lon: float
    # 部分站点不公开储气能力，缺失用 None 表达：把未知误当 0 会污染容量分析。
    working_capacity_mcm: float | None = None
    status: str = "operational"


class StorageObservation(BaseModel):
    """One storage level or flow observation.

    Attributes:
        observation_id: Unique identifier of the observation.
        site_id: Identifier of the storage site.
        site_name: Display name of the storage site.
        observation_type: Kind of observation (e.g. fill level, volume).
        fill_pct: Fill level as a percentage; None when not applicable.
        volume_mcm: Volume in million cubic metres; None when not applicable.
        period_start_utc: Start of the observation window (ISO-8601 UTC);
            empty string when the window is not provided.
        period_end_utc: End of the observation window (ISO-8601 UTC);
            empty string when the window is not provided.
    """

    observation_id: str
    site_id: str
    site_name: str
    observation_type: str
    # fill_pct 与 volume_mcm 按观测类型二选一（如盘点只有容积），
    # 缺失保留 None 而非 0，避免展示层把"缺失"误判为"零库存"。
    fill_pct: float | None = None
    volume_mcm: float | None = None
    # 观测可能没有明确时段（如月末盘点），空串表示"未提供"而非时间零点。
    period_start_utc: str = ""
    period_end_utc: str = ""


def _get(url: str) -> dict:
    """GET a JSON envelope and return the parsed payload."""

    r = _http.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_storage_sites(base_url: str) -> list[StorageSite]:
    """Return all storage sites.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All storage sites currently exposed by the backend.
    """
    return [StorageSite(**s) for s in _get(f"{base_url}/api/storage/sites")["data"]]

def fetch_storage_observations(base_url: str) -> list[StorageObservation]:
    """Return all storage observations.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All storage observations currently exposed by the backend.
    """
    url = f"{base_url}/api/storage/observations"
    return [StorageObservation(**o) for o in _get(url)["data"]]
