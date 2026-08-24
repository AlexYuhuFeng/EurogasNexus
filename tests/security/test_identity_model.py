"""R32 identity model unit tests (role, key, and scope primitives)."""

from __future__ import annotations

import pytest

from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    IdentityAuthError,
    generate_api_key,
    legacy_public_token_principal,
    parse_identity_bearer,
    principal_allows_source_family,
    role_allows,
    role_value,
    verify_key_hash,
)


def test_role_precedence_is_least_privilege_ordered() -> None:
    assert role_allows("VIEWER", "VIEWER") is True
    assert role_allows("VIEWER", "ANALYST") is False
    assert role_allows("ANALYST", "GOVERNED".replace("GOVERNED", "ANALYST")) is True
    assert role_allows("ANALYST", "OPERATOR") is False
    assert role_allows("OPERATOR", "OPERATOR") is True
    assert role_allows("ADMIN", "OPERATOR") is True
    assert role_allows("UNKNOWN", "VIEWER") is False


def test_role_value_fails_closed_for_unknown_role() -> None:
    assert role_value(" operator ") is role_value("OPERATOR")
    with pytest.raises(IdentityAuthError) as exc_info:
        role_value("OWNER")
    assert exc_info.value.status_code == 422


def test_api_key_generation_returns_one_time_plaintext_and_hash() -> None:
    key = generate_api_key(key_id="k123", display_name="workstation")

    assert key.bearer.startswith("nexus_k123_")
    assert key.key_hash
    parsed = parse_identity_bearer(key.bearer)
    assert parsed == ("k123", key.bearer.split("_", 2)[2])
    assert verify_key_hash(parsed[1], key.key_hash) is True
    assert verify_key_hash("wrong-secret", key.key_hash) is False


def test_parse_identity_bearer_rejects_malformed_tokens() -> None:
    assert parse_identity_bearer(None) is None
    assert parse_identity_bearer("Bearer something") is None
    assert parse_identity_bearer("nexus_onlyprefix") is None
    assert parse_identity_bearer("nexus_key") is None


def test_legacy_public_token_principal_has_operator_and_wildcard_scope() -> None:
    principal = legacy_public_token_principal()

    assert principal.role == "OPERATOR"
    assert principal.data_scopes == ("*",)
    assert principal.auth_method == "legacy_public_token"


def test_principal_allows_public_baseline_without_explicit_scope() -> None:
    principal = AuthenticatedPrincipal(
        principal_id="principal-x",
        name="viewer",
        principal_type="USER",
        role="VIEWER",
        status="ACTIVE",
        data_scopes=(),
    )

    for source in ("ENTSOG", "GIE", "ECB", "Weather", "operator-input"):
        assert principal_allows_source_family(principal, source) is True


def test_principal_allows_commercial_family_only_with_explicit_scope() -> None:
    principal = AuthenticatedPrincipal(
        principal_id="principal-x",
        name="analyst",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=("EEX",),
    )

    assert principal_allows_source_family(principal, "EEX") is True
    assert principal_allows_source_family(principal, "EEX_Sim") is True
    assert principal_allows_source_family(principal, "Trayport") is False
    assert principal_allows_source_family(principal, "UnknownVendor") is False


def test_wildcard_scope_allows_all_known_commercial_families() -> None:
    principal = AuthenticatedPrincipal(
        principal_id="principal-x",
        name="operator",
        principal_type="USER",
        role="OPERATOR",
        status="ACTIVE",
        data_scopes=("*",),
    )

    assert principal_allows_source_family(principal, "Trayport") is True
    assert principal_allows_source_family(principal, "ICIS") is True
