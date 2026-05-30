"""Integration tests for DB-backed reference-network API reads."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.reference_network import ReferenceNode


def test_reference_network_api_reads_configured_runtime_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "reference-network.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            ReferenceNode(
                id="node-db-test",
                name="DB Test Hub",
                node_type="hub",
                country="NL",
                lat=52.0,
                lon=5.0,
                capacity_boe_d=None,
                metadata_json={"fixture": True},
                created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())

    response = client.get("/api/v1/reference-network/nodes")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == [
        {
            "id": "node-db-test",
            "name": "DB Test Hub",
            "node_type": "hub",
            "country": "NL",
            "lat": 52.0,
            "lon": 5.0,
            "capacity_boe_d": None,
            "metadata_json": {"fixture": True},
        }
    ]
    assert body["meta"]["source_references"] == ["runtime-postgresql"]

    missing_response = client.get("/api/v1/reference-network/nodes/node-ttf")
    assert missing_response.status_code == 404
