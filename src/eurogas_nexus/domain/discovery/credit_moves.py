"""Credit exposure under a forward price move (a mark-to-market sensitivity, not a PFE model).

Every remaining month of every leg facing a counterparty is revalued by the existing credit
calculation (``domain/risk/limits.credit_exposure``) with the forward mark scaled by (1 + s):

- the stated moves s = +10 %, +20 %, +30 % (and the same downwards: a counterparty we sell
  to is exposed when prices fall);
- the move s* at which the net exposure reaches the limit, found by bisection and reported
  on the front mark of the largest leg as currency per MWh ("headroom in EUR/MWh");
- for a move that breaches, the tenor: the first month whose cumulative exposure (legs
  revalued only up to that month) crosses the limit.

Worked example (test fixture): we buy 1,000 MWh/d for Dec and Jan at 30.00 EUR/MWh from one
counterparty; marks 32.00 both months; limit EUR 150,000, no collateral. Today: 62 d x
1,000 x 2.00 = EUR 124,000 (83 %). At +10 %: 62,000 x (35.20 - 30) = EUR 322,400, breach;
cumulative Dec alone 31,000 x 5.20 = 161,200 > 150,000, so the breach tenor is December.
Limit reached at 62,000 x (32 (1 + s) - 30) = 150,000: s* = 1.3105 %, 0.42 EUR/MWh on 32.00.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from eurogas_nexus.domain.risk.limits import CounterpartyLeg, CreditLine, credit_exposure

#: The stated moves (fractions), up and down.
MOVES = (0.10, 0.20, 0.30, -0.10, -0.20, -0.30)
#: How far the bisection looks for the move that reaches the limit.
SEARCH = (-0.9, 3.0)


@dataclass(frozen=True)
class MoveResult:
    """Net exposure after one move, and the tenor at which it first crosses the limit."""

    move: float
    net_exposure: float
    breach: bool
    tenor: str | None


@dataclass(frozen=True)
class CreditMoves:
    """One counterparty's exposure today and under the moves."""

    counterparty_id: str
    name: str
    currency: str
    limit: float
    net_exposure: float
    utilisation: float | None
    status: str
    unvalued_legs: int
    moves: tuple[MoveResult, ...] = field(default_factory=tuple)
    reach_move: float | None = None
    front_hub: str | None = None
    front_month: str | None = None
    front_mark: float | None = None

    @property
    def reach_price_move(self) -> float | None:
        """The move that reaches the limit, in currency per MWh on the front mark."""

        if self.reach_move is None or self.front_mark is None:
            return None
        return self.reach_move * self.front_mark

    @property
    def projected(self) -> MoveResult | None:
        """The smallest stated move (by size) that breaches, when the line is not over now."""

        breaches = [item for item in self.moves if item.breach]
        return min(breaches, key=lambda item: abs(item.move)) if breaches else None


def _month_end(month: str) -> date:
    year, number = (int(part) for part in month.split("-"))
    first_next = date(year + (number == 12), number % 12 + 1, 1)
    return first_next - timedelta(days=1)


def credit_under_moves(
    line: CreditLine,
    legs: Iterable[CounterpartyLeg],
    *,
    today: date,
    mark: Callable[[str, str], float | None],
    fx: Callable[[str, str], float | None],
) -> CreditMoves:
    """Exposure today, under each stated move, and the move that reaches the limit."""

    legs = list(legs)

    def exposure(move: float, legs_now=None):
        def moved(hub: str, month: str):
            value = mark(hub, month)
            return None if value is None else value * (1.0 + move)

        return credit_exposure(line, legs_now or legs, today=today, mark=moved, fx=fx)

    base = exposure(0.0)
    months = sorted(
        {
            f"{day:%Y-%m}"
            for leg in legs
            for day in (max(leg.first_gas_day, today), leg.last_gas_day)
            if day >= today
        }
    )
    if legs:
        first_month, last_month = months[0], months[-1]
        months = []
        cursor = date(int(first_month[:4]), int(first_month[5:]), 1)
        stop = _month_end(last_month)
        while cursor <= stop and len(months) < 60:
            months.append(f"{cursor:%Y-%m}")
            cursor = _month_end(months[-1]) + timedelta(days=1)

    def tenor(move: float) -> str | None:
        for month in months:
            cut = _month_end(month)
            truncated = [
                replace(leg, last_gas_day=min(leg.last_gas_day, cut), open_ended=False)
                for leg in legs
                if leg.first_gas_day <= cut
            ]
            if exposure(move, truncated).net_exposure > line.limit_amount:
                return month
        return None

    results = []
    for move in MOVES:
        net = exposure(move).net_exposure
        breach = net > line.limit_amount
        results.append(MoveResult(move, net, breach, tenor(move) if breach else None))

    reach = None
    if base.net_exposure >= line.limit_amount:
        reach = 0.0
    else:
        for low, high in ((0.0, SEARCH[1]), (0.0, SEARCH[0])):
            if exposure(high).net_exposure <= line.limit_amount:
                continue
            for _ in range(60):
                mid = (low + high) / 2
                if exposure(mid).net_exposure > line.limit_amount:
                    high = mid
                else:
                    low = mid
            found = high
            if reach is None or abs(found) < abs(reach):
                reach = found
    front = None
    for leg in sorted(legs, key=lambda item: -abs(item.mwh_per_day)):
        start = max(leg.first_gas_day, today)
        if start <= leg.last_gas_day:
            price = mark(leg.hub, f"{start:%Y-%m}")
            if price is not None:
                front = (leg.hub, f"{start:%Y-%m}", price)
                break
    return CreditMoves(
        counterparty_id=line.counterparty_id,
        name=line.name,
        currency=line.currency,
        limit=line.limit_amount,
        net_exposure=base.net_exposure,
        utilisation=base.utilisation,
        status=base.status,
        unvalued_legs=base.unvalued_legs,
        moves=tuple(results),
        reach_move=reach,
        front_hub=None if front is None else front[0],
        front_month=None if front is None else front[1],
        front_mark=None if front is None else front[2],
    )
