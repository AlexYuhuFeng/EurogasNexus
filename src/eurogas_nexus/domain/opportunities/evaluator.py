"""The evaluator contract, registration and evaluation context.

Contract for evaluator authors (one evaluator per opportunity type, design J.2):

1. **Pure and deterministic.** ``evaluate(snapshot, context)`` reads every input through the
   :class:`~eurogas_nexus.domain.valuation.snapshot.SnapshotReader` it is given and nothing
   else: no database, no network, no clock (use ``context.as_of_utc``), no model. The same
   snapshot gives the same candidates, which is what makes a replay reproduce a case.
2. **Never guess a missing input.** Read it; if it is not held, still return the candidate
   with the missing input among ``inputs`` (or a :class:`~.model.Blocker`): the controls turn
   it into a named "cannot evaluate" record ("tariff not held at X"). Never use zero for a
   missing tariff or price.
3. **Arithmetic that reconciles.** ``term`` legs carry signed contributions in the headline's
   unit and sum exactly to the headline; one ``result`` row states it; ``value = headline x
   volume`` when there is a value. FX and unit conversions are their own ``conversion`` rows
   with the rate and its source. :func:`~.model.reconcile` is run on every candidate; a
   candidate that fails it is an evaluator defect: the evaluator's output is discarded for
   that run and an administrator alert is raised, nothing is shown to the desk.
4. **Claims from templates only** (:mod:`.claims`), at least one falsifier, a validity window
   (``expires_at_utc``) and, for must-act types, a ``deadline_utc``.
5. **Value-path inputs only in ``inputs``.** They set the data-quality class (weakest wins),
   staleness and the dependency keys an outbox event will re-evaluate on.
6. **Thresholds are not the evaluator's business.** Return every complete candidate; the
   controls decide actionable, indicative, watch or blocked.
7. **Bounded.** Candidate generation is bounded by the book (design J.2: order 10^2-10^3 per
   run); an evaluator never enumerates the market.

Register with :func:`register`; the service runs every registered evaluator per evaluation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from eurogas_nexus.domain.opportunities.claims import render_claim
from eurogas_nexus.domain.opportunities.controls import Thresholds
from eurogas_nexus.domain.opportunities.model import (
    Candidate,
    OpportunityType,
    ReconciliationError,
    reconcile,
)
from eurogas_nexus.domain.valuation.snapshot import SnapshotReader


@dataclass(frozen=True)
class EvaluationContext:
    """What an evaluator may know besides its snapshot."""

    as_of_utc: datetime
    thresholds: Thresholds
    demo_desk: bool


@runtime_checkable
class Evaluator(Protocol):
    """One opportunity type's evaluator."""

    name: str
    version: str
    type: OpportunityType

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """Every candidate the book supports at this snapshot."""


class ContractBreach(ValueError):
    """A candidate that breaks the evaluator contract (an evaluator defect)."""


def validate_candidate(candidate: Candidate, context: EvaluationContext) -> None:
    """Check one candidate against the contract (rules 3 and 4).

    Raises:
        ContractBreach: naming the rule.
    """

    if candidate.blockers:
        render_claim(candidate.claim_key, candidate.claim_fields)
        return
    try:
        reconcile(candidate)
    except ReconciliationError as exc:
        raise ContractBreach(f"{candidate.evaluator}: {exc}") from exc
    try:
        render_claim(candidate.claim_key, candidate.claim_fields)
    except ValueError as exc:
        raise ContractBreach(f"{candidate.evaluator}: {exc}") from exc
    if not candidate.falsifiers:
        raise ContractBreach(f"{candidate.evaluator}: at least one falsifier is required")
    if candidate.expires_at_utc <= context.as_of_utc:
        raise ContractBreach(f"{candidate.evaluator}: validity window already over")
    if not candidate.inputs:
        raise ContractBreach(f"{candidate.evaluator}: no value-path inputs declared")


_REGISTRY: dict[str, Evaluator] = {}


def register(evaluator: Evaluator) -> Evaluator:
    """Add an evaluator (idempotent by name).

    Raises:
        ValueError: another evaluator already holds the name.
    """

    held = _REGISTRY.get(evaluator.name)
    if held is not None and held is not evaluator:
        raise ValueError(f"evaluator {evaluator.name!r} is already registered")
    _REGISTRY[evaluator.name] = evaluator
    return evaluator


def registered() -> tuple[Evaluator, ...]:
    """Every registered evaluator, in name order (the reference ones are loaded first)."""

    from eurogas_nexus.domain.opportunities import (  # noqa: F401 - registers
        event_exposure,
        hedge_gap,
        locational,
        sell_down,
    )

    return tuple(_REGISTRY[name] for name in sorted(_REGISTRY))
