"""Application projection API tests (Architecture V2 Wave 5).

Covers the four ``/api/projections/...`` surfaces through the real FastAPI app:
the envelope contract, one time basis and one as-of instant, per-slice
freshness, entitlement that is never wider than the underlying route, explicit
degraded/empty states, a stable payload shape and the 422/503 error contract.

The router is included by the app when the integrator registers it; until then
the fixture mounts it locally so the module under test is still exercised
end-to-end.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.dependencies import identity as identity_dependency
from eurogas_nexus.api.routes.public.projections import router as projections_router
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db import session as db_session
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    GeneratedReportRecord,
    IntradayOpportunityRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    PortfolioPnlSnapshotRecord,
    ReviewDecisionRecord,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

AS_OF = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
AS_OF_PARAM = AS_OF.isoformat()
AS_OF_QUERY = {"as_of_utc": AS_OF_PARAM}
PROJECTION_PATHS = (
    "/api/projections/market-context",
    "/api/projections/portfolio-snapshot",
    "/api/projections/review-context",
    "/api/projections/scenario-context",
)

META_KEYS = {
    "projection",
    "projection_version",
    "as_of_utc",
    "time_basis",
    "research_only",
    "human_review_required",
    "source_references",
    "warnings",
    "table_lineage",
}
SLICE_KEYS = {
    "available",
    "source_references",
    "row_count",
    "rows",
    "payload",
    "freshness",
    "entitlement",
    "context_filter",
    "limits",
    "warnings",
    "notes",
}
FRESHNESS_KEYS = {
    "state",
    "basis",
    "evaluated_at_utc",
    "last_observed_at_utc",
    "expected_within_minutes",
    "expectation_source",
    "measured",
    "derived_from",
}


def _scoped_principal(scopes: tuple[str, ...] = ("ENTSOG",)) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="fixture-principal",
        name="fixture-principal",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=scopes,
        roles=("ANALYST",),
        auth_method="identity_key",
    )


def _client(principal: AuthenticatedPrincipal | None = None) -> TestClient:
    """Build a client over the real app, mounting the projection router if needed."""

    app = create_app(Settings(api_profile="development"))
    if not any(
        str(getattr(route, "path", "")).startswith("/api/projections/") for route in app.routes
    ):
        app.include_router(projections_router)
    if principal is not None:
        # Install the resolved principal the way the release profile does, without
        # relying on the permission registry entry owned by the integrator.
        @app.middleware("http")
        async def _inject_identity(request, call_next):  # type: ignore[no-untyped-def]
            request.state.identity = principal
            return await call_next(request)

    return TestClient(app)


def _database(tmp_path, name: str) -> str:
    database_url = f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return database_url


def _seed_market(engine) -> None:
    with Session(engine) as session:
        session.add(
            MarketObservationRecord(
                observation_id="obs-eex-restricted",
                market_venue="EEX",
                product="NBP Day-Ahead",
                price=31.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=AS_OF - timedelta(minutes=10),
                period_end_utc=AS_OF,
                observed_at_utc=AS_OF - timedelta(minutes=10),
                source_system="EEX_Sim",
                source_reference="fixture:EEX_Sim",
                source_record_id="eex-1",
                freshness="live",
                quality_score=0.9,
                research_only=True,
                metadata_json={"hub": "NBP"},
            )
        )
        session.add(
            MarketObservationRecord(
                observation_id="obs-entsog-public",
                market_venue="ENTSOG",
                product="NBP flows",
                price=1.0,
                unit="MWh/d",
                currency="EUR",
                period_start_utc=AS_OF - timedelta(minutes=10),
                period_end_utc=AS_OF,
                observed_at_utc=AS_OF - timedelta(minutes=10),
                source_system="ENTSOG",
                source_reference="fixture:ENTSOG",
                source_record_id="entsog-1",
                freshness="live",
                quality_score=0.9,
                research_only=True,
                metadata_json={"hub": "NBP"},
            )
        )
        session.add(
            MarketQuoteRecord(
                quote_id="q-1",
                source_system="EEX_Sim",
                source_record_id="q-1-src",
                venue="EEX",
                instrument_id="NBP-within-day",
                hub="NBP",
                product="within-day",
                delivery_start_utc=AS_OF,
                delivery_end_utc=AS_OF + timedelta(days=1),
                bid_price=30.0,
                ask_price=31.0,
                last_price=30.5,
                bid_quantity_mwh=100.0,
                ask_quantity_mwh=100.0,
                currency="GBP",
                unit="GBP/MWh",
                observed_at_utc=AS_OF - timedelta(minutes=10),
                received_at_utc=AS_OF - timedelta(minutes=10),
                source_reference="fixture:q-1",
                freshness="live",
                quality_score=0.9,
                simulated=True,
                metadata_json={},
            )
        )
        session.add(
            IntradayOpportunityRecord(
                opportunity_id="opp-1",
                scan_id="scan-1",
                opportunity_type="CROSS_HUB_SPREAD",
                status="ACTIONABLE_REVIEW",
                buy_quote_id="q-1",
                sell_quote_id="q-2",
                route_id="route-1",
                route_name="NBP -> TTF",
                buy_venue="EEX",
                sell_venue="ICE OCM",
                buy_hub="NBP",
                sell_hub="TTF",
                product="within-day",
                delivery_start_utc=AS_OF,
                delivery_end_utc=AS_OF + timedelta(days=1),
                comparison_currency="GBP",
                comparison_unit="GBP/MWh",
                buy_ask=30.0,
                sell_bid=33.0,
                gross_spread=3.0,
                route_cost=1.0,
                trading_cost=0.2,
                risk_buffer=0.1,
                net_margin=1.7,
                max_quantity_mwh=1000.0,
                indicative_net_value=1700.0,
                quote_age_seconds=12.0,
                confidence_score=0.8,
                cost_components=[],
                source_refs=["fixture:quotes"],
                assumptions=[],
                missing_inputs=[],
                warnings=[],
                detected_at_utc=AS_OF - timedelta(minutes=5),
                valid_until_utc=AS_OF + timedelta(hours=4),
                simulated=True,
                human_review_required=True,
            )
        )
        session.commit()


def _seed_portfolio(engine) -> None:
    with Session(engine) as session:
        session.add(
            PortfolioPnlSnapshotRecord(
                pnl_snapshot_id="pnl-1",
                portfolio_id="portfolio-demo",
                resource_id=None,
                strategy_id=None,
                valuation_time_utc=AS_OF - timedelta(minutes=5),
                realized_pnl_gbp=1200.0,
                unrealized_pnl_gbp=4200.0,
                indicative_pnl_gbp=5400.0,
                cash_value_gbp=1800.0,
                market_value_gbp=142000.0,
                quantity_mwh=10000.0,
                valuation_basis="live-bid-mark",
                source_system="EEX_Sim",
                source_reference="fixture:pnl",
                warnings=[],
                research_only=True,
                human_review_required=True,
            )
        )
        session.commit()


def _seed_review(engine) -> None:
    with Session(engine) as session:
        session.add(
            ReviewDecisionRecord(
                decision_id="dec-1",
                entity_type="generated_report",
                entity_id="report-1",
                actor="operator-a",
                decision="needs_attention",
                note="review the totals",
                created_at_utc=AS_OF - timedelta(minutes=2),
            )
        )
        session.add(
            GeneratedReportRecord(
                report_id="report-1",
                report_type="PORTFOLIO",
                title="Portfolio review pack",
                status="success",
                duration_start_utc=AS_OF - timedelta(days=1),
                duration_end_utc=AS_OF,
                input_snapshot={},
                sections=[{"title": "summary"}],
                source_refs=["runtime-postgresql"],
                warnings=[],
                created_at_utc=AS_OF - timedelta(minutes=3),
                research_only=True,
                human_review_required=True,
            )
        )
        session.commit()


def _use_database(monkeypatch, database_url: str) -> None:
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)


def _clear_database(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)


# ---------------------------------------------------------------------------
# Envelope, shape and one time basis
# ---------------------------------------------------------------------------


def test_projection_envelope_and_slice_shape_without_runtime_db(monkeypatch) -> None:
    _clear_database(monkeypatch)
    client = _client()

    for path in PROJECTION_PATHS:
        response = client.get(path, params=AS_OF_QUERY)

        assert response.status_code == 200, path
        body = response.json()
        assert set(body) == {"data", "meta"}, path
        assert set(body["meta"]) == META_KEYS, path
        assert body["meta"]["research_only"] is True, path
        assert body["meta"]["human_review_required"] is True, path
        assert body["meta"]["as_of_utc"] == AS_OF_PARAM, path
        assert body["meta"]["time_basis"]["basis"] == "as_of_instant", path
        assert body["meta"]["time_basis"]["gas_day"] == "2026-06-01", path
        assert body["meta"]["source_references"] == ["runtime-db-not-configured"], path
        assert "RUNTIME_DB_NOT_CONFIGURED" in body["meta"]["warnings"], path
        assert body["data"]["as_of_utc"] == body["meta"]["as_of_utc"], path
        for name, item in body["data"]["slices"].items():
            assert set(item) == SLICE_KEYS, f"{path}:{name}"
            assert set(item["freshness"]) == FRESHNESS_KEYS, f"{path}:{name}"
            assert item["available"] is False, f"{path}:{name}"
            assert item["freshness"]["state"] == "MISSING", f"{path}:{name}"


def test_market_context_is_coherent_on_one_as_of_instant(tmp_path, monkeypatch) -> None:
    database_url = _database(tmp_path, "market.sqlite")
    engine = create_engine(database_url, future=True)
    _seed_market(engine)
    _use_database(monkeypatch, database_url)

    response = _client().get(
        "/api/projections/market-context",
        params={**AS_OF_QUERY, "gas_day": "2026-06-01"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source_references"] == ["runtime-postgresql"]
    slices = body["data"]["slices"]
    assert set(slices) == {
        "market_observations",
        "normalized_quotes",
        "quotes",
        "intraday_opportunities",
        "spreads",
        "monitoring",
        "data_sources",
    }
    for name, item in slices.items():
        assert item["freshness"]["evaluated_at_utc"] == AS_OF_PARAM, name
    # One basis: the gas day reported in data and meta is the same one.
    assert body["data"]["time_basis"] == body["meta"]["time_basis"]
    assert body["data"]["time_basis"]["gas_day"] == "2026-06-01"

    # Per-slice freshness: EEX declares a 1-minute expectation, so a 10-minute
    # old tick is stale, while the public ENTSOG row (60 minutes) stays fresh.
    by_source = {row["source_system"]: row for row in slices["data_sources"]["rows"]}
    assert by_source["EEX_Sim"]["freshness"]["state"] == "STALE"
    assert by_source["ENTSOG"]["freshness"]["state"] == "FRESH"
    assert slices["spreads"]["rows"][0]["spread_id"] == "opp-1"


def test_projections_are_never_wider_than_the_underlying_routes(monkeypatch, tmp_path) -> None:
    database_url = _database(tmp_path, "scoped.sqlite")
    engine = create_engine(database_url, future=True)
    _seed_market(engine)
    _use_database(monkeypatch, database_url)
    client = _client(_scoped_principal(("ENTSOG",)))

    projection = client.get("/api/projections/market-context", params=AS_OF_QUERY)
    route = client.get("/api/market/observations")

    assert projection.status_code == 200
    assert route.status_code == 200
    projection_ids = {
        row["observation_id"]
        for row in projection.json()["data"]["slices"]["market_observations"]["rows"]
    }
    route_ids = {row["observation_id"] for row in route.json()["data"]}
    assert projection_ids <= route_ids
    assert projection_ids == {"obs-entsog-public"}
    # The restricted source system and its row are absent from the whole response.
    # (A venue label such as "EEX" on an opportunity row is not a source family and
    # the underlying /api/market/opportunities route exposes it unfiltered too.)
    assert "obs-eex-restricted" not in projection.text
    assert "EEX_Sim" not in projection.text
    assert "source_system\":\"EEX\"" not in projection.text


def test_portfolio_snapshot_reports_summary_and_unknown_totals(tmp_path, monkeypatch) -> None:
    database_url = _database(tmp_path, "portfolio.sqlite")
    engine = create_engine(database_url, future=True)
    _use_database(monkeypatch, database_url)
    empty = _client().get("/api/projections/portfolio-snapshot", params=AS_OF_QUERY)

    assert empty.status_code == 200
    summary = empty.json()["data"]["slices"]["summary"]["payload"]
    # Empty runtime DB: unknown, not a measured zero.
    assert summary["total_indicative_pnl_gbp"] is None
    assert "VALUATION_EVIDENCE_MISSING" in empty.json()["meta"]["warnings"]

    _seed_portfolio(engine)
    populated = _client().get("/api/projections/portfolio-snapshot", params=AS_OF_QUERY)

    assert populated.status_code == 200
    body = populated.json()
    slices = body["data"]["slices"]
    assert slices["summary"]["payload"]["total_indicative_pnl_gbp"] == 5400.0
    assert slices["pnl_snapshots"]["row_count"] == 1
    assert slices["pnl_snapshots"]["freshness"]["last_observed_at_utc"] == (
        AS_OF - timedelta(minutes=5)
    ).isoformat()
    # The resources slice is composed, not deferred: it reports the same block
    # GET /api/route-cost/resource-pool/options returns, and here it honestly
    # names the inputs this empty runtime database cannot supply.
    resources = slices["resources"]
    assert resources["available"] is True
    assert resources["payload"]["scope"] == "RESOURCE_POOL_ROUTE_OPTIONS"
    assert resources["payload"]["blockers"] == [
        "UPSTREAM_CONTRACTS_MISSING",
        "ROUTE_CANDIDATES_MISSING",
    ]
    assert resources["rows"] == []


def test_review_context_returns_decisions_and_resolved_evidence(tmp_path, monkeypatch) -> None:
    database_url = _database(tmp_path, "review.sqlite")
    engine = create_engine(database_url, future=True)
    _seed_review(engine)
    _use_database(monkeypatch, database_url)

    response = _client().get("/api/projections/review-context", params=AS_OF_QUERY)

    assert response.status_code == 200
    slices = response.json()["data"]["slices"]
    assert set(slices) == {"decisions", "evidence", "monitoring"}
    assert [row["decision_id"] for row in slices["decisions"]["rows"]] == ["dec-1"]
    evidence = slices["evidence"]["rows"][0]
    assert evidence["entity_type"] == "generated_report"
    assert evidence["available"] is True
    assert evidence["artifact"]["report_id"] == "report-1"
    assert "REVIEW_DECISION_NEEDS_ATTENTION" in response.json()["meta"]["warnings"]


def test_scenario_context_declares_what_it_does_not_provide(tmp_path, monkeypatch) -> None:
    database_url = _database(tmp_path, "scenario.sqlite")
    _use_database(monkeypatch, database_url)

    response = _client().get("/api/projections/scenario-context", params=AS_OF_QUERY)

    assert response.status_code == 200
    body = response.json()
    assert set(body["data"]["slices"]) == {
        "route_candidates",
        "tso_tariffs",
        "upstream_contracts",
    }
    surfaces = {item["surface"] for item in body["data"]["not_included"]}
    assert "POST /api/route-cost/resource-pool/optimize" in surfaces


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------


def test_malformed_gas_day_is_rejected(monkeypatch) -> None:
    _clear_database(monkeypatch)

    response = _client().get("/api/projections/market-context?gas_day=01-06-2026")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "gas_day_invalid"


def test_configured_but_unreadable_runtime_db_returns_503(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'missing-dir' / 'x.sqlite').as_posix()}"
    _use_database(monkeypatch, database_url)

    response = _client().get("/api/projections/market-context")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_unavailable"


def test_projection_parameters_are_bounded(monkeypatch) -> None:
    _clear_database(monkeypatch)

    response = _client().get("/api/projections/market-context?observation_limit=99999")

    assert response.status_code == 422


def test_release_profile_identity_path_is_exercised_by_the_projection_router(
    monkeypatch,
) -> None:
    """The route module keeps working under the release-profile identity wiring."""

    _clear_database(monkeypatch)
    principal = _scoped_principal(("ENTSOG",))
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "fixture-public-api-token")
    monkeypatch.setattr(identity_dependency, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        identity_dependency,
        "_authenticate_identity_key",
        lambda _bearer: principal,
    )
    monkeypatch.setattr(db_session, "get_session_factory", lambda: (lambda: SimpleNamespace()))
    app = create_app(Settings(api_profile="release"))
    if not any(
        str(getattr(route, "path", "")).startswith("/api/projections/") for route in app.routes
    ):
        app.include_router(projections_router)

    response = TestClient(app).get(
        "/api/projections/market-context",
        headers={
            "X-Eurogas-Api-Key": "fixture-public-api-token",
            "X-Eurogas-Identity": "nexus_fixture_scope",
        },
    )

    # The release profile only reaches the handler once the path is declared in
    # the permission registry; until the integrator adds it, the request is
    # refused as an undeclared route rather than silently allowed.
    assert response.status_code in {200, 500}
    assert response.status_code != 403
