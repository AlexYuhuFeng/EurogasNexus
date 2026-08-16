"""Provider certification gate API tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord, ProviderCredentialRecord

CERT_URL = "/api/internal/sources/certification"
VALID_CERTIFICATION = {
    "source_system": "EEX",
    "stage": "live_validated",
    "checks": ["simulated_shape_match", "live_sample_validation"],
    "evidence": {"reference": "eex-replay-2026-07"},
    "note": "first live gate",
}


def _internal_client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="internal")))


def _auth_headers() -> dict[str, str]:
    return {
        "X-Eurogas-Principal": "ops-user",
        "X-Eurogas-Internal-Token": "test-internal-token",
    }


def test_certification_write_rejects_missing_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", "test-internal-token")

    response = _internal_client().post(CERT_URL, json=VALID_CERTIFICATION)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "internal_api_token_missing"


def test_certification_write_fails_closed_without_configured_token(monkeypatch) -> None:
    monkeypatch.delenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", raising=False)

    response = _internal_client().post(
        CERT_URL,
        headers=_auth_headers(),
        json=VALID_CERTIFICATION,
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "internal_api_token_not_configured"


def test_certification_write_rejects_invalid_payload_before_db(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", "test-internal-token")
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = _internal_client().post(
        CERT_URL,
        headers=_auth_headers(),
        json={**VALID_CERTIFICATION, "stage": "blessed"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_certification"


def test_certification_write_requires_runtime_db(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", "test-internal-token")
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = _internal_client().post(
        CERT_URL,
        headers=_auth_headers(),
        json=VALID_CERTIFICATION,
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_required"


def test_certified_source_goes_native_live_uncertified_does_not(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "certification.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    observed_at = datetime(2026, 7, 1, 10, 15, tzinfo=UTC)
    with Session(engine) as session:
        for source_system in ("EEX", "ICIS"):
            session.add(
                MarketObservationRecord(
                    observation_id=f"market-{source_system.lower()}",
                    market_venue="EEX",
                    product="TTF day-ahead",
                    price=33.0,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=observed_at,
                    period_end_utc=observed_at,
                    observed_at_utc=observed_at,
                    source_system=source_system,
                    source_reference=f"fixture:{source_system.lower()}",
                    freshness="fresh",
                    quality_score=1.0,
                    research_only=True,
                )
            )
            session.add(
                ProviderCredentialRecord(
                    provider_id=source_system,
                    label=f"{source_system} test credential",
                    encrypted_payload="test-only-encrypted-payload",
                    redacted_preview="test***",
                    credential_fingerprint=f"test-{source_system.lower()}",
                    status="configured",
                    created_at_utc=observed_at,
                    updated_at_utc=observed_at,
                    last_tested_at_utc=observed_at,
                    last_test_status="connection_test_success",
                    last_test_message="Validated test fixture.",
                    research_only=True,
                    human_review_required=True,
                )
            )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", "test-internal-token")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = _internal_client()
    response = client.post(
        CERT_URL,
        headers=_auth_headers(),
        json=VALID_CERTIFICATION,
    )
    assert response.status_code == 200
    assert response.json()["data"]["stage"] == "live_validated"

    sources_response = client.get("/api/sources")
    assert sources_response.status_code == 200
    sources = {row["source_system"]: row for row in sources_response.json()["data"]}

    eex = sources["EEX"]
    assert eex["certification_stage"] == "live_validated"
    assert eex["certification_allows_live"] is True
    assert eex["operational_status"] == "active"
    assert eex["workflow_ready"] is True

    icis = sources["ICIS"]
    assert icis["certification_stage"] == "unverified"
    assert icis["certification_allows_live"] is False
    assert icis["operational_status"] == "active_uncertified"
    assert icis["workflow_ready"] is False
    assert "certification_required" in icis["diagnostics"]
