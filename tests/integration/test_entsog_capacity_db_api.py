"""Integration tests for DB-backed ENTSOG capacity observation API reads."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import CapacityObservationRecord


def test_capacity_api_reads_configured_runtime_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "entsog-capacity.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            CapacityObservationRecord(
                observation_id="entsog-capacity-test",
                point_id="BE-IUK-ZEEBRUGGE-ENTRY",
                point_name="Zeebrugge Interconnector Entry",
                direction="entry",
                capacity_type="firm_technical",
                capacity_mcm_d=112.5,
                original_value=1186875000,
                original_unit="kwh/d",
                period_start_utc=datetime(2026, 6, 1, tzinfo=UTC),
                period_end_utc=datetime(2026, 6, 2, tzinfo=UTC),
                observed_at_utc=datetime(2026, 6, 1, 12, tzinfo=UTC),
                source_system="ENTSOG",
                source_reference="entsog-operationaldatas",
                source_record_id="cap-test",
                freshness="live",
                research_only=True,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.get("/api/physical/capacity")
    sources_response = client.get("/api/sources")

    assert response.status_code == 200
    payload = response.json()
    # The legacy row is stored, but its kWh -> assumed-CV volume is not admissible.
    assert payload["data"] == []
    assert payload["meta"]["source_references"] == ["runtime-postgresql"]
    warnings = " ".join(payload["meta"]["warnings"]).lower()
    assert "legacy entsog" in warnings
    assert "does not mean" in warnings
    entsog_source = next(
        source for source in sources_response.json()["data"] if source["source_system"] == "ENTSOG"
    )
    # Storage/ingestion count is retained; it is not an eligible quantity count.
    assert entsog_source["live_record_count"] == 1
