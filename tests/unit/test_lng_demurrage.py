"""LNG-4 demurrage by contract and the one FX conversion function (``_fx_rate``).

Every rate here is a row the test supplies; nothing is fetched and no rate is hard-coded in
the code under test.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from eurogas_nexus.application.lng_demurrage import (
    FxBook,
    FxChoice,
    FxChoiceError,
    _fx_rate,
    amounts,
    convert,
    demurrage_terms,
    reporting,
)

ON = date(2027, 1, 20)


def _row(source: str, pair: str, rate: float, day: str, rate_type: str = "reference"):
    return {
        "source_system": source,
        "pair": pair,
        "rate": rate,
        "value_date": day,
        "rate_type": rate_type,
    }


ROWS = [
    _row("ECB", "EURUSD", 1.10, "2027-01-19"),
    _row("ECB", "EURUSD", 1.08, "2027-01-15"),
    _row("ECB", "EURGBP", 0.85, "2027-01-19"),
    _row("WMR", "EURUSD", 1.0950, "2027-01-19", "WMR_1600_LDN"),
]


def book(choice: FxChoice | None = None, rows=ROWS, *, demo: bool = False) -> FxBook:
    return FxBook(choice or FxChoice(), ON, list(rows), allow_demo=demo)


# --------------------------------------------------------------------------- _fx_rate


def test_fx_rate_defaults_to_the_latest_ecb_fix_on_or_before_the_day():
    used = _fx_rate(None, "USD", "EUR", ON, book())
    assert used.rate == pytest.approx(1 / 1.10)
    assert (used.source, used.label, used.rate_date) == (
        "ECB",
        "ECB euro reference rate",
        "2027-01-19",
    )
    assert used.tried == ("ECB euro reference rate for USD on or before 2027-01-20",)
    assert not used.entered and not used.simulated and used.missing is None


def test_fx_rate_takes_the_rate_date_the_user_picks():
    used = _fx_rate(None, "USD", "EUR", ON, book(FxChoice(rate_date=date(2027, 1, 16))))
    assert (used.rate, used.rate_date) == (pytest.approx(1 / 1.08), "2027-01-15")


def test_fx_rate_crosses_through_eur_and_names_both_legs_tried():
    used = _fx_rate(None, "USD", "GBP", ON, book())
    assert used.rate == pytest.approx(0.85 / 1.10)
    assert len(used.tried) == 2


def test_fx_rate_uses_a_licensed_fix_only_when_picked_and_held():
    wmr = _fx_rate(None, "USD", "EUR", ON, book(FxChoice(source="WMR")))
    assert wmr.source == "WMR" and wmr.rate == pytest.approx(1 / 1.0950)
    missing = _fx_rate(None, "USD", "EUR", ON, book(FxChoice(source="BFIX")))
    assert missing.rate is None and missing.apply(100.0) is None
    assert missing.missing == "no Bloomberg BFIX 4pm London for USD on or before 2027-01-20 is held"


def test_fx_rate_entered_by_hand_is_said_so_and_covers_its_currency_only():
    choice = FxChoice(source="manual", rate=1.20, rate_currency="USD")
    used = _fx_rate(None, "USD", "EUR", ON, book(choice))
    assert used.rate == pytest.approx(1 / 1.20) and used.entered
    assert used.tried == ("rate entered by hand (USD)",)
    other = _fx_rate(None, "GBP", "EUR", ON, book(choice))
    assert other.rate is None
    assert other.missing == "the rate entered by hand is for USD, not GBP"


def test_fx_rate_same_currency_and_no_rows():
    assert _fx_rate(None, "EUR", "EUR", ON, book()).rate == 1.0
    none = _fx_rate(None, "USD", "EUR", ON, book(rows=[]))
    assert none.rate is None and "no ECB euro reference rate" in none.missing


def test_fx_rate_falls_back_to_the_demo_rate_only_when_demo_is_allowed():
    rows = [_row("DEMO_Sim", "EURUSD", 1.05, "2027-01-19")]
    assert _fx_rate(None, "USD", "EUR", ON, book(rows=rows)).rate is None
    used = _fx_rate(None, "USD", "EUR", ON, book(rows=rows, demo=True))
    assert used.simulated and used.source == "DEMO_Sim"
    assert "(simulated demo rate)" in used.text()


def test_an_fx_choice_is_checked():
    with pytest.raises(FxChoiceError):
        FxChoice(source="manual")
    with pytest.raises(FxChoiceError):
        FxChoice(source="XYZ")
    with pytest.raises(FxChoiceError):
        FxChoice(reporting_currency="JPY")
    assert FxChoice().as_dict()["default"] is True
    assert FxChoice(source="WMR").as_dict()["fixing"] == "WMR_1600_LDN"


# ------------------------------------------------------------------------ demurrage terms


def voyage(**values):
    base = {
        "demurrage_rate_per_day": None,
        "demurrage_currency": None,
        "demurrage_terms": None,
        "demurrage_eur_per_day": None,
        "laytime_hours": None,
        "source_reference": "desk",
    }
    return SimpleNamespace(**{**base, **values})


NOTICE = SimpleNamespace(
    demurrage_rate_per_day=80_000.0,
    demurrage_currency="usd",
    demurrage_terms="pro rata per hour",
    laytime_hours=30.0,
)
MSPA = {"master_contract_id": "mspa-1", "demurrage_usd_per_day": 60_000.0, "laytime_hours": 40}


def test_the_confirmation_notice_wins_over_the_voyage_terms_and_the_master_agreement():
    terms = demurrage_terms(voyage(demurrage_eur_per_day=70_000.0), ("cn-1", NOTICE), MSPA)
    assert (terms["rate_per_day"], terms["currency"], terms["source"]) == (
        80_000.0,
        "USD",
        "confirmation notice cn-1",
    )
    assert terms["terms"] == "pro rata per hour"
    assert (terms["laytime_hours"], terms["laytime_source"]) == (30.0, "confirmation notice cn-1")


def test_the_voyage_terms_in_their_currency_then_in_eur_then_the_master_agreement():
    held = voyage(demurrage_rate_per_day=77_000.0, demurrage_currency="USD", laytime_hours=36.0)
    terms = demurrage_terms(held, None, MSPA)
    assert (terms["rate_per_day"], terms["currency"]) == (77_000.0, "USD")
    assert terms["laytime_source"] == "voyage terms"
    legacy = demurrage_terms(voyage(demurrage_eur_per_day=70_000.0), None, MSPA)
    assert (legacy["rate_per_day"], legacy["currency"]) == (70_000.0, "EUR")
    assert legacy["laytime_source"] == "master agreement mspa-1"
    master = demurrage_terms(None, None, MSPA)
    assert (master["currency"], master["source"]) == ("USD", "master agreement mspa-1")
    nothing = demurrage_terms(None, None, None)
    assert nothing["rate_per_day"] is None
    assert nothing["laytime_source"] == "desk standard 36 h (none recorded)"


def test_convert_shows_the_original_currency_the_rate_its_source_and_date():
    terms = demurrage_terms(None, ("cn-1", NOTICE), None)
    block = convert(terms, book(), vessel="ZEE-1")
    assert (block["rate_per_day"], block["currency"]) == (80_000.0, "USD")
    assert block["eur_per_day"] == round(80_000 / 1.10, 2)
    assert (block["fx"]["source"], block["fx"]["rate_date"]) == ("ECB", "2027-01-19")
    assert block["note"].startswith("80,000 USD/day from confirmation notice cn-1, at ECB")
    paid = amounts(block, -block["eur_per_day"] / 2)
    assert (paid["amount_original"], paid["currency"], paid["excess_days"]) == (
        -40_000.0,
        "USD",
        -0.5,
    )


def test_convert_without_a_rate_warns_and_costs_boil_off_only():
    terms = demurrage_terms(None, ("cn-1", NOTICE), None)
    block = convert(terms, book(rows=[]), vessel="ZEE-1")
    assert block["eur_per_day"] is None
    assert "is not converted" in block["warning"] and "boil-off only" in block["warning"]
    empty = convert(demurrage_terms(None, None, None), book(), vessel="ZEE-1")
    assert "no demurrage rate held" in empty["warning"]
    assert amounts(empty, -1_000.0) is None


def test_reporting_shows_eur_figures_in_the_viewers_currency_at_the_same_fix():
    assert reporting(book(), {"pnl": -20_000.0})["figures"] is None
    usd = reporting(book(FxChoice(reporting_currency="USD")), {"pnl": -20_000.0})
    assert usd["figures"] == {"pnl": -22_000.0} and usd["fx"]["source"] == "ECB"
    gbp = reporting(book(FxChoice(reporting_currency="GBP"), rows=[]), {"pnl": -1.0})
    assert gbp["figures"] is None and gbp["warning"].startswith("not shown in GBP")
