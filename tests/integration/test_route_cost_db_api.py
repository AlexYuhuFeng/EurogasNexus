"""DB-backed route-cost API tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    MarketObservationRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)


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


def test_resource_pool_options_are_built_from_runtime_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "resource-pool-options.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with Session(engine) as session:
        session.add_all(
            [
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
                ),
                UpstreamResourceContractRecord(
                    contract_id="resource-pool-contract-ttf-2025",
                    contract_name="Resource pool TTF supply 2025",
                    resource_type="PIPELINE_IMPORT",
                    delivery_point_name="TTF",
                    gas_year="2025+",
                    delivery_quantity_mwh_per_day=100.0,
                    contract_price_gbp_mwh=30.0,
                    settlement_frequency="monthly",
                    upstream_payment_lag_days=20,
                    screen_sale_cash_lag_days=1,
                    delivery_tolerance_pct=2.0,
                    nomination_tolerance_pct=1.0,
                    tolerance_risk_allowance_gbp_mwh=0.1,
                    annual_financing_rate_pct=6.0,
                    owned_entry_capacity_mwh_per_day=None,
                    owned_exit_capacity_mwh_per_day=None,
                    allowed_exit_points=["NBP", "TTF"],
                    eligible_sale_modes=["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
                    notes="test_fixture:not_customer_data",
                    created_at_utc=now,
                    updated_at_utc=now,
                ),
                RouteCandidateRecord(
                    route_id="public-route-ttf-bbl-nbp",
                    route_name="TTF -> BBL -> NBP",
                    start_point_name="TTF",
                    target_point_name="NBP",
                    business_model="CROSS_BORDER_TRANSFER",
                    route_legs=[
                        {
                            "leg_id": "bbl-forward",
                            "country": "NL",
                            "tso": "BBL Company",
                            "market_area": "BBL",
                            "point_name": "BBL Forward Flow NL to GB",
                            "direction": "EXIT",
                        }
                    ],
                    required_entry_point_name=None,
                    required_exit_point_name=None,
                    required_tso_access=["BBL Company"],
                    source_systems=["public_route_template", "BBL"],
                    active=True,
                    created_at_utc=now,
                ),
                RouteCandidateRecord(
                    route_id="public-route-ttf-local",
                    route_name="Sell locally at TTF",
                    start_point_name="TTF",
                    target_point_name="TTF",
                    business_model="VIRTUAL_HUB_SALE",
                    route_legs=[],
                    required_entry_point_name=None,
                    required_exit_point_name=None,
                    required_tso_access=[],
                    source_systems=["public_route_template"],
                    active=True,
                    created_at_utc=now,
                ),
                MarketObservationRecord(
                    observation_id="demo-market-nbp-day-ahead",
                    market_venue="NBP",
                    product="day-ahead",
                    price=35.0,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=now,
                    period_end_utc=now,
                    observed_at_utc=now,
                    source_system="demo_market_price",
                    source_reference="demo:market-price:nbp-day-ahead",
                    source_record_id=None,
                    freshness="demo",
                    quality_score=0.8,
                    research_only=True,
                    metadata_json={"hub": "NBP"},
                ),
                MarketObservationRecord(
                    observation_id="demo-market-ttf-day-ahead",
                    market_venue="TTF",
                    product="day-ahead",
                    price=31.0,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=now,
                    period_end_utc=now,
                    observed_at_utc=now,
                    source_system="demo_market_price",
                    source_reference="demo:market-price:ttf-day-ahead",
                    source_record_id=None,
                    freshness="demo",
                    quality_score=0.8,
                    research_only=True,
                    metadata_json={"hub": "TTF"},
                ),
            ]
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/route-cost/resource-pool/options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["source_references"] == ["runtime-postgresql"]
    data = payload["data"]
    assert data["blockers"] == []
    assert data["portfolio_resources"][0]["resource_id"] == "resource-pool-contract-ttf-2025"
    assert {option["option_id"] for option in data["sale_options"]} == {
        "public-route-ttf-bbl-nbp",
        "public-route-ttf-local",
    }
    bbl_option = next(
        option
        for option in data["sale_options"]
        if option["option_id"] == "public-route-ttf-bbl-nbp"
    )
    assert bbl_option["target_point_name"] == "NBP"
    assert bbl_option["sale_price_gbp_mwh"] == 35.0
    assert bbl_option["route_cost_gbp_mwh"] == 1.0
    assert bbl_option["required_tso_access"] == ["BBL Company"]


def test_resource_pool_options_report_missing_market_prices(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "resource-pool-options-missing-price.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with Session(engine) as session:
        session.add(
            RouteCandidateRecord(
                route_id="public-route-ttf-bbl-nbp",
                route_name="TTF -> BBL -> NBP",
                start_point_name="TTF",
                target_point_name="NBP",
                business_model="CROSS_BORDER_TRANSFER",
                route_legs=[],
                required_entry_point_name=None,
                required_exit_point_name=None,
                required_tso_access=["BBL Company"],
                source_systems=["public_route_template", "BBL"],
                active=True,
                created_at_utc=now,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/route-cost/resource-pool/options")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sale_options"] == []
    assert data["blockers"] == [
        "UPSTREAM_CONTRACTS_MISSING",
        "MARKET_PRICE_MISSING:NBP",
    ]
