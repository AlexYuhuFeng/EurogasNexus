"""Public API token FastAPI dependency (release profile).

Release 模式下所有公开路由的认证闸门：令牌未配置的部署必须 fail-closed
（503），绝不允许无认证提供服务。
"""

from fastapi import HTTPException, Request

from eurogas_nexus.security.public_api import (
    API_KEY_HEADER,
    PublicApiAuthError,
    verify_public_api_token,
)


async def require_public_api_auth(request: Request) -> None:
    """Enforce the public API token on every request in the release profile.

    校验公开 API 令牌的依赖注入函数（release 模式全量启用）。

    Accepts ``Authorization: Bearer <token>``, ``X-Eurogas-Api-Key: <token>``,
    or ``?api_key=<token>``. The query-parameter channel exists only for SSE
    (``EventSource`` cannot set headers); deployments should avoid logging
    query strings on the streaming paths. A missing token returns 401, an
    invalid one 403, and an unconfigured deployment fails closed with 503
    rather than serving unauthenticated.

    Args:
        request: The incoming FastAPI request carrying credentials.

    Returns:
        None when the token verifies.

    Raises:
        HTTPException: 401 when no token is present, 403 when the token is
            invalid, and 503 when the deployment has no configured token.
    """

    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    # 优先 Bearer，其次专用头；两者皆无再退回查询参数（仅 SSE 通道需要）。
    token = value.strip() if scheme.lower() == "bearer" else request.headers.get(
        API_KEY_HEADER
    )
    if not token:
        token = request.query_params.get("api_key")
    try:
        verify_public_api_token(token)
    except PublicApiAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, "message": exc.message},
        ) from exc
