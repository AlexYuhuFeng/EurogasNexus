"""False-positive controls (design basis 2, B.5 and B.6), each a separate, tested rule.

:func:`assess` turns one evaluator candidate into its system state:

1. **Simulated never mixes**: on a real desk a candidate with any simulated input is refused
   (not produced at all); on a demo desk it is capped at ``indicative`` and marked.
2. **Insider wall**: an internal (unpublished own) input never feeds a margin opportunity.
3. **Evaluator blockers** and **missing value-path inputs** -> ``blocked`` with the single
   missing thing named: a missing tariff reads "tariff not held at <point>".
4. **Failed check** -> ``blocked``.
5. **Stale input** -> ``blocked`` (refused, with the input and its age).
6. **Margin floor** (could-act lane): ``max(0.10 EUR/MWh, half bid-offer of both legs,
   10 % of total route cost)`` after all costs; **minimum value** EUR 10,000; a margin
   inside its FX tolerance; a check ``not assessed`` -> ``watch``.
7. **Input class cap**: a firm's mark (unless the organisation accepts marks), a
   settlement or mid (``indicative``), an assumption, or a simulated input on a demo desk
   -> at most ``indicative``.

Thresholds are organisation settings (decision L5 defaults).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.market.gas_day import gas_day_label
from eurogas_nexus.domain.opportunities.claims import render_claim
from eurogas_nexus.domain.opportunities.model import (
    Blocker,
    Candidate,
    CheckResult,
    Lane,
    Measure,
    OpportunityState,
    OpportunityType,
)
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import InputKind, SnapshotInput

#: Margin opportunity types an internal (unpublished) input may never feed (J.2 insider wall).
MARGIN_TYPES = frozenset(
    {
        OpportunityType.LOCATIONAL,
        OpportunityType.TIME_SPREAD,
        OpportunityType.TERMINAL_CHOICE,
        OpportunityType.ORIGIN,
        OpportunityType.UNUSED_CAPACITY,
        OpportunityType.REROUTE,
    }
)


@dataclass(frozen=True)
class Thresholds:
    """Organisation-tunable controls (decision L5 defaults)."""

    min_margin: Measure = field(default_factory=lambda: Measure(Decimal("0.10"), "EUR/MWh"))
    min_value: Measure = field(default_factory=lambda: Measure(Decimal("10000"), "EUR"))
    route_cost_share: Decimal = Decimal("0.10")
    max_per_lane: int = 7
    persistence: int = 2
    removal_after_misses: int = 2
    material_change: Decimal = Decimal("0.20")
    marks_actionable: bool = False
    assumption_set_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialised settings."""

        return {
            "min_margin": self.min_margin.to_json(),
            "min_value": self.min_value.to_json(),
            "route_cost_share": str(self.route_cost_share),
            "max_per_lane": self.max_per_lane,
            "persistence": self.persistence,
            "removal_after_misses": self.removal_after_misses,
            "material_change": str(self.material_change),
            "marks_actionable": self.marks_actionable,
            "assumption_set_id": self.assumption_set_id,
        }


class ThresholdError(ValueError):
    """A setting outside its bounds."""


_BOUNDS: dict[str, tuple[Decimal, Decimal]] = {
    "min_margin": (Decimal("0"), Decimal("10")),
    "min_value": (Decimal("0"), Decimal("10000000")),
    "route_cost_share": (Decimal("0"), Decimal("1")),
    "max_per_lane": (Decimal("1"), Decimal("20")),
    "persistence": (Decimal("1"), Decimal("5")),
    "removal_after_misses": (Decimal("1"), Decimal("5")),
    "material_change": (Decimal("0.01"), Decimal("1")),
}


def thresholds_from(values: dict[str, Any], base: Thresholds | None = None) -> Thresholds:
    """Validated settings over ``base`` (defaults when absent).

    Raises:
        ThresholdError: unknown key or a value outside its bounds.
    """

    current = base or Thresholds()
    changes: dict[str, Any] = {}
    for key, raw in values.items():
        if key == "marks_actionable":
            if not isinstance(raw, bool):
                raise ThresholdError("marks_actionable must be true or false")
            changes[key] = raw
            continue
        if key == "assumption_set_id":
            if raw is not None and (not isinstance(raw, str) or not 1 <= len(raw) <= 64):
                raise ThresholdError("assumption_set_id must be a set id or null")
            changes[key] = raw
            continue
        if key not in _BOUNDS:
            raise ThresholdError(f"unknown setting {key!r}")
        if isinstance(raw, dict):
            raw = raw.get("value")
        try:
            number = Decimal(str(raw))
        except Exception as exc:  # noqa: BLE001 - any parse failure is the same refusal
            raise ThresholdError(f"{key} must be a number") from exc
        low, high = _BOUNDS[key]
        if not number.is_finite() or not low <= number <= high:
            raise ThresholdError(f"{key} must be between {low} and {high}")
        if key == "min_margin":
            changes[key] = Measure(number, "EUR/MWh")
        elif key == "min_value":
            changes[key] = Measure(number, "EUR")
        elif key in {"max_per_lane", "persistence", "removal_after_misses"}:
            if number != number.to_integral_value():
                raise ThresholdError(f"{key} must be a whole number")
            changes[key] = int(number)
        else:
            changes[key] = number
    return replace(current, **changes)


@dataclass(frozen=True)
class Assessment:
    """The state a candidate earns this evaluation and why."""

    state: OpportunityState | None  # None: refused, not produced at all
    reasons: tuple[str, ...]
    blocker: Blocker | None = None
    claim_text: str = ""


# --------------------------------------------------------------------------- staleness


def _business_days_between(start: datetime, end: datetime) -> int:
    """Whole business days (Monday to Friday) after ``start`` up to ``end``."""

    day = start.date()
    count = 0
    while day < end.date():
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count


def stale_reason(item: SnapshotInput, as_of_utc: datetime, period_kind: str) -> str | None:
    """Why one held input is too old for an evaluation at ``as_of_utc`` (B.6), else ``None``.

    - a day-ahead or within-day price: the same gas day;
    - a forward price, FX or a rate: no older than one business day;
    - a tariff: in force for the delivery period (the reader only returns one that is);
    - capacity: the publication day, stated; an outage message is current until revised
      (the reader serves its latest version), so its age alone is not staleness;
    - an assumption and the book: as approved and recorded (no age rule).
    """

    if not item.held or item.as_of_utc is None:
        return None
    if item.kind is InputKind.PRICE and period_kind == "day":
        if gas_day_label(item.as_of_utc) != gas_day_label(as_of_utc):
            return f"{item.label or item.key}: priced on gas day {gas_day_label(item.as_of_utc)}"
        return None
    if item.kind in {InputKind.PRICE, InputKind.FX, InputKind.RATE}:
        if _business_days_between(item.as_of_utc, as_of_utc) > 1:
            return f"{item.label or item.key}: as of {item.as_of_utc.date().isoformat()}"
        return None
    # An outage message stands until its publisher revises or withdraws it, so its age is
    # not staleness (the reader always serves the latest version); capacity is a reading.
    if item.kind is InputKind.CAPACITY:
        if item.as_of_utc.date() < (as_of_utc - timedelta(days=1)).date():
            return f"{item.label or item.key}: published {item.as_of_utc.date().isoformat()}"
    return None


# --------------------------------------------------------------------------- assess


def _blocked(code: str, subject: str, detail: str = "", fix: str = "") -> Assessment:
    claim = render_claim(f"blocked.{code}", {"subject": subject, "detail": detail})
    return Assessment(
        OpportunityState.BLOCKED,
        (code,),
        Blocker(code=code, subject=subject, text=claim, fix=fix),
        claim,
    )


def _missing_blocker(item: SnapshotInput) -> Assessment:
    if item.kind is InputKind.TARIFF:
        subject = str(
            item.detail.get("point_name") or item.detail.get("point_id") or item.label or item.key
        )
        direction, gas_year = "", ""
        parts = item.key.split(":")
        if len(parts) >= 5:
            direction, gas_year = parts[2].lower(), parts[4]
        named = f"{subject} ({direction}, gas year {gas_year})" if direction else subject
        return _blocked(
            "tariff_not_held",
            named,
            fix="load the operator's tariff for the gas year (entsog-tariffs source)",
        )
    if item.kind is InputKind.PRICE:
        return _blocked(
            "price_missing",
            item.label or item.key,
            fix="connect a licensed price feed or enter the firm's mark",
        )
    return _blocked("input_missing", item.label or item.key, fix="supply the input")


def assess(
    candidate: Candidate,
    thresholds: Thresholds,
    *,
    as_of_utc: datetime,
    demo_desk: bool,
    render: Callable[[Candidate], str] | None = None,
) -> Assessment:
    """Apply the controls in order and return the candidate's state with its reasons."""

    claim = (render or (lambda c: render_claim(c.claim_key, c.claim_fields)))(candidate)
    # 1. Simulated never mixes with real.
    if candidate.simulated and not demo_desk:
        return Assessment(None, ("simulated_input_on_real_desk",))
    # 2. Insider wall.
    if candidate.internal_inputs and candidate.type in MARGIN_TYPES:
        return Assessment(None, ("internal_input_in_margin_type",))
    # 3. Blockers and missing inputs.
    if candidate.blockers:
        blocker = candidate.blockers[0]
        return Assessment(OpportunityState.BLOCKED, (blocker.code,), blocker, blocker.text)
    for item in candidate.inputs:
        if not item.held:
            return _missing_blocker(item)
    # 4. Failed check.
    for check in candidate.checks:
        if check.result is CheckResult.FAIL:
            return _blocked("check_failed", check.kind.value, check.figure)
    # 5. Staleness.
    for item in candidate.inputs:
        reason = stale_reason(item, as_of_utc, candidate.period.kind)
        if reason:
            return _blocked("input_stale", item.label or item.key, reason, fix="refresh it")
    reasons: list[str] = []
    state = OpportunityState.ACTIONABLE
    # 6. Margin floor, minimum value, FX tolerance, checks not assessed (could act only).
    if candidate.lane in (Lane.COULD_ACT, Lane.MARKET):
        margin = candidate.margin_eur
        floor = thresholds.min_margin.value
        if candidate.half_spread_eur is not None:
            floor = max(floor, candidate.half_spread_eur.value)
        if candidate.route_cost_eur is not None:
            floor = max(floor, thresholds.route_cost_share * candidate.route_cost_eur.value)
        if margin is None:
            reasons.append("margin_not_comparable_to_threshold")
        elif margin.value < floor:
            reasons.append("margin_below_minimum")
        if candidate.value_eur is None or candidate.value_eur.value < thresholds.min_value.value:
            reasons.append("value_below_minimum")
        if (
            margin is not None
            and candidate.fx_tolerance_eur is not None
            and abs(margin.value) < candidate.fx_tolerance_eur.value
        ):
            reasons.append("margin_within_fx_tolerance")
        if any(check.result is CheckResult.NOT_ASSESSED for check in candidate.checks):
            reasons.append("check_not_assessed")
        if reasons:
            state = OpportunityState.WATCH
    # 7. Input class cap.
    classes = {item.input_class for item in candidate.inputs}
    capped = {InputClass.INDICATIVE, InputClass.ASSUMPTION, InputClass.SIMULATED}
    if not thresholds.marks_actionable:
        capped.add(InputClass.FIRM_MARK)
    hits = sorted(klass.value for klass in classes & capped)
    if hits and state is OpportunityState.ACTIONABLE:
        state = OpportunityState.INDICATIVE
    reasons.extend(f"input_class_{klass}" for klass in hits)
    return Assessment(state, tuple(reasons), None, claim)
