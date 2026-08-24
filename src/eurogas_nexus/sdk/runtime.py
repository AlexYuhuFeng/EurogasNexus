"""SDK client for /api/runtime status routes."""

from pydantic import BaseModel

from eurogas_nexus.sdk import _http


class RuntimeConnectivity(BaseModel):
    """Connectivity result of one database check.

    Attributes:
        ok: True when the check succeeded.
        error: Failure detail; None when the check succeeded.
    """

    ok: bool
    # error 只在失败时填充：调用方直接用 ok 判断即可，无需解析异常文本。
    error: str | None = None


class RuntimeDbStatus(BaseModel):
    """Overall runtime database health for one server.

    Attributes:
        database_url_present: Whether a database URL is configured.
        redacted_database_url: Redacted URL for display; None when not configured.
        connectivity: Latest connectivity check result.
        alembic_revision: Current schema migration revision; None when unknown.
        required_tables: Tables the runtime expects to exist.
        missing_tables: Required tables that are absent.
        warnings: Non-fatal runtime warnings.
    """

    database_url_present: bool
    # 只回传脱敏 URL：避免把连接串里的口令泄露给客户端；未配置时为 None。
    redacted_database_url: str | None = None
    connectivity: RuntimeConnectivity
    alembic_revision: str | None = None
    required_tables: list[str]
    missing_tables: list[str]
    warnings: list[str]


def fetch_runtime_db_status(base_url: str) -> RuntimeDbStatus:
    """Return the runtime database status of the backend.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        The runtime database status payload.
    """
    # 状态端点返回单个对象（无列表包裹），直接取 data 反序列化。
    response = _http.get(f"{base_url}/api/runtime/db", timeout=10)
    response.raise_for_status()
    return RuntimeDbStatus(**response.json()["data"])
