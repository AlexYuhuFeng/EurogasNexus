"""NEWS-1: the recorded evaluation set for the AI use ``news_note``, scored without a provider.

Every candidate note in ``news_note_cases.json`` must get the verdict it records from
``application.news_grounding.check_note``: a faithful note, each sentence citing the lines it
rests on, passes; each bad note (an uncited or wrongly cited sentence, a figure, hub, unit,
direction, source, name or superlative its cited lines do not hold, advice to trade, the wrong
language or shape) is refused by the check the case names. A bad note that passes would put an
unsupported claim in front of a desk under an "AI-generated" label; a good note refused means
the rule note stands where the model's was fine. Both fail here. This module is the use's
scorer in the AI register, so the evaluation gate records its pass rate.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from eurogas_nexus.application.news_grounding import check_note

SET = Path(__file__).with_name("news_note_cases.json")
DATA = json.loads(SET.read_text(encoding="utf-8"))
EVIDENCE = DATA["evidence"]
CASES = DATA["cases"]


def _verdict(case):
    evidence = EVIDENCE[case["evidence"]]
    return check_note(case["output"], evidence["lines"], language=evidence["language"])


def test_the_set_covers_every_fault_the_check_must_catch():
    assert len(CASES) >= 30
    categories = {case["category"] for case in CASES}
    for needed in ("good", "cites", "no_item", "number", "hub", "unit", "direction", "advice",
                   "source", "name", "superlative", "format", "sentences", "length", "chinese"):
        assert needed in categories, needed
    ids = [case["case_id"] for case in CASES]
    assert len(ids) == len(set(ids))
    for case in CASES:
        assert case["reason"], case["case_id"]
        assert case["expect"] in {"pass", "refuse"}
        assert (case["expect"] == "refuse") == bool(case["check"]), case["case_id"]
        assert case["evidence"] in EVIDENCE, case["case_id"]
    assert sum(case["expect"] == "pass" for case in CASES) >= 5


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_each_case_gets_its_recorded_verdict(case):
    verdict = _verdict(case)
    if case["expect"] == "pass":
        assert verdict.ok, (
            f"good note refused by {verdict.check}: {verdict.detail} ({case['reason']})"
        )
    else:
        assert not verdict.ok, f"bad note passed ({case['reason']})"
        assert verdict.check == case["check"], (
            f"refused by {verdict.check!r} ({verdict.detail}), expected {case['check']!r}"
        )


def test_a_refusal_names_the_sentence_that_failed():
    case = next(c for c in CASES if c["case_id"] == "cite-mixed-one-bad")
    verdict = _verdict(case)
    assert not verdict.ok
    assert [flag["check"] for flag in verdict.flags] == ["cites"]
    assert verdict.flags[0]["text"] == "Flows to Easington are lower."


def test_pass_rate_per_category(capsys):
    totals: dict[str, Counter] = defaultdict(Counter)
    for case in CASES:
        verdict = _verdict(case)
        right = verdict.ok == (case["expect"] == "pass")
        totals[case["category"]]["right" if right else "wrong"] += 1
    with capsys.disabled():
        print("\nNEWS-1 note check on the recorded set (category: correct verdicts/cases)")
        for category, counts in sorted(totals.items()):
            total = counts["right"] + counts["wrong"]
            print(f"  {category:14s} {counts['right']:3d}/{total:<3d}")
    assert all(counts["wrong"] == 0 for counts in totals.values()), json.dumps(totals)
