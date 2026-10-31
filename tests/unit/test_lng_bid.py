"""LNG cargo bid sheet across terminals."""

from __future__ import annotations

import pytest

from eurogas_nexus.domain.portfolio.lng_bid import (
    MWH_PER_MMBTU,
    CargoBidRequest,
    TerminalTerms,
    cargo_bid_sheet,
    region_ranges,
)
from eurogas_nexus.domain.risk.limits import fx_lookup

MARKS = {
    ("TTF", "2026-12"): 40.0,
    ("TTF", "2026-11"): 38.0,
    ("TTF", "2027-01"): 41.0,
    ("NBP", "2026-12"): 30.0,
}
FX = fx_lookup({"EUR": 1.0, "GBP": 0.85, "USD": 1.10})


def sheet(terminals, **kw):
    request = CargoBidRequest(cargo_mwh=1_000_000, arrival_month="2026-12", **kw)
    return cargo_bid_sheet(
        terminals,
        request,
        mark=lambda h, m: MARKS.get((h, m)),
        spot=lambda h: 39.5 if h == "TTF" else None,
        fx=FX,
    )


GATE = TerminalTerms(
    "gate",
    "Gate",
    "NL",
    "TTF",
    "EUR",
    regas_tariff_per_mwh=1.5,
    entry_tariff_per_mwh=0.5,
    fuel_retention_pct=1.0,
    port_costs_per_cargo=100_000,
)
GRAIN = TerminalTerms(
    "grain", "Isle of Grain", "GB", "NBP", "GBP", regas_tariff_per_mwh=1.2, extra_sailing_days=2
)


def test_breakeven_and_bid_at_one_terminal():
    (row,), warnings = sheet([GATE], target_margin_per_mwh=0.5)
    assert not warnings
    sent_out = 1_000_000 * 0.99
    costs = 1_000_000 * 1.5 + sent_out * 0.5 + 100_000
    breakeven = (sent_out * 40.0 - costs) / 1_000_000
    assert row["breakeven_per_mwh"] == pytest.approx(breakeven, abs=1e-3)
    assert row["max_bid_per_mwh"] == pytest.approx(breakeven - 0.5, abs=1e-3)
    assert row["max_bid_usd_mmbtu"] == pytest.approx(
        (breakeven - 0.5) * 1.1 * MWH_PER_MMBTU, abs=1e-3
    )
    assert row["bid_low_per_mwh"] < row["max_bid_per_mwh"] < row["bid_high_per_mwh"]
    assert row["spot"] == 39.5 and row["rank"] == 1 and row["bid_pct_of_hub"] < 100


def test_terminals_rank_in_one_currency_with_boil_off_and_charter():
    rows, warnings = sheet([GRAIN, GATE], charter_per_day=50_000, boil_off_pct_per_day=0.1)
    assert [row["terminal"] for row in rows] == ["Gate", "Isle of Grain"]
    grain = rows[1]
    assert grain["currency"] == "GBP" and grain["sent_out_mwh"] == 998_000
    assert grain["max_bid_eur_per_mwh"] == pytest.approx(grain["max_bid_per_mwh"] / 0.85, rel=1e-4)
    ranges = region_ranges(rows, "EUR")
    assert ranges[0]["country"] == "NL" and ranges[0]["terminals"] == 1


def test_missing_mark_or_fx_is_reported_not_guessed():
    other = TerminalTerms("x", "Dunkerque", "FR", "PEG", "EUR", regas_tariff_per_mwh=1.0)
    yen = TerminalTerms("y", "Sodegaura", "JP", "JKM", "JPY", regas_tariff_per_mwh=1.0)
    rows, warnings = sheet([other, yen])
    assert rows == [] and len(warnings) == 2
    with pytest.raises(ValueError):
        cargo_bid_sheet(
            [GATE],
            CargoBidRequest(cargo_mwh=0, arrival_month="2026-12"),
            mark=lambda h, m: 1.0,
            spot=lambda h: None,
            fx=FX,
        )
