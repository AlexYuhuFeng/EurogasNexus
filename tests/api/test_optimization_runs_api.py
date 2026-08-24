"""Optimization run persistence tests (Gate 3)."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.optimization import (
    get_optimization_run,
    persist_optimization_run,
)


def _engine(tmp_path):
    db_path = tmp_path / "optimization-runs.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    return engine, f"sqlite+pysqlite:///{db_path.as_posix()}"


def test_persist_and_get_optimization_run_roundtrip(tmp_path) -> None:
    engine, _ = _engine(tmp_path)
    now = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)

    with Session(engine) as session:
        persist_optimization_run(
            session,
            run_id="opt-roundtrip",
            optimization_type="contracts",
            decision_context="SANDBOX_SCENARIO",
            status="SUCCESS",
            input_snapshot={"resources": []},
            output_snapshot={"status": "optimal"},
            source_refs=["operator-input"],
            warnings=["demo"],
            created_at_utc=now,
        )
        session.commit()

    with Session(engine) as session:
        run = get_optimization_run(session, "opt-roundtrip")
        assert run is not None
        assert run.optimization_type == "contracts"
        assert run.status == "SUCCESS"
        assert run.input_snapshot == {"resources": []}
        assert run.output_snapshot == {"status": "optimal"}
        assert run.human_review_required is True
        assert get_optimization_run(session, "missing") is None


def test_optimization_api_persists_runs_and_exposes_evidence(tmp_path, monkeypatch) -> None:
    engine, database_url = _engine(tmp_path)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.post(
        "/api/optimization/contracts",
        json={
            "resources": [
                {
                    "resource_id": "supply-a",
                    "available_mwh": 100,
                    "unit_cost_gbp_mwh": 20,
                    "minimum_take_mwh": 10,
                }
            ],
            "market_price_gbp_mwh": 25,
            "demand_limit_mwh": 100,
            "decision_context": "SANDBOX_SCENARIO",
        },
    )

    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta["decision_context"] == "SANDBOX_SCENARIO"
    run_id = meta["run_id"]
    assert run_id is not None and run_id.startswith("opt-")

    evidence = client.get(f"/api/optimization/runs/{run_id}")
    assert evidence.status_code == 200
    data = evidence.json()["data"]
    assert data["run_id"] == run_id
    assert data["optimization_type"] == "contracts"
    assert data["decision_context"] == "SANDBOX_SCENARIO"
    assert data["status"] == "SUCCESS"
    assert data["input_snapshot"]["market_price_gbp_mwh"] == 25
    assert data["output_snapshot"]["status"] == "optimal"

    missing = client.get("/api/optimization/runs/opt-does-not-exist")
    assert missing.status_code == 404


def test_runtime_decision_rejected_for_unimplemented_endpoints() -> None:
    client = TestClient(create_app())
    for path, payload in [
        (
            "/api/optimization/route",
            {"source": "A", "target": "B", "required_capacity_mwh": 1, "edges": []},
        ),
        ("/api/optimization/capacity", {"products": [], "required_capacity_mwh": 1}),
        (
            "/api/optimization/contracts",
            {"resources": [], "market_price_gbp_mwh": 1, "demand_limit_mwh": 1},
        ),
    ]:
        payload["decision_context"] = "RUNTIME_DECISION"
        response = client.post(path, json=payload)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "runtime_decision_not_supported"


def test_runtime_resource_pool_requires_db_and_rejects_client_inputs() -> None:
    client = TestClient(create_app())

    no_db = client.post(
        "/api/optimization/resource-pool",
        json={"portfolio_id": "p1", "decision_context": "RUNTIME_DECISION"},
    )
    assert no_db.status_code == 503
    assert no_db.json()["detail"]["code"] == "runtime_db_not_configured"

    client_input = client.post(
        "/api/optimization/resource-pool",
        json={
            "portfolio_id": "p1",
            "decision_context": "RUNTIME_DECISION",
            "resources": [
                {"resource_id": "r", "available_mwh": 1, "unit_cost_gbp_mwh": 1}
            ],
            "sale_options": [
                {
                    "option_id": "o",
                    "destination_node": "X",
                    "sale_price_gbp_mwh": 2,
                    "capacity_mwh": 1,
                }
            ],
        },
    )
    assert client_input.status_code == 422
    assert client_input.json()["detail"]["code"] == "runtime_decision_client_input_forbidden"

    no_portfolio = client.post(
        "/api/optimization/resource-pool",
        json={"decision_context": "RUNTIME_DECISION"},
    )
    assert no_portfolio.status_code == 422
    assert no_portfolio.json()["detail"]["code"] == "runtime_decision_portfolio_required"


def test_runtime_resource_pool_uses_db_snapshot(tmp_path, monkeypatch) -> None:
    """RUNTIME_DECISION assembles inputs from the DB snapshot only (Gate 3)."""

    from datetime import UTC, datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import (
        FxObservationRecord,
        RouteCandidateRecord,
        UpstreamResourceContractRecord,
    )
    from eurogas_nexus.ingestion.simulated_market_prices import (
        upsert_simulated_market_observations,
    )

    db_path = tmp_path / "runtime-resource-pool.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with Session(engine) as session:
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
                allowed_exit_points=["TTF"],
                eligible_sale_modes=["LOCAL_MARKET_SALE"],
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
        upsert_simulated_market_observations(session, observed_at_utc=now)
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
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.post(
        "/api/optimization/resource-pool",
        json={"portfolio_id": "runtime-p1", "decision_context": "RUNTIME_DECISION"},
    )

    assert response.status_code == 200
    payload = response.json()
    meta = payload["meta"]
    assert meta["decision_context"] == "RUNTIME_DECISION"
    assert meta["source_references"] == ["runtime-postgresql"]
    run_id = meta["run_id"]
    assert run_id is not None
    assert meta["snapshot_id"] == run_id
    data = payload["data"]
    assert data["status"] == "optimal"
    assert data["allocations"], "expected at least one DB-assembled allocation"
    assert data["allocations"][0]["resource_id"] == "runtime-contract-ttf"

    evidence = client.get(f"/api/optimization/runs/{run_id}")
    assert evidence.status_code == 200
    snapshot = evidence.json()["data"]["input_snapshot"]
    assert snapshot["portfolio_id"] == "runtime-p1"
    assert snapshot["decision_context"] == "RUNTIME_DECISION"
    assert snapshot["fx_observation_ids"] == ["fx-eur-gbp"]
    assert snapshot["sale_options"][0]["destination_node"] == "TTF"


def test_runtime_resource_pool_fails_closed_on_blocked_snapshot(
    tmp_path, monkeypatch
) -> None:
    """A snapshot that cannot assemble inputs must not run (fail-closed)."""

    from datetime import UTC, datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import UpstreamResourceContractRecord

    db_path = tmp_path / "runtime-blocked.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with Session(engine) as session:
        # Contract exists but no route candidates / market rows at all.
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
                allowed_exit_points=["TTF"],
                eligible_sale_modes=["LOCAL_MARKET_SALE"],
                notes="test_fixture:not_customer_data",
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.post(
        "/api/optimization/resource-pool",
        json={"portfolio_id": "runtime-p2", "decision_context": "RUNTIME_DECISION"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "runtime_decision_input_blocked"
    assert "SALE_OPTIONS_UNAVAILABLE" in detail["blockers"]


def test_optimization_run_status_maps_to_status_kind() -> None:
    from eurogas_nexus.api.routes.public.optimization import _status_kind
    from eurogas_nexus.domain.ontology.vocabulary import StatusKind

    assert _status_kind("optimal") == StatusKind.SUCCESS.value
    assert _status_kind("feasible") == StatusKind.PARTIAL.value
    assert _status_kind("infeasible") == StatusKind.BLOCKED.value
    assert _status_kind("mystery") == StatusKind.UNKNOWN.value


def test_resource_pool_and_route_optimizer_use_status_kind_values() -> None:
    from eurogas_nexus.domain.ontology.vocabulary import StatusKind
    from eurogas_nexus.domain.route_cost.enums import CapacityProduct, Firmness
    from eurogas_nexus.domain.route_cost.european_public_tariffs import (
        published_european_corridor_tariffs,
    )
    from eurogas_nexus.domain.route_cost.resource_pool import (
        PortfolioOptimizationScenario,
        PortfolioResource,
        PortfolioSaleOption,
        optimize_resource_pool,
    )
    from eurogas_nexus.domain.route_cost.route_optimizer import (
        RouteOptionCandidate,
        RouteRecommendationRequest,
        recommend_route_allocation,
    )
    from eurogas_nexus.domain.route_cost.schemas import RouteTariffLeg

    pool_result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="p",
            resources=[
                PortfolioResource(
                    resource_id="r1",
                    resource_name="R1",
                    resource_type="PIPELINE_IMPORT",
                    delivery_mode="PHYSICAL_ENTRY_DELIVERY",
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=100,
                    contract_cost_gbp_mwh=25,
                    delivery_tolerance_pct=0,
                    nomination_tolerance_pct=0,
                )
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="o1",
                    label="O1",
                    delivery_mode="VIRTUAL_HUB_SALE",
                    target_point_name="TTF",
                    sale_price_gbp_mwh=30,
                    capacity_limit_mwh_per_day=50,
                )
            ],
        )
    )
    assert pool_result.status in {status.value for status in StatusKind}
    assert pool_result.status == StatusKind.PARTIAL.value  # 50 of 100 allocated

    route_result = recommend_route_allocation(
        RouteRecommendationRequest(
            request_id="r",
            source_point_id="TTF",
            required_quantity_mwh_per_day=100,
            gas_year="2025+",
            capacity_product=CapacityProduct.ANNUAL,
            firmness=Firmness.FIRM,
            candidates=[
                RouteOptionCandidate(
                    route_id="c1",
                    route_name="C1",
                    available_capacity_mwh_per_day=100,
                    tariff_legs=[
                        RouteTariffLeg(
                            leg_id="l1",
                            country="NL",
                            tso="BBL Company",
                            market_area="BBL",
                            point_name="BBL Forward Flow NL to GB",
                            direction="EXIT",
                        )
                    ],
                )
            ],
        ),
        published_european_corridor_tariffs(),
    )
    assert route_result.status == StatusKind.SUCCESS.value
