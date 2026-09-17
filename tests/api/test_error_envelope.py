"""Product error envelope tests (Architecture V2 Wave 8, API wiring).

Every HTTP failure must keep the ``detail`` an endpoint raised - so existing Web,
SDK and CLI clients are unaffected - and add the stable code, family, severity,
recoverability, message/action keys and the correlation id alongside it, with
operator detail only on an operator identity.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _prepare(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "error-envelope.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _bearer(database_url: str, *, name: str, role: str) -> str:
    with Session(create_engine(database_url, future=True)) as session:
        row = create_identity_principal(
            session, name=name, display_name=name.title(), role=role, data_scopes=[]
        )
        _key, bearer = create_identity_api_key(session, row.principal_id, display_name="envelope")
        session.commit()
    return bearer


def _headers(bearer: str | None = None) -> dict[str, str]:
    headers = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}
    if bearer:
        headers["X-Eurogas-Identity"] = bearer
    return headers


def test_a_declared_code_keeps_detail_and_gains_the_taxonomy(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    viewer = _bearer(database_url, name="envelope-viewer", role="VIEWER")
    client = TestClient(create_app(Settings(api_profile="release")))

    # A VIEWER hitting an ADMIN route: the endpoint raises
    # 403 identity_role_forbidden with a dict detail.
    response = client.get("/api/access/users", headers=_headers(viewer))
    assert response.status_code == 403

    body = response.json()
    # The original shape is untouched: existing clients read detail["error"].
    assert body["detail"]["error"] == "identity_role_forbidden"
    assert "requires role" in body["detail"]["message"]

    # ...and the taxonomy rides alongside.
    assert body["error"] == "identity_role_forbidden"
    assert body["family"] == "AUTH"
    assert body["severity"] == "error"
    assert body["recoverability"] == "permanent"
    assert body["message_key"] == "errors.identity_role_forbidden.message"
    assert body["action_key"] == "errors.identity_role_forbidden.action"
    assert body["correlation_id"]
    assert body["correlation_id"] == response.headers["x-request-id"]


def test_commercial_refusal_is_an_entitlement_family_failure(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    admin = _bearer(database_url, name="envelope-admin", role="ADMIN")
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get("/api/market/observations", headers=_headers(admin))
    assert response.status_code == 403
    body = response.json()

    assert body["detail"]["error"] == "commercial_access_not_granted"
    assert body["error"] == "commercial_access_not_granted"
    assert body["family"] == "ENTITLEMENT"
    assert body["recoverability"] == "after_user_action"
    assert body["severity"] == "error"
    assert body["correlation_id"] == response.headers["x-request-id"]
    # The endpoint's own guidance is preserved for every caller.
    assert body["detail"]["capabilities_required"] == ["market.read", "portfolio.read"]


def test_a_string_detail_is_left_exactly_as_raised(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    bearer = _bearer(database_url, name="envelope-viewer-2", role="VIEWER")
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get(
        "/api/reference-network/nodes/node-that-does-not-exist", headers=_headers(bearer)
    )
    assert response.status_code == 404
    body = response.json()

    # A plain string stays a plain string: no client has to learn a new shape.
    assert isinstance(body["detail"], str)
    assert "node-that-does-not-exist" in body["detail"]
    assert body["error"] == "not_found"
    assert body["family"] == "VALIDATION"
    assert body["recoverability"] == "permanent"
    assert body["correlation_id"]


def test_an_uncatalogued_endpoint_code_is_still_classified(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    analyst = _bearer(database_url, name="envelope-analyst-2", role="ANALYST")
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get(
        "/api/analysis-snapshots/snapshot-that-does-not-exist", headers=_headers(analyst)
    )
    assert response.status_code == 404
    body = response.json()

    # The code is reported unchanged, with an inferred family and family-level keys,
    # so a client always has text to render. This endpoint declares its code under
    # ``code`` rather than ``error``; the envelope reads both conventions.
    assert body["detail"]["code"] == "analysis_snapshot_not_found"
    assert body["error"] == "analysis_snapshot_not_found"
    assert body["family"] == "VALIDATION"
    assert body["message_key"] == "errors.family.VALIDATION.title"
    assert body["action_key"] == "errors.family.VALIDATION.action"


def test_a_missing_api_token_is_a_configuration_failure(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    monkeypatch.delenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", raising=False)
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get("/api/market/observations", headers={})
    assert response.status_code == 503
    body = response.json()

    assert body["detail"]["error"] == "public_api_token_not_configured"
    assert body["error"] == "public_api_token_not_configured"
    assert body["family"] == "CONFIGURATION"
    assert body["severity"] == "critical"
    assert body["correlation_id"]


def test_operator_detail_is_separate_and_gated_on_an_operator_identity(
    tmp_path, monkeypatch
) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    viewer = _bearer(database_url, name="envelope-viewer-3", role="VIEWER")
    operator = _bearer(database_url, name="envelope-operator", role="OPERATOR")
    client = TestClient(create_app(Settings(api_profile="release")))

    business = client.get("/api/access/users", headers=_headers(viewer))
    privileged = client.get("/api/access/users", headers=_headers(operator))
    assert business.status_code == privileged.status_code == 403

    # The endpoint's own detail is never rewritten for anyone...
    assert business.json()["detail"]["error"] == "identity_role_forbidden"
    assert privileged.json()["detail"]["error"] == "identity_role_forbidden"
    # ...and the technical echo is a separate, operator-only field.
    assert "operator_detail" not in business.json()
    assert privileged.json()["operator_detail"]
    assert "requires role" in privileged.json()["operator_detail"]
