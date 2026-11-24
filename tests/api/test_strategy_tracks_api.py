"""Tracked strategies (paper shadow run) driven by feed ticks, end to end through the API.

An analyst tracks TTF WD − DA mean reversion; a data-operations identity delivers ticks from a
licensed feed (``EEX``); the track is evaluated on arrival, fills on paper against the quote on
the screen, marks the position, closes it, and its changed signal reaches "What needs me" as a
line that is not an instruction. Another analyst cannot see the track; an analyst cannot
deliver ticks; a viewer cannot track.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base

PUBLIC_TOKEN = "test-public-api-token"
SPEC = {"version": 1, "kind": "history", "unit": "EUR/MWh",
        "legs": [{"hub": "TTF", "tenor": "WD", "weight": 1},
                 {"hub": "TTF", "tenor": "DA", "weight": -1}]}
RULE = {"kind": "zscore_window", "window_minutes": 30, "min_points": 20, "entry_z": 2.0,
        "exit_z": 0.5, "size_mw": 10, "min_top_size_mwh": 24, "max_quote_age_seconds": 600,
        "debounce_seconds": 0}


CUTOFF = {"at": None}


@pytest.fixture()
def clients(tmp_path, monkeypatch):
    # The renomination cut-off depends on the hour the suite runs; pin it (far, unless a test
    # moves it) so the result does not depend on the time of day.
    from eurogas_nexus.application import strategy_tracking

    CUTOFF["at"] = datetime.now(UTC) + timedelta(hours=6)
    monkeypatch.setattr(strategy_tracking, "cutoff_for", lambda legs, state, now: CUTOFF["at"])
    url = f"sqlite+pysqlite:///{(tmp_path / 'tracks.sqlite').as_posix()}"
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
                                      ("other", "ANALYST", ["TRADER"]),
                                      ("ops", "OPERATOR", ["DATA_OPERATOR"]),
                                      ("ops_any", "OPERATOR", ["DATA_OPERATOR"]),
                                      ("viewer", "VIEWER", [])):
            principal = create_identity_principal(
                session, name=f"track-{name}", display_name=name, role=role, data_scopes=["*"],
            )
            principal.job_functions = functions
            # The feed's service key is scoped to the licensed family it delivers; a '*'
            # key reads everything but may not label prices as that venue's.
            _, keys[name] = create_identity_api_key(
                session, principal.principal_id, scopes=["EEX"] if name == "ops" else ["*"]
            )
        session.commit()
    app = create_app()
    return {
        name: TestClient(app, headers={"X-Eurogas-Api-Key": PUBLIC_TOKEN,
                                       "X-Eurogas-Identity": bearer})
        for name, bearer in keys.items()
    }


def _ticks(client, at, wd_mid, da_mid=41.0, half=0.01, size=20):
    quotes = [
        {"hub": "TTF", "product": product, "exchange_time": at.isoformat(),
         "bid": round(mid - half, 3), "ask": round(mid + half, 3), "bid_qty": size,
         "ask_qty": size}
        for product, mid in (("WD", wd_mid), ("DA", da_mid))
    ]
    response = client.post("/api/market/ticks", json={"source_system": "EEX", "quotes": quotes})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_a_tracked_strategy_trades_on_paper_as_ticks_arrive(clients):
    created = clients["trader"].post("/api/research/strategy-tracks", json={
        "name": "TTF WD-DA", "mode": "intraday", "spec": SPEC, "rule": RULE})
    assert created.status_code == 200, created.text
    track = created.json()["data"]
    assert track["paper"] is True and created.json()["meta"]["paper_only"] is True
    assert "Paper only" in track["assumptions"]
    track_id = track["track_id"]

    start = datetime.now(UTC) - timedelta(minutes=9)
    for i in range(24):
        data = _ticks(clients["ops"], start + timedelta(seconds=20 * i),
                      41.10 + (0.01 if i % 2 else -0.01))
    assert data["evaluation"]["evaluated"] == 1
    spike = _ticks(clients["ops"], start + timedelta(seconds=500), 41.30)
    assert spike["evaluation"]["results"][0]["signal_changed"] is True

    detail = clients["trader"].get(f"/api/research/strategy-tracks/{track_id}").json()["data"]
    assert detail["snapshot"]["signal"] == "short"
    [fill] = [entry for entry in detail["blotter"] if entry["kind"] == "fill"]
    # Sell the spread: WD at its bid 41.29, DA at its offer 41.01; 10 MW = 240 MWh/d, inside
    # the 20 MW (480 MWh/d) quoted.
    assert fill["price"] == pytest.approx(0.28)
    assert fill["qty_mwh_per_day"] == pytest.approx(240.0)
    assert fill["paper"] is True
    # The paper fill answers an order intent: what a desk would put on the screen, never sent.
    [intent] = detail["intents"]
    assert intent["intent_id"] == fill["intent_id"] and intent["sent"] is False
    assert intent["side"] == "sell_spread" and intent["limit"] == pytest.approx(0.28)
    assert [leg["side"] for leg in intent["legs"]] == ["sell", "buy"]
    assert intent["checks"]["positive_edge"] is True
    advice = detail["snapshot"]["advice"]
    assert advice["signal"] == "short" and advice["entry_level"] == pytest.approx(0.28)
    assert advice["expires_at"]

    # "What needs me": the changed signal, as a sentence that is not an instruction.
    found = clients["trader"].get("/api/discoveries", params={"function": "TRADER"})
    assert found.status_code == 200, found.text
    [line] = [item for item in found.json()["data"]["items"]
              if item["kind"] == "strategy.signal"]
    assert "sell the spread" in line["sentence"] and "Not an instruction" in line["sentence"]
    assert line["link"] == {"page": "research/spreads", "track_id": track_id}

    back = _ticks(clients["ops"], start + timedelta(seconds=520), 41.10)
    assert back["evaluation"]["results"][0]["signal_changed"] is True
    detail = clients["trader"].get(f"/api/research/strategy-tracks/{track_id}").json()["data"]
    close = [entry for entry in detail["blotter"] if entry.get("action") == "close"][0]
    assert close["price"] == pytest.approx(41.11 - 40.99)
    assert close["pnl"] == pytest.approx((0.28 - 0.12) * 240)
    assert detail["snapshot"]["realised"] == pytest.approx(38.4)
    assert detail["equity"][-1]["equity"] == pytest.approx(38.4)
    found = clients["trader"].get("/api/discoveries", params={"function": "TRADER"}).json()
    [closed] = [i for i in found["data"]["items"] if i["kind"] == "strategy.close"]
    assert "closed its paper position" in closed["sentence"] and " at -" not in closed["sentence"]

    # Only the owner sees it; stopping keeps its history.
    assert clients["other"].get(f"/api/research/strategy-tracks/{track_id}").status_code == 404
    assert clients["other"].get("/api/research/strategy-tracks").json()["data"] == []
    stopped = clients["trader"].post(f"/api/research/strategy-tracks/{track_id}/stop")
    assert stopped.json()["data"]["state"] == "stopped"


def test_who_may_track_and_who_may_deliver_ticks(clients):
    refused = clients["viewer"].post("/api/research/strategy-tracks", json={
        "name": "x", "mode": "intraday", "spec": SPEC, "rule": RULE})
    assert refused.status_code == 403
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


def test_bad_tracks_are_refused_with_the_field(clients):
    curve = clients["trader"].post("/api/research/strategy-tracks", json={
        "name": "x", "mode": "intraday",
        "spec": {**SPEC, "legs": [{"hub": "TTF", "tenor": "Q1-27", "weight": 1},
                                  {"hub": "TTF", "tenor": "DA", "weight": -1}]},
        "rule": RULE})
    assert curve.status_code == 422 and curve.json()["detail"]["field"] == "spec.legs"
    mixed = clients["trader"].post("/api/research/strategy-tracks", json={
        "name": "x", "mode": "intraday",
        "spec": {**SPEC, "legs": [{"hub": "NBP", "tenor": "DA", "weight": 1},
                                  {"hub": "TTF", "tenor": "DA", "weight": -1}]},
        "rule": RULE})
    assert mixed.status_code == 422 and "one currency" in mixed.json()["detail"]["message"]
    order = clients["trader"].post("/api/research/strategy-tracks", json={
        "name": "x", "mode": "intraday", "spec": SPEC, "rule": {"order_type": "market"}})
    assert order.status_code == 422 and order.json()["detail"]["field"] == "rule"


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


def test_a_signal_is_withdrawn_at_its_cut_off_and_logged_as_missed(clients):
    track_id = clients["trader"].post("/api/research/strategy-tracks", json={
        "name": "TTF WD-DA", "mode": "intraday", "spec": SPEC, "rule": RULE}).json()["data"][
        "track_id"]
    start = datetime.now(UTC) - timedelta(minutes=9)
    for i in range(24):
        _ticks(clients["ops"], start + timedelta(seconds=20 * i),
               41.10 + (0.01 if i % 2 else -0.01))
    CUTOFF["at"] = datetime.now(UTC) + timedelta(seconds=1)
    _ticks(clients["ops"], start + timedelta(seconds=500), 41.30)
    advice = clients["trader"].get(f"/api/research/strategy-tracks/{track_id}").json()["data"][
        "snapshot"]["advice"]
    assert advice["cutoff_at"] == CUTOFF["at"].isoformat()
    assert advice["expires_at"] <= advice["cutoff_at"]
    assert advice["quote_age_seconds"]
    import time

    time.sleep(1.2)
    _ticks(clients["ops"], start + timedelta(seconds=505), 41.31)
    detail = clients["trader"].get(f"/api/research/strategy-tracks/{track_id}").json()["data"]
    assert detail["snapshot"]["advice"] is None
    assert detail["snapshot"]["withdrawn"]["reason"] == "expired"
    assert [s["reason"] for s in detail["signals"] if s["kind"] == "missed"] == ["expired"]
    found = clients["trader"].get("/api/discoveries", params={"function": "TRADER"}).json()
    assert not [i for i in found["data"]["items"] if i["kind"] == "strategy.signal"]
    desk = clients["trader"].get("/api/market/prompt", params={"hub": "TTF"})
    assert desk.status_code == 200, desk.text
    data = desk.json()["data"]
    assert data["performance"]["missed_signals"][0]["reason"] == "expired"
    assert data["market"]["within_day"]["quote"]["bid"] == pytest.approx(41.30)
    assert data["spread_wd_da"]["sell"] == pytest.approx(41.30 - 41.01, abs=1e-6)
    assert data["execution"].startswith("none")
