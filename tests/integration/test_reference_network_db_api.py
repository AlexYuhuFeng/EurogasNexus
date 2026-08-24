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
                source_system="TEST",
                source_dataset="reference-network-fixture",
                source_reference="test-reference-network-db-api",
                source_record_id="node-db-test",
                data_quality="fixture",
                metadata_json={"fixture": True},
                created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())

    response = client.get("/api/reference-network/nodes")

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
            "source_system": "TEST",
            "source_dataset": "reference-network-fixture",
            "source_reference": "test-reference-network-db-api",
            "source_record_id": "node-db-test",
            "data_quality": "fixture",
            "metadata_json": {"fixture": True},
        }
    ]
    assert body["meta"]["source_references"] == ["runtime-postgresql"]

    missing_response = client.get("/api/reference-network/nodes/node-ttf")
    assert missing_response.status_code == 404


def test_market_hubs_serve_effective_period_and_supersession(tmp_path, monkeypatch) -> None:
    """Gate 2: the hub DB reference master serves validity + supersession."""

    from eurogas_nexus.db.models import ReferenceMarketHub

    db_path = tmp_path / "market-hubs.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with Session(engine) as session:
        session.add_all(
            [
                ReferenceMarketHub(
                    id="hub-the",
                    name="Trading Hub Europe",
                    hub_code="THE",
                    country="DE",
                    market_area="DE",
                    valid_from_utc=datetime(2021, 10, 1, tzinfo=UTC),
                    valid_to_utc=None,
                    superseded_by_hub_id=None,
                    description="German market area.",
                    source_system="preview-configuration",
                    source_dataset="market_hubs",
                    source_reference="preview-configuration:market-hubs:THE",
                    source_record_id="the",
                    data_quality="confirmed",
                    created_at_utc=now,
                ),
                ReferenceMarketHub(
                    id="hub-ncg",
                    name="NetConnect Germany",
                    hub_code="NCG",
                    country="DE",
                    market_area="DE-NCG",
                    valid_from_utc=datetime(2009, 1, 1, tzinfo=UTC),
                    valid_to_utc=datetime(2021, 9, 30, 22, 59, 59, tzinfo=UTC),
                    superseded_by_hub_id="hub-the",
                    description="Historical German market area.",
                    source_system="preview-configuration",
                    source_dataset="market_hubs",
                    source_reference="preview-configuration:market-hubs:NCG",
                    source_record_id="ncg",
                    data_quality="confirmed",
                    created_at_utc=now,
                ),
            ]
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.get("/api/reference-network/market-hubs")

    assert response.status_code == 200
    by_code = {hub["hub_code"]: hub for hub in response.json()["data"]}
    assert by_code["THE"]["market_area"] == "DE"
    assert by_code["THE"]["valid_to_utc"] is None
    assert by_code["THE"]["superseded_by_hub_id"] is None
    assert by_code["NCG"]["superseded_by_hub_id"] == "hub-the"
    assert by_code["NCG"]["valid_from_utc"].startswith("2009-01-01")
    assert by_code["NCG"]["valid_to_utc"].startswith("2021-09-30")
