"""Test harness for evaluator authors.

Typical golden-case test::

    snapshot = fixture_snapshot([...keyed SnapshotInput...], as_of=AS_OF)
    outcome = run(MyEvaluator(), snapshot, as_of=AS_OF)
    (candidate, assessment), = outcome
    assert_legs(candidate, [("my.sell", "31.20"), ("my.buy", "-30.00"), ...])
    assert_reconciles(candidate)
    assert assessment.state is OpportunityState.ACTIONABLE

:func:`run` applies the contract check (:func:`~.evaluator.validate_candidate`) and the
false-positive controls exactly as the service does, so a test sees the state the desk
would see. :func:`book_row` builds a hedge-cover row the way the live reader records one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.opportunities.controls import Assessment, Thresholds, assess
from eurogas_nexus.domain.opportunities.evaluator import (
    EvaluationContext,
    Evaluator,
    validate_candidate,
)
from eurogas_nexus.domain.opportunities.model import Candidate, LegKind, reconcile
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import (
    FixtureReader,
    InputKind,
    SnapshotInput,
)


def fixture_snapshot(
    inputs: Iterable[SnapshotInput],
    *,
    as_of: datetime,
    demo_desk: bool = False,
    collections: Mapping[str, Iterable[str]] | None = None,
) -> FixtureReader:
    """A snapshot that holds exactly the given inputs (anything else reads as missing)."""

    return FixtureReader(inputs, as_of_utc=as_of, demo_desk=demo_desk, collections=collections)


def book_row(
    contract_id: str,
    month: str,
    *,
    contract_mwh: str,
    hedged_mwh: str,
    band_low_pct: str | None,
    band_high_pct: str | None,
    as_of: datetime,
    book_id: str | None = "book-1",
    contract_name: str | None = None,
    input_class: InputClass = InputClass.SOURCED,
    linked_trades: int = 1,
    approval_ref: str | None = None,
    approved_by: str = "risk",
    valid_until: str | None = None,
) -> SnapshotInput:
    """A hedge-cover row shaped like the live reader's (``book:hedge:<contract>:<month>``)."""

    detail: dict[str, Any] = {
        "contract_id": contract_id,
        "contract_name": contract_name or contract_id,
        "book_id": book_id,
        "hub": "TTF",
        "month": month,
        "contract_mwh": contract_mwh,
        "hedged_mwh": hedged_mwh,
        "band_low_pct": band_low_pct,
        "band_high_pct": band_high_pct,
        "approval_ref": approval_ref,
        "approved_by": approved_by,
        "approved_at_utc": as_of.isoformat(),
        "valid_until": valid_until,
        "linked_trades": linked_trades,
    }
    return SnapshotInput(
        key=f"book:hedge:{contract_id}:{month}",
        kind=InputKind.BOOK,
        input_class=input_class,
        value=Decimal(contract_mwh),
        unit="MWh",
        as_of_utc=as_of,
        source_family="DEMO" if input_class is InputClass.SIMULATED else "operator-input",
        source_ref=f"hedge_approval:{contract_id}",
        label=f"{contract_name or contract_id} {month}",
        detail=detail,
    )


def run(
    evaluator: Evaluator,
    snapshot: FixtureReader,
    *,
    as_of: datetime,
    thresholds: Thresholds | None = None,
    demo_desk: bool | None = None,
    route_pricer=None,
) -> list[tuple[Candidate, Assessment]]:
    """Evaluate, check the contract and apply the controls, as the service does.

    ``route_pricer`` is the application's route pricer (tests pass
    ``application.route_tariff_cost.route_cost``; the domain cannot import it).
    """

    demo = snapshot.demo_desk if demo_desk is None else demo_desk
    context = EvaluationContext(
        as_of_utc=as_of,
        thresholds=thresholds or Thresholds(),
        demo_desk=demo,
        route_pricer=route_pricer,
    )
    out = []
    for candidate in evaluator.evaluate(snapshot, context):
        validate_candidate(candidate, context)
        out.append(
            (candidate, assess(candidate, context.thresholds, as_of_utc=as_of, demo_desk=demo))
        )
    return out


def assert_reconciles(candidate: Candidate) -> None:
    """The legs sum to the headline (raises :class:`~.model.ReconciliationError`)."""

    reconcile(candidate)


def assert_legs(candidate: Candidate, expected: Sequence[tuple[str, str]]) -> None:
    """Term rows, in order, as ``(label_key, contribution as decimal text)``.

    Raises:
        AssertionError: with the actual rows when they differ.
    """

    actual = [
        (leg.label_key, leg.contribution.value)
        for leg in candidate.legs
        if leg.kind is LegKind.TERM and leg.contribution is not None
    ]
    wanted = [(key, Decimal(value)) for key, value in expected]
    if actual != wanted:
        raise AssertionError(f"legs {actual} != expected {wanted}")
