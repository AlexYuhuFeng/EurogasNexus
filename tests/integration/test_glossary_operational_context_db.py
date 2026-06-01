"""DB-backed operational glossary context tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CapacityProfileRecord,
    FlowObservationRecord,
    LiveMarketMarkRecord,
    MarketObservationRecord,
    RouteCandidateRecord,
    UpstreamResourceContractRecord,
)


def test_glossary_context_reads_capacity_flow_prices_and_contracts_from_db(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "glossary-context.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    start = datetime(2026, 6, 1, 6, tzinfo=UTC)
    end = datetime(2026, 6, 2, 6, tzinfo=UTC)
    observed = datetime(2026, 6, 1, 12, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            CapacityProfileRecord(
                capacity_profile_id="cap-easington-entry",
                contract_id="contract-easington",
                point_name="Easington Entry Point",
                direction="entry",
                capacity_mwh_per_day=100000.0,
                firmness="firm",
                valid_from_utc=start,
                valid_to_utc=end,
                source_reference="customer-capacity-profile",
                created_at_utc=observed,
            )
        )
        session.add(
            FlowObservationRecord(
                observation_id="flow-easington-entry",
                point_id="easington-entry",
                point_name="Easington Entry Point",
                direction="entry",
                flow_mcm_d=6.0,
                period_start_utc=start,
                period_end_utc=end,
                observed_at_utc=observed,
                source_system="ENTSOG",
                source_reference="entsog:easington",
                freshness="fresh",
                research_only=True,
            )
        )
        session.add(
            MarketObservationRecord(
                observation_id="price-icis-nbp",
                market_venue="ICIS Heren",
                product="NBP day-ahead assessment",
                price=29.15,
                unit="GBP/MWh",
                currency="GBP",
                period_start_utc=start,
                period_end_utc=end,
                observed_at_utc=observed,
                source_system="customer-licensed",
                source_reference="licensed:icis-heren:nbp-da",
                freshness="fresh",
                quality_score=1.0,
                research_only=True,
            )
        )
        session.add(
            LiveMarketMarkRecord(
                mark_id="mark-ice-ocm-nbp",
                venue="ICE OCM",
                hub="NBP",
                product="within-day",
                bid_gbp_mwh=29.4,
                ask_gbp_mwh=29.6,
                last_gbp_mwh=29.5,
                mark_time_utc=observed,
                source_system="customer-screen-import",
                source_reference="screen:ice-ocm:nbp-wd",
                created_at_utc=observed,
            )
        )
        session.add(
            RouteCandidateRecord(
                route_id="route-easington-nbp",
                route_name="Easington beach delivery -> NBP virtual sale",
                start_point_name="Easington Entry Point",
                target_point_name="NBP",
                business_model="VIRTUAL_HUB_SALE",
                route_legs=[{"from": "Easington Entry Point", "to": "NBP"}],
                required_entry_point_name="Easington Entry Point",
                required_exit_point_name=None,
                required_tso_access=["National Gas NTS"],
                source_systems=["customer-route-model"],
                active=True,
                created_at_utc=observed,
            )
        )
        session.add(
            UpstreamResourceContractRecord(
                contract_id="contract-easington",
                contract_name="Easington beach gas year",
                resource_type="BEACH_DELIVERY",
                delivery_point_name="Easington Entry Point",
                gas_year="2026/27",
                delivery_quantity_mwh_per_day=10000.0,
                contract_price_gbp_mwh=25.0,
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=2.0,
                nomination_tolerance_pct=1.0,
                tolerance_risk_allowance_gbp_mwh=0.1,
                annual_financing_rate_pct=6.0,
                owned_entry_capacity_mwh_per_day=100000.0,
                owned_exit_capacity_mwh_per_day=None,
                allowed_exit_points=["NBP"],
                eligible_sale_modes=["VIRTUAL_HUB_SALE"],
                notes=None,
                created_at_utc=observed,
                updated_at_utc=observed,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.get(
        "/api/v1/glossary/Easington%20Entry%20Point/context",
        params={
            "duration_start_utc": "2026-06-01T00:00:00Z",
            "duration_end_utc": "2026-06-03T00:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert body["meta"]["source_references"] == ["runtime-postgresql"]
    assert data["capacity"]["source_reference"] == "customer-capacity-profile"
    assert data["capacity_usage"]["usage_pct"] == 63.3
    assert data["capacity_usage"]["used_mwh_per_day"] == 63300.0
    assert data["related_prices"][0]["source_reference"] == "licensed:icis-heren:nbp-da"
    assert data["live_market_marks"][0]["source_reference"] == "screen:ice-ocm:nbp-wd"
    assert data["related_routes"][0]["route_id"] == "route-easington-nbp"
    assert data["related_contracts"][0]["contract_id"] == "contract-easington"
    assert data["data_quality"]["runtime_db"] is True
