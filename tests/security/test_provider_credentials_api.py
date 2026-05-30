"""Provider credential API tests."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ProviderCredentialRecord


def test_credential_write_requires_secret_key(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'credentials.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("EUROGAS_NEXUS_SECRET_KEY", raising=False)

    response = TestClient(create_app()).put(
        "/api/v1/credentials/GIE",
        json={"api_key": "secret-value", "label": "local-gie"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "credential_store_not_configured"


def test_credentials_are_encrypted_and_redacted(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'credentials.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", "test-local-secret-key")

    client = TestClient(create_app())
    response = client.put(
        "/api/v1/credentials/GIE",
        json={"api_key": "secret-value", "label": "local-gie"},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["provider_id"] == "GIE"
    assert body["configured"] is True
    assert body["redacted_preview"].startswith("se")
    assert "secret-value" not in response.text

    with Session(engine) as session:
        row = session.get(ProviderCredentialRecord, "GIE")
        assert row is not None
        assert "secret-value" not in row.encrypted_payload
        assert row.redacted_preview != "secret-value"

    list_response = client.get("/api/v1/credentials/providers")
    assert list_response.status_code == 200
    assert "secret-value" not in list_response.text
