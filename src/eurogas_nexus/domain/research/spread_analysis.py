"""Spread and benchmark analysis with a point-in-time rule backtest.

The question a gas trader asks of two benchmarks is concrete: how does NBP DA trade
against TTF DA (or summer against winter, or a hub against its own forward month), is
today's level unusual, and would a simple rule on it have made money after costs?
This module answers that over daily closes:

- the spread is a weighted sum of legs, ``sum(w_i * price_i)`` (``NBP - TTF`` is
  weights ``+1, -1``), on dates where every leg has a close;
- statistics: level, mean, standard deviation, rolling z-score, percentile of the
  latest value in its own history, and the AR(1) mean-reversion half-life;
- a backtest of a declared rule, ``zscore`` (mean reversion: short the spread when
  ``z >= entry``, long when ``z <= -entry``, flat when ``|z| <= exit``) or
  ``threshold`` (long below ``low``, short above ``high``, flat at the mean of the
  two). The position decided at the close of day *t* uses only data up to *t* and
  earns the change from *t* to *t + 1*, so there is no look-ahead. Costs are charged per
  MWh on every position change.

Strategies are declared, not programmed: the rule is data that is validated, hashed
and reproducible, never user code executed on the server. Quants who need arbitrary
models use the Python SDK against the same data API on their own machines.

本模块提供价差/基准分析：加权价差、统计量（z 分数、分位、均值回归半衰期），
以及无前视偏差的规则回测（z 分数均值回归或阈值）；策略以声明式参数表达，不在服务器
执行用户代码。
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

MAX_LEGS = 4
MAX_POINTS = 5_000
RULES = ("zscore", "threshold")


class SpreadAnalysisError(ValueError):
    """Invalid legs, rule parameters or too little overlapping history."""


@dataclass(frozen=True)
class SpreadLeg:
    """One leg: a daily close series and its weight in the spread.

    ``deliveries`` (optional) names the contract behind each close as ``(first gas day, gas
    days delivered)``: a rolling series (front month, S+1) changes contract on its roll, and
    a position's energy is the size per gas day times the gas days the contract delivers.
    """

    label: str
    weight: float
    closes: Mapping[date, float]
    deliveries: Mapping[date, tuple[str, int]] | None = None


EXECUTIONS = ("next_close", "same_close")
#: Fewer closed trades than this: the result says it is too few to conclude anything.
MIN_TRADES_TO_CONCLUDE = 10
#: The later share of the days reported as the out-of-sample period.
OUT_OF_SAMPLE_SHARE = 0.3
#: A contract delivering more gas days than this rolls (its move across the roll is not
#: strategy P&L); a day-ahead or weekend series is re-traded every close by nature.
ROLL_EXCLUDE_MIN_DAYS = 2


@dataclass(frozen=True)
class SpreadRule:
    """A declared trading rule on the spread.

    Attributes:
        kind: ``zscore`` or ``threshold``.
        lookback: Rolling window (days) for the z-score mean and deviation.
        entry_z: |z| at or beyond which a position opens (``zscore``).
        exit_z: |z| at or within which the position closes (``zscore``).
        low: Spread level at or below which to go long (``threshold``).
        high: Spread level at or above which to go short (``threshold``).
        volume_mwh_per_day: Position size, MWh per gas day in each leg.
        cost_per_mwh: Cost per MWh charged on each position change (entry and exit), in the
            spread's unit: the bid/offer crossed and any fee.
        execution: ``next_close`` (default: the signal at a close is traded at the next close)
            or ``same_close`` (traded at the very close the signal was computed on, which no
            desk can do; kept for comparison).
    """

    kind: str = "zscore"
    lookback: int = 20
    entry_z: float = 2.0
    exit_z: float = 0.5
    low: float | None = None
    high: float | None = None
    volume_mwh_per_day: float = 1_000.0
    cost_per_mwh: float = 0.02
    execution: str = "next_close"

    def validate(self) -> None:
        """Raise :class:`SpreadAnalysisError` on an unusable rule."""

        if self.kind not in RULES:
            raise SpreadAnalysisError(f"rule kind must be one of {RULES}")
        if not 5 <= self.lookback <= 250:
            raise SpreadAnalysisError("lookback must be 5..250 days")
        if self.kind == "zscore" and not 0 <= self.exit_z < self.entry_z <= 10:
            raise SpreadAnalysisError("need 0 <= exit_z < entry_z <= 10")
        if self.kind == "threshold":
            if self.low is None or self.high is None or not self.low < self.high:
                raise SpreadAnalysisError("threshold rule needs low < high")
        if not 0 < self.volume_mwh_per_day <= 1e7:
            raise SpreadAnalysisError("volume_mwh_per_day must be positive")
        if not 0 <= self.cost_per_mwh <= 100:
            raise SpreadAnalysisError("cost_per_mwh must be 0..100")
        if self.execution not in EXECUTIONS:
            raise SpreadAnalysisError(f"execution must be one of {EXECUTIONS}")

    def identity(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "lookback": self.lookback,
            "entry_z": self.entry_z,
            "exit_z": self.exit_z,
            "low": self.low,
            "high": self.high,
            "volume_mwh_per_day": self.volume_mwh_per_day,
            "cost_per_mwh": self.cost_per_mwh,
            "execution": self.execution,
        }


@dataclass(frozen=True)
class SpreadPoint:
    day: date
    legs: tuple[float, ...]
    spread: float
    zscore: float | None
    position: int
    pnl: float
    cumulative_pnl: float
    signal: int = 0
    signal_level: float | None = None
    drawdown: float = 0.0
    roll: bool = False


@dataclass(frozen=True)
class SpreadTrade:
    opened: date
    closed: date | None
    direction: str
    entry_spread: float
    exit_spread: float | None
    pnl: float
    pnl_per_mwh: float = 0.0
    holding_days: int | None = None


@dataclass(frozen=True)
class SpreadAnalysis:
    labels: tuple[str, ...]
    weights: tuple[float, ...]
    points: tuple[SpreadPoint, ...]
    statistics: dict[str, float | int | None]
    metrics: dict[str, float | int | None]
    trades: tuple[SpreadTrade, ...]
    rule: SpreadRule
    analysis_hash: str
    limitations: tuple[str, ...] = field(default_factory=tuple)
    assumptions: str = ""
    periods: dict[str, dict[str, object]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "labels": list(self.labels),
            "weights": list(self.weights),
            "points": [
                {
                    "date": point.day.isoformat(),
                    "legs": list(point.legs),
                    "spread": point.spread,
                    "signal_level": point.signal_level,
                    "zscore": point.zscore,
                    "signal": point.signal,
                    "position": point.position,
                    "pnl": point.pnl,
                    "cumulative_pnl": point.cumulative_pnl,
                    "drawdown": point.drawdown,
                    "roll": point.roll,
                }
                for point in self.points
            ],
            "statistics": self.statistics,
            "metrics": self.metrics,
            "trades": [
                {
                    "opened": trade.opened.isoformat(),
                    "closed": trade.closed.isoformat() if trade.closed else None,
                    "direction": trade.direction,
                    "entry_spread": trade.entry_spread,
                    "exit_spread": trade.exit_spread,
                    "pnl": trade.pnl,
                    "pnl_per_mwh": trade.pnl_per_mwh,
                    "holding_days": trade.holding_days,
                }
                for trade in self.trades
            ],
            "rule": self.rule.identity(),
            "analysis_hash": self.analysis_hash,
            "limitations": list(self.limitations),
            "assumptions": self.assumptions,
            "periods": self.periods,
        }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _half_life(series: Sequence[float]) -> float | None:
    """AR(1) half-life in days from OLS of the change on the lagged level."""

    if len(series) < 10:
        return None
    lagged = series[:-1]
    delta = [later - earlier for earlier, later in zip(series, series[1:], strict=False)]
    mean_x, mean_y = _mean(lagged), _mean(delta)
    var_x = sum((x - mean_x) ** 2 for x in lagged)
    if var_x == 0:
        return None
    beta = sum((x - mean_x) * (y - mean_y) for x, y in zip(lagged, delta, strict=True)) / var_x
    if not -1 < beta < 0:
        return None
    return -math.log(2) / math.log(1 + beta)


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _deviation_is_zero(window: Sequence[float], deviation: float) -> bool:
    """A window whose spread does not move (to the float noise of its level)."""

    scale = max(1.0, max(abs(value) for value in window))
    return deviation <= 1e-9 * scale


def analyse_spread(
    legs: Sequence[SpreadLeg],
    rule: SpreadRule,
    *,
    simulated_sources: bool = False,
    signal_offsets: Mapping[date, float] | None = None,
    cost_basis: str = "stated",
    fx_note: str = "",
) -> SpreadAnalysis:
    """Build the spread, its statistics and the rule backtest.

    ``signal_offsets`` (a route tariff per day, by the gas year the product delivers in) makes
    the rule read the *net* spread ``gross − offset``; P&L stays the gross spread's moves (a
    financial spread pays no tariff). ``cost_basis`` and ``fx_note`` are stated in the
    assumptions line.

    Raises:
        SpreadAnalysisError: Bad legs/rule or fewer than ``lookback + 2`` common days.
    """

    if not 1 <= len(legs) <= MAX_LEGS:
        raise SpreadAnalysisError(f"between 1 and {MAX_LEGS} legs are required")
    for leg in legs:
        if not math.isfinite(leg.weight) or leg.weight == 0:
            raise SpreadAnalysisError(f"leg {leg.label!r} needs a non-zero finite weight")
    rule.validate()
    common = sorted(set.intersection(*(set(leg.closes) for leg in legs)))[-MAX_POINTS:]
    if len(common) < rule.lookback + 2:
        raise SpreadAnalysisError(
            f"only {len(common)} common days; the rule needs at least {rule.lookback + 2}"
        )
    leg_values = [tuple(float(leg.closes[day]) for leg in legs) for day in common]
    spread = [
        sum(leg.weight * value for leg, value in zip(legs, values, strict=True))
        for values in leg_values
    ]
    offsets = signal_offsets or {}
    level = [value - float(offsets.get(day, 0.0)) for day, value in zip(common, spread,
                                                                         strict=True)]
    missing_offsets = sum(day not in offsets for day in common) if signal_offsets else 0

    # The contract behind each close: (first gas day, gas days delivered) per leg, if known.
    def contract(leg: SpreadLeg, day: date) -> tuple[str, int] | None:
        return None if leg.deliveries is None else leg.deliveries.get(day)

    zscores: list[float | None] = []
    for index in range(len(level)):
        if index + 1 < rule.lookback:
            zscores.append(None)
            continue
        window = level[index + 1 - rule.lookback : index + 1]
        deviation = _std(window)
        zscores.append(
            None
            if _deviation_is_zero(window, deviation)
            else (level[index] - _mean(window)) / deviation
        )

    signals: list[int] = []
    position = 0
    for index, value in enumerate(level):
        z = zscores[index]
        if rule.kind == "zscore":
            if z is not None:
                if position == 0 and z >= rule.entry_z:
                    position = -1
                elif position == 0 and z <= -rule.entry_z:
                    position = 1
                elif position != 0 and abs(z) <= rule.exit_z:
                    position = 0
        else:
            assert rule.low is not None and rule.high is not None
            middle = (rule.low + rule.high) / 2
            if position == 0 and value <= rule.low:
                position = 1
            elif position == 0 and value >= rule.high:
                position = -1
            elif (position == 1 and value >= middle) or (position == -1 and value <= middle):
                position = 0
        signals.append(position)
    # The position held from each close: the signal of that close (same_close) or of the
    # close before (next_close: decided at t, traded at t + 1).
    positions = signals if rule.execution == "same_close" else [0, *signals[:-1]]

    points: list[SpreadPoint] = []
    trades: list[SpreadTrade] = []
    cumulative = 0.0
    peak = 0.0
    previous_position = 0
    open_trade: dict[str, object] | None = None
    daily_pnls: list[float] = []
    daily_per_mwh: list[float] = []
    roll_days = 0
    for index, day in enumerate(common):
        held = positions[index - 1] if index else 0
        rolled = False
        per_mwh = 0.0  # the spread's move earned per MWh of each leg per gas day
        energy_move = 0.0  # Σ w × Δp × gas days of the contract held
        if index:
            yesterday = common[index - 1]
            for leg_index, leg in enumerate(legs):
                move = leg_values[index][leg_index] - leg_values[index - 1][leg_index]
                before, now_held = contract(leg, yesterday), contract(leg, day)
                days_held = before[1] if before else 1
                if (before and now_held and before[0] != now_held[0]
                        and days_held > ROLL_EXCLUDE_MIN_DAYS):
                    # A new contract: the move across the roll is not what the position earned.
                    rolled = True
                    continue
                per_mwh += leg.weight * move
                energy_move += leg.weight * move * days_held
        if rolled and held:
            roll_days += 1
        change = abs(positions[index] - previous_position)
        days_traded = max(
            (contract(leg, day) or ("", 1))[1] for leg in legs
        )
        cost = change * rule.cost_per_mwh * rule.volume_mwh_per_day * days_traded
        pnl = held * energy_move * rule.volume_mwh_per_day - cost
        cumulative += pnl
        peak = max(peak, cumulative)
        daily_pnls.append(pnl)
        daily_per_mwh.append(held * per_mwh - change * rule.cost_per_mwh)
        if open_trade is not None:
            open_trade["pnl"] = float(open_trade["pnl"]) + held * energy_move * (
                rule.volume_mwh_per_day
            )
            open_trade["per_mwh"] = float(open_trade["per_mwh"]) + held * per_mwh
        if positions[index] != previous_position:
            if open_trade is not None:
                opened = open_trade["opened"]
                trades.append(
                    SpreadTrade(
                        opened=opened,  # type: ignore[arg-type]
                        closed=day,
                        direction=str(open_trade["direction"]),
                        entry_spread=float(open_trade["entry"]),
                        exit_spread=round(spread[index], 6),
                        pnl=round(float(open_trade["pnl"]) - float(open_trade["entry_cost"])
                                  - rule.cost_per_mwh * rule.volume_mwh_per_day * days_traded,
                                  2),
                        pnl_per_mwh=round(float(open_trade["per_mwh"])
                                          - 2 * rule.cost_per_mwh, 6),
                        holding_days=(day - opened).days,  # type: ignore[operator]
                    )
                )
                open_trade = None
            if positions[index] != 0:
                open_trade = {
                    "opened": day,
                    "direction": "long" if positions[index] > 0 else "short",
                    "entry": round(spread[index], 6),
                    "pnl": 0.0,
                    "per_mwh": 0.0,
                    "entry_cost": rule.cost_per_mwh * rule.volume_mwh_per_day * days_traded,
                }
        previous_position = positions[index]
        points.append(
            SpreadPoint(
                day=day,
                legs=tuple(round(value, 6) for value in leg_values[index]),
                spread=round(spread[index], 6),
                zscore=_round(zscores[index], 4),
                position=positions[index],
                pnl=round(pnl, 2),
                cumulative_pnl=round(cumulative, 2),
                signal=signals[index],
                signal_level=round(level[index], 6) if signal_offsets else None,
                drawdown=round(cumulative - peak, 2),
                roll=rolled,
            )
        )
    if open_trade is not None:
        trades.append(
            SpreadTrade(
                opened=open_trade["opened"],  # type: ignore[arg-type]
                closed=None,
                direction=str(open_trade["direction"]),
                entry_spread=float(open_trade["entry"]),
                exit_spread=None,
                pnl=round(float(open_trade["pnl"]) - float(open_trade["entry_cost"]), 2),
                pnl_per_mwh=round(float(open_trade["per_mwh"]) - rule.cost_per_mwh, 6),
                holding_days=(common[-1] - open_trade["opened"]).days,  # type: ignore[operator]
            )
        )

    drawdown = min((point.drawdown for point in points), default=0.0)
    closed = [trade for trade in trades if trade.closed is not None]
    deviation = _std(daily_pnls)
    latest = spread[-1]
    statistics: dict[str, float | int | None] = {
        "days": len(spread),
        "last": _round(latest),
        "mean": _round(_mean(spread)),
        "std": _round(_std(spread)),
        "min": _round(min(spread)),
        "max": _round(max(spread)),
        "zscore_last": _round(zscores[-1], 4),
        "percentile_last": round(100 * sum(value <= latest for value in spread) / len(spread), 1),
        "half_life_days": _round(_half_life(spread), 2),
    }
    if signal_offsets:
        statistics["net_last"] = _round(level[-1])
        statistics["net_positive_days"] = sum(value > 0 for value in level)
    metrics: dict[str, float | int | None] = {
        "total_pnl": round(cumulative, 2),
        "pnl_per_mwh": round(sum(daily_per_mwh), 6),
        "trades": len(trades),
        "closed_trades": len(closed),
        "hit_rate": round(sum(trade.pnl > 0 for trade in closed) / len(closed), 3)
        if closed
        else None,
        "max_drawdown": round(drawdown, 2),
        "worst_trade": min((trade.pnl for trade in closed), default=None),
        "best_trade": max((trade.pnl for trade in closed), default=None),
        "average_holding_days": round(
            sum(trade.holding_days or 0 for trade in closed) / len(closed), 1
        ) if closed else None,
        "sharpe_annualised": round(_mean(daily_pnls) / deviation * math.sqrt(252), 2)
        if deviation > 0
        else None,
        "days_in_market": sum(position != 0 for position in positions),
        "roll_days_excluded": roll_days,
        "too_few_trades": len(closed) < MIN_TRADES_TO_CONCLUDE,
    }
    split = common[int(len(common) * (1 - OUT_OF_SAMPLE_SHARE))]
    periods = {
        name: _period_metrics(points, trades, chosen)
        for name, chosen in (
            ("in_sample", lambda day: day < split),
            ("out_of_sample", lambda day: day >= split),
        )
    }
    periods["out_of_sample"]["from"] = split.isoformat()
    identity = {
        "schema": "spread-analysis/v2",
        "legs": [{"label": leg.label, "weight": leg.weight} for leg in legs],
        "dates": [common[0].isoformat(), common[-1].isoformat(), len(common)],
        "spread": [round(value, 9) for value in spread],
        "signal": [round(value, 9) for value in level] if signal_offsets else None,
        "rule": rule.identity(),
    }
    limitations = [
        "Daily closes only; intraday path, liquidity and slippage beyond the stated cost are "
        "not modelled.",
        "A backtest on history is evidence for review, not a forecast or a trading signal.",
    ]
    if len(closed) < MIN_TRADES_TO_CONCLUDE:
        limitations.insert(
            0,
            f"{len(closed)} closed trade(s): too few to conclude anything about this rule.",
        )
    if missing_offsets:
        limitations.append(
            f"{missing_offsets} day(s) without a published tariff for their gas year read the "
            "gross spread."
        )
    if simulated_sources:
        limitations.insert(0, "Includes simulated price sources: not market evidence.")
    return SpreadAnalysis(
        labels=tuple(leg.label for leg in legs),
        weights=tuple(leg.weight for leg in legs),
        points=tuple(points),
        statistics=statistics,
        metrics=metrics,
        trades=tuple(trades),
        rule=rule,
        analysis_hash=hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        limitations=tuple(limitations),
        assumptions=assumptions_line(
            rule.identity(), cost_basis=cost_basis, fx_note=fx_note,
            net=bool(signal_offsets), rolls=any(leg.deliveries for leg in legs),
        ),
        periods=periods,
    )


def _period_metrics(points, trades, chosen) -> dict[str, object]:
    pnl = round(sum(point.pnl for point in points if chosen(point.day)), 2)
    closed = [trade for trade in trades if trade.closed is not None and chosen(trade.opened)]
    return {
        "days": sum(1 for point in points if chosen(point.day)),
        "pnl": pnl,
        "closed_trades": len(closed),
        "hit_rate": round(sum(trade.pnl > 0 for trade in closed) / len(closed), 3)
        if closed else None,
    }


def assumptions_line(
    rule: Mapping[str, object],
    *,
    cost_basis: str = "stated",
    fx_note: str = "",
    net: bool = False,
    rolls: bool = False,
) -> str:
    """The compact "Assumptions" line every rule result carries."""

    kind = rule.get("kind", "zscore")
    execution = rule.get("execution", "next_close")
    traded = (
        "signal at a close, traded at the next close"
        if execution == "next_close"
        else "traded at the same close the signal was computed on (optimistic)"
    )
    window = (
        f"z-score mean and deviation over the last {rule.get('lookback', 20)} closes up to the "
        "signal close, nothing later"
        if kind == "zscore"
        else f"enter at {rule.get('low')} / {rule.get('high')}, exit at their middle"
    )
    cost = float(rule.get("cost_per_mwh", 0.0) or 0.0)
    basis = {
        "quotes": "half the held bid/offer of each leg",
        "stated": "as entered",
        "none": "none held, so zero",
    }.get(cost_basis, cost_basis)
    parts = [
        traded,
        window,
        f"cost {cost:g}/MWh per position change ({basis})",
        f"size {float(rule.get('volume_mwh_per_day', 1000) or 0):g} MWh per gas day per leg × "
        "the gas days the contract delivers",
    ]
    if rolls:
        parts.append("a month or longer contract's move across its roll is not counted; "
                     "day-ahead is re-traded every close")
    if net:
        parts.append("the rule reads the spread net of the route tariff of each day's gas "
                     "year; P&L is the gross spread")
    if fx_note:
        parts.append(fx_note)
    return "; ".join(parts) + "."
