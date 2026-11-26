"""One statement of the inputs entered by hand (rule 19, backend audit O7)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from eurogas_nexus.api.manual_inputs import states_manual_inputs
from eurogas_nexus.application.manual_inputs import (
    attach,
    from_request_body,
    manual_input,
    unit_for,
)

NOW = datetime(2026, 11, 26, 9, tzinfo=UTC)


class Leg(BaseModel):
    leg_id: str
    tso: str
    amount_eur_mwh: float


class Body(BaseModel):
    route_name: str = "R"
    market_price_eur_mwh: float | None = None
    capacity_mcm_d: float = 10.0
    hub: str = "TTF"
    legs: list[Leg] = Field(default_factory=list)


class Plan(BaseModel):
    da_price: float
    lot_mwh: float = 24.0


def test_only_the_figures_the_caller_typed_are_listed() -> None:
    body = Body.model_validate(
        {"market_price_eur_mwh": 42.5, "hub": "NBP",
         "legs": [{"leg_id": "L1", "tso": "GTS", "amount_eur_mwh": 1.2}]}
    )
    found = from_request_body(body, now=NOW)
    # The default capacity, the hub choice and the TSO name are not hand-entered figures.
    assert [(item["name"], item["value"], item["unit"]) for item in found] == [
        ("legs[L1].amount_eur_mwh", 1.2, "EUR/MWh"),
        ("market_price_eur_mwh", 42.5, "EUR/MWh"),
    ]
    assert found[0]["entered_at"] == NOW.isoformat()


def test_nothing_typed_is_an_empty_list() -> None:
    envelope = attach({"data": {}, "meta": {}}, from_request_body(Body(), now=NOW))
    assert envelope["meta"]["manual_inputs"] == []


def test_units_from_names() -> None:
    assert unit_for("route_km") == "km" and unit_for("temperature_shift_c") == "°C"
    assert unit_for("fx_rate") is None
    assert manual_input("shock:TTF:2027-01", 2.0, "per MWh")["unit"] == "per MWh"


def test_the_decorator_states_them_on_any_return_path() -> None:
    app = FastAPI()

    @app.post("/plan")
    @states_manual_inputs(include=("da_price", "lot_mwh"), units={"da_price": "per MWh"})
    def plan(body: Plan, request: Request) -> dict:
        held = [manual_input("stored_override", 5.0, "MWh", entered_by="trader")]
        return attach({"data": {"ok": True}, "meta": {}}, held)

    body = TestClient(app).post("/plan", json={"da_price": 31.5}).json()
    names = [item["name"] for item in body["meta"]["manual_inputs"]]
    # The route's own hand entries are kept; the typed price is added; the default lot is not.
    assert names == ["stored_override", "da_price"]
    assert body["meta"]["manual_inputs"][1]["unit"] == "per MWh"
