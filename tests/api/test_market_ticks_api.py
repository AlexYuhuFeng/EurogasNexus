"""Licensed feed tick ingestion through the API.

A data-operations identity delivers quotes and trade prints from a licensed feed (``EEX``);
they are stored under the source family and read back as normalized quotes. An analyst cannot
deliver ticks; a '*' scope key may read everything but may not label prices as a licensed
venue's.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base

PUBLIC_TOKEN = "test-public-api-token"


@pytest.fixture()
def clients(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'ticks.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    keys = {}
    with Session(engine) as session:
        for name, role, functions in (("trader", "ANALYST", ["TRADER"]),
                                      ("ops", "OPERATOR", ["DATA_OPERATOR"]),
                                      ("ops_any", "OPERATOR", ["DATA_OPERATOR"])):
            principal = create_identity_principal(
                session, name=f"feed-{name}", display_name=name, role=role,
                data_scopes=["*", "PUBLISH:EEX"] if name == "ops" else ["*"],
                # The feed connector is a service identity, not a person (H4).
                principal_type="SERVICE" if name == "ops" else "USER",
            )
            principal.job_functions = functions
            # The feed's service key is scoped to the licensed family it publishes; a '*'
            # key reads everything but may not label prices as that venue's.
            _, keys[name] = create_identity_api_key(
                session, principal.principal_id,
                scopes=["EEX", "PUBLISH:EEX"] if name == "ops" else ["*"],
            )
        session.commit()
    app = create_app()
    return {
        name: TestClient(app, headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN,
                                       "X-Eurogas-Identity": bearer})
        for name, bearer in keys.items()
    }


def test_who_may_deliver_ticks(clients):
    now = datetime.now(UTC).isoformat()
    tick = {"source_system": "EEX", "quotes": [
        {"hub": "TTF", "product": "DA", "exchange_time": now, "bid": 41, "ask": 41.1}]}
    assert clients["trader"].post("/api/market/ticks", json=tick).status_code == 403
    unknown = clients["ops"].post("/api/market/ticks", json={**tick, "source_system": "Nowhere"})
    assert unknown.status_code == 422
    crossed = clients["ops"].post("/api/market/ticks", json={"source_system": "EEX", "quotes": [
        {"hub": "TTF", "product": "DA", "exchange_time": now, "bid": 42, "ask": 41}]})
    assert crossed.status_code == 422
    # A '*' scope reads everything but may not label prices as a licensed venue's.
    star = clients["ops_any"].post("/api/market/ticks", json=tick)
    assert star.status_code == 403 and star.json()["detail"]["code"] == "source_not_granted"
    fat = clients["ops"].post("/api/market/ticks", json={"source_system": "EEX", "quotes": [
        {"hub": "TTF", "product": "M+1", "exchange_time": now, "bid": 4100, "ask": 4110}]})
    assert fat.status_code == 422 and "plausible ceiling" in fat.json()["detail"]["message"]


def test_trade_prints_and_session_fields_are_stored(clients):
    now = datetime.now(UTC)
    body = {
        "source_system": "EEX",
        "quotes": [{"hub": "NBP", "product": "DA", "exchange_time": now.isoformat(),
                    "bid": 97.6, "ask": 97.7, "bid_qty": 50000, "ask_qty": 25000,
                    "vwap": 97.65, "volume": 300000, "trade_count": 7, "open": 97.2,
                    "high": 97.9, "low": 97.1, "prior_settlement": 97.0}],
        "trades": [{"trade_id": "T1", "hub": "NBP", "product": "DA",
                    "exchange_time": now.isoformat(), "price": 97.7, "qty": 25000,
                    "trade_type": "screen", "aggressor": "buy"}],
    }
    response = clients["ops"].post("/api/market/ticks", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["quotes"] == 1 and response.json()["data"]["trades"] == 1
    quotes = clients["trader"].get("/api/market/quotes", params={"hub": "NBP"}).json()["data"]
    quote = next(q for q in quotes if q["source_system"] == "EEX")
    # Pence per therm stored per MWh in GBP; therms/day as MWh per gas day.
    assert quote["vwap"] == pytest.approx(97.65 * 0.01 / 0.0293071, rel=1e-4)
    assert quote["volume_mwh"] == pytest.approx(300000 * 0.0293071, rel=1e-4)
    assert quote["trade_count"] == 7
    bad = clients["ops"].post("/api/market/ticks", json={**body, "quotes": [], "trades": [
        {**body["trades"][0], "trade_id": "T2", "trade_type": "dark"}]})
    assert bad.status_code == 422
