"""Active Context and time basis for application projections (Architecture V2 Wave 5).

Every projection answers one question: *what is true, on one explicit time
basis, as of one instant?* This module owns that declaration so no projection
module re-derives it and no client has to guess it.

Reused repository vocabulary (nothing is re-invented here):

- the time-basis vocabulary is ``domain.data_platform.products.TimeBasis``
  (Architecture V2 Wave 4 declaration);
- gas-day boundaries come from ``domain.market.gas_day`` (the single backend
  implementation of the CAM gas day, DST-correct and versioned);
- the as-of instant is a plain aware UTC ``datetime`` in the same ISO form the
  rest of the ``/api`` surface already returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.data_platform.products import TimeBasis
from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_interval_utc,
    gas_day_label,
    gas_day_start_for_date,
)


class GasDayInputError(ValueError):
    """Raised when a caller-supplied gas day is not an ISO calendar date.

    The projection routes translate this into a 422 ``gas_day_invalid``
    response instead of silently substituting a different day.
    """


@dataclass(frozen=True, slots=True)
class ProjectionContext:
    """The Active Context one projection payload is expressed against.

    Attributes:
        as_of_utc: The single evaluation instant every slice is measured and
            evaluated against (also the freshness evaluation clock).
        basis: The declared time basis of every value in the payload.
        gas_day: ISO label of the gas day containing ``as_of_utc`` (or the gas
            day the caller explicitly asked for).
        gas_day_calendar: Frozen gas-day calendar version id.
        gas_day_start_utc: ISO UTC start of that gas day.
        gas_day_end_utc: ISO UTC end (exclusive) of that gas day.
        delivery_product: Declared delivery product, or ``None``.
        hub: Declared hub, or ``None``.
    """

    as_of_utc: datetime
    basis: TimeBasis
    gas_day: str
    gas_day_calendar: str
    gas_day_start_utc: str
    gas_day_end_utc: str
    delivery_product: str | None = None
    hub: str | None = None

    def time_basis_payload(self) -> dict[str, Any]:
        """Return the ``time_basis`` block shared by data and envelope meta."""

        return {
            "basis": self.basis.value,
            "as_of_utc": self.as_of_utc.isoformat(),
            "gas_day": self.gas_day,
            "gas_day_calendar": self.gas_day_calendar,
            "gas_day_start_utc": self.gas_day_start_utc,
            "gas_day_end_utc": self.gas_day_end_utc,
            "delivery_product": self.delivery_product,
            "hub": self.hub,
        }

    def active_context_payload(self) -> dict[str, Any]:
        """Return the echoed Active Context (gas day / product / hub)."""

        return {
            "gas_day": self.gas_day,
            "gas_day_calendar": self.gas_day_calendar,
            "delivery_product": self.delivery_product,
            "hub": self.hub,
            "as_of_utc": self.as_of_utc.isoformat(),
        }

    def hub_key(self) -> str | None:
        """Return the case-insensitive comparison key for the declared hub."""

        return self.hub.casefold() if self.hub else None

    def product_key(self) -> str | None:
        """Return the case-insensitive comparison key for the declared product."""

        return self.delivery_product.casefold() if self.delivery_product else None


def resolve_projection_context(
    *,
    gas_day: str | None = None,
    delivery_product: str | None = None,
    hub: str | None = None,
    as_of_utc: datetime | None = None,
    now_utc: datetime | None = None,
    basis: TimeBasis = TimeBasis.AS_OF_INSTANT,
    gas_day_calendar: str = DEFAULT_GAS_DAY_CALENDAR,
) -> ProjectionContext:
    """Resolve one projection context from caller input.

    Args:
        gas_day: ISO calendar date of the gas day to select, or ``None`` to
            derive the gas day containing ``as_of_utc``.
        delivery_product: Declared delivery product, or ``None``.
        hub: Declared hub, or ``None``.
        as_of_utc: Explicit as-of instant; defaults to ``now_utc``.
        now_utc: Injectable clock; defaults to ``datetime.now(UTC)``.
        basis: Declared time basis of the payload.
        gas_day_calendar: Gas-day calendar version id.

    Returns:
        The resolved :class:`ProjectionContext`.

    Raises:
        GasDayInputError: When ``gas_day`` is not an ISO ``YYYY-MM-DD`` date.
    """

    as_of = _as_utc(as_of_utc or now_utc or datetime.now(UTC))
    if gas_day:
        selected = _parse_gas_day(gas_day)
        start = gas_day_start_for_date(selected, gas_day_calendar)
        end = gas_day_start_for_date(selected + timedelta(days=1), gas_day_calendar)
        label = selected.isoformat()
    else:
        start, end = gas_day_interval_utc(as_of, gas_day_calendar)
        label = gas_day_label(as_of, gas_day_calendar)
    return ProjectionContext(
        as_of_utc=as_of,
        basis=basis,
        gas_day=label,
        gas_day_calendar=gas_day_calendar,
        gas_day_start_utc=start.isoformat(),
        gas_day_end_utc=end.isoformat(),
        delivery_product=_clean(delivery_product),
        hub=_clean(hub),
    )


def _parse_gas_day(value: str) -> date:
    """Parse a caller-supplied gas day, failing closed on anything else."""

    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise GasDayInputError(
            f"gas_day must be an ISO calendar date (YYYY-MM-DD); received {value!r}."
        ) from exc


def _clean(value: str | None) -> str | None:
    """Trim an optional context string, treating blank as absent."""

    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _as_utc(value: datetime) -> datetime:
    """Normalize a timestamp to aware UTC (naive timestamps are UTC)."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
