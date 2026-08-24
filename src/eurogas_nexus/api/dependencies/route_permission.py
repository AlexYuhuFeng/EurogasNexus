"""Route-permission enforcement dependency (release profile).

Enforces identity requirements declared in the permission registry
(``eurogas_nexus.security.permissions``): OPERATOR routes require an explicit,
valid ``X-Eurogas-Principal`` header. READ/GOVERNED/PUBLIC routes need only the
public API token (enforced by ``require_public_api_auth``).

本模块把"路由路径 → 所需身份"的映射与执行分离：映射在
``security.permissions`` 登记表声明，这里只负责按结果强制校验。
"""

from fastapi import HTTPException, Request

from eurogas_nexus.domain.identity.principal import (
    PrincipalValidationError,
    normalize_principal,
)
from eurogas_nexus.security.identity import legacy_public_token_principal, role_allows
from eurogas_nexus.security.permissions import (
    Permission,
    permission_for_path,
    role_for_permission,
)

PRINCIPAL_HEADER = "X-Eurogas-Principal"


async def require_route_permission(request: Request) -> None:
    """Enforce permission-based identity requirements on public routes.

    按权限登记表对当前路径执行身份要求的强制校验。

    Args:
        request: The incoming FastAPI request.

    Returns:
        None when the path needs no operator identity or the principal is
        valid.

    Raises:
        HTTPException: 500 ``permission_not_declared`` when the path is not
            registered in the permission table (a deployment bug, not a
            client error); 401 ``operator_principal_missing`` when an
            OPERATOR route has no principal header; 403
            ``operator_principal_invalid`` when the header value is invalid.
    """

    try:
        permission = permission_for_path(request.url.path)
    except KeyError as exc:
        # 路径未登记权限：服务端配置缺陷，必须以 500 显式暴露而非静默放行。
        raise HTTPException(
            status_code=500,
            detail={
                "error": "permission_not_declared",
                "message": f"No permission declared for path {request.url.path!r}.",
            },
        ) from exc

    identity = getattr(request.state, "identity", legacy_public_token_principal())
    required_role = role_for_permission(permission)
    if not role_allows(identity.role, required_role):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "identity_role_forbidden",
                "message": (
                    f"Route permission {permission.value!r} requires role "
                    f"{required_role!r}; authenticated identity has role "
                    f"{identity.role!r}."
                ),
            },
        )

    if permission is not Permission.OPERATOR:
        return

    if identity.auth_method == "identity_key":
        # The DB identity is the authenticated actor; no spoofable header is
        # accepted for identity-key callers.
        request.state.actor = identity.name
        return

    principal = request.headers.get(PRINCIPAL_HEADER)
    try:
        normalized = normalize_principal(principal)
    except PrincipalValidationError as exc:
        missing = not (principal or "").strip()
        # 缺失与非法区分状态码：401 表示"未提供身份"，403 表示"身份无效"。
        raise HTTPException(
            status_code=401 if missing else 403,
            detail={
                "error": (
                    "operator_principal_missing" if missing else "operator_principal_invalid"
                ),
                "message": (
                    "OPERATOR routes require a valid X-Eurogas-Principal header "
                    "identifying the acting operator."
                ),
                "reason": str(exc),
            },
        ) from exc
    request.state.actor = normalized
