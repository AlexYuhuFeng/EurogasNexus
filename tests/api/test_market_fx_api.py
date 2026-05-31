"""Market FX API tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FxObservationRecord


def test_market_fx_returns_ecb_fallback_when_db_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/v1/market/fx")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["source_system"] == "ECB"
    assert response.json()["meta"]["source_references"] == ["synthetic-fixture"]


def test_market_fx_reads_ecb_rates_from_runtime_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "fx.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 5, 29, 12, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            FxObservationRecord(
                observation_id="ecb-fx-2026-05-29-gbp",
                pair="EURGBP",
                base_currency="EUR",
                quote_currency="GBP",
                rate=0.851,
                rate_type="reference",
                value_date="2026-05-29",
                observed_at_utc=now,
                source_system="ECB",
                source_reference="ecb-eurofxref-daily",
                freshness="live",
                research_only=True,
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/v1/market/fx")

    assert response.status_code == 200
    assert response.json()["meta"]["source_references"] == ["runtime-postgresql"]
    assert response.json()["data"][0]["pair"] == "EURGBP"
    assert response.json()["data"][0]["source_system"] == "ECB"
