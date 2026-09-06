"""CR-10 access administration and RBAC tests (release profile)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, IdentityApiKeyRecord
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.security.authorization import Permission, authorize

PUBLIC_TOKEN = "test-public-api-token"


def _db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "access.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _principal(session: Session, *, name: str, role: str, scopes: list[str]) -> str:
    row = identity_repository.create_identity_principal(
        session, name=name, display_name=name.title(), role=role, data_scopes=scopes
    )
    _key, bearer = identity_repository.create_identity_api_key(
        session, row.principal_id, display_name="test"
    )
    return row.principal_id, bearer


def _headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_role_permission_matrix_is_least_privilege(tmp_path, monkeypatch) -> None:
    _db(tmp_path, monkeypatch)
    matrix_url = f"sqlite+pysqlite:///{(tmp_path / 'access.sqlite').as_posix()}"
    with Session(create_engine(matrix_url, future=True)) as session:
        viewer_id, _viewer_key = _principal(
            session, name="matrix-viewer", role="VIEWER", scopes=[]
        )
        reviewer_id, _reviewer_key = _principal(
            session, name="matrix-reviewer", role="REVIEWER", scopes=[]
        )
        analyst_id, _analyst_key = _principal(
            session, name="matrix-analyst", role="ANALYST", scopes=[]
        )
        operator_id, _operator_key = _principal(
            session, name="matrix-operator", role="OPERATOR", scopes=[]
        )
        admin_id, _admin_key = _principal(
            session, name="matrix-admin", role="ADMIN", scopes=[]
        )
        session.commit()

    from eurogas_nexus.security.identity import AuthenticatedPrincipal

    def principal_for(pid: str, role: str, _key: str = "") -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            principal_id=pid, name=pid, principal_type="USER", role=role,
            status="ACTIVE", data_scopes=(), roles=(role,),
        )

    viewer = principal_for(viewer_id, "VIEWER")
    analyst = principal_for(analyst_id, "ANALYST")
    reviewer = principal_for(reviewer_id, "REVIEWER")
    operator = principal_for(operator_id, "OPERATOR")
    admin = principal_for(admin_id, "ADMIN")

    assert authorize(viewer, Permission.STRATEGY_CREATE).allowed is False
    assert authorize(analyst, Permission.STRATEGY_CREATE).allowed is True
    assert authorize(analyst, Permission.IDENTITY_MANAGE).allowed is False
    assert authorize(reviewer, Permission.REVIEW_RECORD).allowed is True
    assert authorize(reviewer, Permission.SOURCE_BACKFILL).allowed is False
    assert authorize(operator, Permission.SOURCE_BACKFILL).allowed is True
    assert authorize(operator, Permission.IDENTITY_MANAGE).allowed is False
    assert authorize(admin, Permission.IDENTITY_MANAGE).allowed is True
    assert authorize(admin, "unknown.permission").allowed is False


def test_access_apis_require_admin_and_record_audit(tmp_path, monkeypatch) -> None:
    _db(tmp_path, monkeypatch)
    access_url = f"sqlite+pysqlite:///{(tmp_path / 'access.sqlite').as_posix()}"
    engine = create_engine(access_url, future=True)
    with Session(engine) as session:
        admin_id, admin_key = _principal(
            session, name="access-admin", role="ADMIN", scopes=[]
        )
        analyst_id, analyst_key = _principal(
            session, name="access-analyst", role="ANALYST", scopes=["EEX"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))

    denied = client.get("/api/access/users", headers=_headers(analyst_key))
    assert denied.status_code == 403

    users = client.get("/api/access/users", headers=_headers(admin_key))
    assert users.status_code == 200
    rows = users.json()["data"]
    assert {row["principal_id"] for row in rows} >= {admin_id, analyst_id}

    patched = client.patch(
        f"/api/access/users/{analyst_id}",
        headers=_headers(admin_key),
        json={"roles": ["REVIEWER"], "data_scopes": ["ICIS"]},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["role"] == "REVIEWER"
    assert patched.json()["data"]["data_scopes"] == ["ICIS"]

    roles = client.get("/api/access/roles", headers=_headers(admin_key))
    assert "REVIEWER" in roles.json()["data"]
    sso = client.get("/api/access/sso", headers=_headers(admin_key))
    assert sso.status_code == 200

    with Session(engine) as session:
        actions = {row.action for row in session.query(AuditEventRecord).all()}
        assert "access.users.list" in actions
        assert "access.user.update" in actions


def test_api_key_lifecycle_and_disabled_owner(tmp_path, monkeypatch) -> None:
    _db(tmp_path, monkeypatch)
    key_url = f"sqlite+pysqlite:///{(tmp_path / 'access.sqlite').as_posix()}"
    engine = create_engine(key_url, future=True)
    with Session(engine) as session:
        admin_id, admin_key = _principal(
            session, name="key-admin", role="ADMIN", scopes=[]
        )
        viewer_id, _viewer_key = _principal(
            session, name="key-owner", role="VIEWER", scopes=[]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    created = client.post(
        "/api/access/api-keys",
        headers=_headers(admin_key),
        json={"principal_id": viewer_id, "display_name": "service-key", "scopes": ["market.read"]},
    )
    assert created.status_code == 200
    api_key = created.json()["data"]["api_key"]
    key_id = created.json()["data"]["key"]["key_id"]
    assert api_key.startswith("nexus_")
    assert api_key not in client.get("/api/access/api-keys", headers=_headers(admin_key)).text

    revoked = client.post(
        f"/api/access/api-keys/{key_id}/revoke",
        headers=_headers(admin_key),
    )
    assert revoked.status_code == 200
    denied = client.get("/api/health", headers=_headers(api_key))
    assert denied.status_code == 403

    # Disabled owner stops a still-unrevoked key immediately.
    with Session(engine) as session:
        _key, second_bearer = identity_repository.create_identity_api_key(
            session, viewer_id, display_name="second"
        )
        session.get(IdentityApiKeyRecord, _key.key_id)
        identity_repository.disable_identity_principal(session, viewer_id)
        session.commit()
        key_id_2 = _key.key_id
    denied_owner = client.get("/api/health", headers=_headers(second_bearer))
    assert denied_owner.status_code == 403
    assert key_id_2
