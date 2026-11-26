"""European options on gas futures: Black-76 pricing, implied volatility and smile metrics.

The desk does not trade options, but exchange option settlements say how the market prices
risk: the at-the-money implied volatility, the skew between upside and downside (25-delta
risk reversal), the curvature of the smile (25-delta butterfly) and where open interest sits
(put/call ratio). This module is pure: no database, no network.

Pricing model (Black 1976, options on futures)::

    d1 = (ln(F/K) + sigma^2 T / 2) / (sigma sqrt(T)),  d2 = d1 - sigma sqrt(T)
    call = DF * (F N(d1) - K N(d2)),  put = DF * (K N(-d2) - F N(-d1))

``F`` is the underlying futures settlement, ``K`` the strike, ``T`` the year fraction
ACT/365F from the trade date to the option's expiry and ``DF`` the discount factor.

Discounting. TTF options on ICE Endex and every EEX gas option are **futures-style**: the
premium is margined daily like a future and paid only at exercise or expiry, so there is
nothing to discount and ``DF = 1`` (EEX documents its gas option settlement as Black-76
without a discount term). For a premium-paid ("equity-style") option the premium is paid
up front and ``DF = exp(-r T)``; ``r`` is the currency's overnight benchmark (EUR €STR, GBP
SONIA, USD SOFR) restated ACT/365F, used flat across the tenor. That flat overnight rate is
an approximation of the term rate, documented in ``docs/data/GAS_OPTION_SETTLEMENTS.md``;
for the short tenors of gas options its effect on implied volatility is a fraction of a
volatility point.

Smile conventions:

- ATM is at-the-money forward (``K = F``), the strike interpolated linearly between the two
  listed strikes around ``F``; no extrapolation.
- Delta is the undiscounted forward delta ``N(d1)`` for a call (``N(d1) - 1`` for a put),
  the usual convention for commodity volatility surfaces. Each listed strike is placed on
  the smile with the out-of-the-money option's volatility (put below ``F``, call above),
  and the 25-delta call (call delta 0.25) and 25-delta put (put delta -0.25, call delta
  0.75) volatilities are interpolated linearly in delta between listed strikes. When the
  listed strikes do not reach 25 delta on a side the metric is ``None`` with a reason.
- ``RR25 = vol(25D call) - vol(25D put)`` and ``BF25 = (vol(25D call) + vol(25D put)) / 2
  - vol(ATM)``, in volatility points.
- The put/call ratio is total put open interest over total call open interest for one
  contract and trade date; ``None`` when call open interest is zero or not published.

本模块为期货期权（欧式）Black-76 定价、隐含波动率求解与微笑指标（ATM、25Δ 风险逆转、
蝶式价差、认沽/认购持仓比）。期货式保证金期权（ICE Endex TTF、EEX 全部天然气期权）不贴现。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

#: Volatility bounds the solver searches (decimal per year): 0.1 % to 1000 %.
MIN_VOL = 0.001
MAX_VOL = 10.0
#: Price tolerance of the solver, in the option's price unit.
PRICE_TOLERANCE = 1e-10
MAX_ITERATIONS = 200

FUTURES_STYLE = "futures_style"
PREMIUM_STYLE = "premium"
PREMIUM_STYLES = (FUTURES_STYLE, PREMIUM_STYLE)

CALL = "C"
PUT = "P"


class OptionMathError(ValueError):
    """Inputs outside the model's domain (non-positive price, strike or tenor)."""


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution."""

    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def year_fraction(trade_date: date, expiry_date: date) -> float:
    """ACT/365F year fraction from the settlement (end of trade date) to expiry."""

    return (expiry_date - trade_date).days / 365.0


def discount_factor(style: str, rate_act365_pct: float | None, tenor_years: float) -> float:
    """``1`` for a futures-style option, ``exp(-r T)`` for a premium-paid option.

    Raises:
        OptionMathError: Unknown style, or a premium-paid option without a rate.
    """

    if style == FUTURES_STYLE:
        return 1.0
    if style != PREMIUM_STYLE:
        raise OptionMathError(f"unknown premium style {style!r}")
    if rate_act365_pct is None:
        raise OptionMathError("a premium-paid option needs a discount rate")
    return math.exp(-rate_act365_pct / 100.0 * tenor_years)


def _d1_d2(forward: float, strike: float, vol: float, tenor: float) -> tuple[float, float]:
    spread = vol * math.sqrt(tenor)
    d1 = (math.log(forward / strike) + 0.5 * spread * spread) / spread
    return d1, d1 - spread


def _check(forward: float, strike: float, tenor: float) -> None:
    if not (forward > 0 and math.isfinite(forward)):
        raise OptionMathError("underlying price must be positive")
    if not (strike > 0 and math.isfinite(strike)):
        raise OptionMathError("strike must be positive")
    if not (tenor > 0 and math.isfinite(tenor)):
        raise OptionMathError("time to expiry must be positive")


def black76_price(
    option_type: str,
    forward: float,
    strike: float,
    vol: float,
    tenor: float,
    df: float = 1.0,
) -> float:
    """Black-76 premium of a European call (``C``) or put (``P``) on a future."""

    _check(forward, strike, tenor)
    if vol <= 0:
        intrinsic = forward - strike if option_type == CALL else strike - forward
        return df * max(intrinsic, 0.0)
    d1, d2 = _d1_d2(forward, strike, vol, tenor)
    if option_type == CALL:
        return df * (forward * norm_cdf(d1) - strike * norm_cdf(d2))
    if option_type == PUT:
        return df * (strike * norm_cdf(-d2) - forward * norm_cdf(-d1))
    raise OptionMathError(f"option type must be C or P, not {option_type!r}")


def black76_vega(forward: float, strike: float, vol: float, tenor: float, df: float = 1.0) -> float:
    """Sensitivity of the premium to volatility (per 1.00 of vol)."""

    _check(forward, strike, tenor)
    d1, _ = _d1_d2(forward, strike, vol, tenor)
    return df * forward * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) * math.sqrt(tenor)


def forward_delta(
    option_type: str, forward: float, strike: float, vol: float, tenor: float
) -> float:
    """Undiscounted forward delta: ``N(d1)`` for a call, ``N(d1) - 1`` for a put."""

    _check(forward, strike, tenor)
    d1, _ = _d1_d2(forward, strike, vol, tenor)
    call_delta = norm_cdf(d1)
    return call_delta if option_type == CALL else call_delta - 1.0


@dataclass(frozen=True)
class ImpliedVol:
    """A solved volatility, or why none exists (``reason``)."""

    vol: float | None
    reason: str | None = None
    iterations: int = 0


def implied_vol(
    option_type: str,
    price: float,
    forward: float,
    strike: float,
    tenor: float,
    df: float = 1.0,
) -> ImpliedVol:
    """Black-76 implied volatility of one settlement price.

    Newton steps safeguarded by a bisection bracket on ``[MIN_VOL, MAX_VOL]``, so the solver
    always converges when a solution exists. A price outside the no-arbitrage bounds
    (below discounted intrinsic, at or above the discounted forward/strike) has no implied
    volatility and is reported with a reason instead of a clamped number.

    Reasons: ``expired`` (no time left), ``bad_input``, ``below_intrinsic``,
    ``at_intrinsic`` (the price carries no time value at the settlement tick),
    ``above_upper_bound``, ``vol_out_of_range``.
    """

    if option_type not in (CALL, PUT):
        return ImpliedVol(None, "bad_input")
    if tenor <= 0:
        return ImpliedVol(None, "expired")
    if not (forward > 0 and strike > 0 and price >= 0 and df > 0):
        return ImpliedVol(None, "bad_input")
    intrinsic = df * max(forward - strike if option_type == CALL else strike - forward, 0.0)
    upper = df * (forward if option_type == CALL else strike)
    tolerance = max(PRICE_TOLERANCE, 1e-12 * upper)
    if price < intrinsic - tolerance:
        return ImpliedVol(None, "below_intrinsic")
    if price <= intrinsic + tolerance:
        return ImpliedVol(None, "at_intrinsic")
    if price >= upper - tolerance:
        return ImpliedVol(None, "above_upper_bound")
    low, high = MIN_VOL, MAX_VOL
    if black76_price(option_type, forward, strike, low, tenor, df) > price:
        return ImpliedVol(None, "vol_out_of_range")
    if black76_price(option_type, forward, strike, high, tenor, df) < price:
        return ImpliedVol(None, "vol_out_of_range")
    # Brenner-Subrahmanyam start, inside the bracket.
    vol = min(max(math.sqrt(2 * math.pi / tenor) * price / (df * forward), 0.05), 3.0)
    for iteration in range(1, MAX_ITERATIONS + 1):
        diff = black76_price(option_type, forward, strike, vol, tenor, df) - price
        if abs(diff) <= tolerance:
            return ImpliedVol(vol, None, iteration)
        if diff > 0:
            high = vol
        else:
            low = vol
        vega = black76_vega(forward, strike, vol, tenor, df)
        step = vol - diff / vega if vega > 1e-14 else None
        vol = step if step is not None and low < step < high else 0.5 * (low + high)
        if high - low < 1e-12:
            return ImpliedVol(vol, None, iteration)
    return ImpliedVol(vol, None, MAX_ITERATIONS)  # pragma: no cover - bracket shrinks first


def implied_underlying_from_parity(
    pairs: Iterable[tuple[float, float, float]], df: float = 1.0
) -> float | None:
    """Futures price implied by put-call parity, ``F = K + (C - P) / DF``, median over strikes.

    ``pairs`` holds ``(strike, call_settlement, put_settlement)`` for strikes listed with both.
    Returns ``None`` without a pair or when the median is not positive.
    """

    values = sorted(strike + (call - put) / df for strike, call, put in pairs)
    if not values:
        return None
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else 0.5 * (values[middle - 1] + values[middle])
    return median if median > 0 else None


def roll_back_to_business_day(day: date, holidays: Iterable[date] = ()) -> date:
    """The day itself, or the latest earlier weekday that is not a listed holiday."""

    closed = set(holidays)
    while day.weekday() >= 5 or day in closed:
        day -= timedelta(days=1)
    return day


def ice_endex_ttf_monthly_expiry(
    delivery_start: date, *, futures_expiry: date | None = None, holidays: Iterable[date] = ()
) -> date:
    """Expiry of an ICE Endex Dutch TTF monthly option (futures-style margin).

    The contract specification: trading ceases five calendar days before the first calendar
    day of the delivery month; when that is not a UK business day, the business day before;
    when it falls on the underlying future's expiry, one business day earlier. Only weekends
    and the ``holidays`` passed in are known here, so an import that carries the exchange's
    own expiry column is preferred to this rule.
    """

    expiry = roll_back_to_business_day(delivery_start - timedelta(days=5), holidays)
    if futures_expiry is not None and expiry == futures_expiry:
        expiry = roll_back_to_business_day(expiry - timedelta(days=1), holidays)
    return expiry


# ---------------------------------------------------------------------------
# Smile metrics for one contract on one trade date
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SmileQuote:
    """One listed option of a contract on a trade date (vol decimal, or ``None``)."""

    strike: float
    option_type: str
    vol: float | None
    open_interest: float | None = None


@dataclass(frozen=True)
class SmileMetrics:
    """Derived metrics of one contract's smile (vols decimal; RR/BF in decimal vol)."""

    atm_vol: float | None
    call_25d_vol: float | None
    put_25d_vol: float | None
    risk_reversal_25d: float | None
    butterfly_25d: float | None
    put_call_oi_ratio: float | None
    strikes_used: int
    reasons: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """JSON-ready, in desk units: vol in percent, RR/BF in volatility points."""

        def pct(value: float | None) -> float | None:
            return None if value is None else round(value * 100.0, 4)

        return {
            "atm_iv_pct": pct(self.atm_vol),
            "call_25d_iv_pct": pct(self.call_25d_vol),
            "put_25d_iv_pct": pct(self.put_25d_vol),
            "rr25_vol_pts": pct(self.risk_reversal_25d),
            "bf25_vol_pts": pct(self.butterfly_25d),
            "put_call_oi_ratio": (
                None if self.put_call_oi_ratio is None else round(self.put_call_oi_ratio, 6)
            ),
            "strikes_used": self.strikes_used,
            "reasons": dict(self.reasons),
        }


def smile_points(quotes: Sequence[SmileQuote], forward: float) -> list[tuple[float, float]]:
    """``(strike, vol)`` per listed strike, taking the out-of-the-money option's volatility.

    Below ``F`` the put, above ``F`` the call; at ``F`` the mean of both. When only the
    in-the-money side solved at a strike, its volatility is used (Black-76 gives calls and
    puts at one strike the same volatility when parity holds).
    """

    by_strike: dict[float, dict[str, float]] = {}
    for quote in quotes:
        if quote.vol is not None and quote.vol > 0:
            by_strike.setdefault(quote.strike, {})[quote.option_type] = quote.vol
    points: list[tuple[float, float]] = []
    for strike in sorted(by_strike):
        vols = by_strike[strike]
        if strike < forward:
            vol = vols.get(PUT, vols.get(CALL))
        elif strike > forward:
            vol = vols.get(CALL, vols.get(PUT))
        else:
            vol = sum(vols.values()) / len(vols)
        if vol is not None:
            points.append((strike, vol))
    return points


def _interpolate(xs: Sequence[float], ys: Sequence[float], target: float) -> float | None:
    """Linear interpolation on increasing ``xs``; ``None`` outside their range."""

    for index in range(len(xs)):
        if xs[index] == target:
            return ys[index]
    for index in range(1, len(xs)):
        low, high = xs[index - 1], xs[index]
        if low < target < high:
            weight = (target - low) / (high - low)
            return ys[index - 1] + weight * (ys[index] - ys[index - 1])
    return None


def smile_metrics(quotes: Sequence[SmileQuote], forward: float, tenor: float) -> SmileMetrics:
    """ATM vol, 25-delta call and put vols, RR25, BF25 and the put/call OI ratio."""

    reasons: dict[str, str] = {}
    points = smile_points(quotes, forward) if forward > 0 and tenor > 0 else []
    atm = None
    call25 = put25 = None
    if not points:
        reasons["atm"] = "no_implied_vol"
        reasons["delta_25"] = "no_implied_vol"
    else:
        strikes = [strike for strike, _ in points]
        vols = [vol for _, vol in points]
        atm = _interpolate(strikes, vols, forward)
        if atm is None:
            reasons["atm"] = "strikes_do_not_bracket_the_underlying"
        # Call delta falls as the strike rises; interpolate in increasing delta.
        deltas = [forward_delta(CALL, forward, strike, vol, tenor) for strike, vol in points]
        ordered = sorted(zip(deltas, vols, strict=True))
        delta_axis = [delta for delta, _ in ordered]
        vol_axis = [vol for _, vol in ordered]
        if any(b <= a for a, b in zip(delta_axis, delta_axis[1:], strict=False)):
            reasons["delta_25"] = "smile_not_monotone_in_delta"
        else:
            call25 = _interpolate(delta_axis, vol_axis, 0.25)
            put25 = _interpolate(delta_axis, vol_axis, 0.75)
            if call25 is None:
                reasons["call_25d"] = "strikes_do_not_reach_25_delta"
            if put25 is None:
                reasons["put_25d"] = "strikes_do_not_reach_25_delta"
    rr = call25 - put25 if call25 is not None and put25 is not None else None
    bf = (
        (call25 + put25) / 2.0 - atm
        if call25 is not None and put25 is not None and atm is not None
        else None
    )
    call_all = [q.open_interest for q in quotes if q.option_type == CALL]
    put_all = [q.open_interest for q in quotes if q.option_type == PUT]
    call_oi = [value for value in call_all if value is not None]
    put_oi = [value for value in put_all if value is not None]
    ratio = None
    if not call_oi or not put_oi:
        reasons["put_call_oi_ratio"] = "open_interest_not_published"
    elif len(call_oi) < len(call_all) or len(put_oi) < len(put_all):
        # A total with an unpublished strike in it is unknown, not smaller.
        reasons["put_call_oi_ratio"] = "open_interest_incomplete"
    elif sum(call_oi) <= 0:
        reasons["put_call_oi_ratio"] = "no_call_open_interest"
    else:
        ratio = sum(put_oi) / sum(call_oi)
    return SmileMetrics(
        atm_vol=atm,
        call_25d_vol=call25,
        put_25d_vol=put25,
        risk_reversal_25d=rr,
        butterfly_25d=bf,
        put_call_oi_ratio=ratio,
        strikes_used=len(points),
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Source precedence
# ---------------------------------------------------------------------------

#: Precedence tiers: the exchange's own settlement, then a licensed vendor's redistribution
#: of it, then the demo simulator. Lower ranks first.
EXCHANGE_TIER = 0
VENDOR_TIER = 1
SIMULATED_TIER = 2

OPTION_EXCHANGE_SOURCES = ("ICE_ENDEX", "EEX", "CME")
OPTION_VENDOR_SOURCES = ("Argus", "Platts")


def option_source_tier(source_system: str) -> int:
    """Precedence tier of a source system (unknown sources rank after the simulator)."""

    value = (source_system or "").strip()
    if value.endswith("_Sim"):
        return SIMULATED_TIER
    if value in OPTION_EXCHANGE_SOURCES:
        return EXCHANGE_TIER
    if value in OPTION_VENDOR_SOURCES:
        return VENDOR_TIER
    return SIMULATED_TIER + 1


def choose_option_source(rows_by_source: dict[str, int]) -> str | None:
    """The source to read one contract's smile from: best tier, then most listed options.

    A smile is never mixed from two sources: their settlements are separate contracts
    (two exchanges) or separate copies (an exchange and a vendor). Ties on tier and row
    count go to the alphabetically first source so the choice never depends on row order.
    """

    candidates = [
        (option_source_tier(source), -count, source)
        for source, count in rows_by_source.items()
        if count > 0
    ]
    return min(candidates)[2] if candidates else None
