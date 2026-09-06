"""Model-routing policy (CR-15): high-reasoning vs fast tasks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoutingRule:
    task_class: str
    preferred_provider: str
    preferred_model: str
    structured_output: bool
    deterministic_fallback_required: bool


DEFAULT_MODEL_ROUTING: tuple[ModelRoutingRule, ...] = (
    ModelRoutingRule(
        task_class="research_planning",
        preferred_provider="DEEPSEEK",
        preferred_model="deepseek-v4-flash",
        structured_output=True,
        deterministic_fallback_required=True,
    ),
    ModelRoutingRule(
        task_class="hypothesis_generation",
        preferred_provider="DEEPSEEK",
        preferred_model="deepseek-v4-flash",
        structured_output=True,
        deterministic_fallback_required=True,
    ),
    ModelRoutingRule(
        task_class="strategy_generation",
        preferred_provider="DEEPSEEK",
        preferred_model="deepseek-v4-flash",
        structured_output=True,
        deterministic_fallback_required=True,
    ),
    ModelRoutingRule(
        task_class="risk_challenge",
        preferred_provider="DEEPSEEK",
        preferred_model="deepseek-v4-flash",
        structured_output=True,
        deterministic_fallback_required=True,
    ),
    ModelRoutingRule(
        task_class="summary",
        preferred_provider="DEEPSEEK",
        preferred_model="deepseek-v4-flash",
        structured_output=False,
        deterministic_fallback_required=True,
    ),
    ModelRoutingRule(
        task_class="formatting",
        preferred_provider="DEEPSEEK",
        preferred_model="deepseek-v4-flash",
        structured_output=False,
        deterministic_fallback_required=True,
    ),
    ModelRoutingRule(
        task_class="entity_interpretation",
        preferred_provider="DETERMINISTIC",
        preferred_model="rule-based-ontology/v1",
        structured_output=True,
        deterministic_fallback_required=True,
    ),
)


def routing_for_task(task_class: str) -> ModelRoutingRule:
    for rule in DEFAULT_MODEL_ROUTING:
        if rule.task_class == task_class:
            return rule
    return ModelRoutingRule(
        task_class=task_class,
        preferred_provider="DETERMINISTIC",
        preferred_model="rule-based/v1",
        structured_output=True,
        deterministic_fallback_required=True,
    )
