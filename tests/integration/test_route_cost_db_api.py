"""DB-backed route-cost API tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import TsoTariffRecord


def test_route_cost_api_reads_tso_tariffs_from_runtime_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "route-cost.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with Session(engine) as session:
        session.add(
            TsoTariffRecord(
                tariff_id="db-bbl-forward-2025-plus",
                document_id="db-bbl-doc",
                country="NL",
                tso="BBL Company",
                market_area="BBL",
                gas_year="2025+",
                point_id="bbl-forward-nl-gb",
                source_point_name="BBL Forward Flow NL to GB",
                direction="EXIT",
                capacity_product="ANNUAL",
                firmness="FIRM",
                tariff_value=1.0,
                currency="EUR",
                unit="EUR/MWh",
                effective_from=now,
                effective_to=None,
                tariff_status="FINAL",
                source_table="BBL annual public tariff",
                source_page=None,
                source_refs=["BBL Company DB source"],
                manual_review_required=False,
                created_at_utc=now,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get(
        "/api/route-cost/tso-tariffs",
        params={"tso": "BBL Company"},
    )

    assert response.status_code == 200
    assert response.json()["meta"]["source_references"] == ["runtime-postgresql"]
    assert response.json()["data"]["tariffs"][0]["tariff_id"] == "db-bbl-forward-2025-plus"


def test_route_recommendation_uses_runtime_db_tariffs(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "route-recommend.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with Session(engine) as session:
        session.add(
            TsoTariffRecord(
                tariff_id="db-bbl-forward-annual",
                document_id="db-bbl-doc",
                country="NL",
                tso="BBL Company",
                market_area="BBL",
                gas_year="2025+",
                point_id="bbl-forward-nl-gb",
                source_point_name="BBL Forward Flow NL to GB",
                direction="EXIT",
                capacity_product="ANNUAL",
                firmness="FIRM",
                tariff_value=1.0,
                currency="EUR",
                unit="EUR/MWh",
                effective_from=now,
                effective_to=None,
                tariff_status="FINAL",
                source_table="BBL annual public tariff",
                source_page=None,
                source_refs=["BBL Company DB source"],
                manual_review_required=False,
                created_at_utc=now,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).post(
        "/api/route-cost/recommend",
        json={
            "request_id": "db-recommend",
            "source_point_id": "TTF",
            "target_point_id": "NBP",
            "required_quantity_mwh_per_day": 100,
            "gas_year": "2025+",
            "capacity_product": "ANNUAL",
            "firmness": "FIRM",
            "company_accessible_tsos": ["BBL Company"],
            "candidates": [
                {
                    "route_id": "cheap-nbp-route",
                    "route_name": "TTF -> BBL -> NBP",
                    "destination_market": "NBP",
                    "sale_price": 35,
                    "price_currency": "EUR",
                    "price_unit": "EUR/MWh",
                    "required_tso_access": ["BBL Company"],
                    "available_capacity_mwh_per_day": 20,
                    "tariff_legs": [
                        {
                            "leg_id": "bbl-forward",
                            "country": "NL",
                            "tso": "BBL Company",
                            "market_area": "BBL",
                            "point_name": "BBL Forward Flow NL to GB",
                            "direction": "EXIT",
                        }
                    ],
                },
                {
                    "route_id": "local-ttf-sale",
                    "route_name": "Sell locally at TTF",
                    "destination_market": "TTF",
                    "sale_price": 31,
                    "price_currency": "EUR",
                    "price_unit": "EUR/MWh",
                    "available_capacity_mwh_per_day": 100,
                    "manual_cost": 0,
                    "cost_currency": "EUR",
                    "cost_unit": "EUR/MWh",
                },
            ],
        },
    )

    assert response.status_code == 200
    allocations = response.json()["data"]["allocations"]
    assert [(row["route_id"], row["allocated_mwh_per_day"]) for row in allocations] == [
        ("cheap-nbp-route", 20.0),
        ("local-ttf-sale", 80.0),
    ]
