"""Reference enumeration and cross-engine checks for lower-bound/time-expanded flow."""

import random
from itertools import product

import pytest

from eurogas_nexus.optimization.circulation import Arc, solve_circulation
from eurogas_nexus.optimization.joint import JointRequest, optimize_joint


def brute(arcs):
    nodes = {n for a in arcs for n in (a.source, a.target)}
    best = None
    for values in product(*(range(int(a.lower), int(a.upper) + 1) for a in arcs)):
        balance = {n: 0 for n in nodes}
        for a, value in zip(arcs, values, strict=True):
            balance[a.source] -= value
            balance[a.target] += value
        if any(balance.values()):
            continue
        cost = sum(a.cost * v for a, v in zip(arcs, values, strict=True))
        best = cost if best is None else min(best, cost)
    return best


def test_circulation_matches_exhaustive_integer_reference():
    rng = random.Random(17)
    for _ in range(80):
        arcs = [
            Arc(str(i), u, v, rng.randrange(2), 2, rng.randrange(-4, 5))
            for i, (u, v) in enumerate([("a", "b"), ("b", "c"), ("c", "a"), ("b", "a"), ("a", "c")])
        ]
        expected = brute(arcs)
        result = solve_circulation(arcs)
        if expected is None:
            assert result["status"] == "infeasible"
        else:
            assert result["status"] == "optimal"
            assert result["cost"] == pytest.approx(expected)


def joint():
    return dict(
        days=["2026-11-01", "2026-11-02"],
        supplies=[
            dict(
                supply_id="gas",
                node="A",
                day="2026-11-01",
                maximum_mwh=10,
                cost_gbp_mwh=10,
                annual_financing_rate_pct=0,
                funding_days=0,
                day_count="ACT/365F",
            )
        ],
        sales=[
            dict(sale_id="today", node="B", day="2026-11-01", maximum_mwh=10, value_gbp_mwh=12),
            dict(sale_id="tomorrow", node="B", day="2026-11-02", maximum_mwh=10, value_gbp_mwh=30),
        ],
        transports=[
            dict(
                edge_id="pipe",
                source="A",
                target="B",
                tariff_gbp_mwh=1,
                capacity_by_day={"2026-11-01": 10, "2026-11-02": 4},
                access_confirmed=True,
            )
        ],
        stores=[
            dict(
                storage_id="S",
                node="A",
                initial_mwh=0,
                minimum_mwh=0,
                maximum_mwh=10,
                injection_limit_mwh=10,
                withdrawal_limit_mwh=10,
                injection_cost_gbp_mwh=1,
                withdrawal_cost_gbp_mwh=1,
                terminal_minimum_mwh=0,
                terminal_maximum_mwh=0,
                terminal_value_gbp_mwh=0,
                initial_value_gbp_mwh=0,
            )
        ],
    )


def test_joint_respects_shared_capacity_and_selects_cross_day_storage():
    result = optimize_joint(JointRequest.model_validate(joint()))
    assert result["status"] == "optimal"
    assert result["flows"]["sale:tomorrow"] == pytest.approx(4)
    assert result["flows"]["sale:today"] == pytest.approx(6)
    assert result["net_value_gbp"] == pytest.approx(74)  # 6*(12-10-1)+4*(30-10-1-2)
    assert "edge:pipe:2026-11-02" in result["binding_capacity"]


def test_mandatory_negative_margin_and_infeasible_obligation():
    body = joint()
    body["sales"][0]["minimum_mwh"] = 9
    body["sales"][0]["value_gbp_mwh"] = 1
    result = optimize_joint(JointRequest.model_validate(body))
    assert result["flows"]["sale:today"] == pytest.approx(9)
    body["transports"][0]["access_confirmed"] = False
    assert optimize_joint(JointRequest.model_validate(body))["status"] == "infeasible"


def test_solver_cooperatively_cancels():
    def cancel():
        raise TimeoutError("cancelled")

    with pytest.raises(TimeoutError):
        solve_circulation([Arc("a", "a", "b", 0, 1, -1)], cancel)


def test_joint_matches_existing_storage_grid_for_integral_lossless_case():
    from eurogas_nexus.optimization.storage import (
        StorageFacility,
        StoragePeriod,
        optimize_storage_dispatch,
    )

    body = joint()
    body["transports"] = []
    body["supplies"][0]["node"] = "A"
    body["sales"][0]["maximum_mwh"] = 0
    body["sales"][1]["node"] = "A"
    body["sales"][1]["maximum_mwh"] = 10
    result = optimize_joint(JointRequest.model_validate(body))
    reference = optimize_storage_dispatch(
        StorageFacility(
            0,
            0,
            10,
            10,
            10,
            injection_cost_gbp_mwh=1,
            withdrawal_cost_gbp_mwh=1,
            terminal_inventory_mwh=0,
        ),
        [StoragePeriod("d1", 10), StoragePeriod("d2", 30)],
    )
    assert result["net_value_gbp"] == pytest.approx(reference.objective_value_gbp)


def test_lossy_storage_is_not_silently_treated_as_lossless():
    body = joint()
    body["stores"][0]["injection_efficiency"] = 0.95
    with pytest.raises(ValueError):
        JointRequest.model_validate(body)


def test_capacity_sensitivity_and_ordered_value_attribution():
    from eurogas_nexus.application.functional_comparison import JointComparison, attribute_joint

    body = joint()
    body["analyze_bottlenecks"] = True
    result = optimize_joint(JointRequest.model_validate(body))
    sensitivity = {
        r["edge_period"]: r["incremental_value_gbp"] for r in result["capacity_sensitivity"]
    }
    assert sensitivity["edge:pipe:2026-11-02"] == pytest.approx(16)
    alternative = joint()
    alternative["sales"][1]["value_gbp_mwh"] = 35
    comparison = attribute_joint(
        JointComparison.model_validate({"left": body, "right": alternative})
    )
    assert comparison["total_change_gbp"] == pytest.approx(20)
    assert sum(
        r["incremental_net_value_gbp"] for r in comparison["contributions"]
    ) == pytest.approx(20)


def test_financing_convention_is_shared_with_backtest_costs():
    from eurogas_nexus.domain.backtest.contracts import BacktestCostComponent
    from eurogas_nexus.domain.economics.financing import simple_interest
    from eurogas_nexus.domain.ontology.vocabulary import CostTreatment

    terms = {
        "principal_gbp_mwh": 100,
        "annual_rate_pct": 3,
        "actual_days": 30,
        "day_count": "ACT/360",
    }
    cost = BacktestCostComponent(
        code="FINANCING_COST", treatment=CostTreatment.MODELED_COST, financing=terms
    )
    assert cost.amount_gbp_mwh == pytest.approx(simple_interest(100, 3, 30, "ACT/360"))
    assert cost.amount_gbp_mwh == pytest.approx(0.25)
    with pytest.raises(ValueError):
        BacktestCostComponent(
            code="FINANCING_COST",
            treatment=CostTreatment.MODELED_COST,
            financing=terms,
            amount_gbp_mwh=99,
        )
