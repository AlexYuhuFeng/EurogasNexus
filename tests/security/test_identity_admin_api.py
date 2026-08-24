"""R32 internal identity administration and release-role enforcement tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base

PUBLIC_TOKEN = "test-public-api-token"
INTERNAL_TOKEN = "test-internal-token"


def _db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "identity.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _internal_client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="internal")))


def _internal_headers() -> dict[str, str]:
    return {
        "X-Eurogas-Internal-Token": INTERNAL_TOKEN,
        "X-Eurogas-Principal": "ops-admin",
    }


def _release_client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="release")))


def _identity_headers(bearer: str) -> dict[str, str]:
    return {
        "X-Eurogas-Api-Key": PUBLIC_TOKEN,
        "X-Eurogas-Identity": bearer,
    }


def _create_identity(client: TestClient, *, role: str, name: str, scopes: list[str]) -> dict:
    response = client.post(
        "/api/internal/identities",
        headers=_internal_headers(),
        json={
            "name": name,
            "display_name": name.title(),
            "principal_type": "USER",
            "role": role,
            "data_scopes": scopes,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _issue_key(client: TestClient, principal_id: str) -> str:
    response = client.post(
        f"/api/internal/identities/{principal_id}/keys",
        headers=_internal_headers(),
        json={"display_name": "test-key"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["api_key"]


def test_internal_identity_routes_require_internal_token_and_principal(
    tmp_path, monkeypatch
) -> None:
    _db(tmp_path, monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", INTERNAL_TOKEN)
    client = _internal_client()

    assert client.get("/api/internal/identities").status_code == 401
    assert client.get(
        "/api/internal/identities",
        headers={"X-Eurogas-Internal-Token": INTERNAL_TOKEN},
    ).status_code == 401


def test_identity_lifecycle_and_key_redaction(tmp_path, monkeypatch) -> None:
    _db(tmp_path, monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", INTERNAL_TOKEN)
    client = _internal_client()

    principal = _create_identity(
        client,
        role="OPERATOR",
        name="trader-a",
        scopes=["EEX", "ICE_OCM"],
    )
    principal_id = principal["principal_id"]
    assert principal["status"] == "ACTIVE"
    assert principal["data_scopes"] == ["EEX", "ICE_OCM"]

    bearer = _issue_key(client, principal_id)
    assert bearer.startswith("nexus_")

    listed = client.get("/api/internal/identities", headers=_internal_headers()).json()["data"]
    listed_row = next(row for row in listed if row["principal_id"] == principal_id)
    assert listed_row["keys"][0]["key_prefix"]
    assert "key_hash" not in listed_row["keys"][0]
    assert "bearer" not in listed_row["keys"][0]
    assert bearer not in client.get(
        "/api/internal/identities", headers=_internal_headers()
    ).text

    revoke = client.post(
        f"/api/internal/identities/{principal_id}/keys/{listed_row['keys'][0]['key_id']}/revoke",
        headers=_internal_headers(),
    )
    assert revoke.status_code == 200
    assert revoke.json()["data"]["key"]["revoked_at_utc"] is not None

    rotate = client.post(
        f"/api/internal/identities/{principal_id}/keys/{listed_row['keys'][0]['key_id']}/rotate",
        headers=_internal_headers(),
        json={"display_name": "rotated-key"},
    )
    assert rotate.status_code == 200
    rotated_bearer = rotate.json()["data"]["api_key"]
    assert rotated_bearer != bearer

    disabled = client.post(
        f"/api/internal/identities/{principal_id}/disable",
        headers=_internal_headers(),
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "DISABLED"

    events = client.get("/api/internal/audit/events", headers=_internal_headers()).json()["data"]
    actions = {event["action"] for event in events}
    assert "identity.create" in actions
    assert "identity.key.issue" in actions
    assert "identity.key.rotate" in actions
    assert "identity.key.revoke" in actions
    assert "identity.disable" in actions


def test_release_profile_role_authorization(tmp_path, monkeypatch) -> None:
    _db(tmp_path, monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", INTERNAL_TOKEN)
    internal = _internal_client()
    viewer = _create_identity(internal, role="VIEWER", name="viewer-a", scopes=["EEX"])
    viewer_bearer = _issue_key(internal, viewer["principal_id"])
    analyst = _create_identity(internal, role="ANALYST", name="analyst-a", scopes=["EEX"])
    analyst_bearer = _issue_key(internal, analyst["principal_id"])
    operator = _create_identity(internal, role="OPERATOR", name="operator-a", scopes=["*"])
    operator_bearer = _issue_key(internal, operator["principal_id"])

    client = _release_client()
    route_body = {
        "source": "A",
        "target": "B",
        "required_capacity_mwh": 1,
        "edges": [
            {
                "edge_id": "e",
                "source": "A",
                "target": "B",
                "tariff_gbp_mwh": 0,
                "available_capacity_mwh": 1,
            }
        ],
    }

    # VIEWER is allowed on READ/PUBLIC.
    health = client.get("/api/health", headers=_identity_headers(viewer_bearer))
    assert health.status_code == 200

    # VIEWER is blocked from GOVERNED compute routes.
    viewer_governed = client.post(
        "/api/optimization/route",
        headers=_identity_headers(viewer_bearer),
        json=route_body,
    )
    assert viewer_governed.status_code == 403
    assert viewer_governed.json()["detail"]["error"] == "identity_role_forbidden"

    # ANALYST is allowed on GOVERNED compute routes.
    analyst_governed = client.post(
        "/api/optimization/route",
        headers=_identity_headers(analyst_bearer),
        json=route_body,
    )
    assert analyst_governed.status_code == 200

    # ANALYST is blocked from OPERATOR routes.
    analyst_operator = client.put(
        "/api/credentials/DEEPSEEK",
        headers=_identity_headers(analyst_bearer),
        json={"api_key": "test-key", "label": "test"},
    )
    assert analyst_operator.status_code == 403
    assert analyst_operator.json()["detail"]["error"] == "identity_role_forbidden"

    # OPERATOR passes the OPERATOR permission gate (route may then fail on
    # credential encryption or DB, but never 401/403 from identity).
    operator_credentials = client.put(
        "/api/credentials/DEEPSEEK",
        headers=_identity_headers(operator_bearer),
        json={"api_key": "test-key", "label": "test"},
    )
    assert operator_credentials.status_code not in {401, 403}


def test_revoked_or_disabled_identity_key_fails_closed(tmp_path, monkeypatch) -> None:
    _db(tmp_path, monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", INTERNAL_TOKEN)
    internal = _internal_client()
    principal = _create_identity(internal, role="VIEWER", name="viewer-b", scopes=[])
    bearer = _issue_key(internal, principal["principal_id"])
    listed = internal.get("/api/internal/identities", headers=_internal_headers()).json()["data"]
    key_id = next(
        row["keys"][0]["key_id"]
        for row in listed
        if row["principal_id"] == principal["principal_id"]
    )

    client = _release_client()
    assert client.get("/api/health", headers=_identity_headers(bearer)).status_code == 200

    revoke = internal.post(
        f"/api/internal/identities/{principal['principal_id']}/keys/{key_id}/revoke",
        headers=_internal_headers(),
    )
    assert revoke.status_code == 200
    revoked = client.get("/api/health", headers=_identity_headers(bearer))
    assert revoked.status_code == 403
    assert revoked.json()["detail"]["error"] == "identity_key_revoked"

    bearer2 = _issue_key(internal, principal["principal_id"])
    internal.post(
        f"/api/internal/identities/{principal['principal_id']}/disable",
        headers=_internal_headers(),
    )
    disabled = client.get("/api/health", headers=_identity_headers(bearer2))
    assert disabled.status_code == 403
    assert disabled.json()["detail"]["error"] == "identity_principal_disabled"


def test_expired_identity_key_fails_closed(tmp_path, monkeypatch) -> None:
    from datetime import UTC, datetime, timedelta

    _db(tmp_path, monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", INTERNAL_TOKEN)
    internal = _internal_client()
    principal = _create_identity(internal, role="VIEWER", name="viewer-expired", scopes=[])
    response = internal.post(
        f"/api/internal/identities/{principal['principal_id']}/keys",
        headers=_internal_headers(),
        json={
            "display_name": "expired-key",
            "expires_at_utc": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200
    bearer = response.json()["data"]["api_key"]

    client = _release_client()
    expired = client.get("/api/health", headers=_identity_headers(bearer))
    assert expired.status_code == 403
    assert expired.json()["detail"]["error"] == "identity_key_expired"


def test_identity_header_without_db_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = _release_client()

    response = client.get(
        "/api/health",
        headers={
            "X-Eurogas-Api-Key": PUBLIC_TOKEN,
            "X-Eurogas-Identity": "nexus_missing_secret",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "identity_store_not_configured"
