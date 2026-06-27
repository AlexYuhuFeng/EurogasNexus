"""Integration tests for DB-backed GIE AGSI/ALSI observation API reads."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import LngObservationRecord, StorageObservationRecord


def test_storage_and_lng_api_read_configured_runtime_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "gie-observations.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            StorageObservationRecord(
                observation_id="gie-agsi-test",
                source_dataset="AGSI",
                facility_id="EU",
                facility_name="EU",
                country="EU",
                inventory_twh=650.25,
                working_capacity_twh=1100.50,
                fill_pct=59.1,
                injection_twh_d=2.5,
                withdrawal_twh_d=1.2,
                period_start_utc=datetime(2026, 5, 29, tzinfo=UTC),
                period_end_utc=datetime(2026, 5, 30, tzinfo=UTC),
                observed_at_utc=datetime(2026, 5, 29, 12, tzinfo=UTC),
                source_system="GIE",
                source_reference="test",
                freshness="live",
                research_only=True,
            )
        )
        session.add(
            LngObservationRecord(
                observation_id="gie-alsi-test",
                source_dataset="ALSI",
                terminal_id="EU",
                terminal_name="EU LNG",
                country="EU",
                inventory_twh=42.5,
                send_out_twh_d=3.4,
                dtmi_pct=65.0,
                period_start_utc=datetime(2026, 5, 29, tzinfo=UTC),
                period_end_utc=datetime(2026, 5, 30, tzinfo=UTC),
                observed_at_utc=datetime(2026, 5, 29, 12, tzinfo=UTC),
                source_system="GIE",
                source_reference="test",
                freshness="live",
                research_only=True,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())

    storage_response = client.get("/api/storage/observations")
    lng_response = client.get("/api/lng/observations")

    assert storage_response.status_code == 200
    assert lng_response.status_code == 200
    assert storage_response.json()["data"][0]["observation_id"] == "gie-agsi-test"
    assert lng_response.json()["data"][0]["observation_id"] == "gie-alsi-test"
    assert storage_response.json()["meta"]["source_references"] == ["runtime-postgresql"]
    assert lng_response.json()["meta"]["source_references"] == ["runtime-postgresql"]
