"""Day-ahead versus within-day: how much of tomorrow's supply to sell now.

A desk long upstream gas sells most of it day-ahead, where liquidity is deepest, and keeps
some back for within-day because tomorrow's delivery is not certain: the field, the
terminal or the seller can deliver less (or more) than nominated. Sell too much day-ahead
and the shortfall is bought back within-day or cashed out short at the system's penalty
price; sell too little and the surplus goes within-day at whatever that market pays, or is
cashed out long.

This is the newsvendor problem. With tomorrow's delivery D ~ Normal(mu, sigma), selling Q
day-ahead costs, per MWh,

* ``c_over`` for each MWh sold that does not arrive: buying it back within-day above the
  day-ahead price, or the short cash-out premium, whichever the desk expects to pay;
* ``c_under`` for each MWh that arrives unsold: day-ahead price less what the within-day
  market or the long cash-out is expected to pay.

The volume that minimises the expected cost is Q* = mu + sigma x z, where z is the
quantile of the critical ratio c_under / (c_under + c_over). A small within-day discount
and a large short penalty pushes Q* below expected supply: keep a buffer. mu and sigma come
from the contract's own measured delivery (allocations against nominations), so a volatile
field automatically keeps more back. Decision support only: nothing is nominated or sold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist


@dataclass(frozen=True)
class SellDownInputs:
    expected_supply_mwh: float  # tomorrow's nominated supply, after measured bias
    supply_stdev_mwh: float  # measured standard deviation of delivery
    da_price: float  # day-ahead bid the desk can hit, per MWh
    wd_expected_price: float  # within-day price the desk expects, per MWh
    short_penalty_per_mwh: float = 0.0  # premium over within-day to cover a shortfall
    long_discount_per_mwh: float = 0.0  # discount below within-day to dispose of surplus
    lot_mwh: float = 24.0  # day-ahead lot (1 MW for a gas day)


@dataclass(frozen=True)
class SellDownPlan:
    sell_day_ahead_mwh: float
    keep_within_day_mwh: float
    critical_ratio: float
    probability_short: float
    expected_cost_vs_perfect: float
    sell_all_cost_vs_perfect: float
    cost_over_per_mwh: float
    cost_under_per_mwh: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "sell_day_ahead_mwh": round(self.sell_day_ahead_mwh, 0),
            "keep_within_day_mwh": round(self.keep_within_day_mwh, 0),
            "critical_ratio": round(self.critical_ratio, 3),
            "probability_short_pct": round(100 * self.probability_short, 1),
            "expected_cost_vs_perfect": round(self.expected_cost_vs_perfect, 0),
            "sell_all_cost_vs_perfect": round(self.sell_all_cost_vs_perfect, 0),
            "cost_over_per_mwh": round(self.cost_over_per_mwh, 3),
            "cost_under_per_mwh": round(self.cost_under_per_mwh, 3),
            "reasons": list(self.reasons),
        }


_NORMAL = NormalDist()


def _expected_cost(q: float, mu: float, sigma: float, c_over: float, c_under: float) -> float:
    """E[c_over (Q-D)+ + c_under (D-Q)+] for D ~ N(mu, sigma)."""

    if sigma <= 0:
        return c_over * max(0.0, q - mu) + c_under * max(0.0, mu - q)
    z = (q - mu) / sigma
    loss = sigma * (_NORMAL.pdf(z) - z * (1 - _NORMAL.cdf(z)))  # E[(D-Q)+]
    shortfall = loss + (q - mu)  # E[(Q-D)+]
    return c_over * shortfall + c_under * loss


def plan_sell_down(inputs: SellDownInputs) -> SellDownPlan:
    mu = max(0.0, inputs.expected_supply_mwh)
    sigma = max(0.0, inputs.supply_stdev_mwh)
    # Selling a MWh that does not arrive: buy it back within-day (plus the short premium),
    # having received the day-ahead price for it.
    c_over = max(0.0, inputs.wd_expected_price + inputs.short_penalty_per_mwh - inputs.da_price)
    # Keeping a MWh back that does arrive: it fetches the within-day price less the long
    # discount instead of the day-ahead price.
    c_under = max(0.0, inputs.da_price - (inputs.wd_expected_price - inputs.long_discount_per_mwh))
    reasons = []
    if c_over + c_under <= 0:
        ratio = 0.5
        reasons.append("Within-day is expected to pay as much as day-ahead: no cost either way.")
    else:
        ratio = c_under / (c_over + c_under)
    if sigma <= 0:
        q = mu
    else:
        clipped = min(max(ratio, 1e-4), 1 - 1e-4)
        q = mu + sigma * _NORMAL.inv_cdf(clipped)
    q = min(max(0.0, q), mu + 3 * sigma)
    lot = max(inputs.lot_mwh, 1e-9)
    q = math.floor(q / lot + 1e-9) * lot
    # Short when delivery falls below what was sold day-ahead: P(D < Q).
    probability_short = 0.0 if sigma <= 0 else _NORMAL.cdf((q - mu) / sigma)
    if c_over > c_under:
        reasons.append(
            "A shortfall costs more than a surplus, so keep a buffer back for within-day."
        )
    elif c_under > c_over:
        reasons.append("Within-day is expected to pay less than day-ahead, so sell more now.")
    if sigma > 0:
        reasons.append(
            f"Delivery varies by about {sigma:,.0f} MWh a day (one standard deviation), "
            "measured from allocations against nominations."
        )
    return SellDownPlan(
        sell_day_ahead_mwh=q,
        keep_within_day_mwh=max(0.0, mu - q),
        critical_ratio=ratio,
        probability_short=probability_short,
        expected_cost_vs_perfect=_expected_cost(q, mu, sigma, c_over, c_under),
        sell_all_cost_vs_perfect=_expected_cost(mu, mu, sigma, c_over, c_under),
        cost_over_per_mwh=c_over,
        cost_under_per_mwh=c_under,
        reasons=tuple(reasons),
    )
