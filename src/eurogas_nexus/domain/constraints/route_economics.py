"""Route economics constraints (netback definition).

净回值（netback）的唯一口径：币种或单位不一致时返回 None 而非静默比较，
与资源池的 fail-closed 币种纪律（P0-3）保持一致。
"""

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

    计算可执行的净回值；口径不兼容时返回 None（fail-closed）。

    Netback = sale price minus route cost. A currency or unit mismatch makes the
    netback non-computable (returns None) instead of silently comparing
    incompatible values.

    Args:
        sale_price: Gross sale price, or None when unpriced.
        route_cost: Total route cost, or None when unestimated.
        price_currency: Currency of the sale price (optional).
        cost_currency: Currency of the route cost (optional).
        price_unit: Unit of the sale price (optional).
        cost_unit: Unit of the route cost (optional).

    Returns:
        Round(6) netback when both values exist and the optional currency/
        unit pairs are compatible; None otherwise.
    """

    if sale_price is None or route_cost is None:
        return None
    # 币种/单位任一不一致即不可计算：宁可返回 None 也不做跨口径相减。
    if price_currency and cost_currency and price_currency != cost_currency:
        return None
    if price_unit and cost_unit and price_unit != cost_unit:
        return None
    return round(sale_price - route_cost, 6)
