"""Public API token FastAPI dependency (release profile).

Release 模式下所有公开路由的认证闸门：令牌未配置的部署必须 fail-closed
（503），绝不允许无认证提供服务。
"""

from fastapi import HTTPException, Request

from eurogas_nexus.api.dependencies.exempt_paths import is_credential_exempt
from eurogas_nexus.security.public_api import (
    API_KEY_HEADER,
    PublicApiAuthError,
    verify_public_api_token,
)

# Deprecated alias: the exemption list has one home now (``exempt_paths``), because the identity
# dependency needs the same list and two copies would drift.
AUTH_EXEMPT_PREFIXES = ("/api/auth/",)


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

    if is_credential_exempt(request.url.path):
        return
    if request.cookies.get("eurogas_session"):
        # Interactive browser session is authenticated by require_identity.
        return

    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    # 优先 Bearer，其次专用头；两者皆无再退回查询参数（仅 SSE 通道需要）。
    token = value.strip() if scheme.lower() == "bearer" else request.headers.get(
        API_KEY_HEADER
    )
    if not token:
        token = request.query_params.get("api_key")
    if not token and _allow_anonymous(request):
        # Owner decision D1: a deployment that says it trusts its network is stating that a caller
        # presenting nothing is acceptable. The token gate has to honour that too - otherwise "no
        # credential" would still be refused here, and the deployment's own choice would never
        # reach the identity dependency that acts on it. A *presented* credential is still
        # verified: a wrong token stays a 403 rather than becoming anonymity.
        return
    try:
        verify_public_api_token(token)
    except PublicApiAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, "message": exc.message},
        ) from exc
    # The static deployment token is a verified credential: routes that ask
    # "was anything authenticated?" treat this as the legacy compatibility
    # case (SDK/CLI) rather than as an anonymous caller.
    request.state.public_api_token_verified = True


def _allow_anonymous(request: Request) -> bool:
    """Whether this deployment explicitly permits callers that present no credential."""

    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        from eurogas_nexus.core.config import get_settings

        settings = get_settings()
    return bool(getattr(settings, "allow_anonymous_callers", False))
