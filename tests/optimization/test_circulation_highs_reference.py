"""Optional independent HiGHS numerical reference; not a product dependency."""

import random

import pytest

from eurogas_nexus.optimization.circulation import Arc, solve_circulation


def test_circulation_agrees_with_independent_linear_program():
    scipy = pytest.importorskip("scipy.optimize")
    rng = random.Random(9187)
    for _ in range(120):
        arcs = [
            Arc(
                str(i),
                str(u),
                str(v),
                rng.choice([0, 0, 0.25]),
                rng.uniform(1, 20),
                rng.uniform(-20, 30),
            )
            for i, (u, v) in enumerate(
                [(0, 1), (1, 2), (2, 0), (0, 3), (3, 2), (2, 4), (4, 0), (1, 4)]
            )
        ]
        matrix = [
            [(1 if a.target == str(n) else 0) - (1 if a.source == str(n) else 0) for a in arcs]
            for n in range(5)
        ]
        reference = scipy.linprog(
            [a.cost for a in arcs],
            A_eq=matrix,
            b_eq=[0] * 5,
            bounds=[(a.lower, a.upper) for a in arcs],
            method="highs",
        )
        result = solve_circulation(arcs)
        if reference.status == 2:
            assert result["status"] == "infeasible"
        else:
            assert reference.success, reference.message
            assert result["status"] == "optimal"
            assert result["cost"] == pytest.approx(reference.fun, abs=1e-6)
