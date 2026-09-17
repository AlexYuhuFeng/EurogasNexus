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
    # Development-only credential login; the route profile gates mounting, and
    # the credential store gating happens inside the handler.
    ("/api/dev/auth/login", Permission.PUBLIC),
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
    # --- unified data platform (Architecture V2 Wave 4) ---
    # The data product catalogue is a governed *declaration*: it names products,
    # their time basis, availability state and per-principal entitlement
    # posture, and returns values only through each product's own surface. It
    # stays outside the commercial boundary for the same reason the capability
    # catalogue does - a caller must be able to see that a product exists and
    # that its own entitlement is limited, which is the point of the surface.
    ("/api/data-products", Permission.READ),
    # Recording an Analysis Snapshot is analysed decision evidence (GOVERNED,
    # ANALYST floor). Reading a descriptor is lineage/provenance metadata with no
    # commercial values in it, so it keeps the READ floor - the same treatment as
    # /api/ingestion-runs - and every value the snapshot points at stays behind
    # its own commercial endpoint.
    ("/api/analysis-snapshots", Permission.READ),
    ("/api/analysis-snapshots/{snapshot_id}", Permission.READ),
    # --- Architecture V2 Decision Cases ---
    # Reading a case is decision evidence (READ floor: any authenticated caller who
    # may read review evidence may read the container). Opening a case and
    # attaching evidence are analysis work (GOVERNED, ANALYST floor). Recording or
    # reopening a decision is reviewer-gated (REVIEW), matching the existing
    # /api/review/decisions rule and the decision.review capability.
    ("/api/decision-cases", Permission.READ),
    ("/api/decision-cases/{case_id}", Permission.READ),
    ("/api/decision-cases/{case_id}/evidence", Permission.GOVERNED),
    ("/api/decision-cases/{case_id}/decisions", Permission.REVIEW),
    ("/api/decision-cases/{case_id}/reopen", Permission.REVIEW),
    # --- Architecture V2 application projections ---
    # Projections are read models over the same material as the endpoints they
    # compose, so their floors match: market, portfolio and review reads stay at
    # the READ floor, while scenario/economics content keeps the GOVERNED
    # (ANALYST) floor its underlying route already declares - a projection must
    # never widen what a principal can see. They also sit inside the commercial
    # boundary (COMMERCIAL_DATA_PREFIXES).
    ("/api/projections/market-context", Permission.READ),
    ("/api/projections/portfolio-snapshot", Permission.READ),
    ("/api/projections/review-context", Permission.READ),
    ("/api/projections/scenario-context", Permission.GOVERNED),
    # --- agent-native capability layer (CR-15) ---
    ("/api/capabilities", Permission.READ),
    ("/api/capabilities/search", Permission.READ),
    ("/api/capabilities/{capability_id}", Permission.READ),
    ("/api/capabilities/{capability_id}/invoke", Permission.GOVERNED),
    ("/api/agent/profiles", Permission.READ),
    ("/api/agent/plans/validate", Permission.GOVERNED),
    ("/api/agent/research", Permission.GOVERNED),
    ("/api/agent/runs", Permission.READ),
    ("/api/agent/runs/{agent_run_id}", Permission.READ),
    ("/api/agent/runs/{agent_run_id}/replay", Permission.READ),
    ("/api/agent/strategy-ir/validate", Permission.GOVERNED),
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

# A small number of paths expose both read and governed methods. Keep the
# legacy path registry intact for compatibility, and resolve these overrides
# only when the caller supplies an HTTP method.
METHOD_ROUTE_PERMISSIONS: tuple[tuple[str, str, Permission], ...] = (
    ("POST", "/api/research/datasets", Permission.GOVERNED),
    ("POST", "/api/analysis-snapshots", Permission.GOVERNED),
    ("POST", "/api/decision-cases", Permission.GOVERNED),
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

# Architecture V2 commercial-data boundary (06_IDENTITY_ACCESS_CONTROL_PLANE.md
# section 7): platform administration is not a commercial super-user. These path
# families serve prices, contract terms, positions, PnL, strategy parameters,
# decision evidence or licensed research datasets, so they require a commercial
# capability - which a platform-admin-only identity does not hold.
#
# Deliberately excluded (platform/context/system state a platform administrator
# needs): /api/health, /api/me, /api/auth, /api/dev, /api/access, /api/audit,
# /api/credentials, /api/sources, /api/source-certifications, /api/ingestion-runs,
# /api/runtime, /api/glossary, /api/reference-network, /api/physical,
# /api/storage, /api/lng, /api/weather, /api/capabilities (the registered
# capability *catalogue* is control-plane metadata; invoking a capability over
# commercial evidence stays commercial through /api/agent/ and the governed
# invoke path).
COMMERCIAL_DATA_PREFIXES: tuple[str, ...] = (
    "/api/market/",
    "/api/monitoring/",
    "/api/projections/",
    "/api/stream/",
    "/api/cost-observations/",
    "/api/portfolio/",
    "/api/contracts/",
    "/api/optimization/",
    "/api/route-cost/",
    "/api/analysis/",
    "/api/reports/",
    "/api/backtest-experiments/",
    "/api/strategies/",
    "/api/strategy-lab/",
    "/api/strategy-runs/",
    "/api/strategy-versions/",
    "/api/shadow-alerts/",
    "/api/shadow-monitors/",
    "/api/shadow-evaluations/",
    "/api/shadow-runtime/",
    "/api/review/",
    "/api/research/",
    "/api/agent/",
)


def serves_commercial_data(path: str) -> bool:
    """Whether a public path serves commercial data (V2 platform-admin boundary)."""

    return any(path.startswith(prefix) for prefix in COMMERCIAL_DATA_PREFIXES)



def permission_for_path(path: str, method: str | None = None) -> Permission:
    """Resolve the permission for a public path.

    Matching ranks: literal routes (0) beat templated routes (1) beat prefix
    families (2); within a rank the longest pattern wins. So
    ``/api/credentials/providers`` stays READ even though
    ``/api/credentials/{provider_id}`` is OPERATOR, and
    ``/api/optimization/runs/{run_id}`` beats the ``/api/optimization/``
    family.
    """

    normalized_method = (method or "").upper()
    best: Permission | None = None
    best_key: tuple[int, int] | None = None
    routes = (
        (pattern, permission)
        for route_method, pattern, permission in METHOD_ROUTE_PERMISSIONS
        if route_method == normalized_method
    )
    for pattern, permission in (*routes, *ROUTE_PERMISSIONS):
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
