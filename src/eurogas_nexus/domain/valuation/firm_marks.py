"""The firm's own price marks per hub and delivery period.

A mark is what the desk itself says a hub and month is worth. It is the customer's figure,
not a market price, so its class is always ``firm_mark``: there is no field that could make
it ``sourced``, and every reader receives the class from :data:`FIRM_MARK_CLASS`. Marks are
kept in the hub's native quotation (NBP in pence per therm, continental hubs in EUR/MWh) and
converted only through the unit authority (``domain/market/units.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from eurogas_nexus.domain.market.units import (
    PRICE_UNITS,
    UnitConversionError,
    canonical_price_unit,
)
from eurogas_nexus.domain.ontology.markets import european_gas_hubs
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod, PeriodError
from eurogas_nexus.domain.valuation.quality import InputClass

#: The class of every firm mark, wherever it is read.
FIRM_MARK_CLASS = InputClass.FIRM_MARK

#: Plausibility bounds per MWh-equivalent quotation; a mark outside is a typing error.
_BOUNDS = (Decimal("-500"), Decimal("5000"))


class FirmMarkError(ValueError):
    """A mark the desk cannot store; ``code`` names the rule."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FirmMark:
    """One stored mark."""

    mark_id: str
    hub: str
    period: DeliveryPeriod
    value: Decimal
    unit: str
    currency: str
    entered_by: str
    entered_at_utc: datetime
    note: str = ""

    @property
    def input_class(self) -> InputClass:
        """Always ``firm_mark``."""

        return FIRM_MARK_CLASS


@dataclass(frozen=True)
class FirmMarkEntry:
    """A validated mark before it is stored."""

    hub: str
    period: DeliveryPeriod
    value: Decimal
    unit: str
    currency: str
    note: str = ""


def validate_firm_mark(
    hub: str, period: str, value: object, unit: str, note: str = ""
) -> FirmMarkEntry:
    """Check one grid cell (hub x period, native unit).

    Raises:
        FirmMarkError: unknown hub, period, unit, a non-number or an implausible value.
    """

    code = (hub or "").strip().upper()
    if code not in european_gas_hubs(include_superseded=True):
        raise FirmMarkError("unknown_hub", f"{hub!r} is not a European gas hub")
    try:
        parsed = DeliveryPeriod.parse(period)
    except PeriodError as exc:
        raise FirmMarkError("period_invalid", str(exc)) from exc
    try:
        canonical = canonical_price_unit(unit)
    except UnitConversionError as exc:
        raise FirmMarkError("unit_invalid", str(exc)) from exc
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FirmMarkError("value_not_a_number", "a mark is a number") from exc
    if not number.is_finite():
        raise FirmMarkError("value_not_a_number", "a mark is a finite number")
    low, high = _BOUNDS
    if not low <= number <= high:
        raise FirmMarkError("value_implausible", f"a mark must lie between {low} and {high}")
    if len(note) > 200:
        raise FirmMarkError("note_invalid", "a note is at most 200 characters")
    return FirmMarkEntry(
        hub=code,
        period=parsed,
        value=number,
        unit=canonical,
        currency=PRICE_UNITS[canonical][0],
        note=note.strip(),
    )
