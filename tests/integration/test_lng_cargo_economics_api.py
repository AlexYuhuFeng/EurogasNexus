"""The cargo economics read end to end (CP-12): routes, assumptions, marks, FX, terms.

Figures are synthetic (design C.3 inputs). The hub mark is the firm's own mark and the FX is the
ECB reference rate (spot for a forward month: indicative, "FX: spot").
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    FxObservationRecord,
    InterestRateObservationRecord,
    LngTerminalTermsRecord,
    MarketObservationRecord,
)
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.db.repositories.commercial_assumptions import (
    approve_assumption_version,
    create_assumption_set,
    create_assumption_version,
    put_firm_marks,
)
from eurogas_nexus.domain.valuation.assumptions import validate_assumption_value
from eurogas_nexus.domain.valuation.firm_marks import validate_firm_mark
from eurogas_nexus.security import rate_limit as rate_limit_module

PUBLIC_TOKEN = "test-public-api-token"


def _arrival() -> str:
    today = datetime.now(UTC).date()
    year, month = (today.year + 1, 1) if today.month >= 11 else (today.year, today.month + 2)
    return f"{year:04d}-{month:02d}"


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'cargo.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_TOKEN)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rate_limit_module._WINDOWS.clear()
    now = datetime.now(UTC)
    bearers = {}
    with Session(engine) as db:
        for name, role in (("c-analyst", "ANALYST"), ("c-viewer", "VIEWER")):
            row = identity_repository.create_identity_principal(
                db, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearers[name] = identity_repository.create_identity_api_key(db, row.principal_id)
        arrival = _arrival()
        put_firm_marks(
            db,
            [validate_firm_mark("TTF", arrival, "30.00", "EUR/MWh")],
            actor="trader",
            now_utc=now - timedelta(hours=1),
        )
        db.add(
            FxObservationRecord(
                observation_id="ecb-usd",
                pair="EURUSD",
                base_currency="EUR",
                quote_currency="USD",
                rate=1.16,
                rate_type="reference",
                value_date=(now.date() - timedelta(days=1)).isoformat(),
                observed_at_utc=now - timedelta(hours=20),
                source_system="ECB",
                source_reference="ecb",
                freshness="daily",
                research_only=True,
            )
        )
        day = now.date() - timedelta(days=1)
        start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        db.add(
            MarketObservationRecord(
                observation_id="eia-hh",
                market_venue="EIA",
                product="HH spot",
                price=3.50,
                unit="USD/MMBtu",
                currency="USD",
                period_start_utc=start,
                period_end_utc=start + timedelta(days=1),
                observed_at_utc=start + timedelta(hours=18),
                source_system="EIA",
                source_reference="eia",
                freshness="end_of_day",
                quality_score=1.0,
                research_only=True,
                metadata_json={"hub": "HH", "tenor": "spot"},
            )
        )
        db.add(
            LngTerminalTermsRecord(
                terminal_id="gate",
                name="Gate",
                country="NL",
                hub="TTF",
                regas_tariff_per_mwh=0.95,
                entry_tariff_per_mwh=0.45,
                fuel_retention_pct=0.5,
                source_note="our terminal agreement",
                updated_by="desk",
                updated_at_utc=now,
            )
        )
        made = create_assumption_set(
            db, name="LNG desk", book_id=None, description="", actor="trader", now_utc=now
        )
        values = [
            validate_assumption_value("lng.cargo_size", 3_800_000),
            validate_assumption_value("lng.charter_hire", 45_000, currency="USD"),
            validate_assumption_value("lng.boil_off", "0.10"),
            validate_assumption_value("lng.port_costs", 150_000, currency="USD"),
            validate_assumption_value("lng.speed", 17),
            validate_assumption_value("lng.ballast_fuel", 2_000),
            validate_assumption_value("lng.insurance", "0.05"),
            validate_assumption_value("lng.fob_slope", "1.15"),
            validate_assumption_value("lng.fob_fee", "2.50", currency="USD"),
        ]
        create_assumption_version(
            db,
            set_id=made["set_id"],
            values=values,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            note="",
            actor="trader",
            now_utc=now - timedelta(hours=2),
        )
        approve_assumption_version(
            db, set_id=made["set_id"], version=1, actor="risk", now_utc=now - timedelta(hours=2)
        )
        db.commit()
    return engine, bearers, arrival


def _h(bearer):
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_fob_and_des_cargoes_in_one_table(store):
    engine, bearers, arrival = store
    client = TestClient(create_app(Settings(api_profile="release")))
    route = {
        "load_port": "Sabine Pass",
        "discharge_port": "Rotterdam",
        "discharge_terminal_id": "gate",
        "routing": "direct",
        "distance_nm": 4900,
        "source": "synthetic test distance",
    }
    assert (
        client.put(
            "/api/lng/freight-routes/sabine-rotterdam", json=route, headers=_h(bearers["c-viewer"])
        ).status_code
        == 403
    )
    saved = client.put(
        "/api/lng/freight-routes/sabine-rotterdam", json=route, headers=_h(bearers["c-analyst"])
    )
    assert saved.status_code == 200 and saved.json()["data"]["version"] == 1
    again = client.put(
        "/api/lng/freight-routes/sabine-rotterdam",
        json={**route, "distance_nm": 4950},
        headers=_h(bearers["c-analyst"]),
    ).json()["data"]
    assert again["version"] == 2  # a change adds a version
    listed = client.get("/api/lng/freight-routes", headers=_h(bearers["c-viewer"])).json()["data"]
    assert [(r["route_id"], r["version"], r["distance_nm"]) for r in listed] == [
        ("sabine-rotterdam", 2, 4950.0)
    ]
    client.put(
        "/api/lng/freight-routes/sabine-rotterdam", json=route, headers=_h(bearers["c-analyst"])
    )
    body = {
        "arrival_month": arrival,
        "cargoes": [
            {"cargo_id": "us", "label": "US Gulf", "term": "FOB", "route_id": "sabine-rotterdam"},
            {"cargo_id": "des", "label": "DES ARA", "term": "DES", "des_price": 30.00},
            {"cargo_id": "unrouted", "term": "FOB"},
            {"cargo_id": "noroute", "term": "FOB", "route_id": "nowhere"},
        ],
    }
    response = client.post("/api/lng/cargo-economics", json=body, headers=_h(bearers["c-viewer"]))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    us, des, unrouted, noroute = data["cargoes"]
    # HH is the EIA spot as an indicative proxy; the cost side matches design C.3.
    assert us["blocked"] is None and us["cost_usd_mmbtu"] == pytest.approx(7.0408, abs=1e-4)
    assert any("spot proxy" in leg["source"] for leg in us["legs"] if leg["key"] == "hh")
    gate = us["terminals"][0]
    # (30.00 - 0.45) x 0.995 - 0.95 = 28.4523; margin 28.4523 - 20.7107 = 7.7416.
    assert gate["netback_per_mwh"] == pytest.approx(28.4523, abs=1e-4)
    assert gate["margin_per_mwh"] == pytest.approx(7.7416, abs=1e-3)
    assert gate["regas_basis"] == "firm_terms" and gate["grade"] in {"assumption", "indicative"}
    # DES: 28.4523 - 30.00 = -1.5477 at a 30.00 mark.
    assert des["terminals"][0]["margin_per_mwh"] == pytest.approx(-1.5477, abs=1e-4)
    assert unrouted["blocked"] == "no_distance"  # no route given: never a guessed distance
    assert noroute["blocked"] == "no_distance"
    table = {row["cargo_id"]: row for row in data["table"]}
    assert table["us"]["best_terminal"] == "Gate" and table["des"]["term"] == "DES"
    assert data["fx_method"]
    with Session(engine) as db:
        assert db.query(AuditEventRecord).filter_by(action="lng.freight_route").count() == 3


def test_an_entered_zero_is_a_value_and_a_past_arrival_is_refused(store):
    _engine, bearers, arrival = store
    client = TestClient(create_app(Settings(api_profile="release")))
    client.put(
        "/api/lng/freight-routes/r1",
        json={
            "load_port": "A",
            "discharge_port": "B",
            "routing": "direct",
            "distance_nm": 1000,
            "source": "synthetic",
        },
        headers=_h(bearers["c-analyst"]),
    )
    body = {
        "arrival_month": arrival,
        "cargoes": [{"cargo_id": "x", "term": "FOB", "route_id": "r1", "hire_per_day": 0}],
    }
    ok = client.post("/api/lng/cargo-economics", json=body, headers=_h(bearers["c-viewer"]))
    assert ok.json()["data"]["cargoes"][0]["blocked"] is None  # zero entered is a value
    past = client.post(
        "/api/lng/cargo-economics",
        json={**body, "arrival_month": "2020-01"},
        headers=_h(bearers["c-viewer"]),
    )
    assert past.status_code == 422 and past.json()["detail"]["code"] == "arrival_in_the_past"


def test_a_voyage_the_desk_enters_and_the_delivered_spread(store):
    """No freight route held (the product ships none): the desk states the voyage as a distance
    at a speed, or as days laden; the study then gets the delivered spread by arrival month and
    the margin's sensitivities."""
    _engine, bearers, arrival = store
    client = TestClient(create_app(Settings(api_profile="release")))
    assert (
        client.get("/api/lng/freight-routes", headers=_h(bearers["c-viewer"])).json()["data"] == []
    )
    body = {
        "arrival_month": arrival,
        "series_months": 3,
        "cargoes": [
            {"cargo_id": "nm", "term": "FOB", "distance_nm": 4900, "speed_kn": 17},
            {"cargo_id": "days", "term": "FOB", "laden_days": 12},
        ],
    }
    response = client.post("/api/lng/cargo-economics", json=body, headers=_h(bearers["c-viewer"]))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    nm, days = data["cargoes"]
    assert nm["voyage"]["basis"] == "entered_distance" and days["voyage"]["basis"] == "entered_days"
    assert nm["cost_usd_mmbtu"] == pytest.approx(7.0408, abs=1e-4)
    assert days["cost_usd_mmbtu"] == nm["cost_usd_mmbtu"]  # 12.0 days is 4,900 nm at 17 kn
    distance = next(leg for leg in nm["legs"] if leg["key"] == "distance")
    assert distance["input_class"] == "assumption" and distance["source"].startswith("entered")
    gate = nm["terminals"][0]
    spread = gate["delivered_spread"]
    assert spread["arb_total"] == pytest.approx(spread["netback_total"], abs=0.01)
    assert spread["arb_total"] == pytest.approx(gate["margin_total"], abs=0.01)
    assert {row["key"] for row in nm["sensitivity"]} >= {"hire", "hub", "fx"}
    series = data["delivered_spread_series"]
    assert series["cargo_id"] == "nm" and len(series["points"]) == 3
    assert series["points"][0]["arb_per_mwh"] == pytest.approx(spread["arb_per_mwh"], abs=1e-4)
    bad = client.post(
        "/api/lng/cargo-economics",
        json={**body, "cargoes": [{"cargo_id": "x", "term": "FOB", "laden_days": 0}]},
        headers=_h(bearers["c-viewer"]),
    )
    assert bad.status_code == 422


def _henry_hub_days(db, days: int, price: float = 3.4) -> None:
    today = datetime.now(UTC).date()
    for back in range(2, days + 2):
        day = today - timedelta(days=back)
        start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        db.add(
            MarketObservationRecord(
                observation_id=f"eia-rngwhhd-{day.isoformat()}",
                market_venue="EIA",
                product="HH spot",
                price=price + back / 1000,
                unit="USD/MMBtu",
                currency="USD",
                period_start_utc=start,
                period_end_utc=start + timedelta(days=1),
                observed_at_utc=start + timedelta(hours=18),
                source_system="EIA",
                source_reference="eia",
                freshness="end_of_day",
                quality_score=1.0,
                research_only=True,
                metadata_json={"hub": "HH", "tenor": "spot"},
            )
        )


def _ttf_month_ahead_days(db, days: int) -> None:
    now = datetime.now(UTC)
    for back in range(2, days + 2):
        moment = now - timedelta(days=back)
        front = (moment.date().replace(day=1) + timedelta(days=32)).replace(day=1)
        start = datetime.combine(front, datetime.min.time(), tzinfo=UTC)
        db.add(
            MarketObservationRecord(
                observation_id=f"ice-ttf-ma-{back}",
                market_venue="EEX",
                product="TTF month-ahead",
                price=31.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=start,
                period_end_utc=(start + timedelta(days=32)).replace(day=1),
                observed_at_utc=moment.replace(hour=17),
                source_system="EEX",
                source_reference="ice",
                freshness="end_of_day",
                quality_score=1.0,
                research_only=True,
                metadata_json={"hub": "TTF", "tenor": "month-ahead", "settlement": True},
            )
        )


def test_forward_fx_and_the_henry_hub_history(store):
    """FX for the arrival month: without benchmark fixings no forward can be derived and the
    ECB spot answers, saying so; with €STR and SOFR it is the interest-parity forward, stated per
    month. Henry Hub against TTF, daily: the same chain on each day both prices are held."""
    engine, bearers, arrival = store
    client = TestClient(create_app(Settings(api_profile="release")))
    body = {
        "arrival_month": arrival,
        "history_days": 60,
        "cargoes": [{"cargo_id": "us", "term": "FOB", "distance_nm": 4900}],
    }
    first = client.post("/api/lng/cargo-economics", json=body, headers=_h(bearers["c-viewer"]))
    gate = first.json()["data"]["cargoes"][0]["terminals"][0]
    assert "FX: spot" in gate["fx_source"] and gate["fx_usd_per_unit"] == 1.16
    with Session(engine) as db:
        today = datetime.now(UTC).date()
        for benchmark, currency, rate in (("ESTR", "EUR", 2.0), ("SOFR", "USD", 4.0)):
            db.add(
                InterestRateObservationRecord(
                    observation_id=f"{benchmark}-{today}",
                    benchmark_id=benchmark,
                    currency=currency,
                    value_date=today - timedelta(days=1),
                    rate_pct=rate,
                    day_count="ACT/360",
                    source_system="ECB" if currency == "EUR" else "NYFED",
                    source_reference="test",
                    ingested_at_utc=datetime.now(UTC),
                )
            )
        _henry_hub_days(db, 30)
        _ttf_month_ahead_days(db, 30)
        # The TTF closes are EEX's: read with a key that holds that entitlement.
        reader = identity_repository.create_identity_principal(
            db, name="eex-reader", display_name="eex", role="VIEWER", data_scopes=["EEX"]
        )
        _key, eex = identity_repository.create_identity_api_key(
            db, reader.principal_id, scopes=["EEX"]
        )
        db.commit()
    data = client.post("/api/lng/cargo-economics", json=body, headers=_h(eex)).json()["data"]
    us = data["cargoes"][0]
    gate = us["terminals"][0]
    # USD rates above EUR rates: the EUR/USD forward is above spot, derived, for the month.
    assert gate["fx_usd_per_unit"] > 1.16
    assert "derived" in gate["fx_source"] and "value date" in gate["fx_source"]
    hh = next(leg for leg in us["legs"] if leg["key"] == "hh")
    assert hh["input_class"] == "indicative" and "(EIA), spot proxy" in hh["source"]
    history = data["delivered_spread_history"]
    assert history["hub"] == "TTF" and history["hh_source"] == "EIA"
    assert len(history["points"]) == 30
    point = history["points"][-1]
    assert point["hub_per_mwh"] == 31.0 and point["simulated"] is False
    assert point["arb_per_mwh"] == pytest.approx(31.0 - point["delivered_per_mwh"], abs=1e-3)


def test_the_standard_cargo_opens_priced_and_labels_what_is_not_held(store):
    """Research → Cargo & netback opens on the desk's standard cargo: what the request and the
    assumption set do not hold is the desk standard, each figure labelled; the set's own
    figures still win."""
    _engine, bearers, arrival = store
    client = TestClient(create_app(Settings(api_profile="release")))
    body = {
        "arrival_month": arrival,
        "cargoes": [{"cargo_id": "s", "term": "FOB", "standard": True}],
    }
    data = client.post(
        "/api/lng/cargo-economics", json=body, headers=_h(bearers["c-viewer"])
    ).json()["data"]
    cargo = data["cargoes"][0]
    assert cargo["blocked"] is None and cargo["voyage"]["basis"] == "standard"
    distance = next(leg for leg in cargo["legs"] if leg["key"] == "distance")
    assert distance["source"].startswith("desk standard") and distance["amount"] == 4900
    hire = next(leg for leg in cargo["legs"] if leg["key"] == "hire")
    assert not hire["source"].startswith("desk standard")  # the approved set holds it
    without = client.post(
        "/api/lng/cargo-economics",
        json={**body, "cargoes": [{"cargo_id": "s", "term": "FOB"}]},
        headers=_h(bearers["c-viewer"]),
    ).json()["data"]["cargoes"][0]
    assert without["blocked"] == "no_distance"  # never a guessed voyage unless asked
