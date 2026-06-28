"""Route recommendation tests with capacity and TSO access constraints."""

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
)
from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    published_european_corridor_tariffs,
)
from eurogas_nexus.domain.route_cost.route_optimizer import (
    RouteOptionCandidate,
    RouteRecommendationRequest,
    recommend_route_allocation,
)
from eurogas_nexus.domain.route_cost.schemas import RouteTariffLeg


def test_recommendation_splits_volume_when_cheapest_route_capacity_is_insufficient() -> None:
    request = RouteRecommendationRequest(
        request_id="ttf-to-nbp-split",
        source_point_id="TTF",
        target_point_id="NBP",
        required_quantity_mwh_per_day=250.0,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        company_accessible_tsos=["BBL Company"],
        candidates=[
            RouteOptionCandidate(
                route_id="bbl-forward-direct",
                route_name="TTF -> BBL -> NBP",
                required_tso_access=["BBL Company"],
                available_capacity_mwh_per_day=100.0,
                tariff_legs=[
                    RouteTariffLeg(
                        leg_id="bbl-forward",
                        country="NL",
                        tso="BBL Company",
                        market_area="BBL",
                        point_name="BBL Forward Flow NL to GB",
                        direction=TariffDirection.EXIT,
                    )
                ],
            ),
            RouteOptionCandidate(
                route_id="bbl-roundtrip-backup",
                route_name="TTF -> BBL backup path",
                required_tso_access=["BBL Company"],
                available_capacity_mwh_per_day=200.0,
                tariff_legs=[
                    RouteTariffLeg(
                        leg_id="bbl-forward",
                        country="NL",
                        tso="BBL Company",
                        market_area="BBL",
                        point_name="BBL Forward Flow NL to GB",
                        direction=TariffDirection.EXIT,
                    ),
                    RouteTariffLeg(
                        leg_id="bbl-reverse",
                        country="GB",
                        tso="BBL Company",
                        market_area="BBL",
                        point_name="BBL Reverse Flow GB to NL",
                        direction=TariffDirection.ENTRY,
                    ),
                ],
            ),
        ],
    )

    result = recommend_route_allocation(request, published_european_corridor_tariffs())

    assert result.status == "SUCCESS"
    assert result.total_allocated_mwh_per_day == 250.0
    assert result.unallocated_mwh_per_day == 0.0
    assert [allocation.route_id for allocation in result.allocations] == [
        "bbl-forward-direct",
        "bbl-roundtrip-backup",
    ]
    assert [allocation.allocated_mwh_per_day for allocation in result.allocations] == [
        100.0,
        150.0,
    ]
    assert [allocation.route_cost for allocation in result.allocations] == [1.0, 2.0]


def test_recommendation_excludes_routes_without_company_tso_access() -> None:
    request = RouteRecommendationRequest(
        request_id="avoid-uncontracted-tso",
        source_point_id="TTF",
        target_point_id="NBP",
        required_quantity_mwh_per_day=100.0,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        company_accessible_tsos=["BBL Company"],
        candidates=[
            RouteOptionCandidate(
                route_id="missing-access-route",
                route_name="Cheap route through unsigned TSO",
                required_tso_access=["Uncontracted TSO"],
                available_capacity_mwh_per_day=500.0,
                tariff_legs=[
                    RouteTariffLeg(
                        leg_id="bbl-forward",
                        country="NL",
                        tso="BBL Company",
                        market_area="BBL",
                        point_name="BBL Forward Flow NL to GB",
                        direction=TariffDirection.EXIT,
                    )
                ],
            ),
            RouteOptionCandidate(
                route_id="accessible-route",
                route_name="Accessible BBL route",
                required_tso_access=["BBL Company"],
                available_capacity_mwh_per_day=100.0,
                tariff_legs=[
                    RouteTariffLeg(
                        leg_id="bbl-forward",
                        country="NL",
                        tso="BBL Company",
                        market_area="BBL",
                        point_name="BBL Forward Flow NL to GB",
                        direction=TariffDirection.EXIT,
                    )
                ],
            ),
        ],
    )

    result = recommend_route_allocation(request, published_european_corridor_tariffs())

    assert result.status == "SUCCESS"
    assert [allocation.route_id for allocation in result.allocations] == ["accessible-route"]
    excluded = {route.route_id: route.blockers for route in result.excluded_routes}
    assert excluded["missing-access-route"] == ["TSO_ACCESS_MISSING:Uncontracted TSO"]


def test_recommendation_reports_unallocated_volume_when_capacity_is_insufficient() -> None:
    request = RouteRecommendationRequest(
        request_id="capacity-shortfall",
        source_point_id="TTF",
        target_point_id="NBP",
        required_quantity_mwh_per_day=300.0,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        company_accessible_tsos=["BBL Company"],
        candidates=[
            RouteOptionCandidate(
                route_id="limited-bbl",
                route_name="Limited BBL route",
                required_tso_access=["BBL Company"],
                available_capacity_mwh_per_day=120.0,
                tariff_legs=[
                    RouteTariffLeg(
                        leg_id="bbl-forward",
                        country="NL",
                        tso="BBL Company",
                        market_area="BBL",
                        point_name="BBL Forward Flow NL to GB",
                        direction=TariffDirection.EXIT,
                    )
                ],
            )
        ],
    )

    result = recommend_route_allocation(request, published_european_corridor_tariffs())

    assert result.status == "PARTIAL"
    assert result.total_allocated_mwh_per_day == 120.0
    assert result.unallocated_mwh_per_day == 180.0
    assert "ROUTE_CAPACITY_SHORTFALL" in result.warnings


def test_recommendation_chooses_local_sale_when_reroute_netback_is_worse() -> None:
    request = RouteRecommendationRequest(
        request_id="target-market-capacity-and-local-alternative",
        source_point_id="TTF",
        target_point_id="NBP",
        required_quantity_mwh_per_day=100.0,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        company_accessible_tsos=["BBL Company"],
        candidates=[
            RouteOptionCandidate(
                route_id="cheap-nbp-route",
                route_name="TTF -> BBL -> NBP",
                destination_market="NBP",
                sale_price=35.0,
                price_currency="EUR",
                price_unit="EUR/MWh",
                required_tso_access=["BBL Company"],
                available_capacity_mwh_per_day=20.0,
                tariff_legs=[
                    RouteTariffLeg(
                        leg_id="bbl-forward",
                        country="NL",
                        tso="BBL Company",
                        market_area="BBL",
                        point_name="BBL Forward Flow NL to GB",
                        direction=TariffDirection.EXIT,
                    )
                ],
            ),
            RouteOptionCandidate(
                route_id="expensive-reroute-to-nbp",
                route_name="TTF -> BBL loop -> NBP",
                destination_market="NBP",
                sale_price=35.0,
                price_currency="EUR",
                price_unit="EUR/MWh",
                required_tso_access=["BBL Company"],
                available_capacity_mwh_per_day=100.0,
                manual_cost=8.0,
                cost_currency="EUR",
                cost_unit="EUR/MWh",
            ),
            RouteOptionCandidate(
                route_id="local-ttf-sale",
                route_name="Sell locally at TTF",
                destination_market="TTF",
                sale_price=31.0,
                price_currency="EUR",
                price_unit="EUR/MWh",
                required_tso_access=[],
                available_capacity_mwh_per_day=100.0,
                manual_cost=0.0,
                cost_currency="EUR",
                cost_unit="EUR/MWh",
            ),
        ],
    )

    result = recommend_route_allocation(request, published_european_corridor_tariffs())

    assert result.status == "SUCCESS"
    assert [(item.route_id, item.allocated_mwh_per_day) for item in result.allocations] == [
        ("cheap-nbp-route", 20.0),
        ("local-ttf-sale", 80.0),
    ]
    assert result.allocations[0].netback == 34.0
    assert result.allocations[1].netback == 31.0
    excluded = {route.route_id: route.blockers for route in result.excluded_routes}
    assert excluded["expensive-reroute-to-nbp"] == [
        "ECONOMICALLY_INFERIOR_TO_SELECTED_OPTIONS"
    ]
