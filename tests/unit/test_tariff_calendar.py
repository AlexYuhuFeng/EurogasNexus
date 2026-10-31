"""Tariff publication calendar (NC TAR) and what the desk must act on."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.domain.route_cost.tariff_calendar import (
    annual_yearly_auction,
    final_tariff_deadline,
    gas_year_start,
    publication_state,
)


def test_calendar():
    assert gas_year_start("2027/28") == date(2027, 10, 1)
    assert gas_year_start("2027-2028") == date(2027, 10, 1)
    assert annual_yearly_auction(2027) == date(2027, 7, 5)  # first Monday of July
    assert annual_yearly_auction(2024) == date(2024, 7, 1)
    assert final_tariff_deadline("2027/28") == date(2027, 6, 5)
    with pytest.raises(ValueError):
        gas_year_start("next year")


@pytest.mark.parametrize(
    ("status", "today", "state", "severity"),
    [
        ("final", date(2027, 11, 1), "final", "ok"),
        ("expected", date(2027, 2, 1), "not_yet_due", "ok"),
        ("indicative", date(2027, 5, 1), "due_soon", "watch"),
        ("indicative", date(2027, 6, 10), "overdue", "breach"),
        ("indicative", date(2027, 10, 2), "in_force_without_final", "breach"),
    ],
)
def test_states(status, today, state, severity):
    result = publication_state(tso="GTS", gas_year="2027/28", status=status, today=today)
    assert (result.state, result.severity) == (state, severity)


def test_a_changed_page_needs_review_until_reviewed():
    changed = datetime(2027, 3, 1, tzinfo=UTC)
    pending = publication_state(
        tso="BBL",
        gas_year="2027/28",
        status="final",
        today=date(2027, 3, 2),
        changed_at=changed,
        reviewed_at=None,
    )
    assert pending.state == "changed"
    reviewed = publication_state(
        tso="BBL",
        gas_year="2027/28",
        status="final",
        today=date(2027, 3, 2),
        changed_at=changed,
        reviewed_at=datetime(2027, 3, 2, tzinfo=UTC),
    )
    assert reviewed.state == "final"
