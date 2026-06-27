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
        "/api/credentials/GIE",
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
        "/api/credentials/GIE",
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

    list_response = client.get("/api/credentials/providers")
    assert list_response.status_code == 200
    assert "secret-value" not in list_response.text


def test_credential_rotation_disable_and_local_validation_are_write_only(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'credentials.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", "test-local-secret-key")

    client = TestClient(create_app())
    first = client.put(
        "/api/credentials/GIE",
        json={"api_key": "first-secret-value", "label": "local-gie"},
    )
    assert first.status_code == 200
    with Session(engine) as session:
        first_row = session.get(ProviderCredentialRecord, "GIE")
        assert first_row is not None
        first_fingerprint = first_row.credential_fingerprint

    rotated = client.post(
        "/api/credentials/GIE/rotate",
        json={"api_key": "second-secret-value", "label": "rotated-gie"},
    )
    assert rotated.status_code == 200
    assert rotated.json()["data"]["status"] == "configured"
    assert "second-secret-value" not in rotated.text
    with Session(engine) as session:
        rotated_row = session.get(ProviderCredentialRecord, "GIE")
        assert rotated_row is not None
        assert rotated_row.credential_fingerprint != first_fingerprint
        assert rotated_row.label == "rotated-gie"

    local_test = client.post("/api/credentials/GIE/local-validation")
    assert local_test.status_code == 200
    assert local_test.json()["data"]["last_test_status"] == "local_validation_passed"
    assert "second-secret-value" not in local_test.text

    disabled = client.patch(
        "/api/credentials/GIE/status",
        json={"status": "disabled", "reason": "operator rotation window"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["configured"] is False
    assert disabled.json()["data"]["status"] == "disabled"
    assert "second-secret-value" not in disabled.text
    with Session(engine) as session:
        disabled_row = session.get(ProviderCredentialRecord, "GIE")
        assert disabled_row is not None
        assert disabled_row.status == "disabled"
        assert "second-secret-value" not in disabled_row.encrypted_payload

    listed = client.get("/api/credentials/providers")
    assert listed.status_code == 200
    gie = next(item for item in listed.json()["data"] if item["provider_id"] == "GIE")
    assert gie["configured"] is False
    assert gie["status"] == "disabled"
    assert "second-secret-value" not in listed.text


def test_public_provider_credentials_cannot_be_rotated_or_disabled() -> None:
    client = TestClient(create_app())

    rotate = client.post(
        "/api/credentials/ECB/rotate",
        json={"api_key": "not-needed", "label": "ecb"},
    )
    disable = client.patch(
        "/api/credentials/ECB/status",
        json={"status": "disabled", "reason": "not applicable"},
    )

    assert rotate.status_code == 400
    assert rotate.json()["detail"]["code"] == "credential_not_required"
    assert disable.status_code == 400
    assert disable.json()["detail"]["code"] == "credential_not_required"


def test_provider_registry_covers_v1_source_center() -> None:
    response = TestClient(create_app()).get("/api/credentials/providers")
    assert response.status_code == 200

    providers = {item["provider_id"]: item for item in response.json()["data"]}
    assert providers["ECB"]["credential_required"] is False
    assert providers["ENTSOG"]["credential_required"] is False
    for provider_id in {
        "Argus",
        "DEEPSEEK",
        "EEX",
        "GIE",
        "ICE_OCM",
        "ICIS",
        "Kpler",
        "Platts",
        "Trayport",
        "Weather",
    }:
        assert providers[provider_id]["credential_required"] is True
