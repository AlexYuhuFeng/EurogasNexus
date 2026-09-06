"""Deterministic business-task evaluation suite (CR-15).

Scoring is evidence-based: required capabilities must exist with correct
metadata, forbidden execution tools must never exist, and adversarial cases
must fail closed. This suite is a contract harness for future model-upgrade
evaluation; it never calls a live LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

from eurogas_nexus.application.agents.registry import register_builtin_capabilities
from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    DeterminismClass,
    SideEffectClass,
)

_CASES = json.loads((Path(__file__).parent / "agent_task_evals.json").read_text(encoding="utf-8"))[
    "cases"
]


def test_eval_corpus_has_thirty_cases() -> None:
    assert len(_CASES) == 30
    assert len({item["id"] for item in _CASES}) == 30


def test_every_required_capability_exists_and_is_semantic() -> None:
    registry = register_builtin_capabilities()
    known = {item.capability_id for item in registry.list_definitions()}
    for case in _CASES:
        missing = [item for item in case["required_capabilities"] if item not in known]
        assert missing == [], f"{case['id']} missing capabilities: {missing}"


def test_no_execution_capability_exists() -> None:
    registry = register_builtin_capabilities()
    known = {item.capability_id for item in registry.list_definitions()}
    banned = {
        "trade.execute",
        "order.place",
        "order.cancel",
        "nomination.submit",
        "trade.capture",
        "run_sql",
    }
    assert not (known & banned)


def test_read_and_write_classification_is_explicit() -> None:
    registry = register_builtin_capabilities()
    for definition in registry.list_definitions():
        assert definition.side_effect_class in SideEffectClass
        assert definition.determinism_class in DeterminismClass
        assert definition.action_policy in ActionPolicy


def test_adversarial_cases_never_require_execution_or_sql() -> None:
    registry = register_builtin_capabilities()
    known = {item.capability_id for item in registry.list_definitions()}
    for case in _CASES:
        if case["checks"].get("prompt_injection_safe"):
            assert "trade.execute" not in case["required_capabilities"]
            assert "run_sql" not in case["required_capabilities"]
            for forbidden in case["forbidden_capabilities"]:
                assert forbidden not in known


def test_route_capability_keeps_cost_attribution_metadata() -> None:
    registry = register_builtin_capabilities()
    definition = registry.get("route.calculate_economics")
    assert definition.output_schema["type"] == "object"
    assert definition.provenance_contract == "returns_source_references"


def test_strategy_ir_cases_are_compile_only_not_execution() -> None:
    registry = register_builtin_capabilities()
    definition = registry.get("strategy.create_version")
    assert definition.side_effect_class == SideEffectClass.RESEARCH_OBJECT_WRITE
    assert definition.action_policy == ActionPolicy.AGENT_ALLOWED_WITHIN_RESEARCH
    assert "execute" not in definition.capability_id
