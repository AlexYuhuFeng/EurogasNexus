"""Architecture V2 capability and experience-profile contract tests.

These tests pin the two properties the identity/experience split depends on:

1. the capability catalogue is a *derived* view of the existing role/permission
   model, so it can never grant more than the role already grants;
2. the ExperienceProfile is composition only - functional assignments and work
   modes change how the product is composed, never what the caller may do.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.security.authorization import (
    ROLE_PERMISSIONS,
    permissions_for_principal,
)
from eurogas_nexus.security.capabilities import (
    CAPABILITY_PERMISSIONS,
    COMMERCIAL_CAPABILITIES,
    EXPERIENCE_PROFILE_GRANTS_AUTHORITY,
    PLATFORM_ADMINISTRATION_CAPABILITIES,
    SUPPORTED_SCOPE_KINDS,
    UNSUPPORTED_SCOPE_KINDS,
    WORK_MODE_CAPABILITIES,
    Capability,
    FunctionalAssignment,
    WorkMode,
    available_work_modes,
    build_experience_profile,
    capabilities_for_principal,
    capability_source_permissions,
    commercial_capabilities_for_principal,
    default_work_mode,
    functional_assignments_for,
    profile_stays_within_role_permissions,
)
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    Role,
    legacy_public_token_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _principal(
    role: str,
    *,
    roles: tuple[str, ...] | None = None,
    scopes: tuple[str, ...] = (),
    status: str = "ACTIVE",
    auth_method: str = "identity_key",
    name: str | None = None,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=f"principal-{role.lower()}",
        name=name or role.lower(),
        principal_type="USER",
        role=role,
        status=status,
        data_scopes=scopes,
        roles=roles if roles is not None else (role,),
        auth_method=auth_method,
    )


def test_every_capability_is_bound_to_real_permissions() -> None:
    """No capability may exist without role-reachable permissions behind it."""

    role_reachable = {permission for granted in ROLE_PERMISSIONS.values() for permission in granted}
    for capability, sources in CAPABILITY_PERMISSIONS.items():
        assert sources, capability
        for permission in sources:
            assert permission in role_reachable, (
                f"{capability} is bound to unreachable {permission}"
            )


def test_capability_catalogue_cannot_widen_any_role() -> None:
    """The derived capability set never exceeds the role's permission set."""

    for role in Role:
        principal = _principal(role.value)
        profile = build_experience_profile(principal)
        assert profile_stays_within_role_permissions(principal, profile) is True

        permissions = permissions_for_principal(principal)
        for capability in profile.effective_capabilities:
            assert capability_source_permissions(capability) & permissions, capability


def test_platform_administration_is_not_commercial_access() -> None:
    """ADMIN holds platform capabilities and no commercial capability of its own."""

    admin = _principal("ADMIN", roles=("ADMIN",))
    capabilities = capabilities_for_principal(admin)

    assert Capability.ACCESS_MANAGE in capabilities
    assert Capability.AUDIT_READ in capabilities
    assert Capability.PROVIDER_INGESTION_OPERATE in capabilities
    assert Capability.PROVIDER_CREDENTIAL_MANAGE in capabilities
    assert Capability.RUNTIME_READ in capabilities

    assert commercial_capabilities_for_principal(admin) == frozenset()
    assert capabilities & COMMERCIAL_CAPABILITIES == frozenset()
    # Platform administration is exactly the non-commercial capability set.
    assert set(capabilities) == PLATFORM_ADMINISTRATION_CAPABILITIES


def test_commercial_roles_keep_commercial_capabilities() -> None:
    """Every non-admin role keeps the commercial capabilities it has today."""

    expected = {
        "VIEWER": {Capability.MARKET_READ, Capability.PORTFOLIO_READ},
        "REVIEWER": {Capability.MARKET_READ, Capability.DECISION_REVIEW},
        "ANALYST": {
            Capability.MARKET_READ,
            Capability.PORTFOLIO_READ,
            Capability.OPTIMIZATION_RUN,
            Capability.STRATEGY_DESIGN,
        },
        "OPERATOR": {Capability.MARKET_READ, Capability.PROVIDER_INGESTION_OPERATE},
    }
    for role, required in expected.items():
        capabilities = capabilities_for_principal(_principal(role))
        assert required <= capabilities, role
        assert capabilities & COMMERCIAL_CAPABILITIES, role


def test_legacy_service_principal_keeps_its_commercial_reach() -> None:
    """The static deployment token remains the single-trust-domain operator."""

    capabilities = capabilities_for_principal(legacy_public_token_principal())

    assert Capability.MARKET_READ in capabilities
    assert Capability.PORTFOLIO_READ in capabilities
    assert Capability.PROVIDER_INGESTION_OPERATE in capabilities
    assert Capability.ACCESS_MANAGE not in capabilities


def test_overlapping_assignments_are_derived_not_exclusive() -> None:
    """An admin who also analyses holds both assignments."""

    combined = _principal("ADMIN", roles=("ADMIN", "ANALYST"))
    capabilities = capabilities_for_principal(combined)
    profile = build_experience_profile(combined)

    assert Capability.ACCESS_MANAGE in capabilities
    assert Capability.MARKET_READ in capabilities
    assert FunctionalAssignment.PLATFORM_ADMINISTRATOR in profile.functional_assignments
    assert FunctionalAssignment.TRADER in profile.functional_assignments
    assert profile_stays_within_role_permissions(combined, profile) is True


def test_work_modes_are_composition_only() -> None:
    """Work modes are a filtered view over capabilities, never a grant."""

    assert EXPERIENCE_PROFILE_GRANTS_AUTHORITY is False

    admin_profile = build_experience_profile(_principal("ADMIN", roles=("ADMIN",)))
    assert admin_profile.available_work_modes == (WorkMode.ADMINISTRATION,)
    assert admin_profile.default_work_mode is WorkMode.ADMINISTRATION

    analyst_profile = build_experience_profile(_principal("ANALYST"))
    assert analyst_profile.available_work_modes == (
        WorkMode.TRADING_ANALYSIS,
        WorkMode.PORTFOLIO_OVERSIGHT,
        WorkMode.RESEARCH,
    )
    assert analyst_profile.default_work_mode is WorkMode.TRADING_ANALYSIS

    # A mode is only ever offered when every capability it composes is held.
    for mode, required in WORK_MODE_CAPABILITIES.items():
        holder = _principal("ADMIN", roles=("ADMIN", "ANALYST", "REVIEWER", "OPERATOR"))
        if required <= capabilities_for_principal(holder):
            assert mode in available_work_modes(capabilities_for_principal(holder))
        else:
            assert mode not in available_work_modes(capabilities_for_principal(holder))

    assert default_work_mode(()) is None
    assert functional_assignments_for(frozenset()) == ()


def test_disabled_principal_gets_no_capability_beyond_its_permissions() -> None:
    """A non-active principal still cannot exceed its role, and the profile says so."""

    disabled = _principal("ANALYST", status="DISABLED")
    profile = build_experience_profile(disabled)

    # The profile reports role-derived capabilities; enforcement (which denies a
    # disabled principal outright) stays in ``authorize``.
    assert profile_stays_within_role_permissions(disabled, profile) is True
    assert Capability.MARKET_READ in profile.effective_capabilities


def test_scope_kinds_report_what_the_backend_cannot_express() -> None:
    """Scope honesty: only DATA scopes exist, the rest are declared unsupported."""

    profile = build_experience_profile(_principal("ANALYST", scopes=("*", "EEX")))

    assert profile.scope_refs == ("DATA:ALL", "DATA:EEX")
    assert profile.data_entitlement_refs == ("*", "EEX")
    assert set(SUPPORTED_SCOPE_KINDS) == {"DATA"}
    assert set(UNSUPPORTED_SCOPE_KINDS) == {"ORGANIZATION", "PORTFOLIO", "MARKET", "REGION"}
    assert profile.unsupported_scope_kinds == UNSUPPORTED_SCOPE_KINDS


def test_experience_profile_payload_carries_no_secret_or_record() -> None:
    """The contract carries capability names only."""

    payload = build_experience_profile(_principal("ANALYST", scopes=("EEX",))).to_payload()

    assert set(payload) == {
        "principal_id",
        "role",
        "roles",
        "functional_assignments",
        "available_work_modes",
        "default_work_mode",
        "effective_capabilities",
        "commercial_capabilities",
        "scope_refs",
        "data_entitlement_refs",
        "unsupported_scope_kinds",
        "work_mode_grants_authority",
    }
    assert payload["work_mode_grants_authority"] is False
    assert all(isinstance(item, str) for item in payload["effective_capabilities"])
    assert all(isinstance(item, str) for item in payload["scope_refs"])


def _db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "experience.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", f"sqlite+pysqlite:///{db_path.as_posix()}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)


def _db_principal(session: Session, *, name: str, role: str, scopes: list[str]) -> str:
    row = identity_repository.create_identity_principal(
        session, name=name, display_name=name.title(), role=role, data_scopes=scopes
    )
    _key, bearer = identity_repository.create_identity_api_key(
        session, row.principal_id, display_name="experience-test"
    )
    return bearer


def test_me_returns_the_experience_profile_for_the_authenticated_identity(
    tmp_path, monkeypatch
) -> None:
    """``GET /api/me`` carries the composition contract without widening access."""

    _db(tmp_path, monkeypatch)
    url = f"sqlite+pysqlite:///{(tmp_path / 'experience.sqlite').as_posix()}"
    with Session(create_engine(url, future=True)) as session:
        admin_key = _db_principal(session, name="exp-admin", role="ADMIN", scopes=[])
        analyst_key = _db_principal(session, name="exp-analyst", role="ANALYST", scopes=["EEX"])
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))

    admin = client.get(
        "/api/me",
        headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": admin_key},
    )
    assert admin.status_code == 200
    admin_experience = admin.json()["data"]["experience"]
    assert admin_experience["available_work_modes"] == [WorkMode.ADMINISTRATION.value]
    assert admin_experience["commercial_capabilities"] == []
    assert "access.manage" in admin_experience["effective_capabilities"]

    analyst = client.get(
        "/api/me",
        headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": analyst_key},
    )
    assert analyst.status_code == 200
    analyst_experience = analyst.json()["data"]["experience"]
    assert "market.read" in analyst_experience["commercial_capabilities"]
    assert analyst_experience["default_work_mode"] == WorkMode.TRADING_ANALYSIS.value
    assert analyst_experience["scope_refs"] == ["DATA:EEX"]
