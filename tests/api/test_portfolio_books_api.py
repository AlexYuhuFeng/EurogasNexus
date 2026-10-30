"""Books roll positions up by legal entity, region and business, in one reporting currency."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    MarketObservationRecord,
    ScreenOrderObservationRecord,
    StrategyRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)


def _order(order_id, hub, side, price, currency, month_start, now):
    return ScreenOrderObservationRecord(
        order_observation_id=order_id,
        provider_id="ICE_OCM",
        venue="ICE",
        account_label="desk",
        external_order_id=order_id,
        side=side,
        order_type="LIMIT",
        hub=hub,
        product="M+1",
        contract_code=f"{hub}-M1",
        delivery_start_utc=month_start,
        delivery_end_utc=month_start + timedelta(days=30),
        price=price,
        currency=currency,
        unit=f"{currency}/MWh",
        quantity_mwh=30_000,
        filled_quantity_mwh=30_000,
        remaining_quantity_mwh=0,
        status="FILLED",
        observed_at_utc=now,
        source_system="fixture-runtime",
        source_reference=f"fixture:{order_id}",
        linked_strategy_id="book-test",
        linked_resource_id=None,
        research_only=True,
        human_review_required=True,
    )


def _quote(obs_id, hub, price, currency, month_start, at):
    return MarketObservationRecord(
        observation_id=obs_id,
        market_venue="ICE",
        product=f"{hub} month-ahead",
        price=price,
        unit=f"{currency}/MWh",
        currency=currency,
        period_start_utc=month_start,
        period_end_utc=(month_start.replace(day=28) + timedelta(days=4)).replace(day=1),
        observed_at_utc=at,
        source_system="ICE_OCM",
        source_reference=obs_id,
        freshness="end_of_day",
        quality_score=0.9,
        research_only=True,
        metadata_json={"hub": hub, "tenor": "month-ahead"},
    )


def test_books_roll_up_by_legal_entity_in_eur(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'books.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    month_start = (now.replace(day=1) + timedelta(days=32)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    with Session(engine) as session:
        owner = create_identity_principal(
            session, name="mo", display_name="Middle office", role="OPERATOR", data_scopes=["*"]
        )
        _, bearer = create_identity_api_key(
            session, owner.principal_id, display_name="b", scopes=["*"]
        )
        session.add(
            StrategyRecord(
                strategy_id="book-test",
                name="Books",
                owner_principal_id=owner.principal_id,
                visibility="PRIVATE",
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        session.add(_order("nbp-buy", "NBP", "BUY", 30.0, "GBP", month_start, now))
        session.add(_order("ttf-sell", "TTF", "SELL", 36.0, "EUR", month_start, now))
        session.add(_quote("nbp-q", "NBP", 31.0, "GBP", month_start, now - timedelta(hours=2)))
        session.add(_quote("ttf-q", "TTF", 35.0, "EUR", month_start, now - timedelta(hours=2)))
        session.add(
            FxObservationRecord(
                observation_id="ecb-gbp",
                pair="EURGBP",
                base_currency="EUR",
                quote_currency="GBP",
                rate=0.8,
                rate_type="reference",
                value_date=now.date().isoformat(),
                observed_at_utc=now,
                source_system="ECB",
                source_reference="t",
                freshness="daily",
                research_only=True,
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(
        create_app(),
        headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
    )

    for book_id, entity, order in (
        ("uk-nbp", "EGN-UK", "nbp-buy"),
        ("nl-ttf", "EGN-NL", "ttf-sell"),
    ):
        response = client.put(
            f"/api/portfolio/books/{book_id}",
            json={
                "name": book_id,
                "legal_entity": entity,
                "region": "europe",
                "business": "NW Europe gas",
                "commodities": ["natural_gas"],
                "order_ids": [order],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["orders_assigned"] == 1
    books = client.get("/api/portfolio/books").json()["data"]
    assert books["hierarchy"]["EGN-UK"]["europe"]["NW Europe gas"] == ["uk-nbp"]

    ladder = client.get("/api/portfolio/position-ladder?months=3&group_by=legal_entity").json()[
        "data"
    ]
    assert ladder["reporting_currency"] == "EUR"
    groups = {row["group"]: row for row in ladder["rollup"]}
    # NBP: bought 30,000 MWh at 30 GBP, marked 31 -> +30,000 GBP = 37,500 EUR at 0.8.
    assert groups["EGN-UK"]["mark_to_market"] == 37_500.0
    # TTF: sold 30,000 MWh at 36 EUR, marked 35 -> +30,000 EUR.
    assert groups["EGN-NL"]["mark_to_market"] == 30_000.0
    assert ladder["mark_to_market"] == 67_500.0
    firm = client.get("/api/portfolio/position-ladder?months=3&group_by=firm").json()["data"]
    assert firm["rollup"][0]["group"] == "FIRM" and firm["rollup"][0]["mark_to_market"] == 67_500.0
    in_gbp = client.get("/api/portfolio/position-ladder?months=3&reporting_currency=GBP").json()
    assert in_gbp["data"]["mark_to_market"] == 54_000.0  # 30,000 + 30,000 EUR x 0.8
