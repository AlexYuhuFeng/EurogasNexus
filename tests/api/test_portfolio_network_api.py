"""API tests for the DB-composed portfolio network optimization (R31)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CompanyTsoAccessRecord,
    FxObservationRecord,
    MarketObservationRecord,
    ReferenceNode,
    RouteCandidateRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    published_european_corridor_tariffs,
)

GAS_DAY = "2026-01-01"


def _engine(tmp_path):
    db_path = tmp_path / "portfolio-network.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    return engine, f"sqlite+pysqlite:///{db_path.as_posix()}"


def _seed_full_snapshot(session: Session) -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    session.add(
        UpstreamResourceContractRecord(
            contract_id="runtime-contract-ttf",
            contract_name="Runtime TTF supply",
            resource_type="PIPELINE_IMPORT",
            delivery_point_name="TTF",
            gas_year="2025+",
            delivery_quantity_mwh_per_day=100.0,
            contract_price_gbp_mwh=25.0,
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
        )
    )
    session.add(
        RouteCandidateRecord(
            route_id="runtime-route-ttf-local",
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
        )
    )
    session.add(
        RouteCandidateRecord(
            route_id="runtime-route-bbl",
            route_name="TTF to NBP via BBL",
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
                    "available_capacity_mwh_per_day": 2000.0,
                }
            ],
            required_entry_point_name=None,
            required_exit_point_name=None,
            required_tso_access=["BBL Company"],
            source_systems=["public_route_template", "BBL"],
            active=True,
            created_at_utc=now,
        )
    )
    session.add(
        ReferenceNode(
            id="node-ttf",
            name="TTF",
            node_type="hub",
            country="NL",
            lat=0.0,
            lon=0.0,
        )
    )
    session.add(
        ReferenceNode(
            id="node-nbp",
            name="NBP",
            node_type="hub",
            country="GB",
            lat=0.0,
            lon=0.0,
        )
    )
    session.add(
        CompanyTsoAccessRecord(
            access_id="runtime-access-bbl",
            tso="BBL Company",
            market_area="BBL",
            status="ACTIVE",
            valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to_utc=None,
            source_reference="preview-configuration:company-tso-access:BBL",
            notes="test_fixture:not_customer_data",
            updated_at_utc=now,
        )
    )
    for hub, price in [("TTF", 31.4), ("NBP", 33.2)]:
        session.add(
            MarketObservationRecord(
                observation_id=f"market-{hub.lower()}",
                market_venue="EEX",
                product=f"{hub} Day-Ahead",
                price=price,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=datetime(2025, 12, 31, 6, 0, tzinfo=UTC),
                period_end_utc=datetime(2026, 1, 2, 6, 0, tzinfo=UTC),
                observed_at_utc=now,
                source_system="EEX_Sim",
                source_reference="simulated:test",
                source_record_id=f"sim-{hub.lower()}",
                freshness="simulated_live",
                quality_score=0.9,
                research_only=True,
                metadata_json={"hub": hub, "tenor": "day-ahead", "simulated": True},
            )
        )
    session.add(
        FxObservationRecord(
            observation_id="fx-eur-gbp",
            pair="EURGBP",
            base_currency="EUR",
            quote_currency="GBP",
            rate=0.85,
            rate_type="reference",
            value_date="2026-01-01",
            observed_at_utc=now,
            source_system="ECB",
            source_reference="ecb-eurofxref-daily",
            source_record_id="2026-01-01-GBP",
            freshness="live",
            research_only=True,
            metadata_json={"dataset": "eurofxref-daily"},
        )
    )
    _seed_tariffs(session, now)
    session.commit()


def _seed_tariffs(session: Session, now: datetime) -> None:
    for tariff in published_european_corridor_tariffs():
        session.add(
            TsoTariffRecord(
                tariff_id=tariff.tariff_id,
                document_id=tariff.document_id,
                country=tariff.country,
                tso=tariff.tso,
                market_area=tariff.market_area,
                gas_year=tariff.gas_year,
                point_id=tariff.point_id,
                source_point_name=tariff.source_point_name,
                direction=tariff.direction.value,
                capacity_product=tariff.capacity_product.value,
                firmness=tariff.firmness.value,
                tariff_value=tariff.tariff_value,
                currency=tariff.currency,
                unit=tariff.unit,
                effective_from=datetime.combine(
                    tariff.effective_from, datetime.min.time(), UTC
                ),
                effective_to=(
                    datetime.combine(tariff.effective_to, datetime.min.time(), UTC)
                    if tariff.effective_to
                    else None
                ),
                tariff_status=tariff.tariff_status.value,
                source_table=tariff.source_table,
                source_page=tariff.source_page,
                source_refs=tariff.source_refs,
                manual_review_required=tariff.manual_review_required,
                created_at_utc=now,
            )
        )


def _configured_client(tmp_path, monkeypatch) -> tuple[TestClient, str, object]:
    engine, database_url = _engine(tmp_path)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    with Session(engine) as session:
        _seed_full_snapshot(session)
    return TestClient(create_app()), database_url, engine


def _post(client: TestClient, **overrides):
    payload = {
        "portfolio_id": "portfolio-runtime",
        "gas_day": GAS_DAY,
        "capacity_product": "ANNUAL",
        "firmness": "FIRM",
        "max_market_price_age_hours": 72,
        "decision_context": "RUNTIME_DECISION",
    }
    payload.update(overrides)
    return client.post("/api/optimization/portfolio-network", json=payload)


def test_portfolio_network_requires_runtime_db() -> None:
    client = TestClient(create_app())

    response = _post(client)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_not_configured"


def test_portfolio_network_rejects_sandbox_context() -> None:
    client = TestClient(create_app())

    response = _post(client, decision_context="SANDBOX_SCENARIO")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "sandbox_scenario_not_supported"


def test_portfolio_network_rejects_client_network_facts() -> None:
    client = TestClient(create_app())

    response = _post(client, edges=[], accessible_tsos=["BBL Company"])

    assert response.status_code == 422
    # Pydantic must reject the fabricated facts before any DB lookup.
    assert response.json()["detail"][0]["loc"][-1] in {"edges", "accessible_tsos"}


def test_portfolio_network_optimizes_db_snapshot_and_persists_evidence(
    tmp_path, monkeypatch
) -> None:
    client, _, _ = _configured_client(tmp_path, monkeypatch)

    response = _post(client)

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    meta = payload["meta"]
    assert data["status"] == "optimal"
    assert data["allocations"], "expected at least one DB-assembled allocation"
    assert data["contract_attributions"]
    assert data["contract_attributions"][0]["contract_id"] == "runtime-contract-ttf"
    assert meta["decision_context"] == "RUNTIME_DECISION"
    assert meta["source_references"] == ["runtime-postgresql"]
    assert meta["lineage"]
    assert meta["assumptions"]
    run_id = meta["run_id"]
    assert run_id is not None
    assert meta["snapshot_id"] == run_id

    evidence = client.get(f"/api/optimization/runs/{run_id}")
    assert evidence.status_code == 200
    snapshot = evidence.json()["data"]["input_snapshot"]
    assert snapshot["portfolio_id"] == "portfolio-runtime"
    assert snapshot["resources"][0]["resource_id"] == "runtime-contract-ttf"
    assert snapshot["edges"][0]["edge_id"] == "route:runtime-route-bbl"
    assert snapshot["edge_lineage"][0]["route_id"] == "runtime-route-bbl"
    assert snapshot["fx_observation_ids"] == ["fx-eur-gbp"]


def test_portfolio_network_fails_closed_when_snapshot_is_blocked(
    tmp_path, monkeypatch
) -> None:
    engine, database_url = _engine(tmp_path)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    with Session(engine) as session:
        _seed_full_snapshot(session)
        # Remove the NBP market row: the cross-border route must block, while
        # the local TTF sale remains composable.
        row = session.get(MarketObservationRecord, "market-nbp")
        session.delete(row)
        session.commit()

    client = TestClient(create_app())
    response = _post(client)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "runtime_decision_input_blocked"
    assert "MARKET_PRICE_MISSING:NBP" in detail["blockers"]
