"""SSO pre-provisioning: an administrator adds a person before their first company sign-in."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.enterprise_auth import _principal_for_identity
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, IdentityPrincipalRecord
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.security import rate_limit as rate_limit_module
from eurogas_nexus.security.oidc import OidcIdentity, OidcValidationError

ISSUER = "https://idp.example.test"
PUBLIC_TOKEN = "test-public-api-token"


@pytest.fixture
def sso_store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'sso.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_TOKEN)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", "nexus")
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_PROVISIONING_MODE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rate_limit_module._WINDOWS.clear()
    with Session(engine) as session:
        admin = identity_repository.create_identity_principal(
            session, name="sso-admin", display_name="Admin", role="ADMIN"
        )
        _key, bearer = identity_repository.create_identity_api_key(session, admin.principal_id)
        session.commit()
    return engine, bearer


def _identity(subject: str, email: str | None, verified: bool | None = None) -> OidcIdentity:
    return OidcIdentity(
        subject=subject,
        name="Ana Risk",
        role="VIEWER",
        data_scopes=(),
        issuer=ISSUER,
        email=email,
        email_verified=verified,
    )


def _invite(bearer: str, **body) -> dict:
    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(
        "/api/access/users",
        headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer},
        json={"kind": "sso", "display_name": "Ana Risk", **body},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert "one_time_password" not in data
    return data["user"]


def test_invited_by_email_is_linked_and_activated_at_first_sign_in(sso_store):
    engine, bearer = sso_store
    user = _invite(
        bearer,
        email="Ana.Risk@Corp.example",
        roles=["REVIEWER"],
        job_functions=["RISK_MANAGER"],
    )
    assert user["account_state"] == "INVITED" and user["account_kind"] == "sso"
    with Session(engine) as session:
        principal = _principal_for_identity(
            session, _identity("sub-123", "ana.risk@corp.example"), now_utc=None
        )
        session.commit()
        assert principal.principal_id == user["principal_id"]
        assert principal.status == "ACTIVE" and principal.roles == ["REVIEWER"]
        assert principal.job_functions == ["RISK_MANAGER"]
        actions = {e.action for e in session.query(AuditEventRecord).all()}
        assert {"access.user.invite", "access.user.invite_accepted"} <= actions
        # The second sign-in uses the link, not the address.
        again = _principal_for_identity(session, _identity("sub-123", None), now_utc=None)
        assert again.principal_id == user["principal_id"]


def test_an_unverified_address_does_not_claim_an_invite(sso_store):
    engine, bearer = sso_store
    _invite(bearer, email="ana.risk@corp.example")
    with Session(engine) as session:
        with pytest.raises(OidcValidationError):
            _principal_for_identity(
                session, _identity("sub-x", "ana.risk@corp.example", verified=False), now_utc=None
            )


def test_invited_by_subject_matches_that_subject_only(sso_store):
    engine, bearer = sso_store
    user = _invite(bearer, email="ana.risk@corp.example", subject="sub-pinned")
    with Session(engine) as session:
        # Same address, another subject: not this invite.
        with pytest.raises(OidcValidationError):
            _principal_for_identity(
                session, _identity("sub-other", "ana.risk@corp.example"), now_utc=None
            )
        principal = _principal_for_identity(
            session, _identity("sub-pinned", "someone@else.example"), now_utc=None
        )
        assert principal.principal_id == user["principal_id"] and principal.status == "ACTIVE"


def test_a_disabled_invite_never_signs_in(sso_store):
    engine, bearer = sso_store
    user = _invite(bearer, email="ana.risk@corp.example")
    with Session(engine) as session:
        session.get(IdentityPrincipalRecord, user["principal_id"]).status = "DISABLED"
        session.commit()
        with pytest.raises(OidcValidationError):
            _principal_for_identity(
                session, _identity("sub-123", "ana.risk@corp.example"), now_utc=None
            )


def test_sso_invites_need_sso_configured(sso_store, monkeypatch):
    _engine, bearer = sso_store
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_ISSUER")
    client = TestClient(create_app(Settings(api_profile="release")))
    refused = client.post(
        "/api/access/users",
        headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer},
        json={"kind": "sso", "email": "x@corp.example"},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "sso_not_configured"
