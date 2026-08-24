"""OPERATOR route principal enforcement tests (Gate 1)."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.security.permissions import Permission, permission_for_path

TOKEN_HEADERS = {"X-Eurogas-Api-Key": "test-public-api-token"}


def test_operator_routes_require_principal_in_release() -> None:
    assert permission_for_path("/api/credentials/DEEPSEEK") is Permission.OPERATOR
    client = TestClient(create_app(Settings(api_profile="release")))
    body = {"api_key": "test-key", "label": "test"}

    # Token alone is not enough for OPERATOR routes.
    response = client.put("/api/credentials/DEEPSEEK", headers=TOKEN_HEADERS, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "operator_principal_missing"

    # An invalid principal is rejected.
    response = client.put(
        "/api/credentials/DEEPSEEK",
        headers={**TOKEN_HEADERS, "X-Eurogas-Principal": "bad principal!"},
        json=body,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "operator_principal_invalid"

    # A valid principal passes the permission gate (route then runs).
    response = client.put(
        "/api/credentials/DEEPSEEK",
        headers={**TOKEN_HEADERS, "X-Eurogas-Principal": "operator-alice"},
        json=body,
    )
    assert response.status_code != 401
    assert response.status_code != 403


def test_read_routes_do_not_require_principal_in_release() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get(
        "/api/route-cost/tso-tariffs",
        headers=TOKEN_HEADERS,
    )

    assert response.status_code != 401
    assert response.status_code != 403


def test_operator_routes_are_not_enforced_in_development() -> None:
    client = TestClient(create_app(Settings(api_profile="development")))

    response = client.put(
        "/api/credentials/DEEPSEEK",
        json={"api_key": "test-key", "label": "test"},
    )

    assert response.status_code != 401
    assert response.status_code != 403


def test_write_operator_routes_require_principal_too() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(
        "/api/credentials/DEEPSEEK/rotate",
        headers=TOKEN_HEADERS,
        json={},
    )
    assert response.status_code == 401
