"""Tests for the cookie transport-security policy.

Regression context: ``Secure`` used to be set only when the inbound request
scheme was ``https``. In the shipped deployment Caddy terminates TLS and proxies
to ``api:8000``, and uvicorn rewrites the scheme only for peers listed in
``FORWARDED_ALLOW_IPS`` (default ``127.0.0.1,::1``), so the proxy hop is not
trusted and the 12-hour session cookie was issued without ``Secure``.
"""

from __future__ import annotations

import pytest

from eurogas_nexus.security.cookie_policy import (
    deployment_cookie_context,
    request_cookie_secure,
    session_cookie_secure,
)


@pytest.mark.parametrize("scheme", ["https", "HTTPS", " https "])
def test_secure_request_always_sets_secure(scheme: str) -> None:
    assert session_cookie_secure(scheme=scheme) is True


@pytest.mark.parametrize("api_profile", ["release", "internal", "RELEASE"])
def test_production_api_profile_forces_secure_over_plain_http(api_profile: str) -> None:
    """The shipped topology reports http; production must still set Secure."""

    assert session_cookie_secure(scheme="http", api_profile=api_profile) is True


@pytest.mark.parametrize("environment", ["release", "trial"])
def test_production_environment_forces_secure(environment: str) -> None:
    assert session_cookie_secure(scheme="http", environment=environment) is True


def test_internal_profile_is_production_even_in_development_environment() -> None:
    assert (
        session_cookie_secure(scheme="http", api_profile="internal", environment="development")
        is True
    )


def test_development_http_cookie_stays_usable() -> None:
    """A plain-HTTP localhost workflow must not be locked out."""

    assert (
        session_cookie_secure(scheme="http", api_profile="development", environment="development")
        is False
    )


def test_test_environment_is_not_treated_as_production() -> None:
    assert session_cookie_secure(scheme="http", environment="test") is False


def test_unknown_context_falls_back_to_the_request_scheme() -> None:
    assert session_cookie_secure(scheme="http") is False
    assert session_cookie_secure(scheme="") is False


class _Request:
    def __init__(self, scheme: str) -> None:
        self.scheme = scheme


def test_request_helper_uses_the_supplied_context() -> None:
    request = _Request("http")
    assert request_cookie_secure(request, api_profile="release") is True
    assert request_cookie_secure(request, api_profile="development") is False
    assert request_cookie_secure(_Request("https"), api_profile="development") is True


class _State:
    def __init__(self, settings=None, route_profile=None) -> None:
        self.settings = settings
        self.route_profile = route_profile


class _App:
    def __init__(self, state) -> None:
        self.state = state


class _AppRequest:
    def __init__(self, state) -> None:
        self.app = _App(state)


class _Settings:
    def __init__(self, api_profile, environment) -> None:
        self.api_profile = api_profile
        self.environment = environment


class _Profile:
    def __init__(self, name) -> None:
        self.name = name


def test_deployment_context_prefers_settings() -> None:
    request = _AppRequest(_State(_Settings("release", "release"), _Profile("development")))
    assert deployment_cookie_context(request) == ("release", "release")


def test_deployment_context_falls_back_to_route_profile_name() -> None:
    request = _AppRequest(_State(None, _Profile("internal")))
    assert deployment_cookie_context(request) == ("internal", None)


def test_deployment_context_survives_a_bare_object() -> None:
    """An application built without the usual lifespan state must not raise."""

    assert deployment_cookie_context(object()) == (None, None)
