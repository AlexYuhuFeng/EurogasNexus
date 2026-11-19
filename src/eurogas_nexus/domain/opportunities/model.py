"""The opportunity object (design basis 2, section B.2), typed end to end.

Figures are :class:`Measure` values: a :class:`~decimal.Decimal` and its unit (``EUR/MWh``,
``MWh``, ``EUR``, ``%``). A money amount is a measure whose unit is an ISO currency; no field
name carries a currency. The arithmetic is a list of :class:`Leg` rows: ``term`` rows carry a
signed ``contribution`` in the headline's unit and must sum to the headline exactly
(:func:`reconcile`); ``subtotal`` rows state the running total; ``conversion`` rows state an
FX or unit conversion applied to the term above them; ``result`` states the headline; and
``volume``/``value`` rows state the executable volume and ``value = headline x volume``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from eurogas_nexus.domain.ontology.currency import CURRENCIES
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass, weakest
from eurogas_nexus.domain.valuation.snapshot import SnapshotInput, dependency_key


class OpportunityType(StrEnum):
    """The opportunity types of design B.3."""

    LOCATIONAL = "locational"
    UNUSED_CAPACITY = "unused_capacity"
    TIME_SPREAD = "time_spread"
    REROUTE = "reroute"
    SELL_DOWN = "sell_down"
    HEDGE_GAP = "hedge_gap"
    TERMINAL_CHOICE = "terminal_choice"
    ORIGIN = "origin"
    EVENT_EXPOSURE = "event_exposure"
    #: Prompt or time arbitrage at one hub (within-day vs day-ahead, day-ahead vs weekend or
    #: balance of month): a market item, never on the book. Code "P": "A" is the design's
    #: cargo-origin type.
    PROMPT_ARBITRAGE = "prompt_arbitrage"


#: The letter each type carries in the design (B.3).
TYPE_CODE: dict[OpportunityType, str] = {
    OpportunityType.LOCATIONAL: "L",
    OpportunityType.UNUSED_CAPACITY: "C",
    OpportunityType.TIME_SPREAD: "T",
    OpportunityType.REROUTE: "R",
    OpportunityType.SELL_DOWN: "S",
    OpportunityType.HEDGE_GAP: "G",
    OpportunityType.TERMINAL_CHOICE: "D",
    OpportunityType.ORIGIN: "A",
    OpportunityType.EVENT_EXPOSURE: "E",
    OpportunityType.PROMPT_ARBITRAGE: "P",
}


class Lane(StrEnum):
    """The lanes, never mixed (B.5), and the market lane below them: opportunities that need
    no existing position ("in the market, not on your book"), never in must act."""

    MUST_ACT = "must_act"
    COULD_ACT = "could_act"
    MARKET = "market"


#: Obligation or risk: ordered by deadline, then size. Everything else is margin.
MUST_ACT_TYPES: frozenset[OpportunityType] = frozenset(
    {OpportunityType.HEDGE_GAP, OpportunityType.EVENT_EXPOSURE, OpportunityType.SELL_DOWN}
)


def lane_of(kind: OpportunityType) -> Lane:
    """The lane a type is listed in."""

    return Lane.MUST_ACT if kind in MUST_ACT_TYPES else Lane.COULD_ACT


class OpportunityState(StrEnum):
    """System state of a stored opportunity (B.5 plus its lifecycle).

    ``actionable``, ``watch`` and ``blocked`` are the existing intraday engine's three states
    (``ACTIONABLE_REVIEW``, ``WATCH``, ``BLOCKED``) generalised; ``indicative`` is the cap for
    an opportunity standing on a firm's mark, a settlement, an assumption or (on a demo desk)
    a simulated input; ``new`` is seen once and not yet shown; ``expired`` and ``converted``
    have left the list. Dismissal and following are per person, not system states.
    """

    NEW = "new"
    ACTIONABLE = "actionable"
    INDICATIVE = "indicative"
    WATCH = "watch"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    CONVERTED = "converted"


#: The existing intraday engine's states, as the core names them.
INTRADAY_STATE: dict[str, OpportunityState] = {
    "ACTIONABLE_REVIEW": OpportunityState.ACTIONABLE,
    "WATCH": OpportunityState.WATCH,
    "BLOCKED": OpportunityState.BLOCKED,
}

LISTED_STATES = frozenset({OpportunityState.ACTIONABLE, OpportunityState.INDICATIVE})
ENDED_STATES = frozenset({OpportunityState.EXPIRED, OpportunityState.CONVERTED})


class LegKind(StrEnum):
    """Role of one arithmetic row."""

    TERM = "term"
    SUBTOTAL = "subtotal"
    CONVERSION = "conversion"
    RESULT = "result"
    VOLUME = "volume"
    VALUE = "value"


class CheckKind(StrEnum):
    """The checks of B.2."""

    CAPACITY = "capacity"
    LIMIT = "limit"
    CREDIT = "credit"
    MANDATE = "mandate"
    OUTAGE = "outage"
    CONTRACT = "contract"


class CheckResult(StrEnum):
    """A check's outcome; ``not_assessed`` is a state, never a pass."""

    PASS = "pass"
    FAIL = "fail"
    NOT_ASSESSED = "not_assessed"


class DismissReason(StrEnum):
    """Why a person dismissed an opportunity (counted per type to tune thresholds)."""

    NOT_EXECUTABLE = "not_executable"
    ALREADY_COVERED = "already_covered"
    MARGIN_TOO_THIN = "margin_too_thin"
    DATA_WRONG = "data_wrong"
    OUTSIDE_MANDATE = "outside_mandate"
    NOT_RELEVANT = "not_relevant"
    OTHER = "other"


# --------------------------------------------------------------------------- figures


@dataclass(frozen=True)
class Measure:
    """A number with its unit; money is a measure whose unit is an ISO currency."""

    value: Decimal
    unit: str

    @property
    def currency(self) -> str | None:
        """The currency of a money amount or of a price per unit (``EUR/MWh`` is EUR)."""

        head = self.unit.split("/")[0]
        return head if head in CURRENCIES else None

    @property
    def is_money(self) -> bool:
        """Whether this is an amount of money (unit is a bare currency code)."""

        return self.unit in CURRENCIES

    def to_json(self) -> dict[str, Any]:
        """``{"value": "<decimal text>", "unit": ..., "currency": ...}``."""

        return {"value": decimal_text(self.value), "unit": self.unit, "currency": self.currency}


def decimal_text(value: Decimal | None) -> str | None:
    """A decimal as plain text without exponent or trailing zeros."""

    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


# --------------------------------------------------------------------------- parts


@dataclass(frozen=True)
class Leg:
    """One row of the arithmetic."""

    kind: LegKind
    label_key: str
    label: str
    quantity: Measure | None = None
    rate: Measure | None = None
    fx: Measure | None = None
    contribution: Measure | None = None
    subtotal: Measure | None = None
    input_class: InputClass | None = None
    source_family: str | None = None
    source_ref: str = ""
    as_of_utc: datetime | None = None
    input_keys: tuple[str, ...] = ()
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        """The row as the API and the frozen case evidence carry it."""

        def measure(item: Measure | None) -> dict[str, Any] | None:
            return None if item is None else item.to_json()

        return {
            "kind": self.kind.value,
            "label_key": self.label_key,
            "label": self.label,
            "quantity": measure(self.quantity),
            "rate": measure(self.rate),
            "fx": measure(self.fx),
            "contribution": measure(self.contribution),
            "subtotal": measure(self.subtotal),
            "input_class": None if self.input_class is None else self.input_class.value,
            "source_family": self.source_family,
            "source_ref": self.source_ref,
            "as_of_utc": None if self.as_of_utc is None else self.as_of_utc.isoformat(),
            "input_keys": list(self.input_keys),
            "note": self.note,
        }


@dataclass(frozen=True)
class AssumptionUse:
    """An assumption on the value path: its value, who set it, its date. Never data."""

    key: str
    value: Measure
    origin: str  # "public" | "firm_set" | "user"
    set_by: str
    set_at_utc: str
    input_key: str
    range_low: Decimal | None = None
    range_high: Decimal | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialised form."""

        return {
            "key": self.key,
            "value": self.value.to_json(),
            "origin": self.origin,
            "set_by": self.set_by,
            "set_at_utc": self.set_at_utc,
            "input_key": self.input_key,
            "range_low": decimal_text(self.range_low),
            "range_high": decimal_text(self.range_high),
        }


@dataclass(frozen=True)
class Falsifier:
    """A testable statement that would make the claim untrue."""

    key: str
    text: str

    def to_json(self) -> dict[str, Any]:
        """Serialised form."""

        return {"key": self.key, "text": self.text}


@dataclass(frozen=True)
class Sensitivity:
    """A computed sensitivity: ``breakeven``, ``per_unit``, ``range_low`` or ``range_high``."""

    driver: str
    kind: str
    value: Measure
    text: str

    def to_json(self) -> dict[str, Any]:
        """Serialised form."""

        return {
            "driver": self.driver,
            "kind": self.kind,
            "value": self.value.to_json(),
            "text": self.text,
        }


@dataclass(frozen=True)
class Check:
    """One check with the figure behind its result."""

    kind: CheckKind
    result: CheckResult
    figure: str
    reference: str = ""

    def to_json(self) -> dict[str, Any]:
        """Serialised form."""

        return {
            "kind": self.kind.value,
            "result": self.result.value,
            "figure": self.figure,
            "reference": self.reference,
        }


@dataclass(frozen=True)
class Blocker:
    """Why something cannot be evaluated: the single missing thing, named, and its fix."""

    code: str
    subject: str
    text: str
    fix: str = ""

    def to_json(self) -> dict[str, Any]:
        """Serialised form."""

        return {"code": self.code, "subject": self.subject, "text": self.text, "fix": self.fix}


# --------------------------------------------------------------------------- the candidate


@dataclass(frozen=True)
class Candidate:
    """What an evaluator returns: a complete opportunity before controls and lifecycle.

    ``identity`` names the legs (contract, hubs, points, side), so that together with type,
    delivery period and books it forms the dedupe key (B.6). ``inputs`` are the snapshot
    inputs on the value path: they decide the data-quality class, staleness and the
    dependency keys.
    """

    type: OpportunityType
    identity: tuple[str, ...]
    period: DeliveryPeriod
    book_ids: tuple[str, ...]
    claim_key: str
    claim_fields: Mapping[str, str]
    headline: Measure
    legs: tuple[Leg, ...]
    falsifiers: tuple[Falsifier, ...]
    expires_at_utc: datetime
    inputs: tuple[SnapshotInput, ...]
    evaluator: str
    evaluator_version: str
    volume: Measure | None = None
    value: Measure | None = None
    #: The value in the threshold currency (EUR) when the evaluator could convert it.
    value_eur: Measure | None = None
    #: The net margin in EUR/MWh when the evaluator could convert it.
    margin_eur: Measure | None = None
    assumptions: tuple[AssumptionUse, ...] = ()
    sensitivity: tuple[Sensitivity, ...] = ()
    checks: tuple[Check, ...] = ()
    blockers: tuple[Blocker, ...] = ()
    deadline_utc: datetime | None = None
    #: Inputs for the margin floor of B.6: total route cost and half the bid-offer of both
    #: legs (EUR/MWh), and the FX tolerance carried into the spread (D.5).
    route_cost_eur: Measure | None = None
    half_spread_eur: Measure | None = None
    fx_tolerance_eur: Measure | None = None
    #: Inputs classified ``internal`` (own unpublished facts) never feed a margin type.
    internal_inputs: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)
    #: ``book`` (bounded by a position, a contract or capacity held) or ``market`` (a market
    #: dislocation the firm holds nothing in: the market lane).
    scope: str = "book"

    @property
    def lane(self) -> Lane:
        """Must act or could act."""

        return Lane.MARKET if self.scope == "market" else lane_of(self.type)

    @property
    def key(self) -> str:
        """Dedupe key: type, legs, delivery period and books (B.6)."""

        payload = json.dumps(
            [self.type.value, list(self.identity), self.period.label, sorted(self.book_ids)]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]

    @property
    def quality(self) -> InputClass:
        """The weakest class on the value path."""

        return weakest(item.input_class for item in self.inputs)

    @property
    def simulated(self) -> bool:
        """Whether any value-path input is simulated."""

        return any(item.input_class is InputClass.SIMULATED for item in self.inputs)

    @property
    def source_families(self) -> tuple[str, ...]:
        """Entitlement families of the value-path inputs (a reader needs all of them)."""

        return tuple(sorted({item.source_family for item in self.inputs if item.source_family}))

    @property
    def dependency_keys(self) -> tuple[str, ...]:
        """What would invalidate it (design J.2), stored from the first release."""

        keys = {dependency_key(item) for item in self.inputs}
        return tuple(sorted(key for key in keys if key))


# --------------------------------------------------------------------------- reconciliation


class ReconciliationError(ValueError):
    """The legs do not add up to the headline (an evaluator defect, never shown)."""


def reconcile(candidate: Candidate) -> None:
    """Check the arithmetic: terms sum to the headline, subtotals run, value = headline x volume.

    Raises:
        ReconciliationError: naming the first rule broken.
    """

    unit = candidate.headline.unit
    running = Decimal(0)
    terms = 0
    for leg in candidate.legs:
        if leg.kind is LegKind.TERM:
            if leg.contribution is None or leg.contribution.unit != unit:
                raise ReconciliationError(f"term {leg.label_key!r} has no {unit} contribution")
            running += leg.contribution.value
            terms += 1
        elif leg.kind in {LegKind.SUBTOTAL, LegKind.RESULT}:
            if leg.subtotal is None or leg.subtotal.unit != unit:
                raise ReconciliationError(f"{leg.kind.value} {leg.label_key!r} has no subtotal")
            if leg.subtotal.value != running:
                raise ReconciliationError(
                    f"{leg.label_key!r} states {leg.subtotal.value}, the terms sum to {running}"
                )
        elif leg.contribution is not None:
            raise ReconciliationError(f"{leg.kind.value} row {leg.label_key!r} contributes")
    if terms == 0:
        raise ReconciliationError("no term rows")
    if running != candidate.headline.value:
        raise ReconciliationError(f"terms sum to {running}, headline {candidate.headline.value}")
    results = [index for index, leg in enumerate(candidate.legs) if leg.kind is LegKind.RESULT]
    if len(results) != 1:
        raise ReconciliationError("exactly one result row")
    after = {leg.kind for leg in candidate.legs[results[0] + 1 :]}
    if after - {LegKind.VOLUME, LegKind.VALUE}:
        raise ReconciliationError("only the volume and value rows follow the result")
    if candidate.value is not None:
        if candidate.volume is None:
            raise ReconciliationError("a value needs its volume")
        expected = (candidate.headline.value * candidate.volume.value).quantize(
            candidate.value.value
        )
        if expected != candidate.value.value:
            raise ReconciliationError(f"value {candidate.value.value} != headline x volume")
