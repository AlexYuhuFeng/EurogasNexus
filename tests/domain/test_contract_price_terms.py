"""Contract price formulas: golden cases of evaluation, words, missing indices and units."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from eurogas_nexus.domain.contracts.price_terms import (
    IndexPoint,
    PriceTerms,
    averaging_window,
    evaluate,
    index_from_label,
)

JAN = (date(2027, 1, 1), date(2027, 1, 31))


def held(table):
    """A lookup over ``{(index, first, last): IndexPoint}`` that records what was asked."""

    asked = []

    def lookup(index, first, last):
        asked.append((index.index, first, last))
        return table.get((index.index, first, last))

    lookup.asked = asked
    return lookup


def test_fixed_price_needs_no_index_and_is_contract_class():
    terms = PriceTerms(basis="fixed", unit="EUR/MWh", fixed_price=31.5)
    result = evaluate(terms, *JAN, held({}))
    assert (result.value, result.unit, result.input_class) == (31.5, "EUR/MWh", "contract")
    assert result.words == "fixed 31.5 EUR/MWh"


def test_ttf_month_ahead_averaged_over_the_month_before_plus_premium():
    terms = PriceTerms.model_validate(
        {
            "basis": "index",
            "unit": "EUR/MWh",
            "index": {"index": "TTF", "product": "month_ahead", "publication": "ICIS Heren"},
            "premium": 0.25,
        }
    )
    window = (date(2026, 12, 1), date(2026, 12, 31))
    lookup = held({("TTF", *window): IndexPoint(36.10, "EUR/MWh", "settlement", "obs:ttf-dec")})
    result = evaluate(terms, *JAN, lookup)
    assert result.value == pytest.approx(36.35)
    assert result.input_class == "settlement"
    assert result.inputs[0]["window"] == ["2026-12-01", "2026-12-31"]
    assert result.words == (
        "TTF month-ahead (ICIS Heren) averaged over the month before delivery + 0.25 EUR/MWh"
    )


def test_nbp_day_ahead_less_a_discount_in_pence_per_therm():
    terms = PriceTerms.model_validate(
        {
            "basis": "index",
            "unit": "GBp/th",
            "index": {"index": "NBP", "product": "day_ahead", "averaging": "delivery_day"},
            "premium": -0.4,
        }
    )
    # The store holds NBP per MWh: 28.83 GBP/MWh is 84.50 p/th (units authority, exact).
    lookup = held({("NBP", *JAN): IndexPoint(28.832596800, "GBP/MWh", "simulated", "obs:nbp")})
    result = evaluate(terms, *JAN, lookup)
    assert result.value == pytest.approx(84.10, abs=1e-6)
    assert result.unit == "GBp/th"
    assert result.input_class == "simulated"
    assert "− 0.4 p/th" in result.words


def test_lng_slope_on_henry_hub_with_cap_and_floor_reads_the_pricing_month():
    terms = PriceTerms.model_validate(
        {
            "basis": "formula",
            "unit": "USD/MMBtu",
            "components": [
                {
                    "index": {
                        "index": "HH",
                        "product": "pricing_month",
                        "averaging": "pricing_month",
                    },
                    "weight": 1.15,
                }
            ],
            "constant": 2.5,
            "cap": 8.0,
            "floor": 4.0,
            "pricing_month": "2026-12",
        }
    )
    window = (date(2026, 12, 1), date(2026, 12, 31))
    result = evaluate(
        terms, *JAN, held({("HH", *window): IndexPoint(3.4, "USD/MMBtu", "settlement", "eia")})
    )
    assert result.value == pytest.approx(1.15 * 3.4 + 2.5)
    high = evaluate(
        terms, *JAN, held({("HH", *window): IndexPoint(6.0, "USD/MMBtu", "settlement", "eia")})
    )
    assert high.value == 8.0 and high.notes == ["capped: 9.4000 > 8"]
    low = evaluate(
        terms, *JAN, held({("HH", *window): IndexPoint(1.0, "USD/MMBtu", "settlement", "eia")})
    )
    assert low.value == 4.0


def test_an_index_not_held_is_named_never_guessed():
    terms = PriceTerms.model_validate(
        {
            "basis": "formula",
            "unit": "USD/MMBtu",
            "components": [{"index": {"index": "BRENT", "product": "month_ahead"}, "weight": 0.12}],
            "constant": 0.5,
        }
    )
    result = evaluate(terms, *JAN, held({}))
    assert result.value is None and result.input_class == "missing"
    assert result.missing[0].startswith(
        "Brent month-ahead averaged over the month before delivery: index not held"
    )


def test_another_currency_is_refused_until_the_fx_rule_is_modelled():
    terms = PriceTerms.model_validate(
        {"basis": "index", "unit": "GBP/MWh", "index": {"index": "TTF"}, "premium": 0}
    )
    window = (date(2026, 12, 1), date(2026, 12, 31))
    result = evaluate(
        terms, *JAN, held({("TTF", *window): IndexPoint(36.0, "EUR/MWh", "settlement", "x")})
    )
    assert result.value is None
    assert "FX rule is not modelled yet" in result.missing[0]


def test_a_weighted_basket_and_last_n_trading_days():
    terms = PriceTerms.model_validate(
        {
            "basis": "formula",
            "unit": "EUR/MWh",
            "components": [
                {
                    "index": {"index": "TTF", "averaging": "last_n_trading_days", "n_days": 5},
                    "weight": 0.5,
                },
                {"index": {"index": "THE", "averaging": "delivery_month"}, "weight": 0.5},
            ],
            "constant": 0.1,
            "rounding_dp": 2,
        }
    )
    ttf_window = averaging_window(terms.components[0].index, *JAN, None)
    assert ttf_window[1] == date(2026, 12, 31)
    lookup = held(
        {
            ("TTF", *ttf_window): IndexPoint(36.0, "EUR/MWh", "settlement", "a"),
            ("THE", *JAN): IndexPoint(37.0, "EUR/MWh", "firm_mark", "b"),
        }
    )
    result = evaluate(terms, *JAN, lookup)
    assert result.value == 36.6
    assert result.input_class == "firm_mark"


def test_terms_refuse_what_a_contract_cannot_say():
    with pytest.raises(ValidationError):
        PriceTerms(basis="fixed", unit="EUR/MWh")
    with pytest.raises(ValidationError):
        PriceTerms.model_validate({"basis": "index", "unit": "EUR/MWh", "index": {"index": "XYZ"}})
    with pytest.raises(ValidationError):
        PriceTerms(basis="fixed", unit="EUR/MWh", fixed_price=30, cap=20, floor=25)
    with pytest.raises(ValidationError):
        PriceTerms.model_validate(
            {
                "basis": "index",
                "unit": "EUR/MWh",
                "index": {"index": "TTF", "averaging": "last_n_trading_days"},
            }
        )


def test_desk_labels_become_indices():
    assert index_from_label("NBP day-ahead").averaging == "delivery_day"
    assert index_from_label("TTF month-ahead").product == "month_ahead"
    assert index_from_label("Oil-indexed") is None
