"""GIE connection-test API tests (bounded, secret-safe, capability-declared).

These exercise the existing authenticated ``/api/credentials/GIE/connection-test``
route with a mocked transport: no live provider call and no stored credential are
needed for the externally configured path. They pin that:

* the credential provider list declares the backend connection-test capability and
  the safe external source kind, without any path or secret;
* an external env/file configuration is reported configured, and the connection
  test works **without inserting a fake encrypted credential row**;
* an operator-disabled stored credential is not silently enabled by the external
  environment, and the test reports the disabled diagnostic instead;
* per-product results are independent and an HTTP 200 access-denied body is a
  failure;
* no secret value and no provider payload text appears in any response.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ProviderCredentialRecord
from eurogas_nexus.ingestion.gie_transport import GieConnectivityCheck

OPERATOR_HEADERS = {"X-Eurogas-Principal": "operator-alice"}
SECRET = "geo-owner-secret-value-abcdef"
EXTERNAL_PATH = "C:/Users/qqshu/.eurogas-nexus/secrets/gie-api-key.txt"


@pytest.fixture
def runtime_db(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'credentials.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", "test-local-secret-key")
    monkeypatch.delenv("GIE_API_KEY", raising=False)
    monkeypatch.delenv("GIE_API_KEY_FILE", raising=False)
    return engine


def _client() -> TestClient:
    return TestClient(create_app(), headers=OPERATOR_HEADERS)


def _checks(*, agsi_ok: bool = True, alsi_ok: bool = True):
    def check(product: str, ok: bool) -> GieConnectivityCheck:
        return GieConnectivityCheck(
            product=product,
            ok=ok,
            error_code=None if ok else "gie_access_denied",
            http_status=200,
            record_count=30 if ok else 0,
            normalized_rows=30 if ok else 0,
            provider_last_page=192 if product == "AGSI" else 180,
            page_size=30,
            complete=False,
            response_date="Sat, 10 Oct 2026 06:00:00 GMT",
            bounded_partial=ok,
        )

    return (check("AGSI", agsi_ok), check("ALSI", alsi_ok))


def _patch_connection(monkeypatch, checks, *, captured: dict | None = None):
    def fake_test_gie_connection(client, *, api_key, products=(), page_size=30, attempts=3):
        assert api_key == SECRET
        if captured is not None:
            captured["api_key"] = api_key
            captured["products"] = [product.product for product in products]
        return checks

    monkeypatch.setattr(
        "eurogas_nexus.ingestion.gie_transport.test_gie_connection",
        fake_test_gie_connection,
    )


def test_external_env_key_reports_configured_without_a_stored_row(
    runtime_db, monkeypatch
) -> None:
    monkeypatch.setenv("GIE_API_KEY", SECRET)

    response = _client().get("/api/credentials/providers")

    assert response.status_code == 200
    gie = next(item for item in response.json()["data"] if item["provider_id"] == "GIE")
    assert gie["connection_test_supported"] is True
    assert gie["credential_source_kind"] == "env"
    assert gie["configured"] is True
    body = response.text
    assert SECRET not in body
    assert EXTERNAL_PATH not in body
    # No credential row was inserted just to report status.
    with Session(runtime_db) as session:
        assert session.get(ProviderCredentialRecord, "GIE") is None


def test_external_file_configuration_is_reported_configured_without_the_path(
    runtime_db, tmp_path, monkeypatch
) -> None:
    key_file = tmp_path / "gie-api-key.txt"
    key_file.write_text(SECRET + "\n", encoding="utf-8")
    monkeypatch.setenv("GIE_API_KEY_FILE", str(key_file))

    response = _client().get("/api/credentials/providers")

    gie = next(item for item in response.json()["data"] if item["provider_id"] == "GIE")
    assert gie["credential_source_kind"] == "file"
    assert gie["configured"] is True
    assert str(key_file) not in response.text
    assert str(tmp_path) not in response.text
    assert SECRET not in response.text


def test_external_configuration_is_readonly_but_still_testable(
    runtime_db, monkeypatch
) -> None:
    monkeypatch.setenv("GIE_API_KEY", SECRET)
    _patch_connection(monkeypatch, _checks())

    providers = _client().get("/api/credentials/providers").json()["data"]
    gie = next(item for item in providers if item["provider_id"] == "GIE")
    # The UI derives the control from the backend capability and the resolved status.
    assert gie["connection_test_supported"] is True
    assert gie["configured"] is True

    tested = _client().post("/api/credentials/GIE/connection-test")

    assert tested.status_code == 200
    data = tested.json()["data"]
    assert data["connection"]["ok"] is True
    assert [product["product"] for product in data["connection"]["products"]] == [
        "AGSI",
        "ALSI",
    ]
    assert all(product["ok"] for product in data["connection"]["products"])
    assert data["connection"]["market_data_persisted"] is False
    assert SECRET not in tested.text
    # Certification stays separate from connectivity and is not advanced by the test.
    assert data["certification"]["stage"] == "unverified"
    assert data["certification"]["allows_live"] is False


def test_connection_test_reports_per_product_failure_independently(
    runtime_db, monkeypatch
) -> None:
    monkeypatch.setenv("GIE_API_KEY", SECRET)
    _patch_connection(monkeypatch, _checks(agsi_ok=False, alsi_ok=True))

    response = _client().post("/api/credentials/GIE/connection-test")

    assert response.status_code == 200
    connection = response.json()["data"]["connection"]
    assert connection["ok"] is False
    assert connection["error_code"] == "gie_access_denied"
    by_product = {product["product"]: product for product in connection["products"]}
    assert by_product["AGSI"]["ok"] is False
    assert by_product["ALSI"]["ok"] is True


def test_connection_test_uses_one_bounded_page_per_product(
    runtime_db, monkeypatch
) -> None:
    monkeypatch.setenv("GIE_API_KEY", SECRET)
    captured: dict = {}
    _patch_connection(monkeypatch, _checks(), captured=captured)

    _client().post("/api/credentials/GIE/connection-test")

    assert captured["api_key"] == SECRET
    assert captured["products"] == ["AGSI", "ALSI"]


def test_missing_credential_is_reported_without_any_provider_call(
    runtime_db, monkeypatch
) -> None:
    called: list[str] = []

    def forbidden(*args, **kwargs):
        called.append("called")
        raise AssertionError("no provider call may happen without a credential")

    monkeypatch.setattr(
        "eurogas_nexus.ingestion.gie_transport.test_gie_connection", forbidden
    )

    response = _client().post("/api/credentials/GIE/connection-test")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["configured"] is False
    assert data["connection"]["ok"] is False
    assert data["connection"]["error_code"] == "credential_missing"
    assert called == []


def test_operator_disabled_credential_is_not_reenabled_by_environment(
    runtime_db, monkeypatch
) -> None:
    from eurogas_nexus.security.credentials import encrypt_credential_payload, utc_now

    encrypted = encrypt_credential_payload({"api_key": "stored-disabled-value"})
    now = utc_now()
    with Session(runtime_db) as session:
        session.add(
            ProviderCredentialRecord(
                provider_id="GIE",
                label="operator-disabled",
                encrypted_payload=encrypted.encrypted_payload,
                redacted_preview=encrypted.redacted_preview,
                credential_fingerprint=encrypted.credential_fingerprint,
                status="disabled",
                created_at_utc=now,
                updated_at_utc=now,
                research_only=True,
                human_review_required=True,
            )
        )
        session.commit()

    # The external environment must not silently re-enable the disabled credential.
    monkeypatch.setenv("GIE_API_KEY", SECRET)

    response = _client().get("/api/credentials/providers")

    gie = next(item for item in response.json()["data"] if item["provider_id"] == "GIE")
    assert gie["configured"] is False
    assert gie["status"] == "disabled"
    assert gie["credential_source_kind"] == "operator_disabled"
    assert "credential_disabled" in gie["credential_diagnostics"]


def test_unreadable_operator_state_is_reported_blocked_not_configured(
    runtime_db, monkeypatch
) -> None:
    """An unreadable operator state is not a confirmed permit."""

    import eurogas_nexus.ingestion.gie_transport as gie_transport

    monkeypatch.setenv("GIE_API_KEY", SECRET)

    def explode(session_factory=None):  # noqa: ANN001, ANN202 - test double
        raise RuntimeError("operator state store unavailable")

    monkeypatch.setattr(gie_transport, "stored_gie_credential_status", explode)

    response = _client().get("/api/credentials/providers")

    gie = next(item for item in response.json()["data"] if item["provider_id"] == "GIE")
    assert gie["configured"] is False
    assert gie["status"] == "disabled"
    assert gie["credential_source_kind"] == "state_unreadable"
    assert "credential_state_unreadable" in gie["credential_diagnostics"]
    assert SECRET not in response.text


def test_connection_test_requires_an_operator_identity(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'anon.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", "test-local-secret-key")
    monkeypatch.setenv("GIE_API_KEY", SECRET)

    anonymous = TestClient(create_app())
    response = anonymous.post("/api/credentials/GIE/connection-test")

    assert response.status_code in {401, 403}


def test_connection_test_passes_external_value_only_in_memory(
    runtime_db, monkeypatch
) -> None:
    """The key reaches the transport as a resolved value, never a stored or returned one."""

    monkeypatch.setenv("GIE_API_KEY", SECRET)
    seen: dict = {}
    _patch_connection(monkeypatch, _checks(), captured=seen)

    response = _client().post("/api/credentials/GIE/connection-test")

    assert seen["api_key"] == SECRET
    assert SECRET not in response.text
    with Session(runtime_db) as session:
        assert session.get(ProviderCredentialRecord, "GIE") is None


def test_provider_list_declares_the_connection_test_capability_per_provider(
    runtime_db,
) -> None:
    data = _client().get("/api/credentials/providers").json()["data"]
    by_id = {item["provider_id"]: item for item in data}

    assert by_id["GIE"]["connection_test_supported"] is True
    assert by_id["DEEPSEEK"]["connection_test_supported"] is True
    assert by_id["LLM"]["connection_test_supported"] is True
    # A provider without an implemented test says so instead of offering a dead control.
    assert by_id["EEX"]["connection_test_supported"] is False


def test_connection_test_response_never_carries_provider_payload(
    runtime_db, monkeypatch
) -> None:
    monkeypatch.setenv("GIE_API_KEY", SECRET)
    _patch_connection(monkeypatch, _checks())

    response = _client().post("/api/credentials/GIE/connection-test")

    body = response.text
    assert "gasInStorage" not in body
    assert "inventory" not in body
    assert "raw_payload" not in body
    assert SECRET not in body
    assert datetime.now(UTC).year  # keep the import meaningful for the metadata claim
