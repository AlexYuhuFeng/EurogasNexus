"""Bounded, offline follow-up planner for synthetic route investigations."""

from __future__ import annotations

import json
from collections.abc import Callable
from time import perf_counter
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from eurogas_nexus.application.agents.decision_research import (
    Assessment,
    ResearchInput,
    RouteDecisionResearch,
    RouteStudy,
    Task,
)
from eurogas_nexus.domain.agents.contracts import AgentInvocationContext
from eurogas_nexus.llm.deepseek import DeepSeekCallResult, invoke_deepseek

PROMPT_VERSION = "route-follow-up/v1"
Purpose = Literal["revised_delivery", "alternative_route", "revised_capacity"]


class Alternative(ResearchInput):
    purpose: Purpose
    study: RouteStudy


class Investigation(ResearchInput):
    baseline: RouteStudy
    alternatives: Annotated[tuple[Alternative, ...], Field(min_length=1, max_length=3)]


class Choice(ResearchInput):
    candidate: Annotated[int, Field(strict=True, ge=1, le=3)]


class InvestigationResult(ResearchInput):
    baseline: Assessment
    follow_up: Assessment | None = None
    candidate: int | None = None
    planner_status: Literal[
        "disabled", "selected", "provider_unavailable", "invalid_selection", "baseline_blocked"
    ]
    planner_ms: float = 0
    prompt_version: Literal["route-follow-up/v1"] = PROMPT_VERSION


def provider_planner(api_key: str) -> Callable[[str], DeepSeekCallResult]:
    """Use the installation's approved provider adapter without widening its profile gate."""

    def plan(summary: str) -> DeepSeekCallResult:
        return invoke_deepseek(
            api_key=api_key,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Select one investigation candidate by ID from the provided synthetic "
                        'options. Return only a JSON object of the form {"candidate": 1}.'
                    ),
                },
                {"role": "user", "content": summary},
            ],
            max_tokens=64,
            temperature=0,
            timeout_seconds=3,
        )

    return plan


def investigate(
    workflow: RouteDecisionResearch,
    request: Investigation,
    context: AgentInvocationContext,
    *,
    planner: Callable[[str], DeepSeekCallResult] | None = None,
) -> InvestigationResult:
    """Run the baseline and one caller-supplied alternative through the same runtime."""
    for study in (request.baseline, *(item.study for item in request.alternatives)):
        if study.task is not Task.ROUTE_INVESTIGATION or study.as_of != request.baseline.as_of:
            raise ValueError("Each route investigation must use the same evidence cutoff")

    baseline = workflow.assess(request.baseline, context)
    if baseline.blockers and baseline.feasibility == "unknown":
        return InvestigationResult(baseline=baseline, planner_status="baseline_blocked")

    candidate = 1
    status = "disabled"
    elapsed = 0.0
    if planner is not None:
        summary = json.dumps({
            "source_class": "SYNTHETIC",
            "baseline_feasibility": baseline.feasibility,
            "evidence_issues": sorted(set(baseline.issues.values())),
            "alternatives": [
                {"candidate": index, "purpose": alternative.purpose}
                for index, alternative in enumerate(request.alternatives, start=1)
            ],
        })
        start = perf_counter()
        try:
            answer = planner(summary)
        except (TimeoutError, OSError):
            answer = DeepSeekCallResult(status="provider_unavailable")
        elapsed = (perf_counter() - start) * 1000
        status = "provider_unavailable"
        if answer.status == "success":
            status = "invalid_selection"
            if answer.content and len(answer.content) <= 256:
                try:
                    selected = Choice.model_validate_json(answer.content).candidate
                except ValidationError:
                    pass
                else:
                    if selected <= len(request.alternatives):
                        candidate = selected
                        status = "selected"

    return InvestigationResult(
        baseline=baseline,
        follow_up=workflow.assess(request.alternatives[candidate - 1].study, context),
        candidate=candidate,
        planner_status=status,
        planner_ms=elapsed,
    )
