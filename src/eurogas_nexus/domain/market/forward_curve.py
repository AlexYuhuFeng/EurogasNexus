"""Monthly forward curve per hub from the products a desk actually quotes.

Hubs trade months, quarters, seasons (Sum/Win) and calendar years; positions are held by
month. The curve gives every delivery month one price, consistent with every quoted
product: the day-weighted average of the months inside a product equals that product's
price (Q1 = (31·Jan + 28·Feb + 31·Mar) / 90).

Method, shortest product first:

1. A month quote is used as it is.
2. A longer product prices its months that no shorter quote has fixed. The residual
   ``(P·days − Σ fixed month prices·days) / remaining days`` is spread over those months,
   flat or in proportion to a seasonal shape (relative monthly levels) when one is given.
3. A month no quote covers gets no price: the curve does not extrapolate.

Every point records how it was obtained, so a mark can always be traced to its quotes.
A residual that comes out negative or far outside the quoted range is still returned and
flagged, because it usually means stale or inconsistent quotes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class CurveQuote:
    """One quoted product: delivery from ``first_day`` to ``end_day`` (exclusive), gas days."""

    hub: str
    first_day: date
    end_day: date
    price: float
    label: str = ""
    reference: str = ""

    @property
    def days(self) -> int:
        return (self.end_day - self.first_day).days


@dataclass(frozen=True)
class CurvePoint:
    hub: str
    month: str  # "2026-11"
    price: float
    method: str  # "quoted", "derived", "front"
    source: str  # product label the price comes from
    warning: str | None = None


@dataclass
class ForwardCurve:
    points: list[CurvePoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def marks(self) -> dict[tuple[str, str], float]:
        return {(point.hub, point.month): point.price for point in self.points}

    def as_dict(self) -> dict[str, object]:
        return {
            "points": [
                {
                    "hub": p.hub,
                    "month": p.month,
                    "price": round(p.price, 4),
                    "method": p.method,
                    "source": p.source,
                    "warning": p.warning,
                }
                for p in self.points
            ],
            "warnings": list(self.warnings),
        }


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _months_in(first: date, end: date) -> dict[str, int]:
    """Gas days per calendar month inside ``[first, end)``."""

    days: dict[str, int] = {}
    day = first
    while day < end:
        next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(next_month, end)
        days[_month_key(day)] = days.get(_month_key(day), 0) + (stop - day).days
        day = stop
    return days


def _is_whole_month(quote: CurveQuote) -> bool:
    return quote.first_day.day == 1 and quote.end_day == (
        quote.first_day.replace(day=28) + timedelta(days=4)
    ).replace(day=1)


def build_forward_curve(
    quotes: Iterable[CurveQuote],
    *,
    first_month: date,
    shape: Mapping[int, float] | None = None,
    front_month_from_prompt: bool = True,
) -> ForwardCurve:
    """Monthly curve per hub from ``first_month`` on.

    ``shape`` maps calendar month (1-12) to a relative level (for example winter 1.08,
    summer 0.94); months without a factor use 1.0. When ``front_month_from_prompt`` is set
    and the current month has no quote, the latest prompt product inside it (balance of
    month, weekend, day-ahead) prices the rest of the current month.
    """

    curve = ForwardCurve()
    start_key = _month_key(first_month)
    by_hub: dict[str, list[CurveQuote]] = {}
    for quote in quotes:
        if quote.days <= 0:
            continue
        by_hub.setdefault(quote.hub.upper(), []).append(quote)

    for hub, hub_quotes in sorted(by_hub.items()):
        fixed: dict[str, CurvePoint] = {}
        # Whole months first, then longer products from shortest to longest.
        months = [q for q in hub_quotes if _is_whole_month(q)]
        longer = sorted(
            (q for q in hub_quotes if not _is_whole_month(q) and q.days > 31),
            key=lambda q: (q.days, q.first_day),
        )
        for quote in months:
            key = _month_key(quote.first_day)
            fixed[key] = CurvePoint(hub, key, quote.price, "quoted", quote.label or key)
        for quote in longer:
            span = _months_in(quote.first_day, quote.end_day)
            known = {m: d for m, d in span.items() if m in fixed}
            open_months = {m: d for m, d in span.items() if m not in fixed}
            if not open_months:
                continue
            residual_value = quote.price * sum(span.values()) - sum(
                fixed[m].price * d for m, d in known.items()
            )
            weights = {m: (shape or {}).get(int(m[5:]), 1.0) for m in open_months}
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
                    hub, month, price, "derived", quote.label or "product", warning
                )
        if front_month_from_prompt and start_key not in fixed:
            prompt = [
                q
                for q in hub_quotes
                if q.days <= 31 and not _is_whole_month(q) and _month_key(q.first_day) == start_key
            ]
            if prompt:
                latest = max(prompt, key=lambda q: (q.first_day, -q.days))
                fixed[start_key] = CurvePoint(
                    hub, start_key, latest.price, "front", latest.label or "prompt"
                )
        curve.points.extend(point for key, point in sorted(fixed.items()) if key >= start_key)
    return curve
