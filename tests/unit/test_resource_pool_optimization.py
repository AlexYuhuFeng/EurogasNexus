"""Portfolio resource-pool optimization tests."""

from eurogas_nexus.domain.route_cost.enums import DeliveryMode, SourceResourceType
from eurogas_nexus.domain.route_cost.resource_pool import (
    PortfolioOptimizationScenario,
    PortfolioResource,
    PortfolioSaleOption,
    optimize_resource_pool,
)


def test_resource_pool_allocates_best_margin_across_multiple_upstreams() -> None:
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-1",
            resources=[
                PortfolioResource(
                    resource_id="beach-a",
                    resource_name="Beach A",
                    resource_type=SourceResourceType.BEACH_DELIVERY,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="Easington Beach Terminal",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    delivery_tolerance_pct=2,
                    nomination_tolerance_pct=1,
                    required_tso_access=["National Gas NTS"],
                    accessible_tsos=["National Gas NTS"],
                ),
                PortfolioResource(
                    resource_id="lng-a",
                    resource_name="LNG A",
                    resource_type=SourceResourceType.LNG_REGAS,
                    delivery_mode=DeliveryMode.TERMINAL_TITLE_TRANSFER,
                    location_point_name="Isle of Grain",
                    available_quantity_mwh_per_day=8_000,
                    contract_cost_gbp_mwh=24,
                    delivery_tolerance_pct=0,
                    nomination_tolerance_pct=0,
                ),
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="nbp",
                    label="NBP sale",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="NBP",
                    sale_price_gbp_mwh=29,
                    route_cost_gbp_mwh=1.4,
                    capacity_limit_mwh_per_day=6_000,
                    required_tso_access=["National Gas NTS"],
                ),
                PortfolioSaleOption(
                    option_id="terminal",
                    label="Terminal title transfer",
                    delivery_mode=DeliveryMode.TERMINAL_TITLE_TRANSFER,
                    target_point_name="Isle of Grain",
                    sale_price_gbp_mwh=27,
                    route_cost_gbp_mwh=0.5,
                ),
            ],
        )
    )

    assert result.status == "SUCCESS"
    assert result.total_allocated_mwh_per_day == 14_000
    assert result.total_unallocated_mwh_per_day == 4_000
    assert result.allocations[0].option_id == "nbp"
    assert result.allocations[0].allocated_quantity_mwh_per_day == 6_000
    assert result.allocations[1].option_id == "terminal"


def test_resource_pool_skips_inaccessible_tso_options() -> None:
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-access",
            resources=[
                PortfolioResource(
                    resource_id="beach-a",
                    resource_name="Beach A",
                    resource_type=SourceResourceType.BEACH_DELIVERY,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="Easington Beach Terminal",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    delivery_tolerance_pct=2,
                    nomination_tolerance_pct=1,
                    required_tso_access=["National Gas NTS"],
                    accessible_tsos=["Fluxys Belgium"],
                ),
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="nbp",
                    label="NBP sale",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="NBP",
                    sale_price_gbp_mwh=29,
                    route_cost_gbp_mwh=1.4,
                    required_tso_access=["National Gas NTS"],
                ),
            ],
        )
    )

    assert result.status == "BLOCKED"
    assert result.allocations == []
