"""A settlement read past the cap is refused, never silently cut to a subset."""

from __future__ import annotations

from datetime import date

import pytest

from eurogas_nexus.application import option_surface


class _Query:
    def __init__(self, count: int) -> None:
        self.count = count
        self.limit_seen: int | None = None

    def filter(self, *_args):
        return self

    def limit(self, value: int):
        self.limit_seen = value
        return self

    def all(self):
        return [object()] * min(self.count, self.limit_seen or self.count)


class _Session:
    def __init__(self, query: _Query) -> None:
        self._query = query

    def query(self, *_args):
        return self._query


def test_a_read_past_the_cap_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(option_surface, "MAX_ROWS", 3)
    query = _Query(count=10)
    with pytest.raises(option_surface.OptionHistoryTooLarge):
        option_surface.option_rows(
            _Session(query), hubs=["TTF"], first=date(2026, 1, 1), last=date(2026, 2, 1)
        )
    assert query.limit_seen == 4


def test_open_interest_ratio_is_stated_without_an_underlying() -> None:
    """The ratio needs no underlying or tenor, so a file without one still carries it."""

    from datetime import UTC, date, datetime

    from eurogas_nexus.application.option_surface import contract_summary

    def row(strike: float, option_type: str, oi: float) -> dict:
        return {
            "hub": "TTF", "contract": "Jan-27", "trade_date": date(2026, 11, 25),
            "expiry_date": date(2026, 12, 24),
            "delivery_start_utc": datetime(2027, 1, 1, tzinfo=UTC),
            "premium_style": "futures_style", "unit": "EUR/MWh", "underlying_price": None,
            "underlying_basis": None, "metadata_json": {}, "venue": "ICE Endex",
            "source_reference": "file", "ingested_at_utc": datetime(2026, 11, 25, 18, tzinfo=UTC),
            "strike": strike, "option_type": option_type, "implied_vol": None, "open_interest": oi,
            "settlement_price": 1.0, "iv_basis": None, "iv_reason": "no_underlying",
            "forward_delta": None, "volume": None, "simulated": False,
        }

    summary = contract_summary("ICE_Endex", [row(30.0, "C", 100.0), row(35.0, "P", 50.0)], [])
    assert summary["metrics"]["put_call_oi_ratio"] == 0.5
    assert summary["metrics"]["reasons"]["metrics"] == "no_underlying"
    assert summary["metrics"]["atm_iv_pct"] is None
