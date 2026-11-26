"""Price moves within one contract: the one roll-aware return rule.

A daily close series of a rolling product (front month, M+1, the front season) changes the
contract it prices on each roll: the close before the roll is October, the close after it is
November. The difference between the two is the October/November spread, not a move of any
price a position held. Every engine that turns closes into moves (the spread lab's P&L, the
ladder's historical VaR, the Today day P&L) uses :func:`contract_move` so that a move is only
ever taken between two closes of the same contract.

A contract that delivers ``ROLL_EXCLUDE_MIN_DAYS`` gas days or fewer (day-ahead, weekend) is a
new delivery every close by nature; its consecutive closes are not a roll. Whether a move of
such a series is a *tradable* P&L is the caller's question (the spread lab answers it for
day-ahead legs; ``domain/research/spread_analysis.py``).

本模块给出唯一的换月感知价格变动规则：只在同一合约的两次收盘之间计算变动，换月当日的
跳变（新旧合约价差）不算作价格变动。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

#: A contract delivering more gas days than this rolls (its move across the roll is not a
#: price move); a day-ahead or weekend series is re-traded every close by nature.
ROLL_EXCLUDE_MIN_DAYS = 2

#: The contract behind a close: (first gas day as ISO text, gas days delivered).
Contract = tuple[str, int]


def is_roll(before: Contract | None, after: Contract | None) -> bool:
    """Whether two consecutive closes price different contracts of a rolling product."""

    return bool(
        before
        and after
        and before[0] != after[0]
        and before[1] > ROLL_EXCLUDE_MIN_DAYS
    )


def contract_move(
    previous: float,
    current: float,
    before: Contract | None = None,
    after: Contract | None = None,
) -> float | None:
    """``current - previous`` when both closes price one contract; ``None`` across a roll.

    Closes whose contract is not known (``None``) are taken as one contract, as before the
    series carried its delivery period.
    """

    if is_roll(before, after):
        return None
    return current - previous


def contract_returns(
    closes: Mapping[date, float],
    contracts: Mapping[date, Contract] | None = None,
    *,
    max_gap_days: int | None = None,
) -> dict[date, float]:
    """Each day's move from the previous close of the series, within one contract.

    A day is left out when its previous close is more than ``max_gap_days`` calendar days
    earlier (missing data, not a one-day move) or prices another contract (a roll).
    """

    ordered = sorted(closes)
    moves: dict[date, float] = {}
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if max_gap_days is not None and (current - previous).days > max_gap_days:
            continue
        before = contracts.get(previous) if contracts else None
        after = contracts.get(current) if contracts else None
        move = contract_move(closes[previous], closes[current], before, after)
        if move is not None:
            moves[current] = move
    return moves
