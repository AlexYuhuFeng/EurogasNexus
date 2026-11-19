"""Research → Spreads ("Describe a strategy"): spec validation, the deterministic reader,
translation through a stubbed model, the checks as questions, and the worked example.

The worked example (design basis 2, D.2 and the owner's acceptance case) is computed by hand
in its docstring; rates and tariffs are illustrative, not market values.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.application.instrument_catalogue import build_catalogue
from eurogas_nexus.application.route_tariff_cost import route_cost, weakest
from eurogas_nexus.application.spreads_workbench import (
    Holdings,
    check,
    evaluate_curve,
    interpret,
    translation_messages,
)
from eurogas_nexus.domain.market.fx_forward import Delivery, FxHoldings
from eurogas_nexus.domain.research.strategy_spec import spec_from_dict
from eurogas_nexus.domain.research.strategy_text import find_tenor, parse_description

TODAY = date(2026, 11, 16)
JAN_27 = Delivery(date(2027, 1, 1), date(2027, 1, 31), "month", "Jan-27")


def _row(hub, tenor, price, unit, *, day=TODAY, source="Settlement_Import", start=None,
         end=None, simulated=False):
    observed = datetime(day.year, day.month, day.day, 18, tzinfo=UTC)
    return {
        "hub": hub, "hub_resolved": True, "tenor": tenor, "source_system": source,
        "currency": unit.split("/")[0], "unit": unit, "day": day, "observed_at_utc": observed,
        "period_start_utc": start, "period_end_utc": end, "price": price,
        "simulated": simulated, "settlement": True,
    }


def _tariff(point, tso, direction, value, *, status="FINAL", currency="EUR"):
    return {
        "tariff_id": f"t-{point}-{tso}-{direction}", "tso": tso, "point_id": point,
        "direction": direction, "gas_year": "2026/27", "tariff_value": value,
        "currency": currency, "unit": f"{currency}/MWh",
        "effective_from": datetime(2026, 10, 1, tzinfo=UTC),
        "effective_to": datetime(2027, 9, 30, tzinfo=UTC),
        "tariff_status": status, "source_table": "ENTSOG TP tariffsfulls (fixture)",
    }


#: The BBL route TTF → NBP (GTS exit Julianadorp, BBL at Bacton, National Gas entry Bacton).
BBL_TARIFFS = [
    _tariff("ITP-00063", "GTS", "EXIT", 0.56),
    _tariff("ITP-00207", "BBL company", "EXIT", 1.20),
    _tariff("ITP-00207", "National Gas TSO", "ENTRY", 0.12),
]


def _holdings(rows=None, tariffs=BBL_TARIFFS, fx_source="ECB") -> Holdings:
    rows = rows if rows is not None else [
        _row("TTF", "jan-27", 30.00, "EUR/MWh"),
        # 78 p/th stored per MWh: 0.78 × 34.1214163 = 26.6147047 GBP/MWh.
        _row("NBP", "jan-27", 26.6147047, "GBP/MWh"),
        _row("TTF", "month-ahead", 29.5, "EUR/MWh"),
        _row("NBP", "month-ahead", 26.0, "GBP/MWh"),
    ]
    fx = FxHoldings.from_rows(
        [{"pair": "EURGBP", "rate": 0.87, "rate_type": "reference",
          "value_date": TODAY.isoformat(), "source_system": fx_source}],
        [{"benchmark_id": "SONIA", "value_date": TODAY.isoformat(), "rate_pct": 3.75,
          "source_system": "BOE"},
         {"benchmark_id": "ESTR", "value_date": TODAY.isoformat(), "rate_pct": 1.90,
          "source_system": "ECB"}],
    )
    return Holdings(rows, fx, list(tariffs), TODAY, build_catalogue(rows, today=TODAY))


# --------------------------------------------------------------------------------- the spec


def test_spec_validation_turns_problems_into_issues_not_exceptions():
    spec = spec_from_dict({"kind": "sideways", "legs": [{"hub": "ttf", "weight": 0}],
                           "fx": "magic", "cost": {"from_hub": "TTF", "to_hub": "PEG"},
                           "rule": {"kind": "zscore", "lookback": 1}})
    codes = {issue.code for issue in spec.issues}
    assert {"kind_unknown", "leg_weight", "legs_too_few", "fx_mode", "cost_hubs",
            "rule_lookback", "rule_needs_history"} <= codes
    assert spec.legs[0].hub == "TTF"
    ok = spec_from_dict({"version": 1, "kind": "curve",
                         "legs": [{"instrument": "NBP:M+1", "weight": 1},
                                  {"hub": "TTF", "weight": -1}],
                         "cost": {"kind": "route_tariff", "from_hub": "TTF", "to_hub": "NBP"}})
    assert ok.issues == ()
    assert ok.legs[0].tenor == "M+1"
    assert ok.sell_hub == "NBP" and ok.buy_hub == "TTF"
    assert spec_from_dict("not a spec").issues[0].code == "spec_unreadable"


# ------------------------------------------------------------------------ the deterministic reader


@pytest.mark.parametrize(
    ("text", "kind", "legs", "cost", "unit"),
    [
        ("forward spread net of transport tariff between TTF and NBP", "curve",
         [("NBP", 1), ("TTF", -1)], ("TTF", "NBP"), None),
        ("NBP vs TTF front month", "history", [("NBP", 1), ("TTF", -1)], None, None),
        ("THE - TTF M+1 z-score in p/th", "history", [("THE", 1), ("TTF", -1)], None,
         "GBp/th"),
        ("PEG minus TTF jan27 after transport tariff", "history", [("PEG", 1), ("TTF", -1)],
         ("TTF", "PEG"), None),
        ("spread from ZTP to NBP curve", "curve", [("NBP", 1), ("ZTP", -1)], None, None),
        ("荷兰和英国之间扣除运输费的远期价差", "curve", [("NBP", 1), ("TTF", -1)],
         ("TTF", "NBP"), None),
        ("英国对荷兰 次月", "history", [("NBP", 1), ("TTF", -1)], None, None),
        ("def spread():\n    return nbp.m1 - ttf.m1  # net of tariff", "history",
         [("NBP", 1), ("TTF", -1)], ("TTF", "NBP"), None),
        ("the forward spread for ttf and nbp", "curve", [("TTF", 1), ("NBP", -1)], None, None),
    ],
)
def test_reader_table_english_chinese_and_pasted_code(text, kind, legs, cost, unit):
    spec = parse_description(text)
    assert spec is not None, text
    assert spec["kind"] == kind
    assert [(leg["hub"], leg["weight"]) for leg in spec["legs"]] == legs
    got_cost = (spec["cost"]["from_hub"], spec["cost"]["to_hub"]) if spec["cost"] else None
    assert got_cost == cost
    assert spec["unit"] == unit


def test_reader_never_guesses_and_flags_unknown_codes():
    assert parse_description("what is the spread") is None
    assert parse_description("TTF only please") is None
    spec = parse_description("XYZ vs TTF")
    assert spec["_unknown_hubs"] == ["XYZ"]
    assert [leg["hub"] for leg in spec["legs"]] == ["XYZ", "TTF"]
    # "the" is an English word; only THE in capitals is the German hub.
    assert [leg["hub"] for leg in parse_description("THE vs TTF")["legs"]] == ["THE", "TTF"]
    assert find_tenor("cal-28") == "Cal-28" and find_tenor("27年3月") == "Mar-27"


# ------------------------------------------------------------------------------ interpretation


def test_interpret_without_a_model_uses_the_reader_and_sets_the_first_named_unit():
    result = interpret("forward spread net of transport tariff between TTF and NBP", _holdings())
    assert result.basis == "parser" and result.ai == "off"
    assert result.issues == []
    assert result.spec.unit == "EUR/MWh"  # TTF, named first
    assert result.spec.cost.from_hub == "TTF" and result.spec.cost.to_hub == "NBP"


def test_interpret_with_a_stubbed_model_chinese_and_the_model_never_supplies_a_figure():
    seen: list[list[dict]] = []

    def model(messages):
        seen.append(messages)
        return "Here you go: " + json.dumps({
            "version": 1, "kind": "curve",
            "legs": [{"hub": "NBP", "weight": 1}, {"hub": "TTF", "weight": -1}],
            "unit": "EUR/MWh", "fx": "forward",
            "cost": {"kind": "route_tariff", "from_hub": "TTF", "to_hub": "NBP"},
            "net_spread": 12.34,  # a model's number is ignored: only the spec is read
        })

    result = interpret("英国和荷兰之间的远期价差，扣除管输费", _holdings(), language="zh-CN",
                       model=model)
    assert result.basis == "model" and result.ai == "used"
    assert "net_spread" not in result.spec.as_dict()
    system = seen[0][0]["content"]
    assert "never compute" in system and "never execute" in system
    assert '"TTF"' in system and '"NBP"' in system  # the held instruments are offered
    assert "zh-CN" in seen[0][1]["content"]


def test_interpret_pasted_code_is_read_as_text_and_a_failed_model_falls_back():
    def broken(_messages):
        return "I cannot help with that"

    code = "import pandas as pd\nspread = df['NBP_M1'] - df['TTF_M1']  # net of tariff\n"
    result = interpret(code, _holdings(), model=broken)
    assert result.read_as_text is True
    assert result.ai == "failed" and result.basis == "parser"
    assert [leg.hub for leg in result.spec.legs] == ["NBP", "TTF"]


def test_unknown_hub_and_missing_tenor_come_back_as_questions_with_choices():
    unknown = interpret("XYZ vs TTF front month", _holdings())
    question = next(issue for issue in unknown.issues if issue.code == "hub_not_held")
    assert question.choices == ("TTF", "NBP")
    vague = interpret("show me something", _holdings())
    assert vague.issues[0].code == "instruments_unclear"
    spec = spec_from_dict({"kind": "history", "legs": [{"hub": "NBP", "tenor": "Q3-27",
                                                       "weight": 1},
                                                      {"hub": "TTF", "tenor": "M+1",
                                                       "weight": -1}]})
    tenor = next(issue for issue in check(spec, _holdings()) if issue.code == "tenor_not_held")
    assert "M+1" in tenor.choices and "Jan-27" in tenor.choices
    unproven = spec_from_dict({"kind": "curve", "legs": [{"hub": "NBP", "weight": 1},
                                                        {"hub": "TTF", "weight": -1}],
                               "unit": "EUR/MWh",
                               "cost": {"from_hub": "TTF", "to_hub": "NBP"}})
    assert not any(issue.code == "route_unproven" for issue in check(unproven, _holdings()))


# ----------------------------------------------------------------------------- the engine


def test_route_cost_ttf_to_nbp_through_bbl_and_missing_is_never_zero():
    """0.56 (GTS exit) + 1.20 (BBL) + 0.12 (National Gas entry) = 1.88 EUR/MWh, 2026/27."""

    route = route_cost("TTF", "NBP", JAN_27, BBL_TARIFFS)
    assert route.proven and route.complete
    assert route.total == pytest.approx(1.88)
    assert route.gas_years == ["2026/27"] and route.input_class == "sourced"
    assert [leg.role for leg in route.legs] == ["market_area_exit", "pipeline",
                                                "market_area_entry"]
    partial = route_cost("TTF", "NBP", JAN_27, BBL_TARIFFS[:2])
    assert partial.total is None and partial.input_class == "missing"
    assert partial.missing_legs() == ["Bacton (BBL) entry (National Gas TSO)"]
    # The other direction has no tariff held: missing, not zero.
    assert route_cost("NBP", "TTF", JAN_27, BBL_TARIFFS).total is None
    assert weakest(["sourced", "derived", "simulated"]) == "simulated"


def test_worked_example_forward_spread_net_of_transport_ttf_to_nbp():
    """"Forward spread net of transport tariff between TTF and NBP", Jan-27, on 16 Nov 2026.

    TTF Jan-27 30.00 EUR/MWh. NBP Jan-27 78.00 p/th = 0.78 × 34.1214163 = 26.6147047 GBP/MWh.
    EUR/GBP forward for Jan-27 (D.5): 0.87 × (1 + 0.0375 × 60/365) / (1 + 0.019 × 60/360)
    = 0.8725998, so NBP = 26.6147047 / 0.8725998 = 30.500 EUR/MWh.
    Gross (sell NBP, buy TTF) = 30.500 − 30.000 = +0.500 EUR/MWh.
    Route TTF → NBP through BBL, gas year 2026/27: 0.56 + 1.20 + 0.12 = 1.880 EUR/MWh.
    Net = 0.500 − 1.880 = −1.380 EUR/MWh: moving gas TTF → NBP does not pay for Jan-27.
    """

    spec = interpret("forward spread net of transport tariff between TTF and NBP",
                     _holdings()).spec
    result = evaluate_curve(spec, _holdings())
    assert result["unit"] == "EUR/MWh"
    row = next(item for item in result["rows"] if item["label"] == "Jan-27")
    nbp = next(leg for leg in row["legs"] if leg["hub"] == "NBP")
    assert round(nbp["native_value"], 2) == 78.00 and nbp["native_unit"] == "p/th"
    assert round(nbp["value"], 3) == 30.500
    assert nbp["fx"]["method"] == "derived: covered interest parity"
    assert round(row["gross"], 3) == 0.500
    assert round(row["cost"], 3) == 1.880
    assert round(row["net"], 3) == -1.380
    assert row["route_gas_years"] == ["2026/27"] and row["tariff_year_differs"] is False
    # Classes: the settlements are indicative, the FX derived, the tariffs sourced → indicative.
    assert row["input_class"] == "indicative"
    assert result["route"]["direction"] == "TTF → NBP"
    assert result["route"]["via"] == ["Julianadorp (GTS) /Balgzand (BBL) / Bacton (BBL)"]


def test_simulated_inputs_make_the_row_simulated_and_spot_fx_is_a_choice():
    rows = [
        _row("TTF", "jan-27", 30.00, "EUR/MWh", source="DEMO_Sim", simulated=True),
        _row("NBP", "jan-27", 26.6147047, "GBP/MWh", source="DEMO_Sim", simulated=True),
    ]
    spec = spec_from_dict({"kind": "curve", "legs": [{"hub": "NBP", "weight": 1},
                                                    {"hub": "TTF", "weight": -1}],
                           "unit": "EUR/MWh", "fx": "spot"})
    result = evaluate_curve(spec, _holdings(rows))
    row = result["rows"][0]
    assert row["simulated"] is True and row["input_class"] == "simulated"
    assert result["simulated"] is True
    # Spot: 26.6147047 / 0.87 = 30.592 EUR/MWh; no cost asked, net = gross = 0.592.
    assert round(row["net"], 3) == 0.592


def test_translation_prompt_lists_only_the_held_instruments():
    messages = translation_messages("NBP vs TTF", _holdings(), "en")
    held = messages[0]["content"]
    assert "Jan-27" in held and "M+1" in held and "PEG" not in held.split("list")[-1]


def test_nbp_to_peg_two_borders_apart_is_priced_over_the_cheapest_route():
    """NBP → PEG has no common border: the route runs through ZTP (or TTF and THE). With
    tariffs held for NBP → ZTP → PEG only (fixture rows, 0.10 EUR/MWh a leg), that route is
    chosen, its legs listed; picking a route the register cannot price names its gaps."""

    from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

    graph = shipped_market_area_graph()
    tariffs = []
    for a, b in (("NBP", "ZTP"), ("ZTP", "PEG")):
        crossing = graph.crossings(graph.hub_for(a), graph.hub_for(b))[0]
        for leg in graph.legs(crossing):
            tariffs.append(_tariff(leg.point_key, leg.tso.split(" / ")[0], leg.direction, 0.10))
    rows = [
        _row("NBP", "jan-27", 26.6147047, "GBP/MWh"),
        _row("PEG", "jan-27", 31.00, "EUR/MWh"),
    ]
    holdings = _holdings(rows, tariffs)
    spec = spec_from_dict({
        "kind": "curve", "legs": [{"hub": "PEG", "weight": 1}, {"hub": "NBP", "weight": -1}],
        "unit": "EUR/MWh", "fx": "forward", "cost": {"from_hub": "NBP", "to_hub": "PEG"},
    })
    assert not [issue for issue in check(spec, holdings) if issue.code == "route_unproven"]
    result = evaluate_curve(spec, holdings)
    route = result["route"]
    assert route["hubs"] == ["NBP", "ZTP", "PEG"] and route["complete"]
    assert len(route["legs"]) >= 4 and all(leg["value"] == 0.10 for leg in route["legs"])
    row = next(item for item in result["rows"] if item["label"] == "Jan-27")
    assert row["cost"] == pytest.approx(0.10 * len(route["legs"]))
    assert route["unavailable"], "the routes through TTF hold no tariffs: named, not priced"
    picked = spec_from_dict({**spec.as_dict(), "cost": {"from_hub": "NBP", "to_hub": "PEG",
                                                        "through": ["TTF", "THE"]}})
    assert picked.cost.through == ("TTF", "THE")
    forced = evaluate_curve(picked, holdings)
    assert forced["route"]["complete"] is False and forced["route"]["missing"]
    assert forced["route"]["alternatives"][0]["hubs"] == ["NBP", "ZTP", "PEG"]
    assert next(r for r in forced["rows"] if r["label"] == "Jan-27")["net"] is None
