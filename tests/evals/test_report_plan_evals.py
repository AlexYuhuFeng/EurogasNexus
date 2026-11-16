"""Asked reports: the recorded question-to-plan cases, with and without a model proposal.

Each case in ``report_plan_cases.json`` runs through ``plan_for_question`` exactly as the
route does; a recorded model output stands in for the provider. A plan that names a hub the
question did not, puts the book in a shareable report, or answers a question the held data
cannot, fails here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eurogas_nexus.application.reports.plan import plan_for_question

CASES = json.loads((Path(__file__).parent / "report_plan_cases.json").read_text("utf-8"))["cases"]
NOW = datetime(2026, 11, 16, 7, tzinfo=UTC)


def test_the_set_covers_the_required_faults():
    ids = {case["id"] for case in CASES}
    assert {"plan-book-shareable", "plan-out-of-scope", "plan-etf-model-swaps"} <= ids
    assert any(not case["question"].isascii() for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_each_question_gets_its_recorded_plan(case):
    model = (lambda _messages, out=case["model"]: out) if "model" in case else None
    result = plan_for_question(case["question"], audience=case["audience"], model=model, now=NOW)
    expect = case["expect"]
    plan = result["plan"] or {"sections": [], "hubs": [], "countries": []}
    if "answerable" in expect:
        assert result["answerable"] is expect["answerable"], result
    if "message" in expect:
        assert result["message"] == expect["message"]
    if "missing_contains" in expect:
        assert any(expect["missing_contains"] in m for m in result["missing"]), result["missing"]
    for key in expect.get("sections_include", []):
        assert key in plan["sections"], (key, plan["sections"])
    for key in expect.get("sections_exclude", []):
        assert key not in plan["sections"], (key, plan["sections"])
    if "hubs" in expect:
        assert plan["hubs"] == expect["hubs"]
    for hub in expect.get("hubs_exclude", []):
        assert hub not in plan["hubs"]
    if "countries" in expect:
        assert plan["countries"] == expect["countries"]
    if "basis" in expect:
        assert result["basis"] == expect["basis"]
    if "model_refusal" in expect:
        assert result["model_refusal"] == expect["model_refusal"]
    if "model_refusal_prefix" in expect:
        assert (result["model_refusal"] or "").startswith(expect["model_refusal_prefix"])
    if "period_days" in expect:
        start = datetime.fromisoformat(plan["period_start"]).date()
        end = datetime.fromisoformat(plan["period_end"]).date()
        assert (end - start).days + 1 == expect["period_days"]
    if case["audience"] == "shareable":
        assert not any(key.startswith("book_") for key in plan["sections"])
