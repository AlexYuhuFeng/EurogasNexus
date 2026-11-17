"""Approving a public source is an ADMIN act, checked on the server; persona never grants it.

``POST /api/sources/{source_id}/approve`` records the firm's acceptance of a provider's terms
and opens the fail-closed ingestion gate for ENTSOG or GIE. Only an ADMIN identity may do it:
an OPERATOR (who runs sources), an ANALYST, and a principal whose declared job function is
"platform administrator" or "data operator" without the ADMIN role are refused. The approval
names the authenticated principal, never a caller-supplied claim.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import public_source_approval as approval
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.observation import AuditEventRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.security.permissions import Permission, permission_for_path

PUBLIC_TOKEN = "test-public-api-token"


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'approval.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    # The provider is not called: the bounded live validation reports a passing sample.
    passing = [approval.DatasetCheck("entsog:operationaldatas", records=10, normalised=10)]
    monkeypatch.setattr(
        approval, "live_validation",
        lambda system, **kwargs: (
            "live_validated",
            ["simulated_shape_match", "live_sample_validation", "sample_archived"],
            passing,
        ),
    )
    monkeypatch.setattr(approval, "_http_client", lambda: _Closable())
    return engine


class _Closable:
    def close(self) -> None:
        return None


def _bearer(engine, name: str, roles: list[str], functions: list[str] | None = None) -> str:
    with Session(engine) as session:
        row = create_identity_principal(
            session, name=name, display_name=name, role=roles[0], data_scopes=["*"]
        )
        row.roles = list(roles)
        row.job_functions = list(functions or [])
        _key, bearer = create_identity_api_key(session, row.principal_id, display_name="t")
        session.commit()
    return bearer


def _post(client, bearer, source="src-entsog", **body):
    return client.post(
        f"/api/sources/{source}/approve",
        json={"reason": "first run", "accept_terms": True, **body},
        headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer},
    )


def test_the_route_is_declared_admin() -> None:
    assert permission_for_path("/api/sources/src-entsog/approve", "POST") is Permission.ADMIN


def test_only_an_admin_approves_and_the_approval_names_them(store) -> None:
    client = TestClient(create_app(Settings(api_profile="release")))
    refused = {
        "operator": _bearer(store, "ops.olga", ["OPERATOR"], ["DATA_OPERATOR"]),
        "analyst": _bearer(store, "an.alan", ["ANALYST"], ["PLATFORM_ADMINISTRATOR"]),
    }
    for bearer in refused.values():
        response = _post(client, bearer)
        assert response.status_code == 403, response.text
    admin = _bearer(store, "admin.anna", ["ADMIN"])
    missing_terms = _post(client, admin, accept_terms=False)
    assert missing_terms.status_code == 422
    assert missing_terms.json()["detail"]["code"] == "terms_not_accepted"
    not_needed = _post(client, admin, source="src-ecb")
    assert not_needed.status_code == 404
    assert not_needed.json()["detail"]["code"] == "approval_not_required"

    approved = _post(client, admin)
    assert approved.status_code == 200, approved.text
    data = approved.json()["data"]
    assert data["state"] == "approved" and data["approval"]["approved_by"] == "admin.anna"
    with Session(store) as session:
        audit = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "approve_public_source")
            .one()
        )
    assert audit.principal == "admin.anna" and "first run" in audit.detail

    sources = client.get(
        "/api/sources", headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": admin}
    )
    by_id = {row["source_id"]: row for row in sources.json()["data"]}
    assert by_id["src-entsog"]["approval"]["approved_by"] == "admin.anna"
    assert by_id["src-gie"]["approval"]["state"] in {"not_approved"}
    assert by_id["src-gie"]["approval"]["reason"] == "source_not_approved"
    assert by_id["src-ecb"]["approval"]["state"] == "not_required"


def test_only_an_admin_revokes_with_confirmation_and_the_source_is_not_approved_again(store):
    client = TestClient(create_app(Settings(api_profile="release")))
    admin = _bearer(store, "admin.anna", ["ADMIN"])
    operator = _bearer(store, "ops.olga", ["OPERATOR"], ["DATA_OPERATOR"])
    assert _post(client, admin).status_code == 200

    def revoke(bearer, **body):
        return client.request(
            "DELETE", "/api/sources/src-entsog/approve",
            json={"reason": "terms review", "confirm": True, **body},
            headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer},
        )

    assert revoke(operator).status_code == 403
    unconfirmed = revoke(admin, confirm=False)
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["detail"]["code"] == "confirmation_required"
    revoked = revoke(admin)
    assert revoked.status_code == 200 and revoked.json()["data"]["changed"] is True
    assert revoke(admin).json()["data"]["changed"] is False  # idempotent
    sources = client.get(
        "/api/sources", headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": admin}
    )
    entsog = next(row for row in sources.json()["data"] if row["source_id"] == "src-entsog")
    assert entsog["approval"]["state"] == "not_approved"
    with Session(store) as session:
        actions = [
            row.action for row in session.query(AuditEventRecord)
            .filter(AuditEventRecord.event_type == "source.approval")
            .order_by(AuditEventRecord.event_ts_utc)
        ]
    assert actions == ["approve_public_source", "revoke_public_source_approval"]
