"""Black-76 pricing, implied volatility, smile metrics and option source precedence."""

from __future__ import annotations

import math
from datetime import date

import pytest

from eurogas_nexus.domain.market.options import (
    CALL,
    FUTURES_STYLE,
    PREMIUM_STYLE,
    PUT,
    SmileQuote,
    black76_price,
    choose_option_source,
    discount_factor,
    forward_delta,
    ice_endex_ttf_monthly_expiry,
    implied_underlying_from_parity,
    implied_vol,
    option_source_tier,
    smile_metrics,
)


def test_hull_futures_option_example() -> None:
    """Hull, Options, Futures and Other Derivatives: F=K=20, r=9 %, T=4 months, vol 25 %.

    d1 = 0.5 * 0.25 * sqrt(1/3) = 0.072169, N(d1) = 0.528766, N(d2) = 0.471234,
    c = exp(-0.03) * 20 * (0.528766 - 0.471234) = 1.1166, and p = c at the money.
    """

    df = math.exp(-0.09 * 4 / 12)
    call = black76_price(CALL, 20.0, 20.0, 0.25, 4 / 12, df)
    put = black76_price(PUT, 20.0, 20.0, 0.25, 4 / 12, df)
    assert call == pytest.approx(1.1166, abs=5e-5)
    assert put == pytest.approx(call, abs=1e-12)


def test_atm_closed_form_without_discounting() -> None:
    # Futures-style ATM: c = F (2 N(sigma sqrt(T) / 2) - 1); F=100, vol 20 %, T=1:
    # N(0.1) = 0.5398278, c = 100 * 0.0796556 = 7.96557.
    assert black76_price(CALL, 100.0, 100.0, 0.2, 1.0) == pytest.approx(7.96557, abs=1e-5)


def test_put_call_parity_holds() -> None:
    forward, strike, tenor, df = 31.7, 34.0, 0.2, 0.99
    call = black76_price(CALL, forward, strike, 0.55, tenor, df)
    put = black76_price(PUT, forward, strike, 0.55, tenor, df)
    assert call - put == pytest.approx(df * (forward - strike), abs=1e-12)


@pytest.mark.parametrize(
    ("option_type", "strike", "vol", "tenor", "df"),
    [
        (CALL, 31.0, 0.45, 0.08, 1.0),
        (PUT, 27.5, 0.62, 0.08, 1.0),
        (CALL, 45.0, 1.8, 0.5, 1.0),  # a 2022-style 180 % volatility
        (PUT, 30.0, 0.05, 1.5, math.exp(-0.03 * 1.5)),
        (CALL, 29.0, 0.30, 0.02, 1.0),  # in the money, a week to expiry
    ],
)
def test_implied_vol_round_trips(option_type, strike, vol, tenor, df) -> None:
    price = black76_price(option_type, 31.4, strike, vol, tenor, df)
    solved = implied_vol(option_type, price, 31.4, strike, tenor, df)
    assert solved.reason is None
    assert solved.vol == pytest.approx(vol, abs=1e-7)


def test_hand_computed_implied_vol() -> None:
    # F=K=100, T=1, futures-style: the price 7.96557 is vol 20 % exactly (closed form above).
    assert implied_vol(CALL, 7.965567455, 100.0, 100.0, 1.0).vol == pytest.approx(0.2, abs=1e-8)


def test_prices_outside_no_arbitrage_bounds_have_no_vol() -> None:
    assert implied_vol(CALL, 9.9, 30.0, 20.0, 0.1).reason == "below_intrinsic"
    assert implied_vol(CALL, 10.0, 30.0, 20.0, 0.1).reason == "at_intrinsic"
    assert implied_vol(PUT, 0.0, 30.0, 20.0, 0.1).reason == "at_intrinsic"
    assert implied_vol(CALL, 30.0, 30.0, 20.0, 0.1).reason == "above_upper_bound"
    assert implied_vol(CALL, 1.0, 30.0, 30.0, 0.0).reason == "expired"
    assert implied_vol("X", 1.0, 30.0, 30.0, 0.1).reason == "bad_input"


def test_discount_factor_by_premium_style() -> None:
    assert discount_factor(FUTURES_STYLE, None, 0.5) == 1.0
    assert discount_factor(PREMIUM_STYLE, 2.0, 0.5) == pytest.approx(math.exp(-0.01))
    with pytest.raises(ValueError):
        discount_factor(PREMIUM_STYLE, None, 0.5)


def test_parity_implied_underlying_is_the_median() -> None:
    # Three strikes implying 31.0, 31.1 and 40.0 (an outlier): the median is 31.1.
    pairs = [(30.0, 1.6, 0.6), (31.0, 1.0, 0.9), (32.0, 8.5, 0.5)]
    assert implied_underlying_from_parity(pairs) == pytest.approx(31.1)
    assert implied_underlying_from_parity([]) is None


def test_ice_endex_ttf_monthly_expiry_rule() -> None:
    # Jan-27: 1 Jan 2027 less 5 days is Sun 27 Dec 2026 -> Fri 25 Dec, and with that day listed
    # as a holiday -> Thu 24 Dec.
    assert ice_endex_ttf_monthly_expiry(date(2027, 1, 1)) == date(2026, 12, 25)
    assert ice_endex_ttf_monthly_expiry(date(2027, 1, 1), holidays=[date(2026, 12, 25)]) == date(
        2026, 12, 24
    )
    # Dec-26: Wed 26 Nov 2026 is a business day; on the future's expiry it moves back one day.
    assert ice_endex_ttf_monthly_expiry(date(2026, 12, 1)) == date(2026, 11, 26)
    assert ice_endex_ttf_monthly_expiry(
        date(2026, 12, 1), futures_expiry=date(2026, 11, 26)
    ) == date(2026, 11, 25)


def _flat_smile(forward: float, tenor: float, vol_at) -> list[SmileQuote]:
    quotes = []
    for step in range(-20, 21):
        strike = forward + step * 0.5
        vol = vol_at(strike)
        quotes.append(SmileQuote(strike, CALL, vol, 100.0))
        quotes.append(SmileQuote(strike, PUT, vol, 50.0))
    return quotes


def test_flat_smile_has_no_skew_and_no_curvature() -> None:
    metrics = smile_metrics(_flat_smile(30.0, 0.25, lambda _k: 0.5), 30.0, 0.25)
    assert metrics.atm_vol == pytest.approx(0.5)
    assert metrics.risk_reversal_25d == pytest.approx(0.0, abs=1e-12)
    assert metrics.butterfly_25d == pytest.approx(0.0, abs=1e-12)
    assert metrics.put_call_oi_ratio == pytest.approx(0.5)


def test_linear_skew_gives_hand_computed_risk_reversal() -> None:
    """vol(K) = 0.40 + 0.02 (K - F): an upside skew of 2 vol points per EUR/MWh.

    The 25-delta strikes solve N(d1) = 0.25 and 0.75 on this smile. The expected RR and BF
    are recomputed independently on the continuous smile by bisection; the listed strikes
    (0.50 apart) only add linear-interpolation error. BF is positive although the smile is
    linear in strike: the 25-delta call sits further from F than the 25-delta put because
    its volatility is higher.
    """

    forward, tenor = 30.0, 0.25

    def vol_at(strike: float) -> float:
        return 0.40 + 0.02 * (strike - forward)

    metrics = smile_metrics(_flat_smile(forward, tenor, vol_at), forward, tenor)
    assert metrics.atm_vol == pytest.approx(0.40)

    # Independent check: find the 25-delta strikes on the continuous smile by bisection.
    def strike_at(target: float) -> float:
        low, high = 10.0, 60.0
        for _ in range(200):
            mid = 0.5 * (low + high)
            if forward_delta(CALL, forward, mid, vol_at(mid), tenor) > target:
                low = mid
            else:
                high = mid
        return 0.5 * (low + high)

    call_vol, put_vol = vol_at(strike_at(0.25)), vol_at(strike_at(0.75))
    assert metrics.call_25d_vol == pytest.approx(call_vol, abs=2e-3)
    assert metrics.put_25d_vol == pytest.approx(put_vol, abs=2e-3)
    assert metrics.risk_reversal_25d == pytest.approx(call_vol - put_vol, abs=3e-3)
    assert metrics.butterfly_25d == pytest.approx((call_vol + put_vol) / 2 - 0.40, abs=3e-3)
    assert metrics.risk_reversal_25d > 0.15 and metrics.butterfly_25d > 0


def test_metrics_need_strikes_that_reach_25_delta() -> None:
    quotes = [SmileQuote(k, CALL, 0.5, None) for k in (29.5, 30.0, 30.5)]
    metrics = smile_metrics(quotes, 30.0, 0.25)
    assert metrics.atm_vol == pytest.approx(0.5)
    assert metrics.risk_reversal_25d is None and metrics.butterfly_25d is None
    assert metrics.reasons["call_25d"] == "strikes_do_not_reach_25_delta"
    assert metrics.reasons["put_call_oi_ratio"] == "open_interest_not_published"
    below = smile_metrics([SmileQuote(25.0, PUT, 0.5, 1.0)], 30.0, 0.25)
    assert below.atm_vol is None
    assert below.reasons["atm"] == "strikes_do_not_bracket_the_underlying"


def test_source_precedence_exchange_then_vendor_then_simulated() -> None:
    assert option_source_tier("ICE_ENDEX") < option_source_tier("Argus")
    assert option_source_tier("Argus") < option_source_tier("ICE_ENDEX_Sim")
    assert option_source_tier("ICE_ENDEX_Sim") < option_source_tier("Unknown")
    assert choose_option_source({"ICE_ENDEX_Sim": 50, "Platts": 10, "EEX": 4}) == "EEX"
    assert choose_option_source({"ICE_ENDEX_Sim": 50, "Platts": 10}) == "Platts"
    assert choose_option_source({"ICE_ENDEX_Sim": 50}) == "ICE_ENDEX_Sim"
    # Same tier: the fuller smile, then the name, never row order.
    assert choose_option_source({"ICE_ENDEX": 30, "EEX": 40}) == "EEX"
    assert choose_option_source({"ICE_ENDEX": 40, "EEX": 40}) == "EEX"
    assert choose_option_source({}) is None


def test_the_open_interest_ratio_is_withheld_when_a_strike_has_none() -> None:
    quotes = [
        SmileQuote(30.0, CALL, 0.5, 100.0),
        SmileQuote(31.0, CALL, 0.5, None),
        SmileQuote(30.0, PUT, 0.5, 50.0),
        SmileQuote(29.0, PUT, 0.5, 50.0),
    ]
    metrics = smile_metrics(quotes, 30.0, 0.25)
    assert metrics.put_call_oi_ratio is None
    assert metrics.reasons["put_call_oi_ratio"] == "open_interest_incomplete"
