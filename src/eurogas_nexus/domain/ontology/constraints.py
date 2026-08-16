"""L5 computable-constraint registry.

Exposes the pure correctness functions in `domain.constraints` as named,
described rules, so the ontology surfaces the "正确性归校验器" rules
declaratively. The implementations remain pure and import-safe.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from eurogas_nexus.domain.constraints.access import inaccessible_tsos
from eurogas_nexus.domain.constraints.risk import ocm_day_split, stop_loss_triggered
from eurogas_nexus.domain.constraints.route_economics import netback


@dataclass(frozen=True)
class Constraint:
    """A named, described computable constraint bound to its validator."""

    constraint_id: str
    name: str
    description: str
    validator: Callable[..., Any]


CONSTRAINTS: tuple[Constraint, ...] = (
    Constraint(
        "TSO_ACCESS_FAIL_CLOSED",
        "TSO access fail-closed",
        "A required TSO absent from the company access list blocks the route/option.",
        inaccessible_tsos,
    ),
    Constraint(
        "NETBACK_DEFINITION",
        "Netback definition",
        "Netback = sale price - route cost, only when currency and unit are compatible.",
        netback,
    ),
    Constraint(
        "SHADOW_RUN_STOP_LOSS",
        "Shadow-run stop loss (cumulative)",
        "Block the run when cumulative paper PnL is at or below the negative threshold.",
        stop_loss_triggered,
    ),
    Constraint(
        "OCM_DAY_ALLOCATION_SPLIT",
        "OCM vs day-ahead allocation split",
        "Derive OCM/day-ahead percentages from score, clamped to configured limits.",
        ocm_day_split,
    ),
)
