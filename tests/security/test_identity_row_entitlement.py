"""Row-level commercial-data entitlement tests for R32 identities."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _market_row(
    observation_id: str,
    source_system: str,
    *,
    hub: str,
    now: datetime,
) -> MarketObservationRecord:
    return MarketObservationRecord(
        observation_id=observation_id,
        market_venue="EEX" if source_system == "EEX_Sim" else "ENTSOG",
        product=f"{hub} Day-Ahead",
        price=31.0,
        unit="EUR/MWh",
        currency="EUR",
        period_start_utc=now,
        period_end_utc=now,
        observed_at_utc=now,
        source_system=source_system,
        source_reference=f"test:{source_system}",
        source_record_id=f"{source_system}-1",
        freshness="live",
        quality_score=0.9,
        research_only=True,
        metadata_json={"hub": hub},
    )


def test_market_observation_rows_are_filtered_by_identity_data_scopes(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "entitlement.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(_market_row("m-eex", "EEX_Sim", hub="TTF", now=now))
        session.add(_market_row("m-entsog", "ENTSOG", hub="NBP", now=now))
        principal = create_identity_principal(
            session,
            name="scoped-analyst",
            display_name="Scoped Analyst",
            role="ANALYST",
            data_scopes=["ENTSOG"],
        )
        _, bearer = create_identity_api_key(
            session,
            principal.principal_id,
            display_name="test-key",
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    headers = {
        "X-Eurogas-Api-Key": PUBLIC_TOKEN,
        "X-Eurogas-Identity": bearer,
    }

    response = client.get("/api/market/observations", headers=headers)

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["observation_id"] for row in rows] == ["m-entsog"]
    assert all(row["source_system"] == "ENTSOG" for row in rows)


def test_legacy_public_token_retains_unfiltered_market_view(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "legacy-entitlement.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(_market_row("m-eex", "EEX_Sim", hub="TTF", now=now))
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.get(
        "/api/market/observations",
        headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN},
    )

    assert response.status_code == 200
    assert [row["observation_id"] for row in response.json()["data"]] == ["m-eex"]
