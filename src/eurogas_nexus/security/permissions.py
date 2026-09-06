"""Declarative public-route permission registry (Gate 1 foundation).

Every public path must resolve to a declared permission — the registry test
fails CI on any path without a declaration, so "which route needs what" is a
machine-checkable contract. Enforcement today: the release profile verifies the public API token,
resolves an optional PostgreSQL identity key, and enforces the role floor
declared for each permission category. OPERATOR routes additionally require
the legacy principal header for non-identity-key callers.
"""

from __future__ import annotations

import re
from enum import StrEnum


class Permission(StrEnum):
    """Permission category of a public route."""

    PUBLIC = "public"  # no sensitive data (health); token still applies in release
    READ = "read"  # read-only governed data
    WRITE = "write"  # creates/modifies records
    GOVERNED = "governed"  # policy evaluation (entitlement/export/LLM) applies
    REVIEW = "review"  # reviewer-gated human review recording
    OPERATOR = "operator"  # explicit operator identity required (planned)
    ADMIN = "admin"  # identity/access administration requires ADMIN


class EnforcementStatus(StrEnum):
    """How a permission is enforced today."""

    API_TOKEN = "api_token"  # enforced now (release profile token + policy gates)
    PRINCIPAL_REQUIRED = "principal_required"  # declared; enforcement in next milestone


# (path pattern, permission). Longest matching pattern wins, so exact routes
# listed here override their prefix families regardless of order.
ROUTE_PERMISSIONS: tuple[tuple[str, Permission], ...] = (
    # --- health / bootstrap ---
    ("/api/health", Permission.PUBLIC),
    ("/api/health/live", Permission.PUBLIC),
    ("/api/health/ready", Permission.PUBLIC),
    ("/api/dev/health", Permission.PUBLIC),
    ("/api/auth/status", Permission.PUBLIC),
    ("/api/auth/oidc/login", Permission.PUBLIC),
    ("/api/auth/oidc/callback", Permission.PUBLIC),
    ("/api/auth/oidc/desktop/login", Permission.PUBLIC),
    ("/api/auth/oidc/desktop/token", Permission.PUBLIC),
    ("/api/auth/logout", Permission.READ),
    ("/api/me", Permission.READ),
    ("/api/access/users", Permission.ADMIN),
    ("/api/access/users/{principal_id}", Permission.ADMIN),
    ("/api/access/roles", Permission.ADMIN),
    ("/api/access/data-scopes", Permission.ADMIN),
    ("/api/access/api-keys", Permission.ADMIN),
    ("/api/access/api-keys/{key_id}/revoke", Permission.ADMIN),
    ("/api/audit", Permission.ADMIN),
    ("/api/access/sso", Permission.ADMIN),
    # --- credentials: reads are safe metadata; every write is operator-only ---
    ("/api/credentials/providers", Permission.READ),
    ("/api/credentials/{provider_id}", Permission.OPERATOR),
    ("/api/credentials/{provider_id}/connection-test", Permission.OPERATOR),
    ("/api/credentials/{provider_id}/local-validation", Permission.OPERATOR),
    ("/api/credentials/{provider_id}/rotate", Permission.OPERATOR),
    ("/api/credentials/{provider_id}/status", Permission.OPERATOR),
    # --- analysis / reports: policy-gated (entitlement, export, LLM) ---
    ("/api/analysis/query", Permission.GOVERNED),
    ("/api/reports/portfolio", Permission.GOVERNED),
    ("/api/analysis/ontology", Permission.READ),
    ("/api/review/decisions", Permission.REVIEW),
    ("/api/ingestion-runs", Permission.READ),
    # --- read families ---
    ("/api/contracts/", Permission.READ),
    ("/api/cost-observations/", Permission.READ),
    ("/api/glossary", Permission.READ),
    ("/api/glossary/{term}", Permission.READ),
    ("/api/glossary/{term}/context", Permission.READ),
    ("/api/lng/", Permission.READ),
    ("/api/market/", Permission.READ),
    ("/api/monitoring/", Permission.READ),
    ("/api/physical/", Permission.READ),
    ("/api/portfolio/", Permission.READ),
    ("/api/reference-network/", Permission.READ),
    ("/api/runtime/", Permission.READ),
    ("/api/runtime/dependencies", Permission.READ),
    ("/api/runtime/metrics", Permission.READ),
    ("/api/runtime/source-operations", Permission.READ),
    ("/api/sources", Permission.READ),
    ("/api/sources/{source_id}", Permission.READ),
    ("/api/sources/{source_id}/health", Permission.READ),
    ("/api/sources/{source_id}/runs", Permission.READ),
    ("/api/sources/{source_id}/run", Permission.OPERATOR),
    ("/api/sources/{source_id}/backfill", Permission.OPERATOR),
    ("/api/sources/{source_id}/retry", Permission.OPERATOR),
    ("/api/sources/{source_id}/enabled", Permission.OPERATOR),
    ("/api/source-certifications", Permission.READ),
    ("/api/source-certifications/{source_id}/certify", Permission.OPERATOR),
    ("/api/storage/", Permission.READ),
    ("/api/stream/", Permission.READ),
    ("/api/weather/", Permission.READ),
    ("/api/strategy-lab/runs", Permission.READ),
    ("/api/strategy-lab/runs/{run_id}", Permission.READ),
    ("/api/strategy-lab/summary", Permission.READ),
    ("/api/strategy-runs/{run_id}", Permission.READ),
    ("/api/strategy-runs/{run_id}/events", Permission.READ),
    ("/api/strategy-runs/{run_id}/series", Permission.READ),
    ("/api/strategy-runs/{run_id}/attribution", Permission.READ),
    ("/api/strategy-runs", Permission.GOVERNED),
    ("/api/backtest-experiments/{experiment_id}", Permission.READ),
    ("/api/backtest-experiments", Permission.GOVERNED),
    ("/api/shadow-monitors/{monitor_id}", Permission.READ),
    ("/api/shadow-monitors/{monitor_id}/evaluations", Permission.READ),
    ("/api/shadow-monitors/{monitor_id}/drift", Permission.READ),
    ("/api/shadow-monitors/{monitor_id}/pause", Permission.GOVERNED),
    ("/api/shadow-monitors/{monitor_id}/resume", Permission.GOVERNED),
    ("/api/shadow-monitors/{monitor_id}/retire", Permission.GOVERNED),
    ("/api/shadow-monitors", Permission.GOVERNED),
    ("/api/shadow-evaluations/{evaluation_id}", Permission.READ),
    ("/api/shadow-alerts/{alert_id}/acknowledge", Permission.GOVERNED),
    ("/api/shadow-alerts", Permission.READ),
    ("/api/shadow-runtime/status", Permission.READ),
    ("/api/strategies/{strategy_id}", Permission.READ),
    ("/api/strategies/{strategy_id}/metadata", Permission.GOVERNED),
    ("/api/strategies/{strategy_id}/versions", Permission.GOVERNED),
    ("/api/strategies", Permission.GOVERNED),
    ("/api/strategy-versions/{version_id}", Permission.READ),
    ("/api/strategy-versions/{version_id}/draft", Permission.GOVERNED),
    ("/api/strategy-versions/{version_id}/freeze", Permission.GOVERNED),
    ("/api/strategy-versions/{version_id}/fork", Permission.GOVERNED),
    ("/api/optimization/runs/{run_id}", Permission.READ),
    ("/api/route-cost/tso-tariffs", Permission.READ),
    ("/api/route-cost/route-candidates", Permission.READ),
    # GET lists + POST upserts contracts: policy-gated write surface.
    ("/api/route-cost/upstream-contracts", Permission.GOVERNED),
    ("/api/route-cost/resource-pool/options", Permission.READ),
    # --- research-data catalog is read-only; build/export are governed ---
    ("/api/research/capabilities", Permission.READ),
    ("/api/research/features", Permission.READ),
    ("/api/research/features/{feature_id}", Permission.READ),
    ("/api/research/targets", Permission.READ),
    ("/api/research/targets/{target_id}", Permission.READ),
    ("/api/research/datasets", Permission.READ),
    ("/api/research/datasets/{dataset_snapshot_id}", Permission.READ),
    ("/api/research/datasets/{dataset_snapshot_id}/quality", Permission.READ),
    ("/api/research/datasets/validate", Permission.GOVERNED),
    ("/api/research/datasets/{dataset_snapshot_id}/export", Permission.GOVERNED),
    # --- compute / persistence families: policy-gated decision support ---
    ("/api/optimization/", Permission.GOVERNED),
    ("/api/research/", Permission.GOVERNED),
    ("/api/route-cost/", Permission.GOVERNED),
    ("/api/strategy-lab/evaluate", Permission.GOVERNED),
)

PERMISSION_ENFORCEMENT: dict[Permission, EnforcementStatus] = {
    Permission.PUBLIC: EnforcementStatus.API_TOKEN,
    Permission.READ: EnforcementStatus.API_TOKEN,
    Permission.GOVERNED: EnforcementStatus.API_TOKEN,
    Permission.REVIEW: EnforcementStatus.API_TOKEN,
    Permission.OPERATOR: EnforcementStatus.PRINCIPAL_REQUIRED,
    Permission.ADMIN: EnforcementStatus.PRINCIPAL_REQUIRED,
}

# R32 role floor per permission category. The legacy public-token service
# principal has OPERATOR and remains compatible; DB-backed identities are
# checked against these floors by the route-permission dependency.
ROLE_REQUIREMENTS: dict[Permission, str] = {
    Permission.PUBLIC: "VIEWER",
    Permission.READ: "VIEWER",
    Permission.GOVERNED: "ANALYST",
    Permission.REVIEW: "REVIEWER",
    Permission.OPERATOR: "OPERATOR",
    Permission.ADMIN: "ADMIN",
}


def permission_for_path(path: str) -> Permission:
    """Resolve the permission for a public path.

    Matching ranks: literal routes (0) beat templated routes (1) beat prefix
    families (2); within a rank the longest pattern wins. So
    ``/api/credentials/providers`` stays READ even though
    ``/api/credentials/{provider_id}`` is OPERATOR, and
    ``/api/optimization/runs/{run_id}`` beats the ``/api/optimization/``
    family.
    """

    best: Permission | None = None
    best_key: tuple[int, int] | None = None
    for pattern, permission in ROUTE_PERMISSIONS:
        rank = _pattern_rank(pattern)
        if rank == 2:
            ok = path.startswith(pattern)
        else:
            ok = _pattern_regex(pattern).match(path) is not None
        if not ok:
            continue
        key = (rank, -len(pattern))
        if best_key is None or key < best_key:
            best_key = key
            best = permission
    if best is None:
        raise KeyError(f"No permission declared for public path {path!r}")
    return best


def _pattern_rank(pattern: str) -> int:
    """0 = literal route, 1 = templated route, 2 = prefix family."""

    if pattern.endswith("/"):
        return 2
    if "{" in pattern:
        return 1
    return 0


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}]+\})", pattern)
    expression = "".join("[^/]+" if part.startswith("{") else re.escape(part) for part in parts)
    return re.compile(f"^{expression}$")


def role_for_permission(permission: Permission) -> str:
    """Return the minimum role required by a permission category."""

    return ROLE_REQUIREMENTS[permission]


def enforcement_status(permission: Permission) -> EnforcementStatus:
    """Return the enforcement level declared for a permission.

    返回权限声明的强制级别（identity/audit/none），供依赖注入与
    安全测试按级别施加校验。

    Args:
        permission: The permission kind.

    Returns:
        The declared EnforcementStatus.
    """

    return PERMISSION_ENFORCEMENT[permission]
