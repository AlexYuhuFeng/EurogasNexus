"""QA-L-03 / QA-R-26: the firm's cargoes and the hedges recorded on them are on the ladder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.gas_day import contract_lines, trade_lines
from eurogas_nexus.application.position_inputs import cargo_legs
from eurogas_nexus.db.models import LngCargoHedgeRecord
from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord
from eurogas_nexus.domain.contracts import kinds
from tests.api.test_lng_cargo_plan_api import _setup


def _hedge(link_id: str, month: str, mwh: float, *, reference: str | None = None):
    return LngCargoHedgeRecord(
        link_id=link_id,
        cargo_id="own-1",
        hub="TTF",
        delivery_month=month,
        mwh=mwh,
        reference=reference,
        created_at_utc=datetime.now(UTC),
        created_by="test",
    )


def test_the_ladder_holds_the_cargo_send_out_and_its_hedges_by_cargo(tmp_path, monkeypatch):
    _engine, who, _now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    plan = client.get("/api/lng/cargoes/own-1/plan", headers=who["viewer"]).json()["data"]["plan"]
    hedges = [
        {"hub": "TTF", "month": item["month"], "mwh": -round(item["physical_mwh"] / 2)}
        for item in plan["months"]
    ]
    assert client.put(
        "/api/lng/cargoes/own-1/hedges", headers=who["analyst"], json={"legs": hedges}
    ).status_code == 200

    response = client.get("/api/portfolio/position-ladder?months=3", headers=who["viewer"])
    assert response.status_code == 200, response.text
    body = response.json()
    ladder = body["data"]

    # The send-out by gas day is the physical position, at the terminal's hub, by month.
    assert ladder["totals"]["physical_mwh"] == pytest.approx(plan["delivered_mwh"], abs=1)
    held = {row["month"]: row for row in ladder["rows"] if row["hub"] == "TTF"}
    for month in plan["months"]:
        row = held[month["month"]]
        assert row["physical_mwh"] == pytest.approx(month["physical_mwh"], abs=1)
        # Hedges are spread over the month's gas days; the horizon starts today.
        assert row["cargoes"] == [
            {
                "cargo_id": "own-1",
                "physical_mwh": pytest.approx(month["physical_mwh"], abs=1),
                "financial_mwh": row["financial_mwh"],
            }
        ]
        assert row["financial_mwh"] < 0
    assert ladder["legs"]["cargoes"] == 1  # the vessel feed's market cargo is not the firm's
    assert any("cargo(es) on the ladder" in warning for warning in body["meta"]["warnings"])


def test_a_cargo_already_on_the_ladder_is_not_counted_twice(tmp_path, monkeypatch):
    engine, _who, _now = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        session.add(_hedge("h-1", "2027-01", -100_000))
        session.add(_hedge("h-2", "2027-02", -50_000, reference="ORDER-7"))
        session.commit()

        legs, warnings, planned = cargo_legs(session, on_ladder={}, booked_refs=set())
        assert planned == {"own-1"}
        assert {leg.source for leg in legs} == {"cargo_plan", "cargo_hedge"}
        assert {leg.reference for leg in legs} == {"cargo:own-1"}
        assert all(leg.book_id == "lng-nwe" for leg in legs)
        (january,) = [
            leg for leg in legs if leg.source == "cargo_hedge" and leg.first_gas_day.month == 1
        ]
        assert january.mwh_per_day * 31 == pytest.approx(-100_000)

        # A contract leg that holds the cargo keeps it, and a hedge whose reference is a
        # trade already on the ladder is that trade.
        legs, warnings, planned = cargo_legs(
            session, on_ladder={"own-1": "CN-own-1"}, booked_refs={"ORDER-7"}
        )
    assert planned == set()
    assert [leg.source for leg in legs] == ["cargo_hedge"]  # only the January hedge
    assert any("on the ladder as contract CN-own-1" in warning for warning in warnings)
    assert any("ORDER-7 is a trade already on the ladder" in warning for warning in warnings)


def test_a_des_contract_naming_the_cargo_holds_its_physical(tmp_path, monkeypatch):
    engine, who, now = _setup(tmp_path, monkeypatch)
    start = (now + timedelta(days=5)).date()
    with Session(engine) as session:
        session.add(
            UpstreamResourceContractRecord(
                contract_id="CN-own-1",
                contract_name="Own-1 DES",
                resource_type="LNG",
                delivery_point_name="Gate Terminal",
                gas_year=str(start.year),
                delivery_quantity_mwh_per_day=100_000.0,
                contract_price_gbp_mwh=30.0,
                contract_price_currency="EUR",
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=2.0,
                nomination_tolerance_pct=1.0,
                annual_financing_rate_pct=5.0,
                allowed_exit_points=["TTF"],
                eligible_sale_modes=["LOCAL_MARKET_SALE"],
                book_id="lng-nwe",
                contract_kind=kinds.LNG_CARGO,
                kind_terms={
                    "schema": "lng-cargo/v1",
                    "delivery_term": "DES",
                    "discharge_terminal": "Gate Terminal",
                    "terminal_hub": "TTF",
                    "window_start": start.isoformat(),
                    "window_end": (start + timedelta(days=9)).isoformat(),
                    "quantity_mmbtu": 3_400_000,
                    "tolerance_pct": 5,
                    "price_formula": "fixed",
                    "fixed_price": 30,
                    "price_unit": "EUR/MWh",
                    "pricing_month": f"{start:%Y-%m}",
                    "lng_cargo_id": "own-1",
                },
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        session.commit()
    client = TestClient(create_app())
    response = client.get("/api/portfolio/position-ladder?months=3", headers=who["viewer"])
    assert response.status_code == 200, response.text
    ladder = response.json()["data"]
    # Ten days of the contract's quantity, once: the plan's send-out is not added on top.
    assert ladder["totals"]["physical_mwh"] == pytest.approx(1_000_000, abs=1)
    assert all(row["cargoes"] == [] for row in ladder["rows"])
    assert any(
        "on the ladder as contract CN-own-1" in warning
        for warning in response.json()["meta"]["warnings"]
    )


def test_the_gas_day_keeps_cargoes_to_its_slot_lines(tmp_path, monkeypatch):
    engine, _who, _now = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        session.add(_hedge("h-1", "2027-01", -100_000))
        session.commit()
        legs, _warnings, _planned = cargo_legs(session, on_ladder={}, booked_refs=set())
    days = sorted({leg.first_gas_day for leg in legs if leg.source == "cargo_plan"})
    inputs = SimpleNamespace(legs=legs, contracts=[], orders=[])
    # The send-out is the slot's line (``lng_lines``) from the same plan; the recorded hedge
    # is not a booked trade. Neither is added to the gas day a second time.
    assert contract_lines(inputs, days, {}) == []
    assert trade_lines(inputs, days, days[0]) == []
