"""SDK API client for health endpoint."""

from pydantic import BaseModel

from eurogas_nexus.sdk import _http


class HealthPayload(BaseModel):
    """Health payload describing one backend service instance.

    Attributes:
        status: Health verdict (e.g. ``ok``).
        service: Name of the reported service.
        version: Backend version string.
        profile: Deployment profile (e.g. dev, trial, release).
    """

    status: str
    service: str
    version: str
    profile: str


def fetch_health(base_url: str, timeout_seconds: float = 5.0) -> HealthPayload:
    """Fetch health payload from backend API."""

    # 健康检查必须短超时：长阻塞会拖垮客户端启动探测与定期轮询。
    response = _http.get(f"{base_url.rstrip('/')}/api/health", timeout=timeout_seconds)
    response.raise_for_status()
    # model_validate 而非 **payload：后端未来新增字段会被自动忽略，
    # 保证客户端与后端向前兼容。
    return HealthPayload.model_validate(response.json())
