"""P-08, QA-T-02, QA-L-22: one hub and month reads one price on every screen at one instant.

On the demo desk TTF's front month is held three ways: the board's month quote (five minutes
old), the demo forward curve (an hour old) and the month-ahead close history (yesterday). Before
the price resolver the Prices board showed the quote, Today and the brief the close and the
ladder the curve. Now each screen's endpoint states the same price, kind and source for the
same hub and month, and it is the freshest one in date.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.price_resolver import open_price_book
from eurogas_nexus.application.valuation_snapshot import open_valuation_snapshot
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.security.identity import legacy_public_token_principal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'desk.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, datetime.now(UTC), history_days=40)
        owner = create_identity_principal(
            session,
            name="desk-trader",
            display_name="Trader",
            role="ANALYST",
            data_scopes=["*"],
        )
        _, bearer = create_identity_api_key(
            session, owner.principal_id, display_name="desk", scopes=["*"]
        )
        session.commit()
    client = TestClient(
        create_app(),
        headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
    )
    return engine, client


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_ttf_front_month_reads_one_price_on_every_screen(desk):
    engine, client = desk
    today = _ok(client.get("/api/desk/today"))
    key = next(item for item in today["rows"][0]["prices"] if item.get("hub") == "TTF")
    one = key["resolved_price"]
    assert one is not None, key
    month = one["period_start"][:7]
    # The freshest in-date price wins: the board's month quote, not the hour-old curve or
    # yesterday's close; it says what it is, where it came from and how fresh it is.
    assert one["kind"] == "live_tick" and one["source_system"] == "DEMO_Sim"
    assert one["state"] in {"current", "late"} and one["simulated"] is True
    assert key["value"] == one["value"] and key["state"] == one["state"]

    # Today, "My market": the same price for the front month.
    market = next(h for h in today["rows"][0]["market"]["hubs"] if h["hub"] == "TTF")
    assert market["front_month"]["resolved_price"] == one
    assert market["front_month"]["value"] == one["value"]
    # Today, the book row's mark is that price.
    book = next(h for h in today["rows"][2]["hubs"] if h["hub"] == "TTF")
    assert book["mark"]["value_mwh"] == pytest.approx(one["value_mwh"], abs=1e-4)

    # Position ladder: the TTF row for that month is marked at the same price.
    ladder = _ok(client.get("/api/portfolio/position-ladder?months=3"))
    row = next(r for r in ladder["rows"] if r["hub"] == "TTF" and r["month"] == month)
    assert row["mark"] == pytest.approx(one["value_mwh"], abs=1e-4)
    assert row["resolved_price"]["reference"] == one["reference"]
    assert row["mark_method"] == "quoted"

    # Desk brief: the TTF line states the same price.
    brief = _ok(client.post("/api/analysis/brief", json={"kind": "morning"}))
    stated = next(item for item in brief["resolved_prices"] if item["hub"] == "TTF")
    assert stated["value_mwh"] == pytest.approx(one["value_mwh"])
    assert stated["reference"] == one["reference"]
    line = next(
        text
        for s in brief["sections"]
        if s["key"] == "prices"
        for text in s["lines"]
        if text.startswith("TTF")
    )
    assert f"{one['value']:.2f}" in line

    # Prices board: every TTF quote for that month carries the same resolved price.
    quotes = _ok(client.get("/api/market/quotes?hub=TTF"))
    for_month = [
        q
        for q in quotes
        if q["resolved_price"]
        and q["resolved_price"]["period_start"] == one["period_start"]
        and q["resolved_price"]["period_end"] == one["period_end"]
    ]
    assert for_month, "the board holds the month"
    assert all(q["resolved_price"]["value_mwh"] == one["value_mwh"] for q in for_month)

    # The valuation snapshot behind the opportunity scan and the LNG cargo economics.
    first = datetime.fromisoformat(one["period_start"]).date()
    with Session(engine) as session:
        reader = open_valuation_snapshot(
            session, caller=Caller(legacy_public_token_principal()), demo_desk=True
        )
        mid = reader.price("TTF", DeliveryPeriod.month(first.year, first.month), "mid")
    assert float(mid.value) == pytest.approx(one["value_mwh"], abs=1e-6)
    assert mid.source_ref == one["reference"]


def test_the_curve_and_the_close_are_held_but_lose_to_the_fresher_quote(desk):
    engine, _ = desk
    now = datetime.now(UTC)
    start = (now.date().replace(day=28) + timedelta(days=4)).replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    with Session(engine) as session:
        book = open_price_book(session, None, now=now)
    held = {c.kind for c in book.for_hub("TTF") if c.covers(start, end)}
    assert {"live_tick", "settlement"} <= held
    answer = book.month("TTF", f"{start:%Y-%m}")
    assert answer.kind == "live_tick" and answer.considered >= 2
