"""Compare route follow-up selectors on a counterbalanced synthetic fixture suite.

The live arm takes an OpenAI-compatible endpoint from Nexus configuration.
Use an approved local model and supply its key through the existing LLM key setting.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import timedelta
from statistics import median, quantiles
from time import perf_counter, sleep

from eurogas_nexus.application.agents.decision_research import RouteDecisionResearch, RouteStudy
from eurogas_nexus.application.agents.registry import register_builtin_capabilities
from eurogas_nexus.application.agents.route_follow_up import (
    Alternative,
    Investigation,
    investigate,
    provider_planner,
)
from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.domain.agents.contracts import AgentInvocationContext
from eurogas_nexus.llm.deepseek import DeepSeekCallResult
from scripts.research.benchmark_decision_research import scenario

PURPOSE_BY_FAILURE = {
    "late": "revised_delivery",
    "capacity": "revised_capacity",
    "conflict": "alternative_route",
}
RULE_BY_SIGNAL = {
    ("unknown", ("OUTSIDE_VALIDITY",)): "revised_delivery",
    ("infeasible", ()): "revised_capacity",
    ("unknown", ("CONFLICTED",)): "alternative_route",
}


def studies(kind):
    base = RouteStudy.model_validate(scenario())
    if kind == "late":
        return base.model_copy(update={"delivery_at": base.delivery_at + timedelta(days=2)}), base
    if kind == "capacity":
        limited = base.capacity.model_copy(update={"value": 2})
        return base.model_copy(update={"capacity": limited}), base
    disputed = base.capacity.model_copy(update={"conflicted": True})
    diversion = RouteStudy.model_validate(
        {**scenario(), "route_name": "Synthetic route A to C", "to_node_id": "C"}
    )
    return base.model_copy(update={"capacity": disputed}), diversion


def fixtures():
    for kind, expected_purpose in PURPOSE_BY_FAILURE.items():
        baseline, feasible = studies(kind)
        options = [
            Alternative(
                purpose=purpose, study=feasible if purpose == expected_purpose else baseline
            )
            for purpose in PURPOSE_BY_FAILURE.values()
        ]
        for shift in range(3):
            yield (
                f"{kind}-{shift + 1}",
                True,
                Investigation(baseline=baseline, alternatives=options[shift:] + options[:shift]),
            )
        yield (
            f"{kind}-no-feasible",
            False,
            Investigation(
                baseline=baseline,
                alternatives=[item.model_copy(update={"study": baseline}) for item in options],
            ),
        )


def rules(summary):
    payload = json.loads(summary)
    preferred = RULE_BY_SIGNAL.get(
        (payload["baseline_feasibility"], tuple(payload["evidence_issues"]))
    )
    choice = next(
        (item["candidate"] for item in payload["alternatives"] if item["purpose"] == preferred),
        1,
    )
    return DeepSeekCallResult(status="success", content=json.dumps({"candidate": choice}))


def evaluate(key: str | None, *, recovery_pause_seconds: float = 0) -> dict:
    service = RouteDecisionResearch(CapabilityRuntime(register_builtin_capabilities()))
    context = AgentInvocationContext(principal_id="evaluation:synthetic")
    arms = {"fixed_order": None, "purpose_rule": rules}
    if key:
        arms["live_model"] = provider_planner(key)
    rows = []
    for label, has_feasible, request in fixtures():
        for arm, planner in arms.items():
            start = perf_counter()
            report = investigate(service, request, context, planner=planner)
            elapsed_ms = (perf_counter() - start) * 1000
            result = report.follow_up
            assert result is not None and result.commercial_status == "NOT_ASSESSED"
            selected_feasible = result.feasibility == "feasible"
            rows.append({
                "case": label,
                "arm": arm,
                "candidate": report.candidate,
                "expected_feasible": has_feasible,
                "selected_feasible": selected_feasible,
                "correct": selected_feasible == has_feasible,
                "planner_status": report.planner_status,
                "planner_ms": round(report.planner_ms, 3),
                "wall_ms": round(elapsed_ms, 3),
            })
            if arm == "live_model" and report.planner_status == "provider_unavailable":
                # Let a single-sequence local fixture release timed-out work between samples.
                sleep(recovery_pause_seconds)
    summary = {}
    for arm in arms:
        cases = [row for row in rows if row["arm"] == arm]
        times = [row["wall_ms"] for row in cases]
        summary[arm] = {
            "feasible_found": sum(row["correct"] for row in cases if row["expected_feasible"]),
            "feasible_cases": sum(row["expected_feasible"] for row in cases),
            "no_feasible_correct": sum(
                row["correct"] for row in cases if not row["expected_feasible"]
            ),
            "invalid_or_unavailable": sum(
                row["planner_status"] in {"invalid_selection", "provider_unavailable"}
                for row in cases
            ),
            "statuses": dict(Counter(row["planner_status"] for row in cases)),
            "wall_ms_p50": round(median(times), 3),
            "wall_ms_p95": round(quantiles(times, n=20, method="inclusive")[18], 3),
        }
    return {
        "source_class": "SYNTHETIC",
        "recovery_pause_seconds": recovery_pause_seconds,
        "summary": summary,
        "cases": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--recovery-pause-seconds", type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.recovery_pause_seconds <= 10:
        parser.error("--recovery-pause-seconds must be between 0 and 10")
    key = os.environ.get("EUROGAS_NEXUS_LLM_API_KEY") if args.live_model else None
    if args.live_model and not key:
        parser.error("--live-model requires an approved EUROGAS_NEXUS_LLM_API_KEY")
    print(json.dumps(evaluate(key, recovery_pause_seconds=args.recovery_pause_seconds), indent=2))
