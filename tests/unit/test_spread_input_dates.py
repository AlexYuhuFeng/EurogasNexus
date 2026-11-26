"""A reversed date window is refused as a date error, not as a missing series."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from eurogas_nexus.application.spread_history import SpreadAnalysisInput

LEGS = [{"hub": "TTF", "tenor": "day-ahead", "weight": 1},
        {"hub": "NBP", "tenor": "day-ahead", "weight": -1}]


def test_date_from_after_date_to_is_refused():
    with pytest.raises(ValidationError) as caught:
        SpreadAnalysisInput(legs=LEGS, date_from=date(2026, 6, 1), date_to=date(2026, 1, 1))
    assert "date_from 2026-06-01 is after date_to 2026-01-01" in str(caught.value)


@pytest.mark.parametrize("window", [
    {}, {"date_from": date(2026, 1, 1)}, {"date_to": date(2026, 1, 1)},
    {"date_from": date(2026, 1, 1), "date_to": date(2026, 1, 1)},
])
def test_open_or_ordered_windows_are_accepted(window):
    assert SpreadAnalysisInput(legs=LEGS, **window).legs[0].hub == "TTF"
