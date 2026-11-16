"""Route pricing walks proven adjacency: market area -> interconnection point -> market area."""

from __future__ import annotations

import pytest

from eurogas_nexus.application.resource_pool import candidate_route_cost
from eurogas_nexus.domain.route_cost.route_adjacency import (
    ENDPOINT_NOT_IN_NETWORK,
    LOCAL,
    NO_PROVEN_CONNECTION,
    PROVEN,
    apply_route_adjacency,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.european_public_tariffs import published_european_corridor_tariffs
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg
from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph
from eurogas_nexus.reference_data.network_bundle import load_bundle


@pytest.fixture(scope="module")
def graph():
    return shipped_market_area_graph()


def hub(graph, code: str) -> str:
    key = graph.hub_for(code)
    assert key, code
    return key


def legs(graph, start: str, target: str, via=()):
    crossings = graph.route(hub(graph, start), hub(graph, target), via_points=via)
    assert crossings is not None, f"{start} -> {target} has no proven route"
    return crossings, [(leg.direction, leg.tso, leg.point_key, leg.role) for c in crossings for leg in graph.legs(c)]


def test_ttf_and_the_are_joined_directly_through_the_nl_de_points(graph):
    points = {c.points[0] for c in graph.crossings(hub(graph, "TTF"), hub(graph, "THE"))}
    # The VIPs and the physical border points (Bocholtz, Oude Statenzijl, Winterswijk, ...).
    assert {"ITP-10012", "ITP-10010", "ITP-00169", "ITP-00078"} <= points
    crossings, priced = legs(graph, "TTF", "THE", via=["ITP-10012"])
    assert [c.points for c in crossings] == [("ITP-10012",)]
    assert priced == [
        ("EXIT", "GTS", "ITP-10012", "market_area_exit"),
        ("ENTRY", "Gasunie Deutschland", "ITP-10012", "market_area_entry"),
    ]


def test_ttf_to_nbp_goes_through_bbl_with_both_market_area_legs(graph):
    crossings, priced = legs(graph, "TTF", "NBP")
    assert [c.pipeline_operator for c in crossings] == ["UK-TSO-0004"]
    assert priced == [
        ("EXIT", "GTS", "ITP-00063", "market_area_exit"),
        ("EXIT", "BBL Company", "ITP-00063", "pipeline"),
        ("ENTRY", "National Gas TSO", "ITP-00207", "market_area_entry"),
    ]


def test_nbp_and_ztp_go_through_iuk_with_the_charges_of_the_flow_direction(graph):
    _, forward = legs(graph, "NBP", "ZTP")
    assert forward == [
        ("EXIT", "National Gas TSO", "ITP-00005", "market_area_exit"),
        ("ENTRY", "Interconnector UK", "ITP-00005", "pipeline"),
        ("EXIT", "Interconnector UK", "ITP-00005", "pipeline"),
        ("ENTRY", "Fluxys Belgium", "ITP-00061", "market_area_entry"),
    ]
    reverse = [leg for c in graph.route(hub(graph, "ZTP"), hub(graph, "NBP")) for leg in graph.legs(c)]
    assert [leg.point_name for leg in reverse][1:3] == ["IUK Zeebrugge Entry", "IUK Bacton Exit"]


def test_the_borders_peg_and_ztp_directly(graph):
    for target in ("PEG", "ZTP"):
        crossings, priced = legs(graph, "THE", target)
        assert len(crossings) == 1 and crossings[0].pipeline_operator is None
        assert [direction for direction, *_ in priced] == ["EXIT", "ENTRY"]


def test_two_market_areas_without_an_interconnection_are_not_priced_as_direct(graph):
    assert graph.crossings(hub(graph, "TTF"), hub(graph, "PEG")) == []
    assert graph.crossings(hub(graph, "NBP"), hub(graph, "THE")) == []
    crossings, _ = legs(graph, "TTF", "PEG")
    assert len(crossings) == 2  # chained through a neighbour, each hop at a named point
    assert crossings[0].to_hub == crossings[1].from_hub


def test_a_named_point_that_does_not_join_the_market_areas_is_not_a_route(graph):
    # Moffat joins NBP and IBP, not TTF and THE.
    assert graph.route(hub(graph, "TTF"), hub(graph, "THE"), via_points=["ITP-00090"]) is None


def test_psv_is_not_in_the_network_so_a_route_to_it_is_not_priced():
    [candidate] = apply_route_adjacency(
        [{"route_id": "the-psv", "start_point_name": "THE", "target_point_name": "PSV", "route_legs": []}]
    )
    assert candidate["route_adjacency"]["status"] == ENDPOINT_NOT_IN_NETWORK
    assert candidate["route_legs"] == []


def test_an_authored_route_gets_the_full_crossing_and_keeps_its_capacity():
    [candidate] = apply_route_adjacency(
        [
            {
                "route_id": "ttf-nbp",
                "start_point_name": "TTF",
                "target_point_name": "NBP",
                "route_legs": [
                    {
                        "leg_id": "bbl-forward",
                        "country": "NL",
                        "tso": "BBL Company",
                        "market_area": "BBL",
                        "point_name": "BBL Forward Flow NL to GB",
                        "direction": "EXIT",
                        "available_capacity_mwh_per_day": 2000.0,
                    }
                ],
            }
        ]
    )
    adjacency = candidate["route_adjacency"]
    assert adjacency["status"] == PROVEN
    assert adjacency["crossings"][0]["points"] == ["ITP-00063", "ITP-00207"]
    assert adjacency["path_node_ids"] == [
        "entsog-vtp-00002",
        "entsog-itp-00063",
        "entsog-itp-00207",
        "entsog-vtp-00006",
    ]
    by_role = {leg["role"]: leg for leg in candidate["route_legs"]}
    assert by_role["pipeline"]["leg_id"] == "bbl-forward"
    assert by_role["pipeline"]["available_capacity_mwh_per_day"] == 2000.0
    assert len(candidate["route_legs"]) == 3


def test_a_leg_whose_tariff_is_not_held_is_missing_not_zero():
    [candidate] = apply_route_adjacency(
        [{"route_id": "ttf-nbp", "start_point_name": "TTF", "target_point_name": "NBP", "route_legs": []}]
    )
    legs_ = [RouteTariffLeg.model_validate(leg) for leg in candidate["route_legs"]]
    result = calculate_route_cost(
        RouteCostScenario(
            scenario_id="ttf-nbp",
            source_resource_type="PIPELINE_IMPORT",
            start_point_id="TTF",
            target_hub_or_point_id="NBP",
            business_model="CROSS_BORDER_TRANSFER",
            delivery_mode="BORDER_TRANSFER",
            gas_year="2025+",
            capacity_product="ANNUAL",
            firmness="FIRM",
            tariff_legs=legs_,
        ),
        published_european_corridor_tariffs(),
    )
    assert result.status != "SUCCESS"
    missing = " ".join(result.missing_inputs)
    assert "ITP-00063:exit" in missing and "ITP-00207:entry" in missing


def test_an_unproven_route_is_blocked_by_the_resource_pool_not_priced_at_zero():
    [candidate] = apply_route_adjacency(
        [{"route_id": "ttf-the-moffat", "start_point_name": "TTF", "target_point_name": "THE", "route_legs": [], "via_point_keys": ["ITP-00090"]}]
    )
    assert candidate["route_adjacency"]["status"] == NO_PROVEN_CONNECTION
    cost, _, _, _, blockers, _ = candidate_route_cost(
        candidate, [], price_currency="EUR", price_unit="EUR/MWh"
    )
    assert cost is None
    assert blockers == ["ROUTE_NOT_CONNECTED:ttf-the-moffat"]


def test_a_local_sale_stays_free_of_route_cost():
    [candidate] = apply_route_adjacency(
        [{"route_id": "ttf-local", "start_point_name": "TTF", "target_point_name": "TTF", "route_legs": []}]
    )
    assert candidate["route_adjacency"]["status"] == LOCAL
    cost, *_ = candidate_route_cost(candidate, [], price_currency="EUR", price_unit="EUR/MWh")
    assert cost == 0.0


def test_the_map_draws_exactly_the_adjacency_the_pricing_walks(graph):
    """Every drawn connection is an adjacency edge, and every pair of neighbouring market
    areas the pricing knows has a drawn hub -> point -> hub line (clients/web isDrawnAdjacency:
    each pipeline, and the representative point of each pair)."""

    bundle = load_bundle()
    drawn = [
        edge
        for edge in bundle["edges"]
        if edge["type"] == "interconnector" or (edge["type"] == "market_area_link" and edge.get("representative"))
    ]
    point_of = {node["id"]: node["point_key"] for node in bundle["nodes"]}
    for edge in drawn:
        if edge["type"] == "market_area_link":
            assert point_of[edge["from"]] in graph.point_hubs
            assert edge["hub_point_key"] in graph.point_hubs[point_of[edge["from"]]]
        else:
            assert edge["operator_key"] in graph.pipelines
    drawn_pairs: set[frozenset[str]] = set()
    by_point: dict[str, set[str]] = {}
    for edge in drawn:
        if edge["type"] == "market_area_link":
            by_point.setdefault(edge["point_key"], set()).add(edge["hub_point_key"])
    for hubs in by_point.values():
        for a in hubs:
            for b in hubs - {a}:
                drawn_pairs.add(frozenset((a, b)))
    for operator, (a, b) in graph.pipelines.items():
        for x in by_point.get(a, set()):
            for y in by_point.get(b, set()):
                drawn_pairs.add(frozenset((x, y)))
    priced_pairs = {
        frozenset((a, b)) for a in graph.hub_names for b in graph.neighbours(a)
    }
    assert priced_pairs == drawn_pairs
