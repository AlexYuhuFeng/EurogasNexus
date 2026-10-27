"""Route recommendation tests with capacity and TSO access constraints."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
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
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff
from eurogas_nexus.domain.route_cost.tariff_selection import (
    TARIFF_APPLICABILITY_AMBIGUOUS,
    TARIFF_APPLICABILITY_NOT_ASSESSED,
    TARIFF_NOT_EFFECTIVE_ON_DATE,
)


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


def _dated_tariff(
    *,
    tariff_id: str,
    point_name: str,
    effective_from: date,
    effective_to: date | None,
    tariff_value: float,
) -> CapacityTariff:
    """One synthetic exact-match row for the route-recommendation golden."""

    return CapacityTariff(
        tariff_id=tariff_id,
        document_id=f"doc-{tariff_id}",
        country="NL",
        tso="BBL Company",
        market_area="BBL",
        gas_year="2025+",
        point_id=f"point-{tariff_id}",
        source_point_name=point_name,
        direction=TariffDirection.EXIT,
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        tariff_value=tariff_value,
        currency="EUR",
        unit="EUR/MWh",
        effective_from=effective_from,
        effective_to=effective_to,
        tariff_status=TariffStatus.FINAL,
        source_table="synthetic recommendation applicability table",
        source_refs=["test:synthetic-route-tariff"],
        manual_review_required=False,
    )


def _dated_candidate(*, route_id: str, point_name: str, leg_id: str) -> RouteOptionCandidate:
    return RouteOptionCandidate(
        route_id=route_id,
        route_name=route_id,
        required_tso_access=["BBL Company"],
        available_capacity_mwh_per_day=100.0,
        tariff_legs=[
            RouteTariffLeg(
                leg_id=leg_id,
                country="NL",
                tso="BBL Company",
                market_area="BBL",
                point_name=point_name,
                direction=TariffDirection.EXIT,
            )
        ],
    )


def test_recommendation_mixed_candidates_block_gap_and_ambiguity_then_price_valid(
) -> None:
    """The declared date, not row order or a clock, decides every candidate."""

    gap_point = "BBL Gap Point"
    ambiguous_point = "BBL Ambiguous Point"
    valid_point = "BBL Valid Point"
    applicability_date = date(2026, 1, 31)
    request = RouteRecommendationRequest(
        request_id="mixed-applicability-golden",
        source_point_id="TTF",
        target_point_id="NBP",
        required_quantity_mwh_per_day=100.0,
        gas_year="2025+",
        tariff_applicability_date=applicability_date,
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        company_accessible_tsos=["BBL Company"],
        candidates=[
            _dated_candidate(
                route_id="gap-route",
                point_name=gap_point,
                leg_id="gap-leg",
            ),
            _dated_candidate(
                route_id="ambiguous-route",
                point_name=ambiguous_point,
                leg_id="ambiguous-leg",
            ),
            _dated_candidate(
                route_id="valid-route",
                point_name=valid_point,
                leg_id="valid-leg",
            ),
        ],
    )
    tariffs = [
        # The gap row exists but does not cover the declared date.
        _dated_tariff(
            tariff_id="gap-feb",
            point_name=gap_point,
            effective_from=date(2026, 2, 1),
            effective_to=date(2026, 2, 28),
            tariff_value=1.0,
        ),
        # Two FINAL rows cover the declared date: row order cannot choose.
        _dated_tariff(
            tariff_id="ambiguous-jan",
            point_name=ambiguous_point,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 1, 31),
            tariff_value=1.0,
        ),
        _dated_tariff(
            tariff_id="ambiguous-feb",
            point_name=ambiguous_point,
            effective_from=date(2026, 1, 15),
            effective_to=date(2026, 2, 28),
            tariff_value=2.0,
        ),
        # Exactly one row covers the date and it is a valid energy tariff.
        _dated_tariff(
            tariff_id="valid-jan",
            point_name=valid_point,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 1, 31),
            tariff_value=2.0,
        ),
    ]

    result = recommend_route_allocation(request, tariffs)

    assert result.status == "SUCCESS"
    assert result.tariff_applicability_date == applicability_date
    assert [allocation.route_id for allocation in result.allocations] == ["valid-route"]
    allocation = result.allocations[0]
    assert allocation.route_cost == 2.0
    assert "tariff:valid-jan" in allocation.source_refs
    assert "tariff_document:doc-valid-jan" in allocation.source_refs
    assert "test:synthetic-route-tariff" in allocation.source_refs
    excluded = {route.route_id: route.blockers for route in result.excluded_routes}
    assert excluded["gap-route"] == [f"{TARIFF_NOT_EFFECTIVE_ON_DATE}:gap-leg"]
    assert excluded["ambiguous-route"] == [
        f"{TARIFF_APPLICABILITY_AMBIGUOUS}:ambiguous-leg"
    ]
    assert TARIFF_APPLICABILITY_NOT_ASSESSED not in result.warnings


def test_recommendation_without_date_discloses_not_assessed_and_no_clock_date(
) -> None:
    """Legacy selection is preserved only with an explicit disclosure."""

    point_name = "BBL Valid Point"
    request = RouteRecommendationRequest(
        request_id="legacy-applicability-golden",
        source_point_id="TTF",
        target_point_id="NBP",
        required_quantity_mwh_per_day=100.0,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        company_accessible_tsos=["BBL Company"],
        candidates=[
            _dated_candidate(
                route_id="legacy-route",
                point_name=point_name,
                leg_id="legacy-leg",
            )
        ],
    )
    tariffs = [
        _dated_tariff(
            tariff_id="valid-jan",
            point_name=point_name,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 1, 31),
            tariff_value=2.0,
        )
    ]

    result = recommend_route_allocation(request, tariffs)

    assert result.tariff_applicability_date is None
    assert TARIFF_APPLICABILITY_NOT_ASSESSED in result.warnings
    assert result.human_review_required is True
    # Legacy selection still prices the route, but the result never claims the
    # row was verified for a delivery date.
    assert result.allocations[0].route_cost == 2.0


def test_recommendation_request_refuses_timestamp_as_applicability_date() -> None:
    for value in ("2026-01-31T00:00:00Z", datetime(2026, 1, 31, 12, 0)):
        with pytest.raises(ValidationError):
            RouteRecommendationRequest(
                request_id="timestamp-not-date",
                source_point_id="TTF",
                required_quantity_mwh_per_day=1.0,
                gas_year="2025+",
                tariff_applicability_date=value,  # type: ignore[arg-type]
                capacity_product=CapacityProduct.ANNUAL,
                firmness=Firmness.FIRM,
            )


def _local_sale_candidate(**overrides: object) -> RouteOptionCandidate:
    """A local sale whose cost is explicitly declared by the caller."""

    values: dict[str, object] = {
        "route_id": "local-ttf-sale",
        "route_name": "Sell locally at TTF",
        "destination_market": "TTF",
        "sale_price": 31.0,
        "price_currency": "GBP",
        "price_unit": "GBP/MWh",
        "available_capacity_mwh_per_day": None,
        "capacity_status": "NOT_REQUIRED",
        "manual_cost": 0.0,
        "cost_currency": "GBP",
        "cost_unit": "GBP/MWh",
    }
    values.update(overrides)
    return RouteOptionCandidate(**values)  # type: ignore[arg-type]


def _local_sale_request(candidates: list[RouteOptionCandidate]) -> RouteRecommendationRequest:
    return RouteRecommendationRequest(
        request_id="cost-identity-golden",
        source_point_id="TTF",
        target_point_id="TTF",
        required_quantity_mwh_per_day=100.0,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        company_accessible_tsos=[],
        candidates=candidates,
    )


def test_recommendation_excludes_unpriceable_candidate_instead_of_zero_cost() -> None:
    """No manual cost and no priceable leg is unknown, not a zero charge."""

    result = recommend_route_allocation(
        _local_sale_request(
            [
                RouteOptionCandidate(
                    route_id="no-cost",
                    route_name="No cost and no legs",
                    destination_market="NBP",
                    sale_price=35.0,
                    price_currency="GBP",
                    price_unit="GBP/MWh",
                    available_capacity_mwh_per_day=100.0,
                )
            ]
        ),
        published_european_corridor_tariffs(),
    )

    assert result.status == "BLOCKED"
    assert result.allocations == []
    assert [(route.route_id, route.blockers) for route in result.excluded_routes] == [
        ("no-cost", ["ROUTE_COST_MISSING"])
    ]
    assert result.excluded_routes[0].route_cost is None


def test_recommendation_keeps_explicit_zero_cost_and_not_required_capacity() -> None:
    """An explicit zero and NOT_REQUIRED are recorded values, not missing ones."""

    result = recommend_route_allocation(
        _local_sale_request([_local_sale_candidate()]),
        published_european_corridor_tariffs(),
    )

    assert result.status == "SUCCESS"
    allocation = result.allocations[0]
    assert allocation.route_cost == 0.0
    assert allocation.route_cost is not None
    assert allocation.netback == 31.0
    assert allocation.available_capacity_mwh_per_day is None
    assert allocation.rationale == ["selected_by_highest_executable_netback"]


def test_recommendation_blocks_manual_cost_without_currency_and_unit() -> None:
    """A numeric manual cost is refused when its basis metadata is missing."""

    result = recommend_route_allocation(
        _local_sale_request(
            [
                _local_sale_candidate(
                    manual_cost=1.5,
                    cost_currency=None,
                    cost_unit=None,
                )
            ]
        ),
        published_european_corridor_tariffs(),
    )

    assert result.allocations == []
    assert result.excluded_routes[0].blockers == ["ROUTE_COST_METADATA_MISSING"]
    assert result.excluded_routes[0].route_cost is None


def test_recommendation_blocks_sale_price_without_a_currency_and_unit() -> None:
    """A supplied price with no basis cannot be compared with a route cost."""

    result = recommend_route_allocation(
        _local_sale_request(
            [
                _local_sale_candidate(
                    price_currency=None,
                    price_unit=None,
                )
            ]
        ),
        published_european_corridor_tariffs(),
    )

    assert result.allocations == []
    assert result.excluded_routes[0].blockers == ["SALE_PRICE_METADATA_MISSING"]


def test_recommendation_blocks_a_source_option_date_that_disagrees() -> None:
    """An option priced for an old gas day cannot be reused under a new request."""

    request = RouteRecommendationRequest(
        request_id="moved-gas-day",
        source_point_id="TTF",
        target_point_id="TTF",
        required_quantity_mwh_per_day=100.0,
        gas_year="2025+",
        tariff_applicability_date=date(2026, 2, 1),
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        company_accessible_tsos=[],
        candidates=[
            _local_sale_candidate(tariff_applicability_date=date(2026, 1, 31))
        ],
    )

    result = recommend_route_allocation(request, published_european_corridor_tariffs())

    assert result.allocations == []
    assert result.excluded_routes[0].blockers == [
        "TARIFF_APPLICABILITY_DATE_MISMATCH:2026-01-31"
    ]


def test_recommendation_blocks_known_capacity_without_a_capacity_value() -> None:
    """KNOWN with no limit cannot become unlimited; only NOT_REQUIRED may."""

    result = recommend_route_allocation(
        _local_sale_request(
            [
                _local_sale_candidate(
                    available_capacity_mwh_per_day=None,
                    capacity_status="KNOWN",
                )
            ]
        ),
        published_european_corridor_tariffs(),
    )

    assert result.allocations == []
    assert result.excluded_routes[0].blockers == ["ROUTE_CAPACITY_UNKNOWN"]


def test_recommendation_echoes_caller_source_refs_as_unverified_input() -> None:
    """Caller references are visible evidence, clearly marked and non-binding."""

    result = recommend_route_allocation(
        _local_sale_request(
            [
                _local_sale_candidate(
                    source_refs=[
                        "route_candidate:local-ttf-sale",
                        "operator:option-read:2026-01-31",
                    ]
                )
            ]
        ),
        published_european_corridor_tariffs(),
    )

    assert result.status == "SUCCESS"
    allocation = result.allocations[0]
    assert allocation.source_refs == [
        "unverified_input:route_candidate:local-ttf-sale",
        "unverified_input:operator:option-read:2026-01-31",
    ]
    # The raw claims are kept in a separate field, so no consumer can mistake
    # them for backend-verified tariff provenance.
    assert allocation.unverified_input_source_refs == [
        "route_candidate:local-ttf-sale",
        "operator:option-read:2026-01-31",
    ]
