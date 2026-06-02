"""Internal API token guard tests."""

import pytest

from eurogas_nexus.security.internal_api import (
    INTERNAL_API_TOKEN_ENV,
    InternalApiAuthError,
    internal_api_token_configured,
    validate_internal_operator_headers,
    verify_internal_api_token,
)


def test_internal_api_token_configuration_detects_non_empty_env(monkeypatch) -> None:
    monkeypatch.delenv(INTERNAL_API_TOKEN_ENV, raising=False)
    assert internal_api_token_configured() is False

    monkeypatch.setenv(INTERNAL_API_TOKEN_ENV, " test-token ")
    assert internal_api_token_configured() is True


def test_internal_api_token_verification_uses_safe_errors(monkeypatch) -> None:
    monkeypatch.setenv(INTERNAL_API_TOKEN_ENV, "super-secret-token")

    verify_internal_api_token("super-secret-token")
    with pytest.raises(InternalApiAuthError) as exc_info:
        verify_internal_api_token("wrong-token")

    assert exc_info.value.code == "internal_api_token_invalid"
    assert exc_info.value.status_code == 403
    assert "super-secret-token" not in str(exc_info.value)


def test_internal_operator_headers_require_token_and_principal(monkeypatch) -> None:
    monkeypatch.setenv(INTERNAL_API_TOKEN_ENV, "super-secret-token")

    assert (
        validate_internal_operator_headers(
            token="super-secret-token",
            principal=" ops-user ",
        )
        == "ops-user"
    )
    with pytest.raises(InternalApiAuthError) as exc_info:
        validate_internal_operator_headers(token="super-secret-token", principal=None)

    assert exc_info.value.code == "internal_principal_missing"
    assert exc_info.value.status_code == 401
