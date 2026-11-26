"""The transport cost of a prompt spread is the marginal one (quant review 2026-11-26, 3.7).

Spreads and Today priced every route on firm yearly capacity at 100 % load factor with no
commodity charge or fuel gas. A day-ahead spread buys daily capacity (its multiplier is in the
published price), pays the commodity charge and gives up fuel gas; yearly capacity is what a
holder has already paid for. Tariffs here are synthetic, built from the shipped graph's legs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.application.route_tariff_cost import marginal_product, marginal_route_cost
from eurogas_nexus.application.spreads_board import locational_rows
from eurogas_nexus.domain.market.fx_forward import Delivery
from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph
from tests.unit.test_spreads_board import _month_ahead
from tests.unit.test_spreads_workbench import TODAY, _holdings, _row


def _rows(a: str, b: str, product: str, value: float, unit: str = "EUR/MWh") -> list[dict]:
    graph = shipped_market_area_graph()
    crossing = graph.crossings(graph.hub_for(a), graph.hub_for(b))[0]
    return [
        {
            "tariff_id": f"t-{leg.point_key}-{leg.direction}-{product}",
            "tso": leg.tso.split(" / ")[0], "point_id": leg.point_key,
            "direction": leg.direction, "capacity_product": product, "firmness": "FIRM",
            "gas_year": "2026/27", "tariff_value": value, "currency": "EUR", "unit": unit,
            "effective_from": datetime(2026, 10, 1, tzinfo=UTC),
            "effective_to": datetime(2027, 9, 30, tzinfo=UTC),
            "tariff_status": "FINAL", "source_table": "synthetic",
        }
        for leg in graph.legs(crossing)
    ]


REGISTER = (
    _rows("TTF", "THE", "ANNUAL", 0.10)
    + _rows("TTF", "THE", "DAILY", 0.25)
    + _rows("TTF", "THE", "MONTHLY", 0.15)
    + _rows("TTF", "THE", "COMMODITY", 0.05)[:1]
    + _rows("TTF", "THE", "FUEL", 0.5, unit="%")[:1]
)


def _rows_for(product):
    return [row for row in REGISTER if row["capacity_product"] == product]


def test_a_day_ahead_spread_is_priced_on_daily_capacity_with_flow_charges():
    day = Delivery(date(2026, 11, 27), date(2026, 11, 27), "day_ahead", "2026-11-27")
    assert marginal_product(day) == "DAILY"
    cost = marginal_route_cost("TTF", "THE", day, _rows_for, gas_price=30.0)
    assert cost.product == "DAILY"
    assert cost.capacity == pytest.approx(0.50)  # two legs at the daily product
    assert cost.commodity == pytest.approx(0.05)
    assert cost.fuel_cost == pytest.approx(0.005 * 30.0)
    assert cost.total == pytest.approx(0.50 + 0.05 + 0.15)
    assert cost.holder == pytest.approx(0.05 + 0.15)  # a holder of capacity pays the flow
    # Before: 0.20, the yearly product at 100 % load factor; now context, as sunk capacity.
    assert cost.as_dict()["sunk_capacity"]["value"] == pytest.approx(0.20)
    assert cost.flow_not_held == ()


def test_a_month_spread_takes_the_monthly_product_and_says_what_is_not_held():
    month = Delivery(date(2027, 1, 1), date(2027, 1, 31), "month", "Jan-27")
    cost = marginal_route_cost(
        "TTF", "THE", month, lambda p: [r for r in _rows_for(p) if p not in {"COMMODITY", "FUEL"}]
    )
    assert cost.product == "MONTHLY" and cost.capacity == pytest.approx(0.30)
    assert cost.commodity is None and cost.fuel_cost is None
    assert "no commodity charge held for the route's points" in cost.flow_not_held
    assert "no fuel gas (gas in kind) held for the route's points" in cost.flow_not_held


def test_the_board_shows_which_product_priced_the_day_ahead_spread():
    tomorrow = TODAY + timedelta(days=1)
    rows = _month_ahead("TTF", 30.0) + _month_ahead("THE", 30.5)
    for hub, price in (("TTF", 30.0), ("THE", 31.0)):
        row = _row(hub, "day-ahead", price, "EUR/MWh", day=TODAY,
                   start=datetime(tomorrow.year, tomorrow.month, tomorrow.day, 5, tzinfo=UTC),
                   end=datetime(tomorrow.year, tomorrow.month, tomorrow.day, 5, tzinfo=UTC)
                   + timedelta(days=1))
        row["price_mwh"], row["unit_mwh"] = price, "EUR/MWh"
        rows.append(row)
    holdings = _holdings(rows, REGISTER)
    month, day_ahead = locational_rows(holdings, ["THE"])[0]["tenors"]
    assert month["route"]["product"] == "MONTHLY"
    assert month["cost"] == pytest.approx(0.30 + 0.05 + 0.005 * 30.01, abs=1e-6)
    assert day_ahead["available"] and day_ahead["route"]["product"] == "DAILY"
    # 0.50 daily capacity + 0.05 commodity + 0.5 % fuel of 30 EUR/MWh; before: 0.20 (yearly).
    assert day_ahead["cost"] == pytest.approx(0.70)
    assert day_ahead["route"]["marginal"]["sunk_capacity"]["value"] == pytest.approx(0.20)
