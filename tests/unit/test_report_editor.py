"""The AI editor: directive from one source, plan checks, element-level fallback."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from eurogas_nexus.application.reports import directive, editor, findings
from eurogas_nexus.application.reports.catalogue import validate_plan
from eurogas_nexus.application.reports.facts import fact

DOC = Path(__file__).resolve().parents[2] / "docs" / "product" / "REPORT_EDITORIAL_DIRECTIVE.md"


def test_the_prompt_is_built_from_the_documents_rules():
    text = DOC.read_text(encoding="utf-8")
    block = text.split("<!-- directive:begin -->")[1].split("<!-- directive:end -->")[0]
    written = [line.strip() for line in block.strip().split("\n\n")]
    assert written == [f"**{name}.** {rule}" for name, rule in directive.RULES]
    assert f"Version {directive.VERSION} " in text
    prompt = directive.system_prompt()
    for name, rule in directive.RULES:
        assert f"{name}. {rule}" in prompt


def sheet():
    items = [
        fact("storage.fill", "storage", "NW Europe storage fill", 64.2, "%", day="2026-11-12",
             state="current", sentence="NW Europe storage was 64.2% full on 12 Nov, 14.3 points "
             "below a year earlier.", score=2.86, reason="14.3 points from a year earlier",
             yoy=-14.3, change_unit="points", years=1,
             implications=["Stocks are lower than a year earlier at this point of the season."],
             exhibits=["fig.storage.season"]),
        fact("landings", "pipeline_supply", "Norwegian pipeline landings", 4595.0, "GWh/d",
             day="2026-11-12", state="current", sentence="Norwegian pipeline landings were 4,595 "
             "GWh/d on 12 Nov, down 42.8 GWh/d on the day.", score=0.6, reason="z 0.6",
             dod=-42.8, exhibits=["fig.landings.total"]),
        fact("balance.forecast", "balance", "Supply call forecast", 12929.0, "GWh/d",
             day="2026-11-19", state="current", forecast="seasonal normal plus recent anomaly",
             scheduled=True, indicator=False, score=4.5, reason="forecast change 45%",
             sentence="The balance forecast (seasonal normal plus recent anomaly) puts the call "
                      "at 12,929 GWh/d on 19 Nov; it is a forecast, not a measurement.",
             implications=["On that forecast the call would be higher by 19 Nov than on 12 Nov."]),
        fact("price.TTF", "prices", "TTF Dec-26", 31.4, "EUR/MWh", day="2026-11-13",
             state="current", simulated=True, dod=-0.35, score=1.2, reason="z 1.2",
             sentence="TTF Dec-26 closed at 31.40 EUR/MWh (simulated) on 13 Nov, down 0.35 "
                      "EUR/MWh on the day."),
    ]
    for index, item in enumerate(items, start=1):
        item["id"] = f"F{index}"
    return items


SECTIONS = [
    {"key": "storage", "title": "Storage", "status": "ok",
     "charts": [{"id": "fig.storage.season", "type": "line", "types": ["line"],
                 "windows": ["gas_year", "91d"], "window": "gas_year", "title": "x"}],
     "commentary": {"headline": "r", "bullets": [], "basis": "rule"}},
    {"key": "pipeline_supply", "title": "Norwegian pipeline landings", "status": "ok",
     "charts": [], "commentary": {"headline": "r", "bullets": [], "basis": "rule"}},
    {"key": "balance", "title": "Balance", "status": "ok", "charts": [],
     "commentary": {"headline": "r", "bullets": [], "basis": "rule"}},
    {"key": "prices", "title": "Prices", "status": "ok", "charts": [],
     "commentary": {"headline": "r", "bullets": [], "basis": "rule"}},
]


def good_plan():
    return {
        "headline": {"text": "NW Europe storage 14.3 points below a year earlier [F1]",
                     "facts": ["F1"]},
        "standfirst": {"text": "NW Europe storage was 64.2% full on 12 Nov [F1]. The balance "
                               "forecast puts the call at 12,929 GWh/d on 19 Nov [F3].",
                       "facts": ["F1", "F3"]},
        "findings": [
            {"facts": ["F1"], "finding": "NW Europe storage was 64.2% full on 12 Nov, 14.3 "
             "points below a year earlier [F1].", "implication": "Stocks are lower than a year "
             "earlier at this point of the season.", "why": "largest gap"},
            {"facts": ["F3"], "finding": "The balance forecast puts the call at 12,929 GWh/d "
             "on 19 Nov [F3].", "implication": None, "why": "forecast change"},
            {"facts": ["F2"], "finding": "Norwegian pipeline landings were 4,595 GWh/d on 12 "
             "Nov, down 42.8 GWh/d on the day [F2].", "implication": None, "why": "supply"},
        ],
        "sections": [
            {"key": "storage", "keep": True, "facts": ["F1"],
             "paragraph": " ".join(["NW Europe storage was 64.2% full on 12 Nov [F1], 14.3 "
                                    "points below a year earlier [F1]."] * 4),
             "exhibits": [{"id": "fig.storage.season", "type": "line", "window": "91d",
                           "title": "Storage 64.2% full, 14.3 points below a year earlier"}]},
            {"key": "prices", "keep": False, "reason": "simulated prices only"},
        ],
        "glance": ["F1", "F2"],
        "watch": [{"facts": ["F3"], "text": "The balance forecast puts the call at 12,929 GWh/d "
                                            "on 19 Nov [F3]."}],
    }


def _apply(plan):
    facts = sheet()
    rule = findings.rule_plan(facts, SECTIONS)
    return editor.apply_plan(plan, facts, [dict(s) for s in SECTIONS], rule, "test-model")


def test_a_good_plan_is_used_element_by_element():
    out = _apply(good_plan())
    record = out["record"]
    assert record["basis"] == "model" and record["directive"] == directive.VERSION
    assert all(v["ok"] for v in record["elements"].values()), record["elements"]
    assert out["headline"] == "NW Europe storage 14.3 points below a year earlier"
    assert "[F" not in out["standfirst"]
    assert [f["fact_ids"] for f in out["findings"]] == [["F1"], ["F3"], ["F2"]]
    assert out["dropped"][0]["key"] == "prices"
    assert out["section_edits"]["storage"]["exhibits"][0]["window"] == "91d"


def test_an_invented_number_falls_back_for_that_element_only():
    plan = good_plan()
    plan["headline"]["text"] = "NW Europe storage 15 points below a year earlier [F1]"
    out = _apply(plan)
    assert not out["record"]["elements"]["headline"]["ok"]
    assert out["headline"] == findings.rule_plan(sheet(), SECTIONS)["headline"]
    assert out["record"]["elements"]["standfirst"]["ok"]


def test_a_refused_finding_is_replaced_in_place_by_the_rule_finding_on_the_same_fact():
    plan = good_plan()
    plan["findings"][0]["finding"] = plan["findings"][0]["finding"].replace("14.3", "15.3")
    out = _apply(plan)
    assert not out["record"]["elements"]["finding.0"]["ok"]
    assert out["findings"][0]["fact_ids"] == ["F1"] and out["findings"][0]["basis"] == "rule"
    assert [f["fact_ids"] for f in out["findings"]] == [["F1"], ["F3"], ["F2"]]


def test_the_record_states_the_temperature_and_it_is_the_lowest():
    assert editor.EDITOR_CALL["temperature"] == 0.0
    assert _apply(good_plan())["record"]["temperature"] == 0.0


def test_a_chinese_paragraph_splits_into_sentences():
    sections = [{"key": "storage", "commentary": {}, "charts": []}]
    paragraph = "储气率为72.6%。较去年低0.5个百分点。"
    editor.apply_section_edits(sections, {"storage": {"paragraph": paragraph}})
    assert sections[0]["commentary"]["headline"] == "储气率为72.6%。"
    assert sections[0]["commentary"]["bullets"] == ["较去年低0.5个百分点。"]


def test_a_forecast_not_called_a_forecast_is_refused():
    plan = good_plan()
    plan["findings"][1]["finding"] = "The call will reach 12,929 GWh/d on 19 Nov [F3]."
    out = _apply(plan)
    assert not out["record"]["elements"]["finding.1"]["ok"]
    assert "forecast" in out["record"]["elements"]["finding.1"]["detail"]


def test_a_simulated_price_called_a_market_price_is_refused():
    ok, why = editor.check_text("TTF Dec-26 traded at 31.40 EUR/MWh on 13 Nov [F4].", ["F4"],
                                {f["id"]: f for f in sheet()})
    assert not ok and why.startswith("simulated_as_market")


def test_a_cause_not_held_is_refused_as_a_new_direction_or_name():
    ok, _ = editor.check_text("Storage fell because Norwegian landings dropped sharply [F1][F2].",
                              ["F1", "F2"], {f["id"]: f for f in sheet()})
    assert not ok


def test_window_type_and_unknown_ids_are_refused_and_counts_held():
    plan = good_plan()
    plan["sections"][0]["exhibits"][0]["window"] = "1825d"
    plan["findings"] = plan["findings"][:2]
    plan["headline"]["facts"] = ["F99"]
    out = _apply(plan)
    elements = out["record"]["elements"]
    assert not elements["exhibit.fig.storage.season"]["ok"]
    assert not elements["findings"]["ok"]
    assert not elements["headline"]["ok"]


def test_a_plan_that_is_not_json_leaves_the_rule_plan():
    assert editor.parse("Here is my plan: ...") is None
    out = editor.apply_plan(None, sheet(), SECTIONS, findings.rule_plan(sheet(), SECTIONS), "m")
    assert out["record"]["basis"] == "rule"


def test_the_fact_sheet_payload_holds_only_the_allowlisted_fields():
    from eurogas_nexus.application.ai_payloads import REPORT_EDITOR_FIELDS, is_identifier

    plan = validate_plan({"kind": "daily", "audience": "shareable",
                          "period_start": "2026-11-16", "period_end": "2026-11-16"},
                         now=__import__("datetime").datetime(2026, 11, 16, 8,
                                                             tzinfo=__import__("datetime").UTC))
    payload = editor.fact_sheet_payload(sheet(), SECTIONS, plan, "en")
    assert tuple(payload) == REPORT_EDITOR_FIELDS
    keys = set()

    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                keys.add(k)
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(payload)
    assert not [k for k in keys if is_identifier(k)]
    assert set(payload["facts"][0]) == {"fact", *editor.FACT_FIELDS} - {"id"}
    blob = json.dumps(payload)
    assert "book_" not in blob
    assert re.search(r'"fact": "F\d+"', blob)
    assert payload["report"]["period_start"] == date(2026, 11, 16).isoformat()


def test_a_chinese_superlative_is_held_when_the_evidence_states_it_in_english():
    from eurogas_nexus.application.grounding import check_grounding

    evidence = "Two outages removed 661 GWh/d; the largest, Demo Haldor field, has 563 GWh/d."
    assert check_grounding("最大的一处停运为 563 GWh/d。", evidence).ok
    bare = "Demo Haldor field has 563 GWh/d."
    assert not check_grounding("最大的一处停运为 563 GWh/d。", bare).ok
