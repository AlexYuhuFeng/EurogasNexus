"""Head office sees every book; a regional head sees only its own office's books."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ScreenOrderObservationRecord, TradingBookRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.security.portfolio_scope import scope_from_data_scopes

PUBLIC = "test-public-api-token"


def _order(order_id, hub, book_id, start):
    return ScreenOrderObservationRecord(
        order_observation_id=order_id,
        provider_id="ETRM",
        venue="Endur",
        account_label="desk",
        external_order_id=order_id,
        side="BUY",
        order_type="TRADE",
        hub=hub,
        product="ETRM",
        contract_code=order_id,
        delivery_start_utc=start,
        delivery_end_utc=start + timedelta(days=30),
        price=30.0,
        currency="GBP" if hub == "NBP" else "EUR",
        unit="GBP/MWh" if hub == "NBP" else "EUR/MWh",
        quantity_mwh=30_000,
        filled_quantity_mwh=30_000,
        remaining_quantity_mwh=0,
        status="FILLED",
        observed_at_utc=start,
        source_system="ETRM",
        source_reference="t",
        linked_strategy_id=None,
        linked_resource_id=None,
        research_only=True,
        human_review_required=True,
        book_id=book_id,
    )


def test_scope_parsing():
    head = scope_from_data_scopes(["EEX", "BOOKS:*"])
    assert head.all_books and head.allows(None, None, None)
    uk = scope_from_data_scopes(["books:entity:egn-uk"])
    assert uk.allows("uk-nbp", "EGN-UK", "europe")
    assert not uk.allows("ca-gas", "EGN-CA", "north_america")
    assert not uk.allows(None, None, None)  # unbooked positions are head-office only
    assert scope_from_data_scopes(["*"]).all_books


def test_regional_heads_cannot_see_each_other(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'iso.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    start = (now.replace(day=1) + timedelta(days=40)).replace(day=1, hour=5, minute=0)
    headers = {}
    with Session(engine) as session:
        for name, scopes in (
            ("head", ["BOOKS:*"]),
            ("uk", ["BOOKS:ENTITY:EGN-UK"]),
            ("ca", ["BOOKS:REGION:NORTH_AMERICA"]),
            ("nobody", []),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role="OPERATOR", data_scopes=scopes
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            headers[name] = {"X-Eurogas-Api-Key": PUBLIC, "X-Eurogas-Identity": bearer}
        for book_id, entity, region in (
            ("uk-nbp", "EGN-UK", "europe"),
            ("ca-gas", "EGN-CA", "north_america"),
        ):
            session.add(
                TradingBookRecord(
                    book_id=book_id,
                    name=book_id,
                    legal_entity=entity,
                    region=region,
                    business="gas",
                    base_currency="EUR",
                    active=True,
                    updated_by="t",
                    updated_at_utc=now,
                )
            )
        session.add(_order("uk-1", "NBP", "uk-nbp", start))
        session.add(_order("ca-1", "TTF", "ca-gas", start))
        session.add(_order("loose-1", "TTF", None, start))
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "true")
    client = TestClient(create_app())

    def orders(who):
        response = client.get("/api/portfolio/screen-orders", headers=headers[who])
        assert response.status_code == 200, response.text
        return sorted(o["order_observation_id"] for o in response.json()["data"])

    assert orders("head") == ["ca-1", "loose-1", "uk-1"]
    assert orders("uk") == ["uk-1"]
    assert orders("ca") == ["ca-1"]
    assert orders("nobody") == []

    def books(who):
        data = client.get("/api/portfolio/books", headers=headers[who]).json()["data"]
        return sorted(b["book_id"] for b in data["books"])

    assert books("head") == ["ca-gas", "uk-nbp"]
    assert books("uk") == ["uk-nbp"]

    ladder = client.get(
        "/api/portfolio/position-ladder?months=4&group_by=legal_entity", headers=headers["uk"]
    ).json()["data"]
    assert [row["group"] for row in ladder["rollup"]] == ["EGN-UK"]
    head = client.get(
        "/api/portfolio/position-ladder?months=4&group_by=legal_entity", headers=headers["head"]
    ).json()["data"]
    assert [row["group"] for row in head["rollup"]] == ["EGN-CA", "EGN-UK", "UNASSIGNED"]

    # The UK head cannot redefine Canada's book or pull its trades.
    refused = client.put(
        "/api/portfolio/books/ca-gas",
        headers=headers["uk"],
        json={"name": "x", "legal_entity": "EGN-CA", "region": "north_america", "business": "g"},
    )
    assert refused.status_code == 403
    moved = client.put(
        "/api/portfolio/books/uk-nbp",
        headers=headers["uk"],
        json={
            "name": "uk",
            "legal_entity": "EGN-UK",
            "region": "europe",
            "business": "gas",
            "order_ids": ["ca-1"],
        },
    )
    assert moved.status_code == 200 and moved.json()["data"]["orders_assigned"] == 0

    # Isolation off: everyone sees everything, as before.
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "false")
    assert orders("nobody") == ["ca-1", "loose-1", "uk-1"]
