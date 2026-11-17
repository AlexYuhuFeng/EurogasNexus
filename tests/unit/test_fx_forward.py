"""Forward FX by covered interest parity (design basis 2, D.5): golden cases.

Every expected figure below is computed by hand in the test's docstring, so it can be
reproduced in a spreadsheet. Rates are illustrative (the design basis's own example), not
market values.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from eurogas_nexus.domain.market.fx_forward import (
    HORIZON_MONTHS,
    LICENSED_FORWARD_RATE_TYPE,
    METHOD_DERIVED,
    METHOD_IDENTITY,
    METHOD_LICENSED,
    METHOD_SPOT,
    Delivery,
    FxForwardError,
    FxHoldings,
    conversion_rate,
    delivery_from_bounds,
    delivery_from_period,
    tolerance_pct_for,
)
from eurogas_nexus.domain.market.products import resolve_product

SPOT_DATE = date(2026, 11, 16)
JAN_27 = Delivery(date(2027, 1, 1), date(2027, 1, 31), "month", "Jan-27")


def _holdings(
    *,
    gbp: float | None = 0.87,
    usd: float | None = 1.08,
    sonia: float | None = 3.75,
    estr: float | None = 1.90,
    sofr: float | None = 4.00,
    source: str = "ECB",
    extra_fx: tuple[dict, ...] = (),
) -> FxHoldings:
    fx = [
        {"pair": f"EUR{ccy}", "rate": rate, "rate_type": "reference",
         "value_date": SPOT_DATE.isoformat(), "source_system": source}
        for ccy, rate in (("GBP", gbp), ("USD", usd))
        if rate is not None
    ]
    fixings = [
        {"benchmark_id": bench, "value_date": SPOT_DATE.isoformat(), "rate_pct": rate,
         "source_system": admin}
        for bench, rate, admin in (("SONIA", sonia, "BOE"), ("ESTR", estr, "ECB"),
                                   ("SOFR", sofr, "NYFED"))
        if rate is not None
    ]
    return FxHoldings.from_rows([*fx, *extra_fx], fixings)


def _on(days: int) -> Delivery:
    value = SPOT_DATE + timedelta(days=days)
    return Delivery(value, value, "value_date", value.isoformat())


def test_golden_nbp_ttf_forward_eurgbp_jan27():
    """EUR/GBP forward for Jan-27, the design basis D.2/D.5 example.

    Spot S(EUR/GBP) = 0.8700 GBP per EUR (ECB, 16 Nov 2026). Value date = 15 Jan 2027
    (a month's 15th) = 60 days after spot. SONIA 3.75 % on ACT/365F, €STR 1.90 % on ACT/360:

        F = 0.87 × (1 + 0.0375 × 60/365) / (1 + 0.0190 × 60/360)
          = 0.87 × 1.0061644 / 1.0031667
          = 0.8725998  → 0.8726 to 4 dp.

    Tolerance: 60 days ≤ 3 months → 0.1 % of the rate.
    """

    rate = conversion_rate(_holdings(), "EUR", "GBP", as_of=SPOT_DATE, delivery=JAN_27)
    assert rate.method == METHOD_DERIVED
    assert rate.value_date == date(2027, 1, 15)
    assert round(rate.rate, 4) == 0.8726
    assert rate.rate == pytest.approx(0.8725998, abs=5e-8)
    assert rate.tolerance_pct == 0.1
    assert rate.input_class == "derived"
    assert rate.label == "derived (interest parity from €STR, SONIA, flat rate)"
    assert rate.compounding == "simple"


def test_golden_nbp_in_eur_per_mwh_spot_and_forward_to_3dp():
    """NBP Jan-27 78.00 p/th in EUR/MWh against TTF Jan-27 30.00 EUR/MWh (D.2 example).

    NBP in GBP/MWh = 0.78 GBP/th × 34.1214163 th/MWh = 26.6147047 GBP/MWh.
    Spot:    26.6147047 / 0.8700    = 30.592 EUR/MWh → spread NBP − TTF = +0.592.
    Forward: 26.6147047 / 0.8725998 = 30.500 EUR/MWh → spread +0.500.
    (The design text prints 30.501 because it rounds F to 0.8726 and the factor to 34.1214
    before dividing; with the authority's factor and the unrounded rate it is 30.500.)
    The 0.09 EUR/MWh between the two is why spot conversion is wrong for a forward.
    """

    from eurogas_nexus.application.market_normalisation import normalise_value

    holdings = _holdings()
    spot = normalise_value(78.0, "p/th", "EUR/MWh", holdings=holdings, as_of=SPOT_DATE)
    forward = normalise_value(
        78.0, "p/th", "EUR/MWh", holdings=holdings, as_of=SPOT_DATE, delivery=JAN_27
    )
    assert round(spot["value"], 3) == 30.592
    assert round(forward["value"], 3) == 30.500
    assert round(spot["value"] - 30.00, 3) == 0.592
    assert round(forward["value"] - 30.00, 3) == 0.500
    assert forward["normalisation"]["fx"]["method"] == METHOD_DERIVED
    assert forward["normalisation"]["fx"]["pair"] == "GBPEUR"
    assert spot["normalisation"]["fx"]["method"] == METHOD_SPOT
    # 0.1 % of 30.500 EUR/MWh
    assert forward["tolerance"]["absolute"] == pytest.approx(0.0305, abs=1e-4)
    assert spot["tolerance"]["absolute"] == 0.0


def test_day_counts_per_currency_eur_usd_act360_both_sides():
    """EUR/USD, 90 days, €STR 2.00 % and SOFR 4.00 %, both ACT/360.

        F = 1.08 × (1 + 0.04 × 90/360) / (1 + 0.02 × 90/360) = 1.08 × 1.01 / 1.005
          = 1.0853731
    """

    rate = conversion_rate(
        _holdings(estr=2.00, sofr=4.00), "EUR", "USD", as_of=SPOT_DATE, delivery=_on(90)
    )
    assert rate.rate == pytest.approx(1.0853731, abs=5e-8)
    by_ccy = {item["currency"]: item for item in rate.as_dict()["rates"]}
    assert by_ccy["EUR"]["day_count"] == "ACT/360"
    assert by_ccy["USD"]["day_count"] == "ACT/360"
    assert by_ccy["USD"]["year_fraction"] == pytest.approx(0.25)


def test_day_counts_per_currency_gbp_usd_crossed_through_eur():
    """GBP/USD crossed through EUR, 181 days; SONIA ACT/365F against SOFR ACT/360.

    S(GBP/USD) = EURUSD / EURGBP = 1.08 / 0.85 = 1.2705882.
        F = 1.2705882 × (1 + 0.043 × 181/360) / (1 + 0.040 × 181/365)
          = 1.2705882 × 1.0216194 / 1.0198356 = 1.2728107
    """

    rate = conversion_rate(
        _holdings(gbp=0.85, sonia=4.00, sofr=4.30), "GBP", "USD", as_of=SPOT_DATE,
        delivery=_on(181),
    )
    assert rate.spot is not None and rate.spot.rate == pytest.approx(1.2705882, abs=5e-8)
    assert rate.as_dict()["spot"]["crossed_via"] == "EUR"
    assert rate.rate == pytest.approx(1.2728107, abs=5e-8)
    by_ccy = {item["currency"]: item for item in rate.as_dict()["rates"]}
    assert by_ccy["GBP"]["day_count"] == "ACT/365F"
    assert by_ccy["GBP"]["year_fraction"] == pytest.approx(181 / 365)
    assert by_ccy["USD"]["year_fraction"] == pytest.approx(181 / 360)
    # 181 days: over 3 months, within 12 → 0.3 %
    assert rate.tolerance_pct == 0.3


def test_beyond_one_year_compounds_annually():
    """500 days, EUR/GBP: annual compounding beyond one year.

        F = 0.87 × 1.0375^(500/365) / 1.019^(500/360) = 0.8913900
    Tolerance beyond 12 months: 1 %.
    """

    rate = conversion_rate(_holdings(), "EUR", "GBP", as_of=SPOT_DATE, delivery=_on(500))
    assert rate.compounding == "annual"
    assert rate.rate == pytest.approx(0.8913900, abs=5e-8)
    assert rate.tolerance_pct == 1.0


def test_refused_beyond_24_months_without_licensed_forwards():
    """Cal-29 has its middle gas day on 2 Jul 2029, more than 24 months after 16 Nov 2026."""

    cal29 = delivery_from_period(resolve_product("Cal-29", SPOT_DATE))
    with pytest.raises(FxForwardError) as refused:
        conversion_rate(_holdings(), "EUR", "GBP", as_of=SPOT_DATE, delivery=cal29)
    assert refused.value.code == "beyond_horizon"
    assert "24 months" in str(refused.value)
    # Exactly at the horizon (16 Nov 2028) a derived forward is still given.
    at_limit = Delivery(date(2028, 11, 16), date(2028, 11, 16), "value_date", "2028-11-16")
    assert conversion_rate(_holdings(), "EUR", "GBP", as_of=SPOT_DATE, delivery=at_limit).rate
    assert HORIZON_MONTHS == 24


def test_licensed_forward_overrides_derived_and_reaches_beyond_the_horizon():
    """A licensed outright EUR/GBP forward of 0.8800 for 15 Jan 2027 replaces the derived 0.8726.

    It is labelled "sourced (<vendor>)", carries no tolerance, and a licensed Cal-29 forward
    converts where a derived one is refused.
    """

    licensed = (
        {"pair": "EURGBP", "rate": 0.8800, "rate_type": LICENSED_FORWARD_RATE_TYPE,
         "value_date": "2027-01-15", "source_system": "WMR",
         "observed_at_utc": "2026-11-16T16:00:00+00:00"},
        {"pair": "GBPEUR", "rate": 1 / 0.9000, "rate_type": LICENSED_FORWARD_RATE_TYPE,
         "value_date": "2029-07-01", "source_system": "WMR",
         "observed_at_utc": "2026-11-16T16:00:00+00:00"},
    )
    holdings = _holdings(extra_fx=licensed)
    rate = conversion_rate(holdings, "EUR", "GBP", as_of=SPOT_DATE, delivery=JAN_27)
    assert rate.method == METHOD_LICENSED
    assert rate.rate == 0.8800
    assert rate.label == "sourced (WMR)"
    assert rate.tolerance_pct == 0.0
    assert rate.input_class == "sourced"
    cal29 = delivery_from_period(resolve_product("Cal-29", SPOT_DATE))
    far = conversion_rate(holdings, "EUR", "GBP", as_of=SPOT_DATE, delivery=cal29)
    assert far.method == METHOD_LICENSED
    assert far.rate == pytest.approx(0.9000)
    # A licensed forward outside the period is not used: Feb-27 is still derived.
    feb = delivery_from_period(resolve_product("Feb-27", SPOT_DATE))
    assert conversion_rate(holdings, "EUR", "GBP", as_of=SPOT_DATE, delivery=feb).method == (
        METHOD_DERIVED
    )


def test_metadata_on_every_result():
    """Each method names its rate, date, inputs and value date (D.5 step 7)."""

    holdings = _holdings()
    results = [
        conversion_rate(holdings, "EUR", "GBP", as_of=SPOT_DATE, delivery=JAN_27),
        conversion_rate(holdings, "EUR", "GBP", as_of=SPOT_DATE),
        conversion_rate(
            holdings, "EUR", "GBP", as_of=SPOT_DATE,
            delivery=delivery_from_period(resolve_product("DA", SPOT_DATE)),
        ),
        conversion_rate(holdings, "EUR", "EUR", as_of=SPOT_DATE, delivery=JAN_27),
    ]
    methods = [item.method for item in results]
    assert methods == [METHOD_DERIVED, METHOD_SPOT, METHOD_SPOT, METHOD_IDENTITY]
    for item in results:
        payload = item.as_dict()
        for key in ("pair", "rate", "method", "label", "input_class", "value_date", "tolerance",
                    "spot", "rates", "limitations", "simulated"):
            assert key in payload
    derived = results[0].as_dict()
    assert derived["spot"]["value_date"] == "2026-11-16"
    assert derived["spot"]["inputs"][0]["source_system"] == "ECB"
    assert {r["benchmark"] for r in derived["rates"]} == {"SONIA", "ESTR"}
    assert all(r["fixing_date"] == "2026-11-16" for r in derived["rates"])
    assert derived["days"] == 60
    assert results[1].as_dict()["spot"]["rate"] == 0.87


def test_refusals_name_the_missing_rate():
    with pytest.raises(FxForwardError, match="not convertible: no EURGBP rate held"):
        conversion_rate(_holdings(gbp=None), "GBP", "EUR", as_of=SPOT_DATE)
    with pytest.raises(FxForwardError, match="no SONIA fixing held") as no_sonia:
        conversion_rate(_holdings(sonia=None), "EUR", "GBP", as_of=SPOT_DATE, delivery=JAN_27)
    assert no_sonia.value.code == "no_benchmark_rate"
    cny = FxHoldings.from_rows(
        [{"pair": "EURCNY", "rate": 7.8, "rate_type": "reference",
          "value_date": SPOT_DATE.isoformat(), "source_system": "ECB"}]
    )
    with pytest.raises(FxForwardError, match="no benchmark rate for CNY"):
        conversion_rate(cny, "EUR", "CNY", as_of=SPOT_DATE, delivery=JAN_27)
    # Spot for CNY still converts (an ECB reference rate is held).
    assert conversion_rate(cny, "EUR", "CNY", as_of=SPOT_DATE).rate == 7.8
    # A rate older than the staleness limit is not used.
    with pytest.raises(FxForwardError):
        conversion_rate(_holdings(), "EUR", "GBP", as_of=SPOT_DATE + timedelta(days=10))


def test_simulated_inputs_make_the_rate_simulated():
    rate = conversion_rate(
        _holdings(source="DEMO_Sim"), "EUR", "GBP", as_of=SPOT_DATE, delivery=JAN_27
    )
    assert rate.simulated
    assert rate.input_class == "simulated"


def test_a_real_reference_rate_beats_a_simulated_one_on_the_same_day():
    sim = {"pair": "EURGBP", "rate": 0.853, "rate_type": "reference",
           "value_date": SPOT_DATE.isoformat(), "source_system": "DEMO_Sim"}
    holdings = _holdings(extra_fx=(sim,))
    assert conversion_rate(holdings, "EUR", "GBP", as_of=SPOT_DATE).rate == 0.87


def test_tolerance_steps_and_value_dates():
    assert tolerance_pct_for(92) == 0.1
    assert tolerance_pct_for(93) == 0.3
    assert tolerance_pct_for(366) == 0.3
    assert tolerance_pct_for(367) == 1.0
    q1 = delivery_from_period(resolve_product("Q1-27", SPOT_DATE))
    assert q1.value_date() == date(2027, 2, 14)  # 1 Jan + 89 days // 2 = 44 days
    month = delivery_from_bounds(date(2027, 2, 1), date(2027, 3, 1))
    assert (month.kind, month.label, month.value_date()) == ("month", "Feb-27", date(2027, 2, 15))
    assert delivery_from_bounds(date(2026, 11, 17), date(2026, 11, 18)).prompt


def test_desk_quote_turns_the_pair_the_way_a_desk_reads_it():
    """GBP→EUR at 1/0.8726 is shown as EUR/GBP 0.8726; GBP/USD keeps GBP as the base."""

    rate = conversion_rate(_holdings(), "GBP", "EUR", as_of=SPOT_DATE, delivery=JAN_27)
    quote = rate.as_dict()["desk_quote"]
    assert quote["pair"] == "EUR/GBP"
    assert round(quote["rate"], 4) == 0.8726
    assert quote["spot_rate"] == pytest.approx(0.87)
    usd = conversion_rate(_holdings(), "USD", "GBP", as_of=SPOT_DATE).as_dict()["desk_quote"]
    assert usd["pair"] == "GBP/USD"
