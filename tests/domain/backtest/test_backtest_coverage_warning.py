"""A backtest over mostly unpriced days must say so in the metric set.

Why this test exists
--------------------
A reviewer ran a 365-day backtest on a deployment whose first market observation was 306
days into the period. The engine behaved correctly: those days were refused, counted as
BLOCKED, and excluded from the profit and loss. But the run was stored as
COMPLETED_WITH_WARNINGS, and the surface presented "+51,009 GBP, Hit ratio 100%, Max
drawdown 0" as the headline. `data_coverage` was 16.2% and accurate; the gap was that
nothing in the metric set made that legible beside the profit figure, so a backtest over a
sixth of its period read as a result for the whole year.

The assertion is about what the run says about itself, not about refusing partial runs:
research on a short history is legitimate, presenting it as a full-period result is not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eurogas_nexus.domain.backtest.contracts import BacktestDecisionEvent
from eurogas_nexus.domain.backtest.engine import (
    MINIMUM_READABLE_BACKTEST_COVERAGE,
    aggregate_metrics,
)

START = datetime(2026, 1, 1, 4, 0, tzinfo=UTC)


def _event(index: int, outcome: str, pnl: float = 0.0) -> BacktestDecisionEvent:
    """One decision event, with the fields `aggregate_metrics` reads populated."""

    gas_day = START + timedelta(days=index)
    return BacktestDecisionEvent(
        event_id=f"event-{index}",
        run_id="run-coverage",
        decision_sequence=index,
        decision_time_utc=gas_day,
        gas_day=gas_day.date().isoformat(),
        gas_day_start_utc=gas_day,
        gas_day_end_utc=gas_day + timedelta(days=1),
        outcome=outcome,
        net_indicative_pnl_gbp=pnl,
        cumulative_net_indicative_pnl_gbp=pnl,
        ending_exposure_mwh_per_day=0.0,
        allocation_targets=[],
    )


def test_a_mostly_blocked_run_carries_a_coverage_warning() -> None:
    """The regression: 59 priced days out of 365 must not pass as a year's result."""

    events = [_event(index, "BLOCKED") for index in range(306)]
    events += [_event(306 + index, "COMPLETED", pnl=100.0) for index in range(59)]

    metrics = aggregate_metrics(events)

    assert metrics.evaluation_count == 365
    assert metrics.candidate_decision_count == 59
    assert metrics.blocked_decision_count == 306
    assert metrics.data_coverage < MINIMUM_READABLE_BACKTEST_COVERAGE
    assert "PARTIAL_PERIOD_COVERAGE" in metrics.warning_counts, (
        "a run priced on 16% of its period reported no warning that it covers only that "
        f"share; warning counts were {metrics.warning_counts}"
    )
    # The profit figure stays as computed. The test is that the run labels itself, not
    # that the number changes.
    assert metrics.net_indicative_pnl_gbp == 5900.0


def test_a_fully_covered_run_carries_no_coverage_warning() -> None:
    """The warning must not fire on a complete run, or it becomes noise."""

    events = [_event(index, "COMPLETED", pnl=10.0) for index in range(30)]
    metrics = aggregate_metrics(events)

    assert metrics.data_coverage == 1.0
    assert "PARTIAL_PERIOD_COVERAGE" not in metrics.warning_counts


def test_the_threshold_boundary_is_respected() -> None:
    """Exactly at the floor is readable; one point below is not.

    The comparison is strictly less-than, so a run priced on exactly half of its points
    is treated as readable. Stating that here keeps the boundary a decision rather than an
    accident of floating-point rounding.
    """

    total = 100
    at_floor = int(MINIMUM_READABLE_BACKTEST_COVERAGE * total)
    assert at_floor == 50, "the fixture below assumes a floor that divides 100 evenly"

    events = [_event(index, "COMPLETED") for index in range(at_floor)]
    events += [_event(at_floor + i, "BLOCKED") for i in range(total - at_floor)]
    exactly = aggregate_metrics(events)
    assert exactly.data_coverage == MINIMUM_READABLE_BACKTEST_COVERAGE
    assert "PARTIAL_PERIOD_COVERAGE" not in exactly.warning_counts, (
        "a run exactly at the floor is treated as readable, so it must not warn"
    )

    just_below = at_floor - 1
    events = [_event(index, "COMPLETED") for index in range(just_below)]
    events += [_event(just_below + i, "BLOCKED") for i in range(total - just_below)]
    below = aggregate_metrics(events)
    assert below.data_coverage < MINIMUM_READABLE_BACKTEST_COVERAGE
    assert "PARTIAL_PERIOD_COVERAGE" in below.warning_counts


def test_an_empty_run_makes_no_coverage_claim() -> None:
    """No events means no coverage to report; a zero denominator must not warn."""

    metrics = aggregate_metrics([])
    assert metrics.evaluation_count == 0
    assert metrics.data_coverage == 0.0
    assert "PARTIAL_PERIOD_COVERAGE" not in metrics.warning_counts


def test_per_event_warnings_are_still_counted_alongside_coverage() -> None:
    """The coverage warning must not displace the warnings the events already carried."""

    events = [_event(index, "BLOCKED") for index in range(10)]
    events[0] = events[0].model_copy(update={"warnings": ["COST_UNAVAILABLE:transport"]})

    metrics = aggregate_metrics(events)

    assert metrics.warning_counts.get("COST_UNAVAILABLE") == 1
    assert "PARTIAL_PERIOD_COVERAGE" in metrics.warning_counts
