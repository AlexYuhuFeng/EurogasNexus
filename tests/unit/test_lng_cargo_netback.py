"""The desk's reading of a cargo study: cost stack, verdict, reasons, two-sided sensitivity, DES
units and currency (``application/lng_cargo_netback.py``)."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from eurogas_nexus.application import lng_cargo_netback as desk
from eurogas_nexus.domain.lng.cargo_economics import (
    MMBTU_PER_MWH,
    CargoOffer,
    OtherCost,
    TerminalOption,
    Valued,
    evaluate_cargo,
)
from eurogas_nexus.domain.lng.voyage import Voyage
from eurogas_nexus.domain.valuation.quality import InputClass

A = InputClass.ASSUMPTION
S = InputClass.SOURCED
Q = D(3_600_000)


def _des(price="100", currency="EUR") -> CargoOffer:
    return CargoOffer(
        cargo_id="c1",
        label="c1",
        term="DES",
        q_load_mmbtu=Valued(Q, A, "entered"),
        des_price=Valued(D(price), A, "entered: DES price"),
        des_currency=currency,
    )


def _fob() -> CargoOffer:
    return CargoOffer(
        cargo_id="f1",
        label="f1",
        term="FOB",
        q_load_mmbtu=Valued(Q, A),
        hh=Valued(D("3.50"), S, "EIA"),
        slope=Valued(D("1.15"), A),
        fee=Valued(D("2.50"), A),
        voyage=Voyage(distance_nm=D(4_900)),
        hire_per_day=Valued(D(45_000), A),
        boil_off_pct_per_day=Valued(D("0.10"), A),
        ballast_fuel_mmbtu_per_day=Valued(D(2_000), A),
        port_load=Valued(D(150_000), A),
        port_discharge=Valued(D(150_000), A),
        insurance_pct=Valued(D("0.05"), A),
        canal=Valued(D(0), InputClass.DERIVED),
    )


def _option(tid, hub_price, regas_per_mwh, *, q_mwh, currency="EUR", gik="0.5", **kw):
    return TerminalOption(
        terminal_id=tid,
        name=tid.title(),
        hub="PEG",
        currency=currency,
        arrival_month="2027-01",
        hub_price=Valued(D(hub_price), InputClass.SIMULATED, "PEG 2027-01 mid (Demo)"),
        entry=Valued(D(0), A, "entry capacity not held: excluded"),
        gas_in_kind_pct=Valued(D(gik), S, "published"),
        regas_total=Valued(D(regas_per_mwh) * q_mwh, S, "published"),
        regas_basis="published_final",
        fx_usd_per_unit=Valued(D("1.09"), S, "ECB"),
        **kw,
    )


Q_MWH = Q / MMBTU_PER_MWH


def _stacks(result, offer, options, excluded=()):
    by_id = {o.terminal_id: o for o in options}
    return {
        row.terminal_id: desk.cost_stack(
            result,
            offer,
            by_id[row.terminal_id],
            row,
            {"excluded": list(excluded), "versions": {}},
        )
        for row in result.terminals
    }


def test_every_terminal_below_the_des_price_names_the_least_bad_and_its_breakeven():
    offer = _des("100")
    options = [
        _option("fos", "43.19", "0.888", q_mwh=Q_MWH, gik="0.1"),
        _option("montoir", "43.19", "0.800", q_mwh=Q_MWH, gik="0.5"),
        _option("brunsbuttel", "43.54", "13.16", q_mwh=Q_MWH, gik="0.9"),
    ]
    result = evaluate_cargo(offer, options)
    stacks = _stacks(result, offer, options, excluded=["entry"])
    verdict = desk.verdict(result, offer, stacks, "EUR", False)
    assert verdict["state"] == "all_negative"
    best = result.terminals[0]
    assert verdict["best_terminal_id"] == best.terminal_id == "fos"
    assert verdict["margin_total"] == pytest.approx(float(best.margin_per_mwh * Q_MWH), abs=0.05)
    # Break-even DES = the best netback: the price at which the cargo nets zero.
    assert verdict["breakeven"]["value"] == pytest.approx(float(best.netback_per_mwh), abs=1e-4)
    assert verdict["partial"] and verdict["partial"][0]["excluded"] == ["entry"]
    why = desk.reasons(result, stacks)
    assert why["fos"]["kind"] == "best"
    assert why["brunsbuttel"]["kind"] == "behind" and why["brunsbuttel"]["driver"] == "regas"
    assert why["montoir"]["driver"] == "gas_in_kind"


def test_the_cost_stack_adds_up_to_netback_cost_and_net_value():
    offer = _fob()
    carbon = OtherCost("carbon_voyage", "EU ETS on the voyage", D(130_000), A, "desk")
    options = [_option("fos", "43.19", "0.888", q_mwh=Q_MWH, other_items=(carbon,))]
    result = evaluate_cargo(offer, options)
    row = result.terminals[0]
    stack = _stacks(result, offer, options)["fos"]
    value = {item["key"]: item["per_mwh"] for item in stack["value"]}
    cost = {item["key"]: item["per_mwh"] for item in stack["cost"]}
    assert sum(v for k, v in value.items() if k != "netback") == pytest.approx(
        value["netback"], abs=5e-4
    )
    assert sum(v for k, v in cost.items() if k != "cost") == pytest.approx(cost["cost"], abs=5e-4)
    assert set(cost) >= {"fob", "boil_off", "hire", "ballast_fuel", "ports", "canal", "insurance"}
    assert stack["net"]["per_mwh"] == pytest.approx(float(row.margin_per_mwh), abs=1e-4)
    assert value["carbon_voyage"] == pytest.approx(float(-D(130_000) / result.q_del_mwh), abs=1e-4)
    assert stack["fx"]["pair"] == "USD/EUR"


def test_a_gbp_des_price_at_a_eur_hub_is_converted_not_left_out():
    offer = _des("34.12", currency="GBP")
    plain = _option("fos", "43.19", "0.888", q_mwh=Q_MWH)
    assert evaluate_cargo(offer, [plain]).terminals[0].reason == "currency_mismatch"
    converted = _option(
        "fos", "43.19", "0.888", q_mwh=Q_MWH, des_fx=Valued(D("1.17"), S, "GBP/EUR via USD")
    )
    row = evaluate_cargo(offer, [converted]).terminals[0]
    assert row.reason is None
    assert row.cost_per_mwh == D("34.12") * D("1.17")


def test_des_price_units_convert_to_per_mwh():
    per_mmbtu, currency, how = desk.des_per_mwh(
        {"des_price": 10, "des_price_unit": "per_mmbtu", "des_currency": "USD"}
    )
    assert currency == "USD" and per_mmbtu == pytest.approx(34.1214, abs=1e-3)
    assert how["factor"].startswith("x 3.412")
    pence, currency, how = desk.des_per_mwh({"des_price": 100, "des_price_unit": "p_th"})
    # 100 p/th = 1 GBP/th x 34.1214 th/MWh.
    assert currency == "GBP" and pence == pytest.approx(34.1214, abs=1e-3)
    flat, currency, how = desk.des_per_mwh({"des_price": 100})
    assert (flat, currency, how["unit"]) == (100.0, "EUR", "per_mwh")


def test_units_show_the_cargo_in_mmbtu_mwh_and_therm():
    result = evaluate_cargo(_des(), [])
    units = desk.units(result, None)
    assert units["loaded"] == {"mmbtu": 3_600_000.0, "mwh": 1_055_055.85, "therm": 36_000_000.0}
    assert units["mwh_per_mmbtu"] == pytest.approx(0.293071, abs=1e-6)


def test_sensitivity_moves_each_input_both_ways_and_flags_a_change_of_best():
    offer = _fob()
    options = [
        _option("fos", "43.19", "0.888", q_mwh=Q_MWH),
        _option("near", "43.10", "0.85", q_mwh=Q_MWH),
    ]
    base = evaluate_cargo(offer, options)
    rows = {
        row["key"]: row
        for row in desk.sensitivity(offer, options, base, reporting=None, eua_eur_t=None)
    }
    assert {"hub", "hire", "boil_off", "hh", "fx"} <= set(rows)
    assert (
        rows["hire"]["down"]["margin_change_per_mwh"]
        > 0
        > rows["hire"]["up"]["margin_change_per_mwh"]
    )
    assert rows["boil_off"]["up"]["margin_change_per_mwh"] < 0
    assert rows["hire"]["margin_change_per_mwh"] == rows["hire"]["up"]["margin_change_per_mwh"]
    assert "des" not in rows and "eua" not in rows
    des_rows = desk.sensitivity(
        _des(), options, evaluate_cargo(_des(), options), reporting=None, eua_eur_t=None
    )
    assert {row["key"] for row in des_rows} == {"hub", "des"}
