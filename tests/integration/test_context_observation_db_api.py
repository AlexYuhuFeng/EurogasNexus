"""Integration tests for DB-backed context observation API reads."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord, MarketObservationRecord


def test_market_and_flow_api_read_configured_runtime_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "context-observations.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            MarketObservationRecord(
                observation_id="mkt-db-test",
                market_venue="TTF",
                product="day-ahead",
                price=40.25,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=datetime(2026, 5, 29, tzinfo=UTC),
                period_end_utc=datetime(2026, 5, 30, tzinfo=UTC),
                observed_at_utc=datetime(2026, 5, 29, 12, tzinfo=UTC),
                source_system="synthetic-fixture",
                source_reference="test",
                freshness="fresh",
                quality_score=1.0,
                research_only=True,
            )
        )
        session.add(
            FlowObservationRecord(
                observation_id="flow-db-test",
                point_id="node-ttf",
                point_name="TTF Hub",
                direction="entry",
                flow_mcm_d=87.5,
                period_start_utc=datetime(2026, 5, 29, tzinfo=UTC),
                period_end_utc=datetime(2026, 5, 30, tzinfo=UTC),
                observed_at_utc=datetime(2026, 5, 29, 12, tzinfo=UTC),
                source_system="synthetic-fixture",
                source_reference="test",
                freshness="fresh",
                research_only=True,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())

    market_response = client.get("/api/market/observations")
    flow_response = client.get("/api/physical/flows")

    assert market_response.status_code == 200
    assert flow_response.status_code == 200
    assert market_response.json()["data"][0]["observation_id"] == "mkt-db-test"
    assert flow_response.json()["data"][0]["observation_id"] == "flow-db-test"
    assert market_response.json()["meta"]["source_references"] == ["runtime-postgresql"]
    assert flow_response.json()["meta"]["source_references"] == ["runtime-postgresql"]
