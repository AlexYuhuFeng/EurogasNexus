"""CR-10 origin/CSRF guard tests."""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.db.repositories.security import create_session


def _setup(tmp_path, monkeypatch):
    db_path = tmp_path / "csrf.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    token = "csrf-session-token"
    with Session(engine) as session:
        principal = identity_repository.create_identity_principal(
            session,
            name="csrf-user",
            display_name="CSRF User",
            role="VIEWER",
            data_scopes=[],
        )
        create_session(session, principal_id=principal.principal_id, token=token)
        session.commit()
    return token


def test_cookie_mutation_requires_origin_and_csrf(tmp_path, monkeypatch) -> None:
    token = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    cookie = f"eurogas_session={token}"

    missing = client.post("/api/auth/logout", headers={"Cookie": cookie})
    assert missing.status_code == 403
    assert missing.json()["error"] == "origin_not_allowed"

    wrong_csrf = client.post(
        "/api/auth/logout",
        headers={"Cookie": cookie, "Origin": "http://testserver", "X-Eurogas-CSRF": "bad"},
    )
    assert wrong_csrf.status_code == 403
    assert wrong_csrf.json()["error"] == "csrf_invalid"

    csrf = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    ok = client.post(
        "/api/auth/logout",
        headers={
            "Cookie": cookie,
            "Origin": "http://testserver",
            "X-Eurogas-CSRF": csrf,
        },
    )
    assert ok.status_code == 200


def test_api_key_mutations_are_not_cookie_guarded(tmp_path, monkeypatch) -> None:
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "public-token")
    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(
        "/api/auth/logout",
        headers={"X-Eurogas-Api-Key": "public-token"},
    )
    # No cookie -> no origin guard; the route itself is permitted.
    assert response.status_code == 200
