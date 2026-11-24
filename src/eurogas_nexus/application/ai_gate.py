"""The AI evaluation gate (GOV-1, rule H6): no prompt or model change without its evaluation.

For each use in the register the gate knows four things that must agree with what was
evaluated and recorded in ``domain/ai/evaluation_record.py``:

1. the prompt version written in the register;
2. the prompt fingerprint (SHA-256 over the prompt parts and the use's tools), so editing a
   prompt without re-evaluating it is caught even when the version is not bumped;
3. the SHA-256 of the evaluation set, so a case cannot be quietly removed;
4. the default model id (``llm/provider.DEFAULT_MODEL``), so a model change is evaluated too.

and the evaluation set must still meet the use's threshold now. Everything runs offline on
recorded fixtures: the note sets are scored here through the product's own checks; a
``pytest`` set is a test module in which every case must pass, which CI runs anyway.

``scripts/ai/ai_gate.py --record`` re-scores every use and rewrites the record only when each
meets its threshold; ``tests/evals/test_ai_gate.py`` fails CI when anything above disagrees.

AI 评估门：提示词、模型或评估集变更而未通过评估集阈值时，CI 失败（离线、基于录制的用例）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eurogas_nexus.application.ai_controls import prompt_fingerprint
from eurogas_nexus.domain.ai.register import AI_USES, AiUse

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Score:
    correct: int
    cases: int

    @property
    def rate(self) -> float:
        return self.correct / self.cases if self.cases else 0.0


def evaluation_set_sha256(item: AiUse) -> str:
    return hashlib.sha256((ROOT / item.evaluation_set).read_bytes()).hexdigest()


def default_model_id() -> str:
    from eurogas_nexus.llm.provider import DEFAULT_MODEL

    return DEFAULT_MODEL


def note_score(item: AiUse) -> Score:
    """Score a note-case use through the product's checks (every verdict must be right)."""

    from eurogas_nexus.application import ai_eval

    _, _, rest = item.scorer.partition(":")
    use, _, variant = rest.partition(":")
    raw = json.loads((ROOT / item.evaluation_set).read_text(encoding="utf-8"))["evidence"]
    evidence, cases = ai_eval.load(ROOT / item.evaluation_set)
    correct = total = 0
    for case in cases:
        entry = raw[case.evidence]
        if entry["use"] != use:
            continue
        if variant == "ask" and not entry.get("ask_lines"):
            continue
        if variant == "alert" and entry.get("ask_lines"):
            continue
        total += 1
        verdict = ai_eval.verdict(evidence[case.evidence], case.output)
        correct += int(verdict.ok == (case.expect == "pass"))
    return Score(correct, total)


def current(item: AiUse) -> dict[str, Any]:
    """What the gate sees for one use now (scores only for note sets)."""

    state: dict[str, Any] = {
        "prompt_version": item.prompt_version,
        "prompt_fingerprint": prompt_fingerprint(item),
        "evaluation_set": item.evaluation_set,
        "evaluation_set_sha256": evaluation_set_sha256(item),
        "scorer": item.scorer,
        "threshold": item.threshold,
    }
    if item.scorer.startswith("note_cases:"):
        score = note_score(item)
        state.update(cases=score.cases, correct=score.correct, pass_rate=round(score.rate, 4))
    return state


def problems(record: dict[str, dict[str, Any]]) -> list[str]:
    """Every way the code disagrees with the evaluation record (empty: the gate passes)."""

    found: list[str] = []
    model = default_model_id()
    for item in AI_USES:
        now = current(item)
        entry = record.get(item.use)
        if entry is None:
            found.append(f"{item.use}: no evaluation recorded")
            continue
        for key, what in (
            ("prompt_version", "prompt version"),
            ("prompt_fingerprint", "prompt text or tools"),
            ("evaluation_set_sha256", "evaluation set"),
        ):
            if entry.get(key) != now[key]:
                found.append(f"{item.use}: {what} changed since it was evaluated")
        if item.calls_model and model not in (entry.get("model_ids") or []):
            found.append(f"{item.use}: model {model} has not been evaluated")
        if "pass_rate" in now:
            if now["cases"] == 0:
                found.append(f"{item.use}: the evaluation set has no case for this use")
            elif now["pass_rate"] < item.threshold:
                found.append(
                    f"{item.use}: {now['correct']}/{now['cases']} below threshold "
                    f"{item.threshold}"
                )
    stale = sorted(set(record) - {item.use for item in AI_USES})
    found.extend(f"{use}: recorded but not in the register" for use in stale)
    return found


__all__ = [
    "Score",
    "current",
    "default_model_id",
    "evaluation_set_sha256",
    "note_score",
    "problems",
]
