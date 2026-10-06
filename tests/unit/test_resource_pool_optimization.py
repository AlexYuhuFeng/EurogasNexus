"""Portfolio resource-pool optimization tests.

The engine is an exact min-cost flow, so the documented greedy counterexample
now resolves to the global optimum; status never claims SUCCESS while volume
remains unallocated, and unknown capacity/access fails closed. The annual
financing rate is a required explicit input: scenario fixtures that make no
financing claim carry an explicit ``0``, and omitted/non-finite/non-numeric
rates are refused at the model boundary instead of receiving the removed 6.0
default. The payment/sale lags are required explicit inputs as well: fixtures
that make no other cash-timing claim restate the previously implicit ``20``
days upstream and ``1`` day screen-sale defaults so their arithmetic is
unchanged, and fixtures that do care declare the lag they mean.
"""

import pytest
from pydantic import ValidationError

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
            annual_financing_rate_pct=0,
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    upstream_payment_lag_days=20,
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
                    upstream_payment_lag_days=20,
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
                    screen_sale_cash_lag_days=1,
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
                    screen_sale_cash_lag_days=1,
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
            annual_financing_rate_pct=0,
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    upstream_payment_lag_days=20,
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
                    screen_sale_cash_lag_days=1,
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
            annual_financing_rate_pct=0,
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    upstream_payment_lag_days=20,
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
                    screen_sale_cash_lag_days=1,
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
            annual_financing_rate_pct=0,
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    upstream_payment_lag_days=20,
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
                    screen_sale_cash_lag_days=1,
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
            annual_financing_rate_pct=0,
            resources=[
                PortfolioResource(
                    resource_id="ttf-pipeline-a",
                    resource_name="TTF pipeline portfolio A",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10_000,
                    contract_cost_gbp_mwh=25,
                    upstream_payment_lag_days=20,
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
                    screen_sale_cash_lag_days=1,
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
            annual_financing_rate_pct=0,
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
                    upstream_payment_lag_days=20,
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
                    screen_sale_cash_lag_days=1,
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
            annual_financing_rate_pct=0,
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


def test_resource_specific_route_eligibility_cannot_leak_between_contracts() -> None:
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-contract-restrictions",
            annual_financing_rate_pct=0,
            resources=[
                PortfolioResource(
                    resource_id="allowed-resource",
                    resource_name="Allowed resource",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=100,
                    contract_cost_gbp_mwh=20,
                    upstream_payment_lag_days=20,
                    delivery_tolerance_pct=0,
                    nomination_tolerance_pct=0,
                ),
                PortfolioResource(
                    resource_id="restricted-resource",
                    resource_name="Restricted resource",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=100,
                    contract_cost_gbp_mwh=10,
                    upstream_payment_lag_days=20,
                    delivery_tolerance_pct=0,
                    nomination_tolerance_pct=0,
                ),
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="ttf-nbp",
                    label="TTF to NBP",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="NBP",
                    sale_price_gbp_mwh=30,
                    capacity_status=CapacityStatus.NOT_REQUIRED,
                    screen_sale_cash_lag_days=1,
                    eligible_resource_ids=["allowed-resource"],
                )
            ],
        )
    )

    assert len(result.allocations) == 1
    assert result.allocations[0].resource_id == "allowed-resource"
    assert result.allocations[0].allocated_quantity_mwh_per_day == 100
    assert result.total_unallocated_mwh_per_day == 100


def test_resource_pool_includes_variable_cost_and_fuel_loss_uplift() -> None:
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="pool-cost-truth",
            annual_financing_rate_pct=0,
            resources=[
                PortfolioResource(
                    resource_id="lng-resource",
                    resource_name="LNG resource",
                    resource_type=SourceResourceType.PIPELINE_IMPORT,
                    delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                    location_point_name="TTF",
                    available_quantity_mwh_per_day=10,
                    contract_cost_gbp_mwh=20,
                    variable_cost_gbp_mwh=1,
                    fuel_loss_allowance_pct=5,
                    upstream_payment_lag_days=20,
                    delivery_tolerance_pct=0,
                    nomination_tolerance_pct=0,
                )
            ],
            sale_options=[
                PortfolioSaleOption(
                    option_id="ttf-local",
                    label="TTF local",
                    delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                    target_point_name="TTF",
                    sale_price_gbp_mwh=30,
                    capacity_status=CapacityStatus.NOT_REQUIRED,
                    screen_sale_cash_lag_days=1,
                )
            ],
        )
    )

    allocation = result.allocations[0]
    assert allocation.total_cost_gbp_mwh == 22.1053
    assert allocation.net_margin_gbp_mwh == 7.8947


# ---------------------------------------------------------------------------
# Explicit financing-rate boundary (audited implicit 6% default defect)
# ---------------------------------------------------------------------------

_SCENARIO_BASE: dict[str, object] = {
    "portfolio_id": "pool-rate",
    "resources": [],
    "sale_options": [],
}


def test_scenario_requires_an_explicit_financing_rate() -> None:
    """Omission is refused: there is no server-side default rate."""

    with pytest.raises(ValidationError) as excinfo:
        PortfolioOptimizationScenario.model_validate(dict(_SCENARIO_BASE))

    assert "annual_financing_rate_pct" in str(excinfo.value)


@pytest.mark.parametrize(
    "invalid_rate",
    [
        None,
        True,
        False,
        "6",
        "6.0",
        "",
        "  ",
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_scenario_refuses_unknown_or_non_finite_financing_rates(
    invalid_rate: object,
) -> None:
    """Null, booleans, strings and non-finite values never become a rate."""

    with pytest.raises(ValidationError):
        PortfolioOptimizationScenario.model_validate(
            {**_SCENARIO_BASE, "annual_financing_rate_pct": invalid_rate}
        )


def test_scenario_accepts_an_explicit_integer_financing_rate() -> None:
    """A JSON integer is an explicit number and is accepted as such."""

    scenario = PortfolioOptimizationScenario.model_validate(
        {**_SCENARIO_BASE, "annual_financing_rate_pct": 6}
    )

    assert scenario.annual_financing_rate_pct == 6.0


def _early_cash_scenario(annual_financing_rate_pct: float) -> PortfolioOptimizationScenario:
    return PortfolioOptimizationScenario(
        portfolio_id="pool-early-cash",
        annual_financing_rate_pct=annual_financing_rate_pct,
        resources=[
            PortfolioResource(
                resource_id="resource-a",
                resource_name="Resource A",
                resource_type=SourceResourceType.PIPELINE_IMPORT,
                delivery_mode=DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
                location_point_name="TTF",
                available_quantity_mwh_per_day=1_000,
                contract_cost_gbp_mwh=25,
                delivery_tolerance_pct=0,
                nomination_tolerance_pct=0,
                upstream_payment_lag_days=30,
                screen_sale_cash_lag_days=0,
            )
        ],
        sale_options=[
            PortfolioSaleOption(
                option_id="ttf-local",
                label="TTF local sale",
                delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE,
                target_point_name="TTF",
                sale_price_gbp_mwh=30,
                capacity_status=CapacityStatus.NOT_REQUIRED,
                # The sale option declares its lag unknown; the resource's
                # explicit override supplies the pair's effective lag.
                screen_sale_cash_lag_days=None,
            )
        ],
    )


def test_explicit_zero_financing_rate_is_a_recorded_zero() -> None:
    """An explicitly supplied 0 stays 0: no financing credit is invented."""

    result = optimize_resource_pool(_early_cash_scenario(0))

    allocation = result.allocations[0]
    assert allocation.early_cash_value_gbp_mwh == 0.0
    assert allocation.total_cost_gbp_mwh == 25.0
    assert allocation.net_margin_gbp_mwh == 5.0


def test_explicit_nonzero_financing_rate_credits_the_early_cash_term() -> None:
    """A declared positive rate still produces the documented credit."""

    # 25 GBP/MWh × 10%/yr × 30 lag days / 365 = 0.2055 GBP/MWh (4 dp).
    result = optimize_resource_pool(_early_cash_scenario(10))

    allocation = result.allocations[0]
    assert allocation.early_cash_value_gbp_mwh == 0.2055
    assert allocation.total_cost_gbp_mwh == 24.7945
    assert allocation.net_margin_gbp_mwh == 5.2055
    assert any("no default rate" in assumption for assumption in result.assumptions)


# ---------------------------------------------------------------------------
# Explicit payment/sale lag boundary (audited implicit 20/1 default defect)
# ---------------------------------------------------------------------------

_LAG_RESOURCE: dict[str, object] = {
    "resource_id": "lag-resource",
    "resource_name": "Lag resource",
    "resource_type": SourceResourceType.PIPELINE_IMPORT,
    "delivery_mode": DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
    "location_point_name": "TTF",
    "available_quantity_mwh_per_day": 1_000,
    "contract_cost_gbp_mwh": 25,
    "delivery_tolerance_pct": 0,
    "nomination_tolerance_pct": 0,
    "upstream_payment_lag_days": 30,
}

_LAG_OPTION: dict[str, object] = {
    "option_id": "lag-option",
    "label": "Lag option",
    "delivery_mode": DeliveryMode.VIRTUAL_HUB_SALE,
    "target_point_name": "TTF",
    "sale_price_gbp_mwh": 30,
    "capacity_status": CapacityStatus.NOT_REQUIRED,
    "screen_sale_cash_lag_days": 10,
}


def _lag_scenario(
    resource: dict[str, object] | None = None,
    option: dict[str, object] | None = None,
) -> PortfolioOptimizationScenario:
    """One pair whose only variable input is the cash-lag declaration."""

    resource_values = {**_LAG_RESOURCE, **(resource or {})}
    option_values = {**_LAG_OPTION, **(option or {})}
    return PortfolioOptimizationScenario(
        portfolio_id="pool-lag",
        annual_financing_rate_pct=10,
        resources=[PortfolioResource.model_validate(resource_values)],
        sale_options=[PortfolioSaleOption.model_validate(option_values)],
    )


def test_resource_requires_an_explicit_upstream_payment_lag() -> None:
    """Omission is refused: there is no server-side 20-day payment lag."""

    payload = {
        key: value
        for key, value in _LAG_RESOURCE.items()
        if key != "upstream_payment_lag_days"
    }

    with pytest.raises(ValidationError) as excinfo:
        PortfolioResource.model_validate(payload)

    assert "upstream_payment_lag_days" in str(excinfo.value)


@pytest.mark.parametrize(
    "invalid_lag",
    [None, True, False, 20.0, "20", "", -1],
)
def test_resource_refuses_non_integer_or_negative_payment_lags(
    invalid_lag: object,
) -> None:
    """Null, booleans, floats, strings and negatives never become a lag."""

    with pytest.raises(ValidationError) as excinfo:
        PortfolioResource.model_validate(
            {**_LAG_RESOURCE, "upstream_payment_lag_days": invalid_lag}
        )

    assert "upstream_payment_lag_days" in str(excinfo.value)


def test_sale_option_requires_an_explicit_screen_sale_cash_lag() -> None:
    """Omission is refused: there is no server-side one-day sale lag."""

    payload = {
        key: value
        for key, value in _LAG_OPTION.items()
        if key != "screen_sale_cash_lag_days"
    }

    with pytest.raises(ValidationError) as excinfo:
        PortfolioSaleOption.model_validate(payload)

    assert "screen_sale_cash_lag_days" in str(excinfo.value)


@pytest.mark.parametrize(
    "invalid_lag",
    [True, False, 1.0, "1", "", -1],
)
def test_sale_option_refuses_non_integer_or_negative_sale_lags(
    invalid_lag: object,
) -> None:
    """Only whole non-negative days or an explicit null are accepted."""

    with pytest.raises(ValidationError) as excinfo:
        PortfolioSaleOption.model_validate(
            {**_LAG_OPTION, "screen_sale_cash_lag_days": invalid_lag}
        )

    assert "screen_sale_cash_lag_days" in str(excinfo.value)


def test_sale_option_accepts_an_explicit_unknown_sale_lag() -> None:
    """An explicit null is a declared unknown, not a value to default."""

    option = PortfolioSaleOption.model_validate(
        {**_LAG_OPTION, "screen_sale_cash_lag_days": None}
    )

    assert option.screen_sale_cash_lag_days is None


@pytest.mark.parametrize(
    "invalid_override",
    [True, False, 0.0, "0", -2],
)
def test_resource_override_refuses_non_integer_or_negative_lags(
    invalid_override: object,
) -> None:
    """The optional override, when present, is held to the same rule."""

    with pytest.raises(ValidationError) as excinfo:
        PortfolioResource.model_validate(
            {**_LAG_RESOURCE, "screen_sale_cash_lag_days": invalid_override}
        )

    assert "screen_sale_cash_lag_days" in str(excinfo.value)


def test_explicit_zero_lags_are_recorded_zeros() -> None:
    """Zero days is a declared value, not "unknown" and not a default."""

    scenario = _lag_scenario(resource={"upstream_payment_lag_days": 0})
    result = optimize_resource_pool(scenario)

    allocation = result.allocations[0]
    assert allocation.early_cash_value_gbp_mwh == 0.0
    assert allocation.total_cost_gbp_mwh == 25.0


def test_explicit_sale_lag_is_used_when_the_resource_declares_no_override() -> None:
    """The option's declared lag prices the credit when no override exists."""

    # 25 GBP/MWh × 10%/yr × 20 lag days / 365 = 0.1370 GBP/MWh (4 dp).
    result = optimize_resource_pool(_lag_scenario())

    allocation = result.allocations[0]
    assert allocation.early_cash_value_gbp_mwh == 0.1370
    assert allocation.net_margin_gbp_mwh == 5.1370


def test_resource_override_is_used_when_the_option_lag_is_unknown() -> None:
    """An explicit override keeps a pair usable when the option lag is null."""

    result = optimize_resource_pool(
        _lag_scenario(
            option={"screen_sale_cash_lag_days": None},
            resource={"screen_sale_cash_lag_days": 0},
        )
    )

    assert result.status == "SUCCESS"
    allocation = result.allocations[0]
    # 25 GBP/MWh × 10%/yr × 30 lag days / 365 = 0.2055 GBP/MWh (4 dp).
    assert allocation.early_cash_value_gbp_mwh == 0.2055
    assert allocation.total_cost_gbp_mwh == 24.7945


def test_unknown_effective_sale_lag_refuses_the_pair_without_zero_credit() -> None:
    """Neither side declares the lag: refuse the pair, never assume day zero."""

    result = optimize_resource_pool(
        _lag_scenario(option={"screen_sale_cash_lag_days": None})
    )

    assert result.status == "BLOCKED"
    assert result.allocations == []
    assert "SALE_CASH_LAG_MISSING:lag-resource:lag-option" in result.missing_inputs
    assert "SALE_CASH_LAG_UNKNOWN:lag-resource:lag-option" in result.warnings
    assert any("assumed receipt day" in assumption for assumption in result.assumptions)
