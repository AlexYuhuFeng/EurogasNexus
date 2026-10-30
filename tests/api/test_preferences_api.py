"""Personal preferences follow the principal; organisation defaults belong to admins."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base


def _clients(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'prefs.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    bearers = {}
    with Session(engine) as session:
        for name, role in (("trader", "ANALYST"), ("other", "ANALYST"), ("admin", "ADMIN")):
            principal = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _, bearers[name] = create_identity_api_key(
                session, principal.principal_id, scopes=["*"]
            )
        session.commit()
    app = create_app()
    return {
        name: TestClient(
            app,
            headers={
                "X-Eurogas-Api-Key": "test-public-api-token",
                "X-Eurogas-Identity": bearer,
            },
        )
        for name, bearer in bearers.items()
    }


def test_preferences_are_per_person_and_merge_over_organisation_defaults(tmp_path, monkeypatch):
    clients = _clients(tmp_path, monkeypatch)
    initial = clients["trader"].get("/api/me/preferences")
    assert initial.status_code == 200, initial.text
    assert initial.json()["data"]["effective"]["theme"] == "system"

    saved = clients["trader"].put(
        "/api/me/preferences", json={"theme": "dark", "market_board_layout": "ladder"}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["personal"] == {"theme": "dark", "market_board_layout": "ladder"}
    # Another person is untouched.
    assert clients["other"].get("/api/me/preferences").json()["data"]["personal"] == {}

    org = clients["admin"].put(
        "/api/settings/organisation", json={"market_view": "network", "theme": "light"}
    )
    assert org.status_code == 200, org.text
    effective = clients["trader"].get("/api/me/preferences").json()["data"]["effective"]
    assert effective["theme"] == "dark"  # personal wins
    assert effective["market_view"] == "network"  # organisation default applies

    cleared = clients["trader"].put("/api/me/preferences", json={"theme": None})
    assert cleared.json()["data"]["effective"]["theme"] == "light"


def test_bad_values_and_non_admin_organisation_writes_are_refused(tmp_path, monkeypatch):
    clients = _clients(tmp_path, monkeypatch)
    bad = clients["trader"].put("/api/me/preferences", json={"theme": "neon"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "preference_invalid"
    denied = clients["trader"].put("/api/settings/organisation", json={"theme": "dark"})
    assert denied.status_code == 403
    assert clients["trader"].get("/api/settings/organisation").status_code == 200
