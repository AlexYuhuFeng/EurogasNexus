"""SDK release-profile auth header tests (Gate 1 client wiring)."""

import httpx

from eurogas_nexus.sdk import _http
from eurogas_nexus.sdk._http import (
    API_TOKEN_ENV,
    IDENTITY_ENV,
    IDENTITY_HEADER,
    PRINCIPAL_ENV,
    auth_headers,
)


def test_auth_headers_from_environment(monkeypatch) -> None:
    monkeypatch.setenv(API_TOKEN_ENV, "secret-token")
    monkeypatch.setenv(PRINCIPAL_ENV, "operator-alice")
    monkeypatch.setenv(IDENTITY_ENV, "nexus_k123_secret")

    headers = auth_headers()

    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["X-Eurogas-Principal"] == "operator-alice"
    assert headers[IDENTITY_HEADER] == "nexus_k123_secret"


def test_auth_headers_empty_without_configuration(monkeypatch) -> None:
    monkeypatch.delenv(API_TOKEN_ENV, raising=False)
    monkeypatch.delenv(PRINCIPAL_ENV, raising=False)
    monkeypatch.delenv(IDENTITY_ENV, raising=False)

    assert auth_headers() == {}


def test_sdk_get_sends_bearer_and_principal_when_configured(
    monkeypatch,
) -> None:
    captured: dict = {}

    def fake_get(url: str, *, timeout: float, **kwargs) -> httpx.Response:
        captured["headers"] = kwargs.get("headers", {})
        return httpx.Response(200, json={}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setenv(API_TOKEN_ENV, "secret-token")
    monkeypatch.setenv(PRINCIPAL_ENV, "operator-alice")
    monkeypatch.setenv(IDENTITY_ENV, "nexus_k123_secret")

    _http.get("http://example.test/api/health")

    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["headers"]["X-Eurogas-Principal"] == "operator-alice"
    assert captured["headers"][IDENTITY_HEADER] == "nexus_k123_secret"


def test_sdk_get_sends_no_auth_headers_when_unconfigured(
    monkeypatch,
) -> None:
    captured: dict = {"headers_sent": False}

    def fake_get(url: str, *, timeout: float, **kwargs) -> httpx.Response:
        captured["headers_sent"] = "headers" in kwargs
        return httpx.Response(200, json={}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.delenv(API_TOKEN_ENV, raising=False)
    monkeypatch.delenv(PRINCIPAL_ENV, raising=False)
    monkeypatch.delenv(IDENTITY_ENV, raising=False)

    _http.get("http://example.test/api/health")

    assert captured["headers_sent"] is False


def test_sdk_post_sends_auth_headers_when_configured(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        captured["headers"] = kwargs.get("headers", {})
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv(API_TOKEN_ENV, "secret-token")
    monkeypatch.setenv(PRINCIPAL_ENV, "operator-bob")

    _http.post("http://example.test/api/analysis/query", json={"q": 1})

    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["headers"]["X-Eurogas-Principal"] == "operator-bob"
