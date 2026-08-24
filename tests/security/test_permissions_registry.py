"""Public-route permission registry tests (Gate 1 foundation)."""

from apps.api.main import app
from eurogas_nexus.security.permissions import (
    EnforcementStatus,
    Permission,
    enforcement_status,
    permission_for_path,
    role_for_permission,
)


def test_every_public_path_resolves_to_a_declared_permission() -> None:
    paths = set(app.openapi()["paths"])
    assert len(paths) >= 80
    for path in sorted(paths):
        permission = permission_for_path(path)
        assert isinstance(permission, Permission), f"{path} -> {permission!r}"


def test_credential_writes_are_operator_only() -> None:
    assert permission_for_path("/api/credentials/providers") is Permission.READ
    for path in (
        "/api/credentials/{provider_id}",
        "/api/credentials/{provider_id}/connection-test",
        "/api/credentials/{provider_id}/rotate",
    ):
        assert permission_for_path(path) is Permission.OPERATOR


def test_policy_gated_paths_are_governed() -> None:
    for path in (
        "/api/analysis/query",
        "/api/reports/portfolio",
        "/api/review/decisions",
        "/api/optimization/resource-pool",
        "/api/route-cost/recommend",
        "/api/strategy-lab/evaluate",
    ):
        assert permission_for_path(path) is Permission.GOVERNED


def test_longest_pattern_wins_for_nested_routes() -> None:
    assert permission_for_path("/api/optimization/runs/opt-abc") is Permission.READ
    assert permission_for_path("/api/optimization/contracts") is Permission.GOVERNED
    assert permission_for_path("/api/route-cost/tso-tariffs") is Permission.READ
    assert permission_for_path("/api/route-cost/calculate") is Permission.GOVERNED
    assert permission_for_path("/api/strategy-lab/runs") is Permission.READ
    assert permission_for_path("/api/strategy-lab/evaluate") is Permission.GOVERNED


def test_unknown_path_raises() -> None:
    try:
        permission_for_path("/api/not-registered")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_role_requirements_are_declared_per_permission() -> None:
    assert role_for_permission(Permission.PUBLIC) == "VIEWER"
    assert role_for_permission(Permission.READ) == "VIEWER"
    assert role_for_permission(Permission.GOVERNED) == "ANALYST"
    assert role_for_permission(Permission.OPERATOR) == "OPERATOR"


def test_operator_permission_documents_planned_enforcement() -> None:
    assert (
        enforcement_status(Permission.OPERATOR)
        is EnforcementStatus.PRINCIPAL_REQUIRED
    )
    assert enforcement_status(Permission.GOVERNED) is EnforcementStatus.API_TOKEN
    assert enforcement_status(Permission.READ) is EnforcementStatus.API_TOKEN
