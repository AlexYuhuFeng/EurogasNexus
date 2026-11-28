"""Centralized fine-grained authorization for enterprise roles.

RBAC job-function roles expand into explicit permissions. Commercial data
entitlement remains separate (principal.data_scopes) and is never encoded in
a role string. Unknown roles/permissions fail closed.

Architecture V2 (``06_IDENTITY_ACCESS_CONTROL_PLANE.md`` section 7) separates
platform administration from commercial-data access: ``ADMIN`` is a
*platform administration bundle* (identity, API keys, audit, providers,
runtime, capability catalogue) and holds no commercial-data permission. An
administrator who also analyses holds a commercial role alongside ``ADMIN`` -
roles are overlapping functional assignments, not exclusive personas.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from eurogas_nexus.security.identity import (
    ROLE_RANK,
    AuthenticatedPrincipal,
    Role,
    role_value,
)


class Permission(StrEnum):
    """Fine-grained backend permission vocabulary (no execution verbs)."""

    ME_READ = "me.read"
    MARKET_READ = "market.read"
    PORTFOLIO_READ = "portfolio.read"
    PORTFOLIO_WRITE = "portfolio.write"
    #: Credit exposure, credit lines, trader mandates and their usage, hedge bands and firm
    #: marks: the risk function's and the front office's, not operations' or finance's unless
    #: granted explicitly (security review H1).
    RISK_LIMITS_READ = "risk.limits.read"
    GAS_DAY_RECORD = "gas_day.record"
    SCENARIO_CREATE = "scenario.create"
    OPTIMIZATION_RUN = "optimization.run"
    REVIEW_READ = "review.read"
    REVIEW_RECORD = "review.record"
    SOURCE_READ = "source.read"
    SOURCE_RUN = "source.run"
    SOURCE_BACKFILL = "source.backfill"
    SOURCE_CREDENTIALS_WRITE = "source.credentials.write"
    SOURCE_CERTIFICATION_MANAGE = "source.certification.manage"
    RUNTIME_READ = "runtime.read"
    IDENTITY_READ = "identity.read"
    IDENTITY_MANAGE = "identity.manage"
    API_KEYS_MANAGE = "api_keys.manage"
    AUDIT_READ = "audit.read"
    ANALYSIS_QUERY = "analysis.query"
    CAPABILITY_READ = "capability.read"
    CAPABILITY_INVOKE = "capability.invoke"
    AGENT_READ = "agent.read"
    AGENT_RESEARCH = "agent.research"


# Permissions that read or write commercial data: prices, positions, contract
# terms, PnL, decision evidence or licensed datasets.
# Distinct from platform administration on purpose - see the module docstring
# and ``eurogas_nexus.security.capabilities.COMMERCIAL_CAPABILITIES``.
COMMERCIAL_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.MARKET_READ,
        Permission.PORTFOLIO_READ,
        Permission.PORTFOLIO_WRITE,
        Permission.RISK_LIMITS_READ,
        Permission.GAS_DAY_RECORD,
        Permission.SCENARIO_CREATE,
        Permission.OPTIMIZATION_RUN,
        Permission.REVIEW_READ,
        Permission.REVIEW_RECORD,
        Permission.ANALYSIS_QUERY,
        Permission.CAPABILITY_INVOKE,
        # Agent runs carry commercial research evidence (plans, findings,
        # artefacts); the capability *catalogue* read stays platform metadata.
        Permission.AGENT_READ,
        Permission.AGENT_RESEARCH,
    }
)

# Permissions a platform administrator holds: operate the platform, its
# providers, its identities and its runtime - without commercial data.
PLATFORM_ADMINISTRATION_PERMISSIONS: frozenset[Permission] = frozenset(
    set(Permission) - COMMERCIAL_PERMISSIONS
)


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(
        {
            Permission.ME_READ,
            Permission.MARKET_READ,
            Permission.PORTFOLIO_READ,
            Permission.REVIEW_READ,
            Permission.SOURCE_READ,
            Permission.RUNTIME_READ,
            Permission.CAPABILITY_READ,
            Permission.AGENT_READ,
        }
    ),
    # Scheduling: a viewer's reads plus recording nomination and terminal-step status.
    Role.SCHEDULER: frozenset(
        {
            Permission.ME_READ,
            Permission.MARKET_READ,
            Permission.PORTFOLIO_READ,
            Permission.GAS_DAY_RECORD,
            Permission.REVIEW_READ,
            Permission.SOURCE_READ,
            Permission.RUNTIME_READ,
            Permission.CAPABILITY_READ,
            Permission.AGENT_READ,
        }
    ),
    Role.REVIEWER: frozenset(
        {
            Permission.ME_READ,
            Permission.MARKET_READ,
            Permission.PORTFOLIO_READ,
            Permission.RISK_LIMITS_READ,
            Permission.REVIEW_READ,
            Permission.REVIEW_RECORD,
            Permission.SOURCE_READ,
            Permission.RUNTIME_READ,
            Permission.CAPABILITY_READ,
            Permission.AGENT_READ,
        }
    ),
    Role.ANALYST: frozenset(
        {
            Permission.ME_READ,
            Permission.MARKET_READ,
            Permission.PORTFOLIO_READ,
            Permission.PORTFOLIO_WRITE,
            Permission.RISK_LIMITS_READ,
            Permission.GAS_DAY_RECORD,
            Permission.SCENARIO_CREATE,
            Permission.OPTIMIZATION_RUN,
            Permission.REVIEW_READ,
            Permission.SOURCE_READ,
            Permission.RUNTIME_READ,
            Permission.ANALYSIS_QUERY,
            Permission.CAPABILITY_READ,
            Permission.CAPABILITY_INVOKE,
            Permission.AGENT_READ,
            Permission.AGENT_RESEARCH,
        }
    ),
    # Source operations: no positions (security review H1). An operator who needs the book
    # is granted ``PERM:portfolio.read`` explicitly (see EXPLICITLY_GRANTABLE).
    Role.OPERATOR: frozenset(
        {
            Permission.ME_READ,
            Permission.MARKET_READ,
            Permission.REVIEW_READ,
            Permission.SOURCE_READ,
            Permission.SOURCE_RUN,
            Permission.SOURCE_BACKFILL,
            Permission.SOURCE_CREDENTIALS_WRITE,
            Permission.SOURCE_CERTIFICATION_MANAGE,
            Permission.RUNTIME_READ,
            Permission.CAPABILITY_READ,
            Permission.CAPABILITY_INVOKE,
            Permission.AGENT_READ,
            Permission.AGENT_RESEARCH,
        }
    ),
    # Platform administration: identity, access, audit, providers, runtime and
    # the capability catalogue. Commercial data is granted by a commercial role
    # assignment (see COMMERCIAL_PERMISSIONS and PLATFORM_ADMINISTRATION_PERMISSIONS).
    Role.ADMIN: PLATFORM_ADMINISTRATION_PERMISSIONS,
}


#: Data-scope prefix of an explicit permission grant (``PERM:risk.limits.read``).
EXPLICIT_GRANT_PREFIX = "PERM:"
#: Read permissions an administrator may grant one person beyond their roles, through a data
#: scope, so that operations or finance staff read positions or limits only when named.
#: A ``*`` scope never grants a permission.
EXPLICITLY_GRANTABLE: frozenset[Permission] = frozenset(
    {Permission.PORTFOLIO_READ, Permission.RISK_LIMITS_READ}
)


def explicit_grants(data_scopes: tuple[str, ...] | list[str]) -> frozenset[Permission]:
    """The permissions named by ``PERM:`` data scopes (only :data:`EXPLICITLY_GRANTABLE`)."""

    granted: set[Permission] = set()
    for raw in data_scopes or ():
        value = str(raw).strip()
        if not value.upper().startswith(EXPLICIT_GRANT_PREFIX):
            continue
        try:
            permission = Permission(value[len(EXPLICIT_GRANT_PREFIX) :].strip().lower())
        except ValueError:
            continue
        if permission in EXPLICITLY_GRANTABLE:
            granted.add(permission)
    return frozenset(granted)


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    """One explicit authorization decision."""

    allowed: bool
    permission: Permission | str
    principal_id: str
    role: str
    reason: str = ""


def effective_roles(principal: AuthenticatedPrincipal) -> tuple[Role, ...]:
    """Return normalized effective roles for a principal (highest first)."""

    roles: list[Role] = []
    for value in (*principal.roles, principal.role):
        try:
            roles.append(role_value(value))
        except Exception:
            continue
    unique = list(dict.fromkeys(roles))
    return tuple(sorted(unique, key=lambda role: ROLE_RANK[role], reverse=True))


def permissions_for_principal(principal: AuthenticatedPrincipal) -> frozenset[Permission]:
    """Expand a principal's effective roles into explicit permissions."""

    granted: set[Permission] = set()
    for role in effective_roles(principal):
        granted.update(ROLE_PERMISSIONS.get(role, frozenset()))
    granted.update(explicit_grants(principal.data_scopes))
    return frozenset(granted)


def authorize(
    principal: AuthenticatedPrincipal,
    permission: Permission | str,
) -> AuthorizationDecision:
    """Evaluate one fine-grained permission for a principal.

    Unknown roles/permissions fail closed. DISABLED/LOCKED principals are
    denied even if their role set would otherwise allow the action.
    """

    try:
        normalized = (
            permission if isinstance(permission, Permission) else Permission(str(permission))
        )
    except ValueError:
        return AuthorizationDecision(
            allowed=False,
            permission=str(permission),
            principal_id=principal.principal_id,
            role=principal.role,
            reason="unknown_permission",
        )
    if principal.status not in {"ACTIVE"}:
        return AuthorizationDecision(
            allowed=False,
            permission=normalized,
            principal_id=principal.principal_id,
            role=principal.role,
            reason="principal_not_active",
        )
    if principal.auth_method == "legacy_public_token":
        # Compatibility service principal remains OPERATOR for existing flows;
        # new ADMIN/identity permissions require an explicit identity key.
        if normalized in {
            Permission.IDENTITY_READ,
            Permission.IDENTITY_MANAGE,
            Permission.API_KEYS_MANAGE,
            Permission.AUDIT_READ,
        }:
            return AuthorizationDecision(
                allowed=False,
                permission=normalized,
                principal_id=principal.principal_id,
                role=principal.role,
                reason="legacy_token_denied_for_identity_administration",
            )
    if normalized in permissions_for_principal(principal):
        return AuthorizationDecision(
            allowed=True,
            permission=normalized,
            principal_id=principal.principal_id,
            role=principal.role,
            reason="role_permission_granted",
        )
    return AuthorizationDecision(
        allowed=False,
        permission=normalized,
        principal_id=principal.principal_id,
        role=principal.role,
        reason="permission_not_granted",
    )


def require_permission(principal: AuthenticatedPrincipal, permission: Permission | str) -> None:
    """Raise PermissionError when the principal is not authorized."""

    decision = authorize(principal, permission)
    if not decision.allowed:
        raise PermissionError(decision.reason)


def permission_role_floor(permission: Permission | str) -> Role:
    """Return the lowest role that grants a permission (used for docs/tests)."""

    normalized = permission if isinstance(permission, Permission) else Permission(str(permission))
    for role in sorted(ROLE_RANK, key=lambda item: ROLE_RANK[item]):
        if normalized in ROLE_PERMISSIONS[role]:
            return role
    return Role.ADMIN
