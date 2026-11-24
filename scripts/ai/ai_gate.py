"""Check or record the AI evaluation gate (GOV-1, rule H6). Offline: no model is called.

    python scripts/ai/ai_gate.py            # check: exit 1 and list every problem
    python scripts/ai/ai_gate.py --record   # re-evaluate; write the record only if all pass

``--record`` scores every use on its recorded evaluation set: note sets through the product's
own checks, ``pytest`` sets by running their test module (every case must pass). Only when
each use meets its threshold is ``src/eurogas_nexus/domain/ai/evaluation_record.py``
rewritten, with each use's prompt version, prompt fingerprint, evaluation-set hash, score and
the default model id. Commit the record with the prompt change it evaluates.
"""

from __future__ import annotations

import argparse
import os
import pprint
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

RECORD = ROOT / "src" / "eurogas_nexus" / "domain" / "ai" / "evaluation_record.py"

HEADER = '''# ruff: noqa: E501
"""What the AI evaluation gate recorded per AI use (by ``scripts/ai/ai_gate.py``).

Do not edit by hand: change a prompt, its version or its evaluation set, then run
``python scripts/ai/ai_gate.py --record``, which rewrites this file only when every use meets
its threshold on its recorded evaluation set. ``tests/evals/test_ai_gate.py`` fails CI when
the code and this record disagree.
"""

from __future__ import annotations

from typing import Any

'''


def _pytest_score(path: str) -> tuple[int, int]:
    """Run one evaluation test module; return (passed, collected)."""

    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", path],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    passed = sum(int(n) for n in re.findall(r"(\d+) passed", tail))
    failed = sum(int(n) for n in re.findall(r"(\d+) (?:failed|errors?)\b", tail))
    return passed, passed + failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    from eurogas_nexus.application import ai_gate
    from eurogas_nexus.domain.ai.evaluation_record import EVALUATION_RECORD
    from eurogas_nexus.domain.ai.register import AI_USES

    if not args.record:
        found = ai_gate.problems(EVALUATION_RECORD)
        for line in found:
            print(f"AI gate: {line}")
        print("AI gate passes" if not found else f"AI gate: {len(found)} problem(s)")
        return 1 if found else 0

    model = ai_gate.default_model_id()
    record: dict[str, dict] = {}
    failures: list[str] = []
    module_scores: dict[str, tuple[int, int]] = {}
    for item in AI_USES:
        state = ai_gate.current(item)
        if item.scorer.startswith("pytest:"):
            path = item.scorer.partition(":")[2]
            if path not in module_scores:
                module_scores[path] = _pytest_score(path)
            passed, total = module_scores[path]
            state.update(cases=total, correct=passed,
                         pass_rate=round(passed / total, 4) if total else 0.0)
        if not state.get("cases") or state["pass_rate"] < item.threshold:
            failures.append(f"{item.use}: {state.get('correct')}/{state.get('cases')}")
        state["model_ids"] = [model] if item.calls_model else []
        state["recorded_on"] = datetime.now(UTC).date().isoformat()
        record[item.use] = state
    if failures:
        for line in failures:
            print(f"AI gate: below threshold, not recorded: {line}")
        return 1
    body = "EVALUATION_RECORD: dict[str, dict[str, Any]] = " + pprint.pformat(
        record, width=96, sort_dicts=True
    )
    RECORD.write_text(HEADER + body + "\n", encoding="utf-8")
    print(f"AI gate: recorded {len(record)} uses at model {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
