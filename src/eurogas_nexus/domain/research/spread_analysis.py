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
    """One leg: a daily close series and its weight in the spread."""

    label: str
    weight: float
    closes: Mapping[date, float]


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
        volume_mwh_per_day: Position size, MWh per day of the spread.
        cost_per_mwh: Transaction cost charged per MWh on each position change.
    """

    kind: str = "zscore"
    lookback: int = 20
    entry_z: float = 2.0
    exit_z: float = 0.5
    low: float | None = None
    high: float | None = None
    volume_mwh_per_day: float = 1_000.0
    cost_per_mwh: float = 0.02

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


@dataclass(frozen=True)
class SpreadTrade:
    opened: date
    closed: date | None
    direction: str
    entry_spread: float
    exit_spread: float | None
    pnl: float


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

    def as_dict(self) -> dict[str, object]:
        return {
            "labels": list(self.labels),
            "weights": list(self.weights),
            "points": [
                {
                    "date": point.day.isoformat(),
                    "legs": list(point.legs),
                    "spread": point.spread,
                    "zscore": point.zscore,
                    "position": point.position,
                    "pnl": point.pnl,
                    "cumulative_pnl": point.cumulative_pnl,
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
                }
                for trade in self.trades
            ],
            "rule": self.rule.identity(),
            "analysis_hash": self.analysis_hash,
            "limitations": list(self.limitations),
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


def analyse_spread(
    legs: Sequence[SpreadLeg],
    rule: SpreadRule,
    *,
    simulated_sources: bool = False,
) -> SpreadAnalysis:
    """Build the spread, its statistics and the rule backtest.

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

    zscores: list[float | None] = []
    for index in range(len(spread)):
        if index + 1 < rule.lookback:
            zscores.append(None)
            continue
        window = spread[index + 1 - rule.lookback : index + 1]
        deviation = _std(window)
        zscores.append(None if deviation == 0 else (spread[index] - _mean(window)) / deviation)

    positions: list[int] = []
    position = 0
    for index, level in enumerate(spread):
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
            if position == 0 and level <= rule.low:
                position = 1
            elif position == 0 and level >= rule.high:
                position = -1
            elif (position == 1 and level >= middle) or (position == -1 and level <= middle):
                position = 0
        positions.append(position)

    points: list[SpreadPoint] = []
    trades: list[SpreadTrade] = []
    cumulative = 0.0
    previous_position = 0
    open_trade: dict[str, object] | None = None
    daily_pnls: list[float] = []
    for index, day in enumerate(common):
        # The position held into today was decided at yesterday's close.
        held = positions[index - 1] if index else 0
        move = spread[index] - spread[index - 1] if index else 0.0
        pnl = held * move * rule.volume_mwh_per_day
        change = abs(positions[index] - previous_position)
        pnl -= change * rule.cost_per_mwh * rule.volume_mwh_per_day
        cumulative += pnl
        daily_pnls.append(pnl)
        if open_trade is not None:
            open_trade["pnl"] = float(open_trade["pnl"]) + held * move * rule.volume_mwh_per_day
        if positions[index] != previous_position:
            if open_trade is not None:
                trades.append(
                    SpreadTrade(
                        opened=open_trade["opened"],  # type: ignore[arg-type]
                        closed=day,
                        direction=str(open_trade["direction"]),
                        entry_spread=float(open_trade["entry"]),
                        exit_spread=spread[index],
                        pnl=round(
                            float(open_trade["pnl"])
                            - 2 * rule.cost_per_mwh * rule.volume_mwh_per_day,
                            2,
                        ),
                    )
                )
                open_trade = None
            if positions[index] != 0:
                open_trade = {
                    "opened": day,
                    "direction": "long" if positions[index] > 0 else "short",
                    "entry": spread[index],
                    "pnl": 0.0,
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
                pnl=round(float(open_trade["pnl"]), 2),
            )
        )

    peak, drawdown = 0.0, 0.0
    running = 0.0
    for pnl in daily_pnls:
        running += pnl
        peak = max(peak, running)
        drawdown = min(drawdown, running - peak)
    closed = [trade for trade in trades if trade.closed is not None]
    deviation = _std(daily_pnls)
    latest = spread[-1]
    statistics: dict[str, float | int | None] = {
        "days": len(spread),
        "first_date_ordinal": common[0].toordinal(),
        "last": _round(latest),
        "mean": _round(_mean(spread)),
        "std": _round(_std(spread)),
        "min": _round(min(spread)),
        "max": _round(max(spread)),
        "zscore_last": _round(zscores[-1], 4),
        "percentile_last": round(100 * sum(value <= latest for value in spread) / len(spread), 1),
        "half_life_days": _round(_half_life(spread), 2),
    }
    statistics.pop("first_date_ordinal")
    metrics: dict[str, float | int | None] = {
        "total_pnl": round(cumulative, 2),
        "trades": len(trades),
        "closed_trades": len(closed),
        "hit_rate": round(sum(trade.pnl > 0 for trade in closed) / len(closed), 3)
        if closed
        else None,
        "max_drawdown": round(drawdown, 2),
        "sharpe_annualised": round(_mean(daily_pnls) / deviation * math.sqrt(252), 2)
        if deviation > 0
        else None,
        "days_in_market": sum(position != 0 for position in positions),
    }
    identity = {
        "schema": "spread-analysis/v1",
        "legs": [{"label": leg.label, "weight": leg.weight} for leg in legs],
        "dates": [common[0].isoformat(), common[-1].isoformat(), len(common)],
        "spread": [round(value, 9) for value in spread],
        "rule": rule.identity(),
    }
    limitations = [
        "Daily closes only; intraday path, liquidity and slippage beyond the declared "
        "cost are not modelled.",
        "A backtest on history is evidence for review, not a forecast or a trading signal.",
    ]
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
    )
