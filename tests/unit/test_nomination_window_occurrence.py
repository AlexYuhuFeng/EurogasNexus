"""Nomination-window occurrence resolution (the desk's clock).

These tests pin the rule that turns a declared window *clock* (``opens_at``/``closes_at`` as times
of day) into the UTC instants a surface can show as deadlines. The rule is not new: it mirrors
``optimization/nomination.py::_find_window``, so several cases here assert the two agree rather
than only asserting the arithmetic. The DST cases are the reason the resolution lives in the
domain layer instead of in a panel.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from eurogas_nexus.domain.market.nomination_windows import (
    gas_day_bounds_utc,
    resolve_window_occurrence,
)
from eurogas_nexus.optimization.nomination import (
    NominationInstruction,
    NominationWindow,
    optimize_nomination_schedule,
)


def _window(*, opens_at: time, closes_at: time) -> NominationWindow:
    return NominationWindow(window_id="w1", opens_at=opens_at, closes_at=closes_at)


def _engine_window_id_at(instant: datetime, *, opens_at: time, closes_at: time) -> str | None:
    """Return the window id the engine applies to one submitted instant."""

    result = optimize_nomination_schedule(
        100.0,
        [NominationInstruction(submitted_at=instant, requested_quantity_mwh=100.0)],
        [_window(opens_at=opens_at, closes_at=closes_at)],
    )
    return result.decisions[0].window_id


def test_winter_gas_day_boundary_is_the_cam_local_start_in_utc() -> None:
    start, end = gas_day_bounds_utc(date(2026, 1, 15))

    assert start == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
    assert end == datetime(2026, 1, 16, 5, 0, tzinfo=UTC)


def test_summer_gas_day_boundary_follows_daylight_saving() -> None:
    start, end = gas_day_bounds_utc(date(2026, 5, 29))

    assert start == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert end == datetime(2026, 5, 30, 4, 0, tzinfo=UTC)


def test_gas_day_length_is_23_hours_across_spring_forward() -> None:
    start, end = gas_day_bounds_utc(date(2026, 3, 28))

    assert start == datetime(2026, 3, 28, 5, 0, tzinfo=UTC)
    assert end == datetime(2026, 3, 29, 4, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=23)


def test_gas_day_length_is_25_hours_across_fall_back() -> None:
    start, end = gas_day_bounds_utc(date(2026, 10, 24))

    assert start == datetime(2026, 10, 24, 4, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 25, 5, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=25)


def test_window_inside_the_gas_day_resolves_without_a_wrap() -> None:
    occurrence = resolve_window_occurrence(
        gas_day=date(2026, 1, 15),
        opens_at=time(5, 0),
        closes_at=time(5, 30),
    )

    assert occurrence.opens_at_utc == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
    assert occurrence.closes_at_utc == datetime(2026, 1, 15, 5, 30, tzinfo=UTC)
    assert occurrence.closes_after_utc_midnight is False


def test_window_boundary_moves_with_daylight_saving_in_summer() -> None:
    """The same declared clock resolves an hour earlier in summer, because the gas day does."""

    occurrence = resolve_window_occurrence(
        gas_day=date(2026, 5, 29),
        opens_at=time(4, 0),
        closes_at=time(4, 30),
    )

    assert occurrence.opens_at_utc == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert occurrence.closes_at_utc == datetime(2026, 5, 29, 4, 30, tzinfo=UTC)


def test_clock_time_before_the_gas_day_start_lands_inside_the_gas_day() -> None:
    """A gas day starts at 05:00 UTC in winter, so a 03:00 clock time is the *next* date's."""

    gas_day = date(2026, 1, 15)
    start, end = gas_day_bounds_utc(gas_day)
    occurrence = resolve_window_occurrence(
        gas_day=gas_day,
        opens_at=time(3, 0),
        closes_at=time(3, 30),
    )

    assert occurrence.opens_at_utc == datetime(2026, 1, 16, 3, 0, tzinfo=UTC)
    assert occurrence.closes_at_utc == datetime(2026, 1, 16, 3, 30, tzinfo=UTC)
    assert start <= occurrence.opens_at_utc < end


def test_wrapping_window_closes_on_the_next_utc_date() -> None:
    occurrence = resolve_window_occurrence(
        gas_day=date(2026, 1, 15),
        opens_at=time(23, 0),
        closes_at=time(1, 0),
    )

    assert occurrence.opens_at_utc == datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
    assert occurrence.closes_at_utc == datetime(2026, 1, 16, 1, 0, tzinfo=UTC)
    assert occurrence.closes_after_utc_midnight is True


def test_zero_length_window_is_not_read_as_a_wrap() -> None:
    """``opens_at == closes_at`` matches that one clock time, exactly as the engine reads it."""

    occurrence = resolve_window_occurrence(
        gas_day=date(2026, 1, 15),
        opens_at=time(5, 0),
        closes_at=time(5, 0),
    )

    assert occurrence.opens_at_utc == occurrence.closes_at_utc
    assert occurrence.closes_after_utc_midnight is False


@pytest.mark.parametrize(
    ("opens_at", "closes_at"),
    [(time(5, 0), time(5, 30)), (time(23, 0), time(1, 0)), (time(5, 0), time(5, 0))],
)
def test_resolved_interval_is_the_engine_interval_within_the_gas_day(
    opens_at: time, closes_at: time
) -> None:
    """Membership in the resolved interval equals the window the engine applies.

    The comparison is bounded to the gas day on purpose: the engine matches a *clock time*, so an
    instant on another date can share a time of day with the window. Showing a deadline for one gas
    day is the claim this resolution makes, and this is the claim under test.
    """

    gas_day = date(2026, 1, 15)
    start, end = gas_day_bounds_utc(gas_day)
    occurrence = resolve_window_occurrence(
        gas_day=gas_day, opens_at=opens_at, closes_at=closes_at
    )
    probe = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    instants = [
        occurrence.opens_at_utc,
        occurrence.closes_at_utc,
        occurrence.opens_at_utc - timedelta(minutes=1),
        occurrence.closes_at_utc + timedelta(minutes=1),
        probe,
    ]
    for instant in instants:
        if not start <= instant < end:
            continue
        inside = occurrence.opens_at_utc <= instant <= occurrence.closes_at_utc
        engine_window_id = _engine_window_id_at(
            instant, opens_at=opens_at, closes_at=closes_at
        )
        assert (engine_window_id == "w1") is inside, instant.isoformat()


def test_offset_bearing_master_times_are_refused() -> None:
    """A master declares a clock, not an instant: an offset would be silently dropped."""

    with pytest.raises(ValueError):
        resolve_window_occurrence(
            gas_day=date(2026, 1, 15),
            opens_at=time(5, 0, tzinfo=UTC),
            closes_at=time(5, 30),
        )


def test_unknown_calendar_is_refused() -> None:
    with pytest.raises(ValueError):
        gas_day_bounds_utc(date(2026, 1, 15), "NOT-A-CALENDAR")
