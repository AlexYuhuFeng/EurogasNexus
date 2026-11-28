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
from eurogas_nexus.domain.constraints.route_economics import netback


@dataclass(frozen=True)
class Constraint:
    """A named, described computable constraint bound to its validator.

    一条可计算约束：把纯校验函数以命名规则的形式暴露给本体层，
    便于审计与文档声明式引用。

    Attributes:
        constraint_id: Stable constraint id (e.g. ``TSO_ACCESS_FAIL_CLOSED``).
        name: Short human-readable name.
        description: One-line description of the rule.
        validator: The pure function implementing the rule (import-safe).
    """

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
)
