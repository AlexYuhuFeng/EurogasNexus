"""DB-backed route-cost API tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import TsoTariffRecord, UpstreamResourceContractRecord


def test_route_cost_api_reads_tariffs_from_runtime_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "route-cost.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with Session(engine) as session:
        session.add(
            TsoTariffRecord(
                tariff_id="db-easington-entry-2025",
                document_id="db-national-gas-doc",
                country="UK",
                tso="National Gas NTS",
                market_area="NTS",
                gas_year="2025/26",
                point_id="uk-ng-nts-easington-beach",
                source_point_name="Easington Beach Terminal",
                direction="ENTRY",
                capacity_product="DAILY",
                firmness="FIRM",
                tariff_value=0.1086,
                currency="GBP",
                unit="p/kWh/day",
                effective_from=now,
                effective_to=None,
                tariff_status="FINAL",
                source_table="Table 4 Entry Capacity Reserve Prices",
                source_page=12,
                source_refs=["National Gas DB source"],
                manual_review_required=False,
                created_at_utc=now,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/v1/route-cost/uk/tariffs/easington")

    assert response.status_code == 200
    assert response.json()["meta"]["source_references"] == ["runtime-postgresql"]
    assert response.json()["data"]["tariffs"][0]["tariff_id"] == "db-easington-entry-2025"


def test_easington_contract_api_persists_contract_when_db_configured(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "route-contract.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    payload = {
        "contract_id": "db-easington-contract",
        "gas_year": "2025/26",
        "delivery_quantity_mwh_per_day": 10000,
        "contract_price_gbp_mwh": 25,
        "nbp_sale_price_gbp_mwh": 28,
        "physical_exit_sale_price_gbp_mwh": 28.5,
        "physical_exit_point_name": "Bacton GDN (EA)",
        "delivery_tolerance_pct": 2,
        "nomination_tolerance_pct": 1,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
    }

    response = TestClient(create_app()).post(
        "/api/v1/route-cost/upstream-contracts/easington",
        json=payload,
    )

    assert response.status_code == 200
    with Session(engine) as session:
        row = session.get(UpstreamResourceContractRecord, "db-easington-contract")
        assert row is not None
        assert row.delivery_point_name == "Easington Beach Terminal"
        assert row.delivery_tolerance_pct == 2
