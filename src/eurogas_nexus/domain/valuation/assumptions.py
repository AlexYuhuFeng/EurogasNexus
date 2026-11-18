"""The firm's assumption sets: the inputs a desk supplies that no publication gives.

A set is named and owned by the organisation or by one book; its values change only by a
new version. A version is a draft until a second person approves it (four eyes), and only
an approved version in force at the evaluation instant is read by a valuation snapshot.
Every value is typed: a key from the catalogue below, a number, its unit, its currency
where the unit is money, an optional stated range (the sensitivity reads it) and a note.

An assumption is never shown as data: whatever reads it receives the class
``assumption`` (``domain/valuation/quality.py``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from eurogas_nexus.domain.ontology.currency import CURRENCIES


class ReviewState(StrEnum):
    """Review state of one assumption-set version."""

    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"


class AssumptionError(ValueError):
    """An assumption value outside its catalogue entry; ``code`` names the rule."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AssumptionSpec:
    """What one catalogue key accepts."""

    key: str
    label: str
    #: Unit text; ``{ccy}`` stands for the value's currency (money units).
    unit: str
    low: Decimal
    high: Decimal
    used_by: str

    @property
    def needs_currency(self) -> bool:
        """Whether the unit is money and the value must name its currency."""

        return "{ccy}" in self.unit

    def unit_for(self, currency: str | None) -> str:
        """The concrete unit text for a value."""

        return self.unit.replace("{ccy}", currency or "")


def _spec(key: str, label: str, unit: str, low: str, high: str, used_by: str) -> AssumptionSpec:
    return AssumptionSpec(key, label, unit, Decimal(low), Decimal(high), used_by)


#: The keys a firm may set. A new input is added here first, with its unit and bounds.
ASSUMPTION_CATALOGUE: dict[str, AssumptionSpec] = {
    spec.key: spec
    for spec in (
        _spec("financing.rate", "Financing rate", "%/yr", "-5", "50", "time spreads, cargo cash"),
        _spec(
            "capacity.load_factor",
            "Load factor on booked capacity",
            "%",
            "1",
            "100",
            "transport tariffs per MWh",
        ),
        _spec(
            "transport.fuel_shrinkage",
            "Fuel and shrinkage (where not published)",
            "%",
            "0",
            "10",
            "locational spreads",
        ),
        _spec("storage.capacity_fee", "Storage capacity fee", "{ccy}/MWh", "0", "100", "storage"),
        _spec("storage.injection_fee", "Storage injection fee", "{ccy}/MWh", "0", "50", "storage"),
        _spec(
            "storage.withdrawal_fee",
            "Storage withdrawal fee",
            "{ccy}/MWh",
            "0",
            "50",
            "storage",
        ),
        _spec("storage.fuel", "Storage fuel", "%", "0", "10", "storage"),
        _spec("lng.charter_hire", "Charter hire", "{ccy}/day", "0", "1000000", "cargo"),
        _spec("lng.boil_off", "Boil-off", "%/day", "0", "1", "cargo"),
        _spec("lng.port_costs", "Port costs per call", "{ccy}/cargo", "0", "10000000", "cargo"),
        _spec("lng.freight", "Freight", "{ccy}/MMBtu", "0", "20", "cargo"),
        _spec("lng.cargo_size", "Cargo size", "MMBtu", "100000", "5000000", "cargo"),
        _spec("lng.speed", "Service speed", "kn", "8", "22", "cargo"),
        _spec("lng.ballast_fuel", "Ballast fuel", "MMBtu/day", "0", "10000", "cargo"),
        _spec("lng.insurance", "Cargo insurance", "%", "0", "2", "cargo"),
        _spec("lng.fob_slope", "FOB formula slope", "x HH", "0", "3", "cargo"),
        _spec("lng.fob_fee", "FOB formula constant", "{ccy}/MMBtu", "-5", "10", "cargo"),
    )
}

#: The set name, key and note text a person may enter: short, printable, no markup.
_TEXT = re.compile(r"^[^<>\x00-\x1f]*$")


@dataclass(frozen=True)
class AssumptionValue:
    """One typed value of one assumption-set version."""

    key: str
    value: Decimal
    unit: str
    currency: str | None = None
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    note: str = ""


@dataclass(frozen=True)
class AssumptionSetVersion:
    """One version of a set, with who set and who approved it."""

    set_id: str
    name: str
    version: int
    book_id: str | None
    effective_from: date
    effective_to: date | None
    review_state: ReviewState
    created_by: str
    created_at_utc: datetime
    approved_by: str | None
    approved_at_utc: datetime | None
    values: tuple[AssumptionValue, ...]

    def in_force(self, day: date) -> bool:
        """Whether this version may be read for a valuation on ``day``."""

        return (
            self.review_state is ReviewState.APPROVED
            and self.effective_from <= day
            and (self.effective_to is None or day < self.effective_to)
        )

    def value(self, key: str) -> AssumptionValue | None:
        """The value of one key, or ``None`` when the set does not hold it."""

        return next((item for item in self.values if item.key == key), None)


def _decimal(raw: object, field: str) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise AssumptionError("value_not_a_number", f"{field} is not a number") from exc
    if not value.is_finite():
        raise AssumptionError("value_not_a_number", f"{field} is not a finite number")
    return value


def validate_assumption_value(
    key: str,
    value: object,
    *,
    currency: str | None = None,
    range_low: object = None,
    range_high: object = None,
    note: str = "",
) -> AssumptionValue:
    """Check one value against its catalogue entry and return it typed.

    Raises:
        AssumptionError: unknown key, missing or unknown currency, value or range outside
            the catalogue bounds, an inverted range, or a value outside its own range.
    """

    spec = ASSUMPTION_CATALOGUE.get(key)
    if spec is None:
        raise AssumptionError("unknown_assumption_key", f"unknown assumption key {key!r}")
    number = _decimal(value, key)
    code = (currency or "").strip().upper() or None
    if spec.needs_currency:
        if code is None or code not in CURRENCIES:
            raise AssumptionError("currency_required", f"{key} needs an ISO currency")
    elif code is not None:
        raise AssumptionError("currency_not_applicable", f"{key} is not a money value")
    if not spec.low <= number <= spec.high:
        raise AssumptionError(
            "value_out_of_bounds", f"{key} must be between {spec.low} and {spec.high}"
        )
    low = None if range_low is None else _decimal(range_low, f"{key} range low")
    high = None if range_high is None else _decimal(range_high, f"{key} range high")
    if low is not None and high is not None and low > high:
        raise AssumptionError("range_inverted", f"{key} range low is above its high")
    if (low is not None and number < low) or (high is not None and number > high):
        raise AssumptionError("value_outside_range", f"{key} lies outside its stated range")
    if len(note) > 400 or not _TEXT.match(note):
        raise AssumptionError("note_invalid", "a note is plain text of at most 400 characters")
    return AssumptionValue(
        key=key,
        value=number,
        unit=spec.unit_for(code),
        currency=code,
        range_low=low,
        range_high=high,
        note=note.strip(),
    )


def validate_set_name(name: str) -> str:
    """A set name: 1-80 printable characters.

    Raises:
        AssumptionError: ``name_invalid``.
    """

    text = (name or "").strip()
    if not 1 <= len(text) <= 80 or not _TEXT.match(text):
        raise AssumptionError("name_invalid", "a set name is 1-80 printable characters")
    return text


def values_digest(values: Iterable[AssumptionValue]) -> str:
    """SHA-256 of a version's values in canonical form.

    The audit trail records this digest and the keys changed, never the values: an
    assumption such as a charter hire is commercially sensitive, and the audit log is read
    by platform administrators who hold no commercial permission.
    """

    canonical = sorted(
        (
            item.key,
            str(item.value),
            item.unit,
            item.currency or "",
            "" if item.range_low is None else str(item.range_low),
            "" if item.range_high is None else str(item.range_high),
        )
        for item in values
    )
    return hashlib.sha256(json.dumps(canonical).encode("utf-8")).hexdigest()


def changed_keys(before: Iterable[AssumptionValue], after: Iterable[AssumptionValue]) -> list[str]:
    """Keys added, removed or changed between two versions (for the audit summary)."""

    old = {item.key: item for item in before}
    new = {item.key: item for item in after}
    return sorted(key for key in old.keys() | new.keys() if old.get(key) != new.get(key))
