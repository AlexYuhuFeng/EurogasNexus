"""The describe-it reader keeps the numbers a trader states and reads one-hub time spreads.

Found by the strategy audit (2026-11-19): "enter at |z| 2 over 60 days, exit at 0.5" came back
as a 20-day rule, and "TTF Win-27 minus Sum-27" or "TTF day-ahead vs month-ahead" asked
"which two hubs?".
"""

import pytest

from eurogas_nexus.domain.research.strategy_spec import spec_from_dict
from eurogas_nexus.domain.research.strategy_text import find_tenors, parse_description


@pytest.mark.parametrize(
    ("text", "legs", "rule"),
    [
        ("NBP vs TTF front month net of BBL tariff, z-score mean reversion, enter at |z| 2 "
         "over 60 days, exit at 0.5",
         [("NBP", "M+1", 1), ("TTF", "M+1", -1)],
         {"kind": "zscore", "lookback": 60, "entry_z": 2.0, "exit_z": 0.5}),
        ("英国对荷兰日前价差，以欧元换算，扣除运输费，均值回归，60天回看，z值2入场，0.5出场",
         [("NBP", "DA", 1), ("TTF", "DA", -1)],
         {"kind": "zscore", "lookback": 60, "entry_z": 2.0, "exit_z": 0.5}),
        ("TTF Win-27 minus Sum-27 against storage cost 3.8 EUR/MWh, threshold rule, buy below 0",
         [("TTF", "Win-27", 1), ("TTF", "Sum-27", -1)],
         {"kind": "threshold", "lookback": 20, "high": 3.8, "low": 0.0}),
        ("TTF day-ahead vs month-ahead mean reversion z-score 20 days",
         [("TTF", "DA", 1), ("TTF", "M+1", -1)], {"kind": "zscore", "lookback": 20}),
        ("荷兰日前对次月均值回归", [("TTF", "DA", 1), ("TTF", "M+1", -1)],
         {"kind": "zscore", "lookback": 20}),
        ("TTF M+1 vs M+2 z-score", [("TTF", "M+1", 1), ("TTF", "M+2", -1)],
         {"kind": "zscore", "lookback": 20}),
    ],
)
def test_stated_rules_and_time_spreads(text, legs, rule):
    spec = parse_description(text, held_hubs={"TTF", "NBP"})
    assert [(leg["hub"], leg["tenor"], leg["weight"]) for leg in spec["legs"]] == legs
    assert spec["kind"] == "history"
    assert spec["rule"] == rule


def test_a_threshold_without_both_levels_is_a_question():
    text = "荷兰27年冬季减27年夏季，对比储气成本3.8欧元/兆瓦时，阈值规则"
    spec = spec_from_dict(parse_description(text))
    assert [issue.code for issue in spec.issues] == ["rule_levels"]
    assert [(leg.hub, leg.tenor) for leg in spec.legs] == [("TTF", "Win-27"), ("TTF", "Sum-27")]


def test_exit_at_zero_is_kept_and_execution_is_stated():
    spec = spec_from_dict({"kind": "history", "legs": [{"hub": "TTF", "tenor": "DA", "weight": 1},
                                                        {"hub": "THE", "tenor": "DA",
                                                         "weight": -1}],
                           "rule": {"kind": "zscore", "exit_z": 0, "execution": "same_close"}})
    assert spec.rule.exit_z == 0.0 and spec.rule.execution == "same_close"
    assert not spec.issues


def test_tenors_in_order_written():
    assert find_tenors("Win-27 minus Sum-27") == ["Win-27", "Sum-27"]
    assert find_tenors("27年冬季减27年夏季") == ["Win-27", "Sum-27"]


def test_a_rule_with_a_cost_keeps_the_route_cost():
    spec = spec_from_dict({"kind": "history",
                           "legs": [{"hub": "NBP", "tenor": "DA", "weight": 1},
                                    {"hub": "TTF", "tenor": "DA", "weight": -1}],
                           "cost": {"kind": "route_tariff", "from_hub": "TTF", "to_hub": "NBP"},
                           "rule": {"kind": "zscore", "lookback": 60, "cost_per_mwh": 0.05}})
    assert (spec.cost.from_hub, spec.cost.to_hub) == ("TTF", "NBP")
    assert spec.rule.cost_per_mwh == 0.05
