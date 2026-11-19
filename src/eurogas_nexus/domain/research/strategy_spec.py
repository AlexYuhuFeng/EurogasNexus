"""StrategySpec: one structured, versioned description of a spread study or strategy.

The Spreads workbench's form and the "Describe it" box are two views of this object; the
deterministic engine (``application/research/spreads.py``) evaluates it, and the model, when
one is used, only ever translates text into it. A spec says:

- ``kind``: ``curve`` (the forward spread by delivery month, from the latest curve of each
  leg) or ``history`` (the daily series of one tenor, its statistics and an optional rule);
- ``legs``: two to four outright instruments by the catalogue's identities (hub and, for a
  history, the stored tenor), each with a weight; the spread is ``Σ weight × price``;
- ``unit`` and ``fx``: the display unit (``EUR/MWh``, ``p/th``, ``USD/MMBtu``…) and whether a
  forward month converts at the forward (``forward``, design D.5) or today's spot (``spot``);
- ``cost``: ``route_tariff`` from one hub to another (the direction gas moves: buy where it
  leaves, sell where it arrives), priced from the published tariffs of the proven route;
- ``rule``: an optional z-score or threshold rule for a history, with its lookback;
- ``volume_mwh_per_day``: sizing for the rule's P&L.

Validation here is structural (shapes, ranges, weights, the cost's hubs among the legs); the
application validates against what the store holds and turns every gap into a question.

StrategySpec：价差研究/策略的唯一结构化描述（版本化）；表单与文字描述是同一对象的两种视图，
模型只负责把文字翻译为此对象，所有数字由确定性引擎计算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SPEC_VERSION = 1
KINDS = ("curve", "history")
FX_MODES = ("forward", "spot")
RULE_KINDS = ("zscore", "threshold")
EXECUTIONS = ("next_close", "same_close")
MAX_LEGS = 4


@dataclass(frozen=True)
class Issue:
    """Something the spec needs before it can run, put as a question with choices."""

    code: str
    field: str
    message: str
    choices: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field, "message": self.message,
                "choices": list(self.choices)}


@dataclass(frozen=True)
class SpecLeg:
    hub: str
    weight: float
    tenor: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"hub": self.hub, "tenor": self.tenor, "weight": self.weight}


@dataclass(frozen=True)
class RouteCostSpec:
    from_hub: str
    to_hub: str
    kind: str = "route_tariff"
    #: Market areas the route must pass through, in order (a route the desk picked from the
    #: alternatives); empty = the cheapest complete route.
    through: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "from_hub": self.from_hub, "to_hub": self.to_hub}
        if self.through:
            out["through"] = list(self.through)
        return out


@dataclass(frozen=True)
class RuleSpec:
    kind: str = "zscore"
    lookback: int = 20
    entry_z: float = 2.0
    exit_z: float = 0.5
    low: float | None = None
    high: float | None = None
    #: Cost per MWh per position change; None: half the held bid/offer, else zero (stated).
    cost_per_mwh: float | None = None
    #: ``next_close`` (default) or ``same_close``.
    execution: str = "next_close"

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "lookback": self.lookback, "entry_z": self.entry_z,
                "exit_z": self.exit_z, "low": self.low, "high": self.high,
                "cost_per_mwh": self.cost_per_mwh, "execution": self.execution}


@dataclass(frozen=True)
class StrategySpec:
    kind: str
    legs: tuple[SpecLeg, ...]
    unit: str | None = None
    fx: str = "forward"
    cost: RouteCostSpec | None = None
    rule: RuleSpec | None = None
    lookback_days: int = 365
    volume_mwh_per_day: float | None = None
    version: int = SPEC_VERSION
    issues: tuple[Issue, ...] = field(default_factory=tuple, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "kind": self.kind,
            "legs": [leg.as_dict() for leg in self.legs],
            "unit": self.unit,
            "fx": self.fx,
            "cost": self.cost.as_dict() if self.cost else None,
            "rule": self.rule.as_dict() if self.rule else None,
            "lookback_days": self.lookback_days,
            "volume_mwh_per_day": self.volume_mwh_per_day,
        }

    @property
    def sell_hub(self) -> str | None:
        """The leg with the largest positive weight (where gas is sold)."""

        positive = [leg for leg in self.legs if leg.weight > 0]
        return max(positive, key=lambda leg: leg.weight).hub if positive else None

    @property
    def buy_hub(self) -> str | None:
        negative = [leg for leg in self.legs if leg.weight < 0]
        return min(negative, key=lambda leg: leg.weight).hub if negative else None


def _number(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float("inf") else default


def spec_from_dict(data: Any) -> StrategySpec:
    """Read a spec from JSON-shaped data; problems become ``issues`` (never an exception).

    Unknown keys are ignored (a model may add commentary); anything that cannot be read is an
    issue with the field it concerns.
    """

    issues: list[Issue] = []
    if not isinstance(data, dict):
        return StrategySpec("curve", (), issues=(Issue("spec_unreadable", "spec",
                                                       "the description could not be read"),))
    version = int(_number(data.get("version"), SPEC_VERSION) or SPEC_VERSION)
    if version != SPEC_VERSION:
        issues.append(Issue("spec_version", "version", f"spec version {version} is not known"))
    kind = str(data.get("kind") or "curve").strip().lower()
    if kind not in KINDS:
        issues.append(Issue("kind_unknown", "kind", f"'{kind}' is not a study kind",
                            choices=KINDS))
        kind = "curve"
    legs: list[SpecLeg] = []
    for index, raw in enumerate(data.get("legs") or []):
        if not isinstance(raw, dict):
            continue
        hub = str(raw.get("hub") or raw.get("instrument") or "").split(":")[0].strip().upper()
        tenor_raw = raw.get("tenor")
        if not tenor_raw and ":" in str(raw.get("instrument") or ""):
            tenor_raw = str(raw.get("instrument")).split(":", 1)[1]
        weight = _number(raw.get("weight"), None)
        if not hub:
            issues.append(Issue("leg_hub_missing", f"legs[{index}].hub", "a leg names no hub"))
            continue
        if weight is None or weight == 0:
            issues.append(Issue("leg_weight", f"legs[{index}].weight",
                                f"{hub}: a leg needs a non-zero weight (+1 sell, −1 buy)"))
            weight = 1.0 if index == 0 else -1.0
        legs.append(SpecLeg(hub, float(weight), str(tenor_raw).strip() if tenor_raw else None))
    if len(legs) < 2:
        issues.append(Issue("legs_too_few", "legs", "a spread needs two legs"))
    if len(legs) > MAX_LEGS:
        issues.append(Issue("legs_too_many", "legs", f"at most {MAX_LEGS} legs"))
        legs = legs[:MAX_LEGS]
    fx = str(data.get("fx") or "forward").strip().lower()
    if fx not in FX_MODES:
        issues.append(Issue("fx_mode", "fx", f"'{fx}' is not an FX choice", choices=FX_MODES))
        fx = "forward"
    unit = data.get("unit")
    unit = str(unit).strip() if unit else None
    cost = None
    raw_cost = data.get("cost")
    if isinstance(raw_cost, dict) and raw_cost:
        from_hub = str(raw_cost.get("from_hub") or "").strip().upper()
        to_hub = str(raw_cost.get("to_hub") or "").strip().upper()
        hubs = {leg.hub for leg in legs}
        if not from_hub or not to_hub or from_hub == to_hub:
            issues.append(Issue("cost_direction", "cost", "the route needs two different hubs"))
        elif not {from_hub, to_hub} <= hubs:
            issues.append(Issue("cost_hubs", "cost",
                                f"the route {from_hub} → {to_hub} is not between the legs",
                                choices=tuple(sorted(hubs))))
        else:
            raw_through = raw_cost.get("through") or ()
            through = tuple(
                str(code).strip().upper()
                for code in (raw_through if isinstance(raw_through, list | tuple) else ())
                if str(code).strip()
            )[:4]
            cost = RouteCostSpec(from_hub, to_hub, through=through)
    rule = None
    raw_rule = data.get("rule")
    if isinstance(raw_rule, dict) and raw_rule:
        rule_kind = str(raw_rule.get("kind") or "zscore").lower()
        if rule_kind not in RULE_KINDS:
            issues.append(Issue("rule_kind", "rule.kind", f"'{rule_kind}' is not a rule",
                                choices=RULE_KINDS))
            rule_kind = "zscore"
        lookback = int(_number(raw_rule.get("lookback"), 20) or 20)
        if not 5 <= lookback <= 250:
            issues.append(Issue("rule_lookback", "rule.lookback", "lookback must be 5–250 days"))
            lookback = min(max(lookback, 5), 250)
        execution = str(raw_rule.get("execution") or "next_close")
        if execution not in EXECUTIONS:
            issues.append(Issue("rule_execution", "rule.execution",
                                f"'{execution}' is not an execution choice", choices=EXECUTIONS))
            execution = "next_close"
        rule_cost = _number(raw_rule.get("cost_per_mwh"))
        if rule_cost is not None and not 0 <= rule_cost <= 100:
            issues.append(Issue("rule_cost", "rule.cost_per_mwh", "cost must be 0–100 per MWh"))
            rule_cost = None
        exit_z = _number(raw_rule.get("exit_z"), 0.5)
        rule = RuleSpec(
            rule_kind,
            lookback,
            _number(raw_rule.get("entry_z"), 2.0) or 2.0,
            0.5 if exit_z is None else exit_z,
            _number(raw_rule.get("low")),
            _number(raw_rule.get("high")),
            rule_cost,
            execution,
        )
        if rule_kind == "threshold" and (
            rule.low is None or rule.high is None or not rule.low < rule.high
        ):
            issues.append(Issue(
                "rule_levels", "rule.low",
                "a threshold rule needs a level to buy the spread at and a higher one to sell "
                "it at; which levels?",
            ))
        if kind == "curve":
            issues.append(Issue("rule_needs_history", "kind",
                                "a rule runs on a history: study the history instead?",
                                choices=("history",)))
    lookback_days = int(_number(data.get("lookback_days"), 365) or 365)
    lookback_days = min(max(lookback_days, 30), 3650)
    volume = _number(data.get("volume_mwh_per_day"))
    if volume is not None and volume <= 0:
        issues.append(Issue("volume", "volume_mwh_per_day", "volume must be positive"))
        volume = None
    return StrategySpec(kind, tuple(legs), unit, fx, cost, rule, lookback_days, volume,
                        SPEC_VERSION, tuple(issues))
