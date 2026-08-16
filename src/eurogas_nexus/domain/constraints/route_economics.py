"""Route economics constraints (netback definition)."""

from __future__ import annotations


def netback(
    sale_price: float | None,
    route_cost: float | None,
    *,
    price_currency: str | None = None,
    cost_currency: str | None = None,
    price_unit: str | None = None,
    cost_unit: str | None = None,
) -> float | None:
    """Return executable netback, or None when units/currencies are incompatible.

    Netback = sale price minus route cost. A currency or unit mismatch makes the
    netback non-computable (returns None) instead of silently comparing
    incompatible values.
    """

    if sale_price is None or route_cost is None:
        return None
    if price_currency and cost_currency and price_currency != cost_currency:
        return None
    if price_unit and cost_unit and price_unit != cost_unit:
        return None
    return round(sale_price - route_cost, 6)
