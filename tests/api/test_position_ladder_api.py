"""Position ladder: stored contracts and filled hedges by hub and month, with MtM and VaR."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    MarketObservationRecord,
    ScreenOrderObservationRecord,
    StrategyRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)


def test_ladder_combines_physical_supply_and_financial_hedge(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'ladder.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    month_start = (now.replace(day=1) + timedelta(days=32)).replace(
        day=1, hour=5, minute=0, second=0, microsecond=0
    )
    with Session(engine) as session:
        owner = create_identity_principal(
            session, name="ladder-owner", display_name="Ladder", role="ANALYST", data_scopes=["*"]
        )
        _, bearer = create_identity_api_key(
            session, owner.principal_id, display_name="ladder", scopes=["*"]
        )
        session.add(
            StrategyRecord(
                strategy_id="hedge-book",
                name="Hedges",
                owner_principal_id=owner.principal_id,
                visibility="PRIVATE",
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        session.add(
            UpstreamResourceContractRecord(
                contract_id="nbp-supply",
                contract_name="NBP supply",
                resource_type="PIPELINE_IMPORT",
                delivery_point_name="NBP",
                gas_year=f"{now.year - 1}+",
                delivery_quantity_mwh_per_day=1_000.0,
                contract_price_gbp_mwh=30.0,
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=2.0,
                nomination_tolerance_pct=1.0,
                tolerance_risk_allowance_gbp_mwh=None,
                annual_financing_rate_pct=5.0,
                owned_entry_capacity_mwh_per_day=None,
                owned_exit_capacity_mwh_per_day=None,
                allowed_exit_points=["NBP"],
                eligible_sale_modes=["LOCAL_MARKET_SALE"],
                notes=None,
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        session.add(
            ScreenOrderObservationRecord(
                order_observation_id="hedge-1",
                provider_id="ICE_OCM",
                venue="ICE",
                account_label="desk",
                external_order_id="h1",
                side="SELL",
                order_type="LIMIT",
                hub="NBP",
                product="M+1",
                contract_code="NBP-M1",
                delivery_start_utc=month_start,
                delivery_end_utc=month_start + timedelta(days=30),
                price=32.0,
                currency="GBP",
                unit="GBP/MWh",
                quantity_mwh=18_000,
                filled_quantity_mwh=18_000,
                remaining_quantity_mwh=0,
                status="FILLED",
                observed_at_utc=now,
                source_system="fixture-runtime",
                source_reference="fixture:hedge",
                linked_strategy_id="hedge-book",
                linked_resource_id=None,
                research_only=True,
                human_review_required=True,
            )
        )
        for day in range(30):
            at = now - timedelta(days=30 - day)
            session.add(
                MarketObservationRecord(
                    observation_id=f"nbp-{day}",
                    market_venue="ICE",
                    product="NBP month-ahead",
                    price=31.0 + (0.5 if day % 2 else 0.0),
                    unit="GBP/MWh",
                    currency="GBP",
                    period_start_utc=month_start,
                    period_end_utc=month_start + timedelta(days=30),
                    observed_at_utc=at,
                    source_system="ICE_OCM",
                    source_reference=f"nbp:{day}",
                    freshness="end_of_day",
                    quality_score=0.9,
                    research_only=True,
                    metadata_json={"hub": "NBP", "tenor": "month-ahead"},
                )
            )
        # A quarter quote after the month: the curve derives the months it does not fix.
        quarter_start = (month_start + timedelta(days=32)).replace(day=1)
        quarter_end = quarter_start
        for _ in range(3):
            quarter_end = (quarter_end + timedelta(days=32)).replace(day=1)
        session.add(
            MarketObservationRecord(
                observation_id="nbp-quarter",
                market_venue="ICE",
                product="NBP quarter",
                price=34.0,
                unit="GBP/MWh",
                currency="GBP",
                period_start_utc=quarter_start,
                period_end_utc=quarter_end,
                observed_at_utc=now - timedelta(hours=1),
                source_system="ICE_OCM",
                source_reference="nbp:quarter",
                freshness="end_of_day",
                quality_score=0.9,
                research_only=True,
                metadata_json={"hub": "NBP", "tenor": "Q+1"},
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(
        create_app(),
        headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
    ).get("/api/portfolio/position-ladder?months=3")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    next_month = f"{month_start.year:04d}-{month_start.month:02d}"
    row = next(r for r in data["rows"] if r["hub"] == "NBP" and r["month"] == next_month)
    days_in_month = (month_start.replace(day=28) + timedelta(days=4)).replace(
        day=1
    ) - month_start.replace(day=1)
    assert row["physical_mwh"] == 1_000.0 * days_in_month.days
    assert row["financial_mwh"] == -18_000.0
    assert row["hedge_ratio"] is not None and 0 < row["hedge_ratio"] < 1
    assert data["legs"] == {"physical": 1, "financial": 1}
    assert data["mark_to_market"] is not None
    assert data["var_95_1d"] is not None and data["var_95_1d"] > 0
    assert any(
        "Not a substitute for the risk system" in w for w in response.json()["meta"]["warnings"]
    )
    # Marks come from the curve: the month quote as quoted, the quarter's months derived.
    assert row["mark"] == 31.5 and row["mark_method"] == "quoted"
    quarter_month = f"{quarter_start.year:04d}-{quarter_start.month:02d}"
    point = next(p for p in data["curve"] if p["hub"] == "NBP" and p["month"] == quarter_month)
    assert point["method"] == "derived" and point["price"] == 34.0
