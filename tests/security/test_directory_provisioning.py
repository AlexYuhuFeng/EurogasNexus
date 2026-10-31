"""Directory mode: SSO users are created on first sign-in and follow their groups after."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IdentityPrincipalRecord

SECRET = "g" * 40


def test_gateway_users_are_provisioned_and_follow_directory_groups(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'dir.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    env = {
        "RUNTIME_STORE_DATABASE_URL": url,
        "EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED": "true",
        "EUROGAS_NEXUS_GATEWAY_SECRET": SECRET,
        "EUROGAS_NEXUS_OIDC_PROVISIONING_MODE": "directory",
        "EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP": (
            '{"EGN-UK-Traders": "ANALYST", "EGN-Heads": "OPERATOR"}'
        ),
        "EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP": (
            '{"EGN-UK-Traders": ["EEX", "BOOKS:ENTITY:EGN-UK"], "EGN-Heads": ["BOOKS:*"]}'
        ),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app())

    def me(groups, office="UK"):
        return client.get(
            "/api/me",
            headers={
                "X-Remote-User": "CORP\\asmith",
                "X-Remote-Groups": groups,
                "X-Remote-Office": office,
                "X-Remote-Email": "asmith@corp.example",
                "X-Eurogas-Gateway-Secret": SECRET,
            },
        )

    first = me("EGN-UK-Traders")
    assert first.status_code == 200, first.text
    with Session(engine) as session:
        (row,) = session.query(IdentityPrincipalRecord).all()
        assert row.status == "ACTIVE" and row.identity_source == "GATEWAY"
        assert row.role == "ANALYST" and row.office == "UK"
        assert sorted(row.data_scopes) == ["BOOKS:ENTITY:EGN-UK", "EEX"]
        principal_id = row.principal_id
    assert first.json()["data"]["principal_id"] == principal_id

    # Promoted in the directory: the next request carries the new access.
    me("EGN-UK-Traders,EGN-Heads")
    with Session(engine) as session:
        row = session.get(IdentityPrincipalRecord, principal_id)
        assert row.role == "OPERATOR" and "BOOKS:*" in row.data_scopes
        assert session.query(IdentityPrincipalRecord).count() == 1
        row.status = "DISABLED"  # a local administrator's decision wins
        session.commit()
    assert me("EGN-Heads").status_code == 403
