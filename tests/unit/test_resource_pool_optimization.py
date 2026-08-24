"""Portfolio resource-pool optimization tests.

The engine is an exact min-cost flow, so the documented greedy counterexample
now resolves to the global optimum; status never claims SUCCESS while volume
remains unallocated, and unknown capacity/access fails closed.
"""

from eurogas_nexus.domain.ontology.vocabulary import CapacityStatus
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
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    delivery_tolerance_pct=2,
                    nomination_tolerance_pct=1,
                    required_tso_access=["BBL Company"],
                    accessible_tsos=["BBL Company"],
                ),
                PortfolioResource(
                    resource_id="gate-lng-a",
                    resource_name="GATE LNG A",
                    resource_type=SourceResourceType.LNG_REGAS,
                    delivery_mode=DeliveryMode.TERMINAL_TITLE_TRANSFER,
                    location_point_name="GATE LNG",
                    available_quantity_mwh_per_day=8_000,
                    contract_cost_gbp_mwh=24,
                    delivery_tolerance_pct=0,
                    nomination_tolerance_pct=0,
                ),
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="nbp",
                    label="NBP sale via BBL",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="NBP",
                    sale_price_gbp_mwh=29,
                    route_cost_gbp_mwh=1.4,
                    capacity_limit_mwh_per_day=6_000,
                    required_tso_access=["BBL Company"],
                ),
                PortfolioSaleOption(
                    option_id="terminal",
                    label="Terminal title transfer",
                    delivery_mode=DeliveryMode.TERMINAL_TITLE_TRANSFER,
                    target_point_name="GATE LNG",
                    sale_price_gbp_mwh=27,
                    route_cost_gbp_mwh=0.5,
                    capacity_status=CapacityStatus.NOT_REQUIRED,
                ),
            ],
        )
    )

    # 4,000 MWh/d remain unallocated, so SUCCESS would be dishonest.
    assert result.status == "PARTIAL"
    assert result.total_allocated_mwh_per_day == 14_000
    assert result.total_unallocated_mwh_per_day == 4_000
    assert result.algorithm == "MIN_COST_FLOW"
    assert len(result.assumptions) >= 3
    assert any("decision support only" in item for item in result.assumptions)
    assert "PORTFOLIO_VOLUME_UNALLOCATED" in result.warnings
    assert result.allocations[0].option_id == "nbp"
    assert result.allocations[0].allocated_quantity_mwh_per_day == 6_000
    assert result.allocations[1].option_id == "terminal"


def test_resource_pool_skips_inaccessible_tso_options() -> None:
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-access",
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    delivery_tolerance_pct=2,
                    nomination_tolerance_pct=1,
                    required_tso_access=["BBL Company"],
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
                    capacity_status=CapacityStatus.NOT_REQUIRED,
                    required_tso_access=["BBL Company"],
                ),
            ],
        )
    )

    assert result.status == "BLOCKED"
    assert result.allocations == []
    assert "TSO_ACCESS_MISSING:BBL Company" in result.warnings


def test_resource_pool_fails_closed_when_tso_access_unknown() -> None:
    # accessible_tsos=None must not be interpreted as unrestricted.
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-unknown-access",
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    delivery_tolerance_pct=2,
                    nomination_tolerance_pct=1,
                    required_tso_access=["BBL Company"],
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
                    capacity_status=CapacityStatus.NOT_REQUIRED,
                    required_tso_access=["BBL Company"],
                ),
            ],
        )
    )

    assert result.status == "BLOCKED"
    assert result.allocations == []
    assert "TSO_ACCESS_UNKNOWN:BBL Company" in result.warnings


def test_resource_pool_fails_closed_when_capacity_unknown() -> None:
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-unknown-capacity",
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    delivery_tolerance_pct=2,
                    nomination_tolerance_pct=1,
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
                    required_tso_access=[],
                ),
            ],
        )
    )

    assert result.status == "BLOCKED"
    assert result.allocations == []
    assert "ROUTE_CAPACITY_UNKNOWN:nbp" in result.warnings


def test_resource_pool_never_mixes_currencies() -> None:
    # EUR sale price vs GBP contract cost must fail closed, not be mixed.
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-currency",
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    delivery_tolerance_pct=2,
                    nomination_tolerance_pct=1,
                ),
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="ttf-sale-eur",
                    label="TTF sale in EUR",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="TTF",
                    sale_price_gbp_mwh=35.0,
                    sale_price_currency="EUR",
                    sale_price_unit="EUR/MWh",
                    capacity_status=CapacityStatus.NOT_REQUIRED,
                ),
            ],
        )
    )

    assert result.status == "BLOCKED"
    assert result.allocations == []
    assert (
        "PRICE_COST_CURRENCY_MISMATCH:ttf-pipeline-a:ttf-sale-eur" in result.warnings
    )


def test_resource_pool_accepts_matching_non_gbp_currencies() -> None:
    # EUR-to-EUR is internally consistent and must allocate normally.
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-eur",
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    contract_cost_currency="EUR",
                    contract_cost_unit="EUR/MWh",
                    delivery_tolerance_pct=2,
                    nomination_tolerance_pct=1,
                ),
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="ttf-sale",
                    label="TTF sale",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="TTF",
                    sale_price_gbp_mwh=29,
                    sale_price_currency="EUR",
                    sale_price_unit="EUR/MWh",
                    capacity_status=CapacityStatus.NOT_REQUIRED,
                ),
            ],
        )
    )

    assert result.status == "SUCCESS"
    assert result.total_allocated_mwh_per_day == 10_000
    assert result.allocations[0].option_id == "ttf-sale"


def test_exact_solver_beats_greedy_on_pairwise_capacity_conflict() -> None:
    """Documented counterexample where greedy marginal allocation is suboptimal.

    Resource A can sell to X (margin 20) and Y (margin 19); resource B can only
    sell to X (margin 18) because Y requires a TSO B has no access to. Option X
    has only 100 MWh/d of capacity. Greedy assigns A->X first (its top margin),
    starving B entirely: total 2000. The exact min-cost flow reroutes A to Y and
    gives X to B: total 3700 (the audit's 100-vs-189 failure mode).
    """

    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-conflict",
            resources=[
                PortfolioResource(
                    resource_id="resource-a",
                    resource_name="Resource A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=100,
                    contract_cost_gbp_mwh=10,
                    delivery_tolerance_pct=0,
                    nomination_tolerance_pct=0,
                    upstream_payment_lag_days=1,
                    accessible_tsos=["TSO-Y"],
                ),
                PortfolioResource(
                    resource_id="resource-b",
                    resource_name="Resource B",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=100,
                    contract_cost_gbp_mwh=12,
                    delivery_tolerance_pct=0,
                    nomination_tolerance_pct=0,
                    upstream_payment_lag_days=1,
                    accessible_tsos=["TSO-X"],
                ),
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="option-x",
                    label="Option X",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="X",
                    sale_price_gbp_mwh=30,
                    capacity_limit_mwh_per_day=100,
                    screen_sale_cash_lag_days=1,
                ),
                PortfolioSaleOption(
                    option_id="option-y",
                    label="Option Y (requires TSO-Y)",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="Y",
                    sale_price_gbp_mwh=29,
                    capacity_status=CapacityStatus.NOT_REQUIRED,
                    screen_sale_cash_lag_days=1,
                    required_tso_access=["TSO-Y"],
                ),
            ],
        )
    )

    assert result.status == "SUCCESS"
    assert result.total_allocated_mwh_per_day == 200
    assert result.total_unallocated_mwh_per_day == 0
    by_option = {item.option_id: item for item in result.allocations}
    assert by_option["option-x"].resource_id == "resource-b"
    assert by_option["option-y"].resource_id == "resource-a"
    assert result.total_net_pnl_gbp_per_day == 3700
