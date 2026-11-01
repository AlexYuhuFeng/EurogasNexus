"""The desk's gas balance per gas day at one hub: what comes in, what is traded, what is left.

Gas is balanced daily. Each gas day the shipper's inputs at a hub (contract supply) plus
purchases must equal its outputs (sales); whatever is left at the end of the day is cashed
out by the TSO at a penal price (NBP: system marginal buy or sell price; THE, TTF, PEG ...:
the balancing neutrality prices). So for every coming gas day the desk wants:

* expected supply: the contracts' daily quantities, corrected by how they actually deliver
  (allocated against nominated, measured);
* traded: day-ahead, within-day, month and longer trades on the exchange, and bilateral
  deals booked in the ETRM, each spread over its delivery days;
* the residual: supply plus purchases minus sales. Positive is gas still to sell, negative
  gas still to buy; left open it is cashed out, and what that would cost.

This reads positions only; nothing is nominated, sold or bought.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BalanceLeg:
    """A flat daily volume over a gas-day window (long or bought positive)."""

    reference: str
    first_gas_day: date
    last_gas_day: date
    mwh_per_day: float
    #: "supply" (a contract), "exchange" (a screen trade) or "bilateral" (an ETRM deal).
    source: str


def daily_balance(
    days: Sequence[date],
    legs: Iterable[BalanceLeg],
    *,
    delivery_ratio: float = 1.0,
    flat_band_mwh: float = 0.0,
    short_premium_per_mwh: float | None = None,
    long_discount_per_mwh: float | None = None,
) -> list[dict]:
    """One row per gas day: supply, purchases and sales by venue, the residual and its cost.

    ``delivery_ratio`` scales contract supply by its measured delivery (0.97 when contracts
    deliver 3 % under nomination). A residual within ``flat_band_mwh`` is "balanced". The
    cash-out cost uses the desk's own premium for being short and discount for being long,
    per MWh; without them the cost is not estimated.
    """

    legs = list(legs)
    rows = []
    for day in days:
        totals = {
            "supply": 0.0,
            "exchange_bought": 0.0,
            "exchange_sold": 0.0,
            "bilateral_bought": 0.0,
            "bilateral_sold": 0.0,
        }
        for leg in legs:
            if not leg.first_gas_day <= day <= leg.last_gas_day:
                continue
            if leg.source == "supply":
                totals["supply"] += leg.mwh_per_day * delivery_ratio
            else:
                side = "bought" if leg.mwh_per_day > 0 else "sold"
                totals[f"{leg.source}_{side}"] += abs(leg.mwh_per_day)
        bought = totals["exchange_bought"] + totals["bilateral_bought"]
        sold = totals["exchange_sold"] + totals["bilateral_sold"]
        residual = totals["supply"] + bought - sold
        if abs(residual) <= flat_band_mwh:
            state, cost = "balanced", 0.0
        elif residual > 0:
            state = "long"
            cost = None if long_discount_per_mwh is None else residual * long_discount_per_mwh
        else:
            state = "short"
            cost = None if short_premium_per_mwh is None else -residual * short_premium_per_mwh
        rows.append(
            {
                "gas_day": day.isoformat(),
                **{key: round(value, 1) for key, value in totals.items()},
                "residual_mwh": round(residual, 1) + 0.0,
                "state": state,
                "cash_out_cost": None if cost is None else round(cost, 2),
            }
        )
    return rows
