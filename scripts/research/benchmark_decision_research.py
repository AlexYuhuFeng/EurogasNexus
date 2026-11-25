"""Compare direct route engines with the governed route workflow on synthetic input."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from statistics import median, quantiles
from time import perf_counter_ns

from eurogas_nexus.application.agents.decision_research import RouteDecisionResearch, RouteStudy
from eurogas_nexus.application.agents.registry import register_builtin_capabilities
from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.domain.agents.contracts import AgentInvocationContext
from eurogas_nexus.domain.research.feasibility import FeasibilityInput, check_feasibility
from eurogas_nexus.domain.research.route_cost import (
    CostComponent,
    RouteCostInput,
    compute_route_cost,
)

AS_OF = datetime(2026, 11, 25, tzinfo=UTC)


def fixture(value, name):
    return {
        "value": value,
        "reference": f"synthetic:{name}",
        "version": "fixture-v1",
        "available_at": AS_OF,
        "valid_from": AS_OF,
        "valid_until": AS_OF + timedelta(days=2),
    }


def scenario():
    return {
        "task": "route_investigation",
        "as_of": AS_OF,
        "delivery_at": AS_OF + timedelta(days=1),
        "route_name": "Synthetic route A to B",
        "from_node_id": "A",
        "to_node_id": "B",
        "capacity": fixture(10, "capacity"),
        "demand": fixture(7, "demand"),
        "eligible": fixture(True, "eligibility"),
        "contract_active": fixture(True, "contract"),
        "costs": [
            fixture(
                {"component_type": "tariff", "amount": 1.1, "unit": "EUR/MWh", "currency": "EUR"},
                "tariff",
            ),
            fixture(
                {"component_type": "fuel", "amount": 0.2, "unit": "EUR/MWh", "currency": "EUR"},
                "fuel",
            ),
        ],
    }


def direct(study: RouteStudy):
    identity = (study.route_name, study.from_node_id, study.to_node_id)
    cost = compute_route_cost(
        RouteCostInput(*identity, components=[CostComponent(**c.value.model_dump())
                                              for c in study.costs])
    )
    feasibility = check_feasibility(
        FeasibilityInput(
            *identity,
            capacity_available_mcm_d=study.capacity.value,
            required_capacity_mcm_d=study.demand.value,
            route_eligible=study.eligible.value,
            contract_active=study.contract_active.value,
        )
    )
    return cost.total_cost_eur_mwh, feasibility.status


def benchmark(iterations: int) -> dict:
    payload = scenario()
    study = RouteStudy.model_validate(payload)
    runtime = CapabilityRuntime(register_builtin_capabilities())
    workflow = RouteDecisionResearch(runtime)
    context = AgentInvocationContext(principal_id="benchmark:synthetic")
    governed = workflow.assess(study, context)
    assert direct(study) == (governed.total_cost_eur_mwh, governed.feasibility)
    operations = {
        "A_direct_engines": lambda: direct(study),
        "B_governed_workflow": lambda: workflow.assess(study, context),
        "B_with_request_validation": lambda: workflow.assess(
            RouteStudy.model_validate(payload), context
        ),
    }
    for operation in operations.values():
        for _ in range(30):
            operation()
    samples = {name: [] for name in operations}
    for _ in range(iterations):
        for name, operation in operations.items():
            start = perf_counter_ns()
            operation()
            samples[name].append((perf_counter_ns() - start) / 1000)
    return {
        "iterations": iterations,
        "source_class": governed.source_class,
        "cost_eur_mwh": governed.total_cost_eur_mwh,
        "feasibility": governed.feasibility,
        "timing_microseconds": {
            name: {"p50": round(median(values), 2), "p95": round(quantiles(values, n=20)[18], 2)}
            for name, values in samples.items()
        },
        "C_agent_assisted": "NOT_MEASURED",
        "provider_calls": 0,
    }


def follow_up_demo(*, use_provider: bool) -> dict:
    from getpass import getpass

    from eurogas_nexus.application.agents.route_follow_up import (
        Alternative,
        Investigation,
        investigate,
        provider_planner,
    )

    baseline = RouteStudy.model_validate(scenario())
    delayed = baseline.model_copy(update={"delivery_at": baseline.delivery_at + timedelta(days=2)})
    diversion = {**scenario(), "route_name": "Synthetic diversion A to C", "to_node_id": "C"}
    investigation = Investigation(
        baseline=delayed,
        alternatives=(
            Alternative(purpose="revised_delivery", study=delayed),
            Alternative(purpose="alternative_route", study=RouteStudy.model_validate(diversion)),
        ),
    )
    workflow = RouteDecisionResearch(CapabilityRuntime(register_builtin_capabilities()))
    context = AgentInvocationContext(principal_id="benchmark:synthetic")
    fixed = investigate(workflow, investigation, context)
    results = {"fixed": fixed.model_dump(mode="json")}
    if use_provider:
        planner = provider_planner(getpass("Approved research provider key: "))
        assisted = investigate(workflow, investigation, context, planner=planner)
        results["assisted"] = assisted.model_dump(mode="json")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--follow-up", action="store_true", help="Run the synthetic investigation")
    parser.add_argument("--provider", action="store_true", help="Opt in to approved provider use")
    args = parser.parse_args()
    if args.provider and not args.follow_up:
        parser.error("--provider requires --follow-up")
    if args.follow_up:
        print(json.dumps(follow_up_demo(use_provider=args.provider), indent=2))
        raise SystemExit(0)
    if args.iterations < 20:
        parser.error("iterations must be at least 20")
    print(json.dumps(benchmark(args.iterations), indent=2))
