"""Tests for the SDK deployment-token resolution.

Regression context: the SDK read only ``EUROGAS_NEXUS_API_TOKEN`` while the
server reads ``EUROGAS_NEXUS_PUBLIC_API_TOKEN``. Nothing in the repository, the
templates or CI set the SDK's name, so an operator following the deployment
documentation sent no ``Authorization`` header at all and every release-profile
call was refused.
"""

from __future__ import annotations

from eurogas_nexus_sdk._http import (
    API_TOKEN_ENV,
    LEGACY_API_TOKEN_ENV,
    auth_headers,
    resolve_api_token,
)


def test_canonical_name_is_read() -> None:
    assert resolve_api_token({API_TOKEN_ENV: "canonical-token"}) == "canonical-token"


def test_legacy_name_still_works() -> None:
    assert resolve_api_token({LEGACY_API_TOKEN_ENV: "legacy-token"}) == "legacy-token"


def test_canonical_name_wins_when_both_are_set() -> None:
    assert (
        resolve_api_token(
            {API_TOKEN_ENV: "canonical-token", LEGACY_API_TOKEN_ENV: "legacy-token"}
        )
        == "canonical-token"
    )


def test_blank_values_are_ignored() -> None:
    assert resolve_api_token({API_TOKEN_ENV: "   ", LEGACY_API_TOKEN_ENV: ""}) == ""


def test_missing_values_yield_no_token() -> None:
    assert resolve_api_token({}) == ""


def test_auth_headers_use_the_canonical_token(monkeypatch) -> None:
    monkeypatch.setenv(API_TOKEN_ENV, "canonical-token")
    monkeypatch.delenv(LEGACY_API_TOKEN_ENV, raising=False)
    headers = auth_headers()
    assert headers["Authorization"] == "Bearer canonical-token"


def test_auth_headers_fall_back_to_the_legacy_token(monkeypatch) -> None:
    monkeypatch.delenv(API_TOKEN_ENV, raising=False)
    monkeypatch.setenv(LEGACY_API_TOKEN_ENV, "legacy-token")
    headers = auth_headers()
    assert headers["Authorization"] == "Bearer legacy-token"


def test_auth_headers_are_empty_without_a_token(monkeypatch) -> None:
    monkeypatch.delenv(API_TOKEN_ENV, raising=False)
    monkeypatch.delenv(LEGACY_API_TOKEN_ENV, raising=False)
    assert auth_headers() == {}
