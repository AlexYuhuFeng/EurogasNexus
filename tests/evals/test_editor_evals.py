"""The report editor's evaluation set: the right lead by rule, and the checks on recorded plans.

No provider: each recorded plan goes through ``editor.apply_plan`` exactly as a live one
would, and each element must get the verdict the case records. ``scripts/ai/run_editor_eval.py``
sends the same sheets to a provider on demand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eurogas_nexus.application.reports import editor, findings
from eurogas_nexus.application.reports.facts import fact

CASES = json.loads((Path(__file__).parent / "editor_cases.json").read_text("utf-8"))["cases"]


def build_sheet(case: dict) -> list[dict]:
    sheet = []
    for index, raw in enumerate(case["facts"], start=1):
        item = fact(raw["key"], raw["section"], raw["label"], raw.get("value"), raw["unit"],
                    day=raw["day"], state=raw.get("state", "current"),
                    simulated=raw.get("simulated", False), sentence=raw["sentence"],
                    score=raw["score"], reason=raw["reason"], dod=raw.get("dod"),
                    yoy=raw.get("yoy"), change_unit=raw.get("change_unit"),
                    years=raw.get("years", 0), implications=raw.get("implications"),
                    forecast=raw.get("forecast"), scheduled=raw.get("scheduled", False),
                    indicator=raw.get("indicator", True), wow=raw.get("wow"),
                    related=raw.get("related"))
        item["id"] = f"F{index}"
        item["question"] = raw.get("question", False)
        sheet.append(item)
    return sheet


def sections_of(sheet: list[dict]) -> list[dict]:
    keys = list(dict.fromkeys(f["section"] for f in sheet))
    return [{"key": k, "title": k, "status": "ok", "charts": [],
             "commentary": {"headline": "", "bullets": [], "basis": "rule"}} for k in keys]


def test_the_set_covers_the_required_situations():
    ids = {case["id"] for case in CASES}
    assert {"outage-outranks-small-storage-move", "stale-price-does-not-lead", "no-news-day",
            "forecast-must-be-labelled", "shareable-question-tempts-the-book",
            "chinese-edition", "linking-connectives", "ask-norwegian-outages-demo",
            "ask-norwegian-outages-public", "ask-not-answerable", "ask-book-in-shareable",
            "ask-chinese-question"} <= ids
    assert all(case["data_class"] in {"demo", "public"} for case in CASES)
    for case in CASES:
        if case["audience"] == "shareable":
            assert not any(f["section"].startswith("book_") for f in case["facts"])


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_the_rule_lead_is_the_expected_lead(case):
    sheet = build_sheet(case)
    ranked = findings.rank_findings(sheet)
    if case["expected_lead"] == "NO_NEWS":
        assert ranked[0]["text"] == findings.NO_NEWS
    else:
        lead = next(f for f in sheet if f["id"] == ranked[0]["fact_ids"][0])
        assert lead["key"] == case["expected_lead"]


def rule_for(case: dict, sheet: list[dict], sections: list[dict]) -> dict:
    """The rule plan, with an asked case's rule answer and what the data cannot tell."""

    rule = findings.rule_plan(sheet, sections)
    if case.get("rule_answer"):
        rule["answer"] = {"text": case["rule_answer"]["text"],
                          "fact_ids": case["rule_answer"]["facts"], "basis": "rule"}
        rule["cannot_tell"] = case.get("cannot_tell", [])
    return rule


PLANS = [(case, plan) for case in CASES for plan in case["plans"]]


@pytest.mark.parametrize("case,plan", PLANS, ids=[f"{c['id']}:{p['name']}" for c, p in PLANS])
def test_each_recorded_plan_gets_its_verdicts(case, plan):
    sheet = build_sheet(case)
    sections = sections_of(sheet)
    out = editor.apply_plan(plan["plan"], sheet, sections, rule_for(case, sheet, sections),
                            "recorded", audience=case["audience"])
    elements = out["record"]["elements"]
    for element, ok in plan["expect"].items():
        assert element in elements, (element, elements)
        assert elements[element]["ok"] is ok, (element, elements[element])
    for element, prefix in (plan.get("expect_detail") or {}).items():
        assert elements[element]["detail"].startswith(prefix), (element, elements[element])
