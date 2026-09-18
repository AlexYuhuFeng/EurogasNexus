"""Agent profile honesty (Architecture V2 Wave 7 / CR-15).

A governed run is *filed under* a profile: the profile is recorded on the run row and scopes its
tracked job. Two ways that could lie, and neither is allowed:

- an undeclared profile was accepted as an arbitrary string, so a run could claim a profile the
  runtime does not have (the catalogue at `GET /api/agent/profiles` was published but never used
  to validate anything);
- a declared profile names the stages it covers, and a run that never entered one of them still
  carried the label - which reads as evidence of a pipeline that did not run.

The second is reported rather than refused, because stopping short is often the honest outcome
(strategy generation without a frozen version terminates at human confirmation by design).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.agents.research_orchestrator import OrchestrationOutcome
from eurogas_nexus.domain.agents.contracts import PROFILES_BY_ID, OrchestrationStage


def test_the_declared_profiles_are_the_ones_the_route_publishes() -> None:
    # One catalogue: the refusal and the published list cannot disagree.
    client = TestClient(create_app())
    response = client.get("/api/agent/profiles")
    assert response.status_code == 200
    published = {item["profile_id"] for item in response.json()["data"]}
    assert published == set(PROFILES_BY_ID)


def test_an_undeclared_profile_is_refused_instead_of_recorded() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/agent/research",
        json={"objective": "Does NBP trade at a premium to TTF?", "agent_profile": "banana"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "agent_profile_unknown"
    assert "banana" in detail["message"]
    # The refusal names what is declared, so a caller can correct itself.
    assert detail["declared_profiles"] == sorted(PROFILES_BY_ID)


def test_a_declared_profile_is_accepted() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/agent/research",
        json={"objective": "Does NBP trade at a premium to TTF?"},
    )

    # The default profile is declared, so the run is attempted (and degrades honestly without a
    # runtime store rather than being refused for its profile).
    assert response.status_code != 422


def test_a_supplied_strategy_ir_is_refused_instead_of_ignored() -> None:
    # The request model accepted a `strategy_ir` and the orchestrator dropped it, so a caller could
    # believe its own specification had been run. The refusal names the path that does own one.
    client = TestClient(create_app())

    response = client.post(
        "/api/agent/research",
        json={
            "objective": "Does NBP trade at a premium to TTF?",
            "strategy_generation_allowed": True,
            "strategy_ir": {"components": []},
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "strategy_ir_not_accepted"
    assert "strategy registry" in detail["message"]

    # A run that supplies none is unaffected.
    assert (
        client.post(
            "/api/agent/research",
            json={"objective": "Does NBP trade at a premium to TTF?"},
        ).status_code
        != 422
    )


def _outcome(*stages: OrchestrationStage) -> OrchestrationOutcome:
    outcome = OrchestrationOutcome("agent-run-1")
    for stage in stages:
        outcome.note_stage(stage)
    return outcome


@pytest.mark.parametrize(
    ("profile", "reached", "expected"),
    [
        # Every declared stage reached: nothing to report.
        (
            "MARKET_RESEARCHER",
            ("PLAN_DRAFTED", "DATA_ANALYSIS", "HYPOTHESIS_FORMED", "CHALLENGED"),
            None,
        ),
        # Strategy generation not requested, so the strategy stages never ran and the label says
        # so - including the spec-drafting stage the profile also declares.
        (
            "STRATEGY_RESEARCHER",
            ("PLAN_DRAFTED", "PLAN_VALIDATED", "DATA_ANALYSIS", "HYPOTHESIS_FORMED", "CHALLENGED"),
            "PROFILE_STAGES_NOT_REACHED:STRATEGY_VALIDATED,BACKTESTED,STRATEGY_SPEC_DRAFTED",
        ),
        # A risk challenger that never challenged is reported too.
        ("RISK_CHALLENGER", ("DATA_ANALYSIS",), "PROFILE_STAGES_NOT_REACHED:CHALLENGED"),
        # An undeclared profile is reported as undeclared rather than compared against nothing.
        ("NOT_DECLARED", ("DATA_ANALYSIS",), "PROFILE_NOT_DECLARED:NOT_DECLARED"),
    ],
)
def test_a_run_says_which_of_its_profile_stages_it_did_not_reach(
    profile: str, reached: tuple[str, ...], expected: str | None
) -> None:
    from eurogas_nexus.application.agents.research_orchestrator import (
        GovernedResearchOrchestrator,
    )

    outcome = _outcome(*(OrchestrationStage[stage] for stage in reached))
    GovernedResearchOrchestrator()._note_unreached_profile_stages(outcome, profile)

    reported = [item for item in outcome.warnings if item.startswith("PROFILE_")]
    assert reported == ([expected] if expected else [])


def test_the_run_reports_the_stages_it_reached_in_order_and_once() -> None:
    outcome = OrchestrationOutcome("agent-run-2")
    outcome.note_stage(OrchestrationStage.PLAN_DRAFTED)
    outcome.note_stage(OrchestrationStage.DATA_ANALYSIS)
    # Re-entering a stage does not duplicate it: the record is a set of what happened, in order.
    outcome.note_stage(OrchestrationStage.DATA_ANALYSIS)

    assert outcome.stages_reached == ["OBJECTIVE_RECEIVED", "PLAN_DRAFTED", "DATA_ANALYSIS"]
    # The payload carries it, so a caller reads the run's own account of what it ran.
    assert outcome.payload()["stages_reached"] == outcome.stages_reached
