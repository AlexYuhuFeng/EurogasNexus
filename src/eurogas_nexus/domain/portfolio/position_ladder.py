"""Position ladder: physical and financial positions by hub and delivery month.

A desk with upstream supply, cargoes and hub sales alongside screen hedges needs one
table that answers "how long or short am I, where and when, and how much of it is
hedged". Physical legs (contracted daily quantities) and financial legs (filled screen
trades) are spread over the gas days they deliver and summed per hub and calendar month
of the gas day. Long is positive.

Mark-to-market uses one price per hub and month when given. Value at risk is historical
simulation: the net position per hub times each observed daily change of that hub's price,
summed across hubs per day, and the loss at the chosen percentile. It is an indicator of
price risk on the open position, not a risk-system VaR: volume, basis, shape and credit risk
are not included, and that is stated with every result.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

#: Gas days run 06:00 to 06:00 local; the ladder works in whole gas days by their start date.


@dataclass(frozen=True)
class PositionLeg:
    """One physical contract or one financial trade, in MWh per gas day."""

    kind: str  # "physical" or "financial"
    hub: str
    first_gas_day: date
    last_gas_day: date  # inclusive
    mwh_per_day: float  # long positive, short negative
    price: float | None = None  # contract or trade price, in the hub's ladder currency/MWh
    reference: str = ""
    book_id: str = ""  # trading book; "" while unassigned


@dataclass(frozen=True)
class LadderRow:
    hub: str
    month: str  # "2026-11"
    physical_mwh: float
    financial_mwh: float

    @property
    def net_mwh(self) -> float:
        return self.physical_mwh + self.financial_mwh

    @property
    def hedge_ratio(self) -> float | None:
        """Share of the physical position offset by financial trades (1.0 = fully hedged)."""

        if abs(self.physical_mwh) < 1e-9:
            return None
        return -self.financial_mwh / self.physical_mwh


@dataclass
class LadderResult:
    rows: list[LadderRow]
    mark_to_market: float | None = None
    unpriced_rows: int = 0
    var_95_1d: float | None = None
    var_observations: int = 0
    warnings: list[str] = field(default_factory=list)
    reporting_currency: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "rows": [
                {
                    "hub": row.hub,
                    "month": row.month,
                    "physical_mwh": round(row.physical_mwh, 1),
                    "financial_mwh": round(row.financial_mwh, 1),
                    "net_mwh": round(row.net_mwh, 1),
                    "hedge_ratio": None if row.hedge_ratio is None else round(row.hedge_ratio, 3),
                }
                for row in self.rows
            ],
            "totals": {
                "physical_mwh": round(sum(r.physical_mwh for r in self.rows), 1),
                "financial_mwh": round(sum(r.financial_mwh for r in self.rows), 1),
                "net_mwh": round(sum(r.net_mwh for r in self.rows), 1),
            },
            "mark_to_market": None
            if self.mark_to_market is None
            else round(self.mark_to_market, 2),
            "unpriced_rows": self.unpriced_rows,
            "var_95_1d": None if self.var_95_1d is None else round(self.var_95_1d, 2),
            "var_observations": self.var_observations,
            "reporting_currency": self.reporting_currency,
            "warnings": list(self.warnings),
        }


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def build_ladder(
    legs: Iterable[PositionLeg],
    *,
    horizon_start: date,
    horizon_end: date,
) -> list[LadderRow]:
    """Sum legs per hub and month over ``[horizon_start, horizon_end]`` (gas days, inclusive)."""

    if horizon_end < horizon_start:
        raise ValueError("horizon_end is before horizon_start")
    buckets: dict[tuple[str, str], list[float]] = {}
    for leg in legs:
        first = max(leg.first_gas_day, horizon_start)
        last = min(leg.last_gas_day, horizon_end)
        day = first
        while day <= last:
            # Whole months at a time: count the days of this leg inside the month.
            month_end = (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            stop = min(month_end, last)
            days = (stop - day).days + 1
            bucket = buckets.setdefault((leg.hub.upper(), _month_key(day)), [0.0, 0.0])
            bucket[0 if leg.kind == "physical" else 1] += leg.mwh_per_day * days
            day = stop + timedelta(days=1)
    return [
        LadderRow(hub=hub, month=month, physical_mwh=values[0], financial_mwh=values[1])
        for (hub, month), values in sorted(
            buckets.items(), key=lambda item: (item[0][1], item[0][0])
        )
    ]


def mark_to_market(
    legs: Iterable[PositionLeg],
    marks: Mapping[tuple[str, str], float],
    *,
    horizon_start: date,
    horizon_end: date,
    fx_by_hub: Mapping[str, float] | None = None,
) -> tuple[float | None, int]:
    """Value of each leg against the mark for its hub and month: (mark − price) × MWh.

    Hubs quote in different currencies (NBP in GBP, continental hubs in EUR). With
    ``fx_by_hub`` each hub's value is multiplied into one reporting currency, and a hub
    without a rate is left unvalued; without it all hubs must share one currency.
    Returns the total (``None`` when no leg-month could be valued) and the number of
    leg-months without a mark, a leg price or an FX rate.
    """

    total, missing, valued = 0.0, 0, 0
    for leg in legs:
        for row in build_ladder([leg], horizon_start=horizon_start, horizon_end=horizon_end):
            mark = marks.get((row.hub, row.month))
            fx = 1.0 if fx_by_hub is None else fx_by_hub.get(row.hub)
            if mark is None or leg.price is None or fx is None:
                missing += 1
                continue
            total += (mark - leg.price) * row.net_mwh * fx
            valued += 1
    # Nothing valued is unknown, not zero.
    return (total if valued else None), missing


def historical_var(
    net_mwh_by_hub: Mapping[str, float],
    daily_closes_by_hub: Mapping[str, Mapping[date, float]],
    *,
    confidence: float = 0.95,
    min_observations: int = 20,
    fx_by_hub: Mapping[str, float] | None = None,
) -> tuple[float | None, int]:
    """One-day historical-simulation VaR of the open position (a positive loss figure).

    Uses the days on which every hub with a position has a close on that day and the day
    before. Returns ``(None, n)`` with fewer than ``min_observations`` scenarios.
    """

    hubs = [hub for hub, mwh in net_mwh_by_hub.items() if abs(mwh) > 1e-9]
    if not hubs:
        return 0.0, 0
    fx = {hub: 1.0 if fx_by_hub is None else fx_by_hub.get(hub) for hub in hubs}
    if any(rate is None for rate in fx.values()):
        return None, 0
    common: set[date] | None = None
    for hub in hubs:
        days = set(daily_closes_by_hub.get(hub, {}))
        common = days if common is None else common & days
    ordered = sorted(common or ())
    scenarios: list[float] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        scenarios.append(
            sum(
                net_mwh_by_hub[hub]
                * (daily_closes_by_hub[hub][current] - daily_closes_by_hub[hub][previous])
                * fx[hub]
                for hub in hubs
            )
        )
    if len(scenarios) < min_observations:
        return None, len(scenarios)
    ordered_pnl = sorted(scenarios)
    index = max(0, math.floor((1 - confidence) * len(ordered_pnl)) - 1)
    return max(0.0, -ordered_pnl[index]), len(scenarios)


def ladder_report(
    legs: Sequence[PositionLeg],
    *,
    horizon_start: date,
    horizon_end: date,
    marks: Mapping[tuple[str, str], float] | None = None,
    daily_closes_by_hub: Mapping[str, Mapping[date, float]] | None = None,
    fx_by_hub: Mapping[str, float] | None = None,
    reporting_currency: str | None = None,
) -> LadderResult:
    rows = build_ladder(legs, horizon_start=horizon_start, horizon_end=horizon_end)
    result = LadderResult(rows=rows, reporting_currency=reporting_currency)
    result.warnings.append(
        "Indicative: price risk on the open position only; volume, basis, shape and credit "
        "risk are not included. Not a substitute for the risk system."
    )
    if marks is not None:
        value, missing = mark_to_market(
            legs, marks, horizon_start=horizon_start, horizon_end=horizon_end, fx_by_hub=fx_by_hub
        )
        result.mark_to_market, result.unpriced_rows = value, missing
        if missing:
            result.warnings.append(
                f"{missing} leg-months have no mark or no price and are not valued."
            )
    if daily_closes_by_hub is not None:
        net_by_hub: dict[str, float] = {}
        for row in rows:
            net_by_hub[row.hub] = net_by_hub.get(row.hub, 0.0) + row.net_mwh
        result.var_95_1d, result.var_observations = historical_var(
            net_by_hub, daily_closes_by_hub, fx_by_hub=fx_by_hub
        )
        if result.var_95_1d is None:
            result.warnings.append(
                f"VaR needs at least 20 daily price changes on every hub held; "
                f"{result.var_observations} available."
            )
    return result
