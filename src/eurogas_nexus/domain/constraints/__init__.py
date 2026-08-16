"""Declarative L5 computable constraints shared by domain evaluation paths.

These are pure functions — no DB, no network, no web framework. They centralize
the correctness rules that deterministic engines and LLM validation must agree
on, per `docs/ontology/europe-natural-gas.md` §3 ("正确性归校验器").
"""

from eurogas_nexus.domain.constraints.access import inaccessible_tsos
from eurogas_nexus.domain.constraints.risk import ocm_day_split, stop_loss_triggered
from eurogas_nexus.domain.constraints.route_economics import netback

__all__ = [
    "inaccessible_tsos",
    "netback",
    "ocm_day_split",
    "stop_loss_triggered",
]
