"""The cheapest route over the market-area graph (route_tariff_cost.cheapest_route).

Any pair of hubs, as many borders apart as needed: every chain of market areas is priced from
the tariff register, each crossing at its cheapest complete way across; the cheapest complete
route is chosen and the next-best carries its extra cost; a leg the register does not hold
makes that route unavailable and is named, never priced at zero. Tariff rows here are
synthetic (built from the shipped graph's own leg names), not publications.
"""

from __future__ import annotations

from datetime import date

import pytest

from eurogas_nexus.application.route_tariff_cost import cheapest_route, route_cost
from eurogas_nexus.domain.market.fx_forward import Delivery
from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

JAN = Delivery(date(2027, 1, 1), date(2027, 1, 31), "month", "Jan-27")


@pytest.fixture(scope="module")
def graph():
    return shipped_market_area_graph()


def _rows_for(graph, path: list[str], value: float, currency: str = "EUR", *, skip=()):
    """One FINAL row per leg of the path's representative crossings."""

    hubs = [graph.hub_for(code) for code in path]
    rows = []
    for a, b in zip(hubs, hubs[1:], strict=False):
        crossing = graph.crossings(a, b)[0]
        for spec in graph.legs(crossing):
            if (spec.point_key, spec.direction) in skip:
                continue
            rows.append(
                {
                    "tariff_id": f"t-{spec.point_key}-{spec.direction}-{spec.tso}",
                    "tso": spec.tso.split(" / ")[0],
                    "point_id": spec.point_key,
                    "direction": spec.direction,
                    "gas_year": "2026/27",
                    "tariff_value": value,
                    "currency": currency,
                    "unit": f"{currency}/MWh",
                    "effective_from": date(2026, 10, 1),
                    "effective_to": None,
                    "tariff_status": "FINAL",
                    "source_table": "synthetic",
                }
            )
    return rows


def _unique(rows):
    return list({row["tariff_id"]: row for row in rows}.values())


def test_nbp_to_peg_two_borders_cheapest_and_the_next_best(graph):
    direct = _rows_for(graph, ["NBP", "ZTP", "PEG"], 0.30)
    via_ttf = _rows_for(graph, ["NBP", "TTF", "THE", "PEG"], 0.05)
    choice = cheapest_route("NBP", "PEG", JAN, _unique(direct + via_ttf), graph=graph)
    chosen = choice.chosen
    assert chosen.complete and chosen.total is not None
    # Every complete route is priced; the chosen one is the cheapest of them.
    totals = [route.total for route in (chosen, *choice.alternatives)]
    assert totals == sorted(totals)
    assert chosen.hubs[0] == "NBP" and chosen.hubs[-1] == "PEG"
    payload = choice.as_dict()
    assert payload["alternatives"][0]["extra_cost"] == pytest.approx(
        choice.alternatives[0].total - chosen.total
    )
    assert payload["chosen"]["through"] == list(chosen.hubs[1:-1])
    # Each leg carries its charge, gas year and class.
    assert all(
        leg["gas_year"] == "2026/27" and leg["input_class"] == "sourced"
        for leg in payload["chosen"]["legs"]
    )


def test_a_route_the_desk_picks_is_priced_through_its_market_areas(graph):
    rows = _unique(
        _rows_for(graph, ["NBP", "ZTP", "PEG"], 0.30)
        + _rows_for(graph, ["NBP", "TTF", "THE", "PEG"], 0.05)
    )
    picked = cheapest_route("NBP", "PEG", JAN, rows, graph=graph, through=("ZTP",))
    assert picked.chosen.hubs == ("NBP", "ZTP", "PEG")
    assert route_cost("NBP", "PEG", JAN, rows, graph=graph, through=("ZTP",)).hubs == (
        "NBP",
        "ZTP",
        "PEG",
    )


def test_a_missing_leg_makes_its_route_unavailable_and_is_named(graph):
    near = graph.crossings(graph.hub_for("ZTP"), graph.hub_for("PEG"))[0]
    entry = next(spec for spec in graph.legs(near) if spec.direction == "ENTRY")
    rows = _unique(_rows_for(graph, ["NBP", "ZTP", "PEG"], 0.30, skip={(entry.point_key, "ENTRY")}))
    choice = cheapest_route("NBP", "PEG", JAN, rows, graph=graph)
    # NBP -> ZTP -> PEG lacks one entry; nothing else is held: no complete route.
    assert not choice.chosen.complete and choice.chosen.total is None
    assert any(entry.point_name in item for item in choice.as_dict()["missing"])
    # Nothing is priced at zero.
    assert route_cost("NBP", "PEG", JAN, rows, graph=graph).total is None


def test_legs_in_another_currency_at_the_stated_fx(graph):
    gbp = _rows_for(graph, ["NBP", "ZTP"], 0.20, "GBP")
    eur = _rows_for(graph, ["ZTP", "PEG"], 0.30, "EUR")
    rows = _unique(gbp + eur)
    without = cheapest_route("NBP", "PEG", JAN, rows, graph=graph)
    assert without.chosen.total is None and any("GBP" in issue for issue in without.issues)
    with_fx = cheapest_route("NBP", "PEG", JAN, rows, graph=graph, fx={"GBP": 1.17})
    route = with_fx.chosen
    gbp_legs = [leg for leg in route.legs if leg.currency == "GBP"]
    eur_legs = [leg for leg in route.legs if leg.currency == "EUR"]
    assert route.currency == "EUR" and gbp_legs and eur_legs
    assert route.total == pytest.approx(
        sum(leg.value * 1.17 for leg in gbp_legs) + sum(leg.value for leg in eur_legs)
    )


def test_no_route_at_all_is_said(graph):
    choice = cheapest_route("NBP", "XYZ", JAN, [], graph=graph)
    assert not choice.chosen.proven and "XYZ" in choice.issues[0]
