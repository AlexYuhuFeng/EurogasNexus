"""GOV-1 rule H6: no prompt or model change ships without its evaluation set passing.

The gate runs offline: note sets are scored here through the product's checks; ``pytest``
sets are the evaluation modules CI already runs. When this test fails, either undo the
change or run ``python scripts/ai/ai_gate.py --record`` and commit the record with it.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from eurogas_nexus.application import ai_gate, ai_style
from eurogas_nexus.domain.ai.evaluation_record import EVALUATION_RECORD
from eurogas_nexus.domain.ai.register import AI_USES

ROOT = Path(__file__).resolve().parents[2]


def test_the_code_matches_what_was_evaluated() -> None:
    assert ai_gate.problems(EVALUATION_RECORD) == []


def test_every_model_use_was_evaluated_on_the_default_model() -> None:
    model = ai_gate.default_model_id()
    for item in AI_USES:
        entry = EVALUATION_RECORD[item.use]
        assert entry["cases"] > 0 and entry["pass_rate"] >= item.threshold, item.use
        assert (model in entry["model_ids"]) is item.calls_model, item.use


def test_a_prompt_edit_without_re_evaluation_fails_the_gate(monkeypatch) -> None:
    monkeypatch.setattr(ai_style, "ANSWER_RULES", ai_style.ANSWER_RULES + " Be bolder.")
    found = ai_gate.problems(EVALUATION_RECORD)
    assert "answer: prompt text or tools changed since it was evaluated" in found
    assert "analysis_query: prompt text or tools changed since it was evaluated" in found


def test_a_model_change_without_evaluation_fails_the_gate(monkeypatch) -> None:
    monkeypatch.setattr(ai_gate, "default_model_id", lambda: "deepseek-v5-pro")
    found = ai_gate.problems(EVALUATION_RECORD)
    model_uses = [item.use for item in AI_USES if item.calls_model]
    assert found == [f"{use}: model deepseek-v5-pro has not been evaluated" for use in model_uses]


def test_a_version_bump_alone_is_not_an_evaluation() -> None:
    record = copy.deepcopy(EVALUATION_RECORD)
    record["explain"]["prompt_version"] = "an-older-version"
    assert ai_gate.problems(record) == ["explain: prompt version changed since it was evaluated"]


def test_an_edited_evaluation_set_fails_the_gate(monkeypatch) -> None:
    monkeypatch.setattr(ai_gate, "evaluation_set_sha256", lambda item: "0" * 64)
    found = ai_gate.problems(EVALUATION_RECORD)
    assert len([line for line in found if "evaluation set changed" in line]) == len(AI_USES)


def test_a_score_below_threshold_fails_the_gate(monkeypatch) -> None:
    monkeypatch.setattr(ai_gate, "note_score", lambda item: ai_gate.Score(1, 2))
    found = ai_gate.problems(EVALUATION_RECORD)
    assert "explain: 1/2 below threshold 1.0" in found
    monkeypatch.setattr(ai_gate, "note_score", lambda item: ai_gate.Score(0, 0))
    assert "explain: the evaluation set has no case for this use" in ai_gate.problems(
        EVALUATION_RECORD
    )


def test_missing_and_stale_records_fail_the_gate() -> None:
    record = copy.deepcopy(EVALUATION_RECORD)
    del record["brief"]
    record["retired_use"] = {}
    found = ai_gate.problems(record)
    assert "brief: no evaluation recorded" in found
    assert "retired_use: recorded but not in the register" in found


def test_the_gate_script_exits_cleanly_in_check_mode(capsys) -> None:
    spec = importlib.util.spec_from_file_location("ai_gate_script", ROOT / "scripts/ai/ai_gate.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert script.main([]) == 0
    assert "AI gate passes" in capsys.readouterr().out
