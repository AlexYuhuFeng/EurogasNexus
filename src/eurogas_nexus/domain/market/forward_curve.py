"""Monthly forward curve per hub from the products a desk actually quotes.

Hubs trade months, quarters, seasons (Sum/Win) and calendar years; positions are held by
month. The curve gives every delivery month one price, consistent with every quoted
product: the energy-weighted average of the months inside a product equals that product's
price. A flat-rate product delivers the same MW every hour, so a month weighs by its
delivery hours, not its days: the gas day that loses an hour to summer time (March) has 23
and the one that gains it back (October) has 25, as the exchanges' contract volumes do
(Q1 = (744·Jan + 672·Feb + 743·Mar) / 2159).

Method, shortest product first:

1. A month quote is used as it is.
2. A longer product prices its months that no shorter quote has fixed. The residual
   ``(P·days − Σ fixed month prices·days) / remaining days`` is spread over those months:
   a quarter flat, a season or a year in proportion to a seasonal shape (relative monthly
   levels). The shape is the one given, else the curve's own: the levels the hub's quoted
   months and quarters put on each calendar month (``implied_shape``), so a winter season
   beyond the quoted quarters keeps the Q4/Q1 shape the quarters show.
3. A month no quote covers gets no price: the curve does not extrapolate, and no other
   product (a day-ahead or a balance-of-month close) stands in for it. With ``last_month``
   such a month is listed with ``method`` ``not_available``.
4. The current month, when unquoted, is priced by a balance-of-month quote (the product that
   delivers the rest of it), never by a day-ahead or weekend price.

Each point carries its ``basis`` in words (``quoted``, ``derived from Q1-27``, ``not
available``) and, when the quotes carry their dates, the quote's ``as_of`` and its
``age_days`` against the curve's as-of. Which quotes enter (one snapshot: one as-of, a stated
source precedence, a staleness limit per tenor) is the caller's selection
(``application/position_inputs.curve_quotes``).

Every point records how it was obtained, so a mark can always be traced to its quotes.
A residual that comes out negative or far outside the quoted range is still returned and
flagged, because it usually means stale or inconsistent quotes. A product whose months are
all priced by shorter quotes is not used, but its strip is repriced and a difference
beyond the tolerance is reported: three months that do not average to the quoted quarter
are a quote problem the desk should see, not something to hide.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

#: Strip repricing difference, as a share of the product price, worth reporting.
STRIP_TOLERANCE = 0.005


@dataclass(frozen=True)
class CurveQuote:
    """One quoted product: delivery from ``first_day`` to ``end_day`` (exclusive), gas days."""

    hub: str
    first_day: date
    end_day: date
    price: float
    label: str = ""
    reference: str = ""
    #: The trade date the quote is for (its observation day); ``None`` when not known.
    as_of: date | None = None

    @property
    def days(self) -> int:
        return (self.end_day - self.first_day).days


#: A product longer than this (a season, a year) is spread over its open months by shape.
SHAPED_PRODUCT_MIN_DAYS = 93


@dataclass(frozen=True)
class CurvePoint:
    hub: str
    month: str  # "2026-11"
    price: float | None
    method: str  # "quoted", "derived", "front", "not_available"
    source: str  # product label the price comes from
    warning: str | None = None
    #: The quote's trade date (for a derived month, its product's) and its age in days
    #: against the curve's as-of.
    as_of: date | None = None
    age_days: int | None = None

    @property
    def basis(self) -> str:
        """How the point was obtained, in words."""

        if self.method == "quoted":
            return "quoted"
        if self.method == "derived":
            return f"derived from {self.source}"
        if self.method == "front":
            return f"balance of month ({self.source})"
        return "not available"


@dataclass
class ForwardCurve:
    points: list[CurvePoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: The curve's as-of: the newest trade date among the quotes used, per hub.
    as_of: dict[str, date] = field(default_factory=dict)

    def marks(self) -> dict[tuple[str, str], float]:
        return {
            (point.hub, point.month): point.price
            for point in self.points
            if point.price is not None
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "points": [
                {
                    "hub": p.hub,
                    "month": p.month,
                    "price": None if p.price is None else round(p.price, 4),
                    "method": p.method,
                    "basis": p.basis,
                    "source": p.source,
                    "as_of": p.as_of.isoformat() if p.as_of else None,
                    "age_days": p.age_days,
                    "warning": p.warning,
                }
                for p in self.points
            ],
            "as_of": {hub: day.isoformat() for hub, day in sorted(self.as_of.items())},
            "warnings": list(self.warnings),
        }


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


@lru_cache(maxsize=4096)
def gas_day_hours(day: date) -> int:
    """Delivery hours of one gas day: 24, or 23/25 on the summer-time changes."""

    # The gas-day calendar owns the boundary (domain/market/gas_day.py).
    start = gas_day_start_for_date(day)
    end = gas_day_start_for_date(day + timedelta(days=1))
    return round((end - start).total_seconds() / 3600)


def _months_in(first: date, end: date) -> dict[str, int]:
    """Delivery hours per calendar month inside the gas days ``[first, end)``."""

    hours: dict[str, int] = {}
    day = first
    while day < end:
        hours[_month_key(day)] = hours.get(_month_key(day), 0) + gas_day_hours(day)
        day += timedelta(days=1)
    return hours


def _is_whole_month(quote: CurveQuote) -> bool:
    return quote.first_day.day == 1 and quote.end_day == (
        quote.first_day.replace(day=28) + timedelta(days=4)
    ).replace(day=1)


def _is_balance_of_month(quote: CurveQuote) -> bool:
    """A prompt product that delivers to the end of its month (not a day-ahead or weekend)."""

    month_end = (quote.first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return quote.end_day == month_end and quote.days > 2 and not _is_whole_month(quote)


def implied_shape(quotes: Iterable[CurveQuote]) -> dict[int, float]:
    """Relative level per calendar month (1-12) that the quoted months and quarters show.

    Each calendar month takes the price of the shortest quote of a month or a quarter that
    covers it (averaged over the years quoted); the levels are divided by their mean. A
    calendar month no such quote covers is left out (level 1.0 where it is used).
    """

    levels: dict[int, list[tuple[int, float]]] = {}
    for quote in quotes:
        if quote.days >= SHAPED_PRODUCT_MIN_DAYS or quote.days < 28:
            continue
        for key in _months_in(quote.first_day, quote.end_day):
            levels.setdefault(int(key[5:]), []).append((quote.days, quote.price))
    shape: dict[int, float] = {}
    for month, found in levels.items():
        shortest = min(days for days, _price in found)
        prices = [price for days, price in found if days == shortest]
        shape[month] = sum(prices) / len(prices)
    if not shape:
        return {}
    mean = sum(shape.values()) / len(shape)
    if mean <= 0:
        return {}
    return {month: level / mean for month, level in shape.items()}


def build_forward_curve(
    quotes: Iterable[CurveQuote],
    *,
    first_month: date,
    shape: Mapping[int, float] | None = None,
    front_month_from_prompt: bool = True,
    last_month: date | None = None,
) -> ForwardCurve:
    """Monthly curve per hub from ``first_month`` on (to ``last_month`` when given).

    ``shape`` maps calendar month (1-12) to a relative level (for example winter 1.08,
    summer 0.94); months without a factor use 1.0. Without it a season or a year is shaped
    by the hub's own quoted months and quarters (:func:`implied_shape`). When
    ``front_month_from_prompt`` is set and the current month has no quote, the latest
    balance-of-month quote prices the rest of the current month; a day-ahead or weekend
    price never does. With ``last_month`` every month to it that no quote prices is listed
    as ``not_available`` (no price).
    """

    curve = ForwardCurve()
    start_key = _month_key(first_month)
    by_hub: dict[str, list[CurveQuote]] = {}
    for quote in quotes:
        if quote.days <= 0:
            continue
        by_hub.setdefault(quote.hub.upper(), []).append(quote)

    for hub, hub_quotes in sorted(by_hub.items()):
        dated = [q.as_of for q in hub_quotes if q.as_of is not None]
        hub_as_of = max(dated) if dated else None
        if hub_as_of is not None:
            curve.as_of[hub] = hub_as_of

        def stamp(quote: CurveQuote, hub_as_of=hub_as_of) -> dict[str, object]:
            if quote.as_of is None or hub_as_of is None:
                return {"as_of": quote.as_of}
            return {"as_of": quote.as_of, "age_days": (hub_as_of - quote.as_of).days}

        own_shape = shape if shape is not None else implied_shape(hub_quotes)
        fixed: dict[str, CurvePoint] = {}
        # Whole months first, then longer products from shortest to longest.
        months = [q for q in hub_quotes if _is_whole_month(q)]
        longer = sorted(
            (q for q in hub_quotes if not _is_whole_month(q) and q.days > 31),
            key=lambda q: (q.days, q.first_day),
        )
        for quote in months:
            key = _month_key(quote.first_day)
            fixed[key] = CurvePoint(
                hub, key, quote.price, "quoted", quote.label or key, **stamp(quote)
            )
        for quote in longer:
            span = _months_in(quote.first_day, quote.end_day)
            known = {m: d for m, d in span.items() if m in fixed}
            open_months = {m: d for m, d in span.items() if m not in fixed}
            if not open_months:
                # Every month is priced by shorter quotes: reprice the strip and say when
                # it does not match the product.
                implied = sum(fixed[m].price * h for m, h in span.items()) / sum(span.values())
                if abs(implied - quote.price) > STRIP_TOLERANCE * max(abs(quote.price), 1.0):
                    curve.warnings.append(
                        f"{hub} {quote.label or 'product'} quoted {quote.price:.3f} but its "
                        f"months average {implied:.3f}; check for stale or inconsistent quotes"
                    )
                continue
            residual_value = quote.price * sum(span.values()) - sum(
                fixed[m].price * d for m, d in known.items()
            )
            shaped = quote.days >= SHAPED_PRODUCT_MIN_DAYS or shape is not None
            weights = {
                m: (own_shape or {}).get(int(m[5:]), 1.0) if shaped else 1.0
                for m in open_months
            }
            weighted_days = sum(weights[m] * d for m, d in open_months.items())
            level = residual_value / weighted_days
            for month, _days in open_months.items():
                price = level * weights[month]
                warning = None
                if price <= 0 or abs(price - quote.price) > 0.5 * abs(quote.price):
                    warning = (
                        f"{month} derived from {quote.label or 'product'} is far from the "
                        "product price; check for stale or inconsistent quotes"
                    )
                    curve.warnings.append(f"{hub} {warning}")
                fixed[month] = CurvePoint(
                    hub, month, price, "derived", quote.label or "product", warning,
                    **stamp(quote),
                )
        if front_month_from_prompt:
            # The current month (whichever month a balance-of-month quote delivers in; the
            # curve may start earlier for a look-back) when no month quote prices it.
            balance: dict[str, CurveQuote] = {}
            for q in hub_quotes:
                key = _month_key(q.first_day)
                if _is_balance_of_month(q) and key not in fixed and (
                    key not in balance or q.first_day > balance[key].first_day
                ):
                    balance[key] = q
            for key, latest in balance.items():
                fixed[key] = CurvePoint(
                    hub, key, latest.price, "front", latest.label or "balance of month",
                    **stamp(latest),
                )
        if last_month is not None:
            month = first_month.replace(day=1)
            while month <= last_month:
                key = _month_key(month)
                if key not in fixed:
                    fixed[key] = CurvePoint(hub, key, None, "not_available", "")
                month = (month + timedelta(days=32)).replace(day=1)
        curve.points.extend(point for key, point in sorted(fixed.items()) if key >= start_key)
    return curve
