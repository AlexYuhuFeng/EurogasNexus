"""The static deployment token is a scoped service principal, never a super-credential (H3)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.security import deployment_token
from eurogas_nexus.security.identity import legacy_public_token_principal

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "test-public-api-token"


@pytest.fixture
def anonymous(monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_TEST_ANONYMOUS", "1")
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)


def test_the_token_is_never_read_from_the_url(anonymous):
    client = TestClient(create_app())
    assert client.get(f"/api/market/observations?api_key={TOKEN}").status_code == 401
    header = client.get("/api/market/observations", headers={"X-Eurogas-Api-Key": TOKEN})
    assert header.status_code != 401


def test_production_defaults_to_the_service_principal(monkeypatch):
    monkeypatch.delenv(deployment_token.MODE_ENV, raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    assert deployment_token.token_mode() == deployment_token.SERVICE
    principal = legacy_public_token_principal()
    assert principal.role == "VIEWER"
    assert "*" not in principal.data_scopes
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    assert deployment_token.token_mode() == deployment_token.LEGACY_OPERATOR


def test_service_mode_reads_no_book_and_cannot_name_an_actor(anonymous, monkeypatch):
    monkeypatch.setenv(deployment_token.MODE_ENV, "service")
    client = TestClient(create_app())
    headers = {"X-Eurogas-Api-Key": TOKEN, "X-Eurogas-Principal": "alice"}
    # An OPERATOR route: a VIEWER token is refused, whatever name it claims.
    response = client.put("/api/portfolio/books/b1", headers=headers, json={})
    assert response.status_code == 403
    # Credit exposure needs the limits read grant, which the service token lacks.
    assert client.get("/api/portfolio/credit-exposure", headers=headers).status_code == 403


def test_an_operator_service_token_acts_as_itself(monkeypatch):
    monkeypatch.setenv(deployment_token.MODE_ENV, "service")
    monkeypatch.setenv(deployment_token.ROLE_ENV, "OPERATOR")
    from starlette.requests import Request

    from eurogas_nexus.api.dependencies.route_permission import require_route_permission

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/market/ticks",
        "headers": [(b"x-eurogas-principal", b"alice")],
        "query_string": b"",
    }
    request = Request(scope)
    request.state.identity = legacy_public_token_principal()
    import asyncio

    asyncio.run(require_route_permission(request))
    assert request.state.actor == "public-api"


def test_legacy_mode_records_the_claimed_name_as_a_claim(monkeypatch):
    monkeypatch.setenv(deployment_token.MODE_ENV, "legacy_operator")
    from starlette.requests import Request

    from eurogas_nexus.api.dependencies.route_permission import require_route_permission

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/market/ticks",
        "headers": [(b"x-eurogas-principal", b"alice")],
        "query_string": b"",
    }
    request = Request(scope)
    request.state.identity = legacy_public_token_principal()
    import asyncio

    asyncio.run(require_route_permission(request))
    assert request.state.actor == "public-api@alice"


def test_the_internal_token_records_a_claimed_operator():
    import os

    from eurogas_nexus.security.internal_api import validate_internal_operator_headers

    os.environ["EUROGAS_NEXUS_INTERNAL_API_TOKEN"] = "internal-secret-value"
    try:
        actor = validate_internal_operator_headers(token="internal-secret-value", principal="bob")
    finally:
        del os.environ["EUROGAS_NEXUS_INTERNAL_API_TOKEN"]
    assert actor == "internal-api@bob"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (deployment_token.ROLE_ENV, "ADMIN"),
        (deployment_token.SCOPES_ENV, "EEX,*"),
        (deployment_token.MODE_ENV, "superuser"),
    ],
)
def test_start_up_refuses_a_super_token(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError):
        create_app()


def test_rotation_accepts_the_previous_token(monkeypatch):
    from eurogas_nexus.security.public_api import PublicApiAuthError, verify_public_api_token

    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "new-token-value")
    monkeypatch.setenv(deployment_token.PREVIOUS_TOKEN_ENV, "old-token-value")
    verify_public_api_token("new-token-value")
    verify_public_api_token("old-token-value")
    monkeypatch.delenv(deployment_token.PREVIOUS_TOKEN_ENV)
    with pytest.raises(PublicApiAuthError):
        verify_public_api_token("old-token-value")


def test_only_the_api_receives_the_deployment_token_and_no_service_the_internal_one():
    compose = yaml.safe_load((ROOT / "deploy/runtime/compose.yaml").read_text(encoding="utf-8"))
    text = (ROOT / "deploy/runtime/compose.yaml").read_text(encoding="utf-8")
    assert "EUROGAS_NEXUS_INTERNAL_API_TOKEN" not in text
    holders = {
        name
        for name, service in compose["services"].items()
        if "EUROGAS_NEXUS_PUBLIC_API_TOKEN" in (service.get("environment") or {})
    }
    assert holders == {"api", "config-check"}
    secret_key = {
        name
        for name, service in compose["services"].items()
        if "EUROGAS_NEXUS_SECRET_KEY" in (service.get("environment") or {})
    }
    assert "migrate" not in secret_key and "reference-seed" not in secret_key
    health = " ".join(compose["services"]["api"]["healthcheck"]["test"])
    assert "API_TOKEN" not in health
