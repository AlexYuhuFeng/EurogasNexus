"""AI-04: the recorded evaluation set, run through the product's checks without a provider.

Every candidate model text in ``ai_note_cases.json`` must get the verdict it records: a
faithful note passes, and each bad note is refused by the check the case names. A bad note
that passes means a model could put a wrong number, hub, unit or direction in front of a
trader; a good note refused means the rule text stands where the note was fine. Both fail
here. The pass rate per category is printed (``pytest -s``) for the evaluation report.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

import pytest

from eurogas_nexus.application import ai_eval

EVIDENCE, CASES = ai_eval.load()


def test_the_set_is_large_enough_and_covers_every_use_and_fault():
    assert len(CASES) >= 60
    assert {ev.use for ev in EVIDENCE.values()} == set(ai_eval.USES)
    categories = {case.category for case in CASES}
    for needed in ("good", "hub", "unit", "number", "direction", "source", "advice",
                   "length", "superlative", "etf_gtf", "simulated_as_market", "chinese"):
        assert needed in categories, needed
    for case in CASES:
        assert case.reason, case.case_id
        assert case.expect in {"pass", "refuse"}
        assert (case.expect == "refuse") == bool(case.check), case.case_id
    # Demo or public data only: the set is also what the provider run sends.
    assert all(ev.demo_or_public for ev in EVIDENCE.values())


@pytest.mark.parametrize("case", CASES, ids=[case.case_id for case in CASES])
def test_each_case_gets_its_recorded_verdict(case):
    verdict = ai_eval.verdict(EVIDENCE[case.evidence], case.output)
    if case.expect == "pass":
        assert verdict.ok, f"good note refused by {verdict.check}: {verdict.detail} ({case.reason})"
    else:
        assert not verdict.ok, f"bad note passed ({case.reason})"
        assert verdict.check == case.check, (
            f"refused by {verdict.check!r} ({verdict.detail}), expected {case.check!r}"
        )


def test_pass_rate_per_category(capsys):
    totals: dict[str, Counter] = defaultdict(Counter)
    for case in CASES:
        verdict = ai_eval.verdict(EVIDENCE[case.evidence], case.output)
        right = verdict.ok == (case.expect == "pass")
        totals[case.category]["right" if right else "wrong"] += 1
    with capsys.disabled():
        print("\nAI-04 checker on the recorded set (category: correct verdicts/cases)")
        for category, counts in sorted(totals.items()):
            total = counts["right"] + counts["wrong"]
            print(f"  {category:22s} {counts['right']:3d}/{total:<3d}")
    assert all(counts["wrong"] == 0 for counts in totals.values()), json.dumps(totals)
