"""#14: a contract funded in segments values early cash per segment, then sums them."""

import pytest

from eurogas_nexus.domain.route_cost.resource_pool import (
    FinancingTranche,
    PortfolioResource,
    _tranched_early_cash_gbp_mwh,
)


def _resource(**extra) -> PortfolioResource:
    return PortfolioResource(
        resource_id="r1",
        resource_name="Contract",
        resource_type="PIPELINE_IMPORT",
        delivery_mode="PHYSICAL_ENTRY_DELIVERY",
        location_point_name="Easington",
        available_quantity_mwh_per_day=1000,
        contract_cost_gbp_mwh=30.0,
        upstream_payment_lag_days=50,
        **extra,
    )


def test_two_lenders_are_valued_separately_and_summed():
    # Bank A lends 100 at 3 %, bank B 200 at 2 %, both ACT/365F, 30 days of lag.
    resource = _resource(
        financing_tranches=[
            FinancingTranche(lender="A", principal=100, annual_rate_pct=3),
            FinancingTranche(lender="B", principal=200, annual_rate_pct=2),
        ]
    )
    total, rows = _tranched_early_cash_gbp_mwh(resource, screen_sale_cash_lag_days=20)
    a = 30.0 * (100 / 300) * 0.03 * 30 / 365
    b = 30.0 * (200 / 300) * 0.02 * 30 / 365
    assert total == pytest.approx(round(a + b, 4))
    assert [row["lender"] for row in rows] == ["A", "B"]
    assert rows[0]["early_cash_value_gbp_mwh"] == pytest.approx(round(a, 4))
    # Not the simple average of 3 % and 2 % applied to the whole cost.
    assert total != pytest.approx(round(30.0 * 0.025 * 30 / 365, 4))


def test_each_segment_keeps_its_own_day_count():
    resource = _resource(
        financing_tranches=[
            FinancingTranche(lender="A", principal=1, annual_rate_pct=3, day_count="ACT/360"),
        ]
    )
    total, _ = _tranched_early_cash_gbp_mwh(resource, screen_sale_cash_lag_days=20)
    assert total == pytest.approx(round(30.0 * 0.03 * 30 / 360, 4))


def test_order_of_segments_does_not_change_the_value():
    a = FinancingTranche(lender="A", principal=100, annual_rate_pct=3)
    b = FinancingTranche(lender="B", principal=200, annual_rate_pct=2)
    first, _ = _tranched_early_cash_gbp_mwh(
        _resource(financing_tranches=[a, b]), screen_sale_cash_lag_days=20
    )
    second, _ = _tranched_early_cash_gbp_mwh(
        _resource(financing_tranches=[b, a]), screen_sale_cash_lag_days=20
    )
    assert first == second


def test_a_segment_needs_a_lender_and_a_positive_principal():
    with pytest.raises(ValueError):
        FinancingTranche(lender="", principal=100, annual_rate_pct=3)
    with pytest.raises(ValueError):
        FinancingTranche(lender="A", principal=0, annual_rate_pct=3)


def test_the_pool_reports_each_segment_on_the_allocation():
    from eurogas_nexus.domain.route_cost.resource_pool import (
        PortfolioOptimizationScenario,
        PortfolioSaleOption,
        optimize_resource_pool,
    )

    resource = _resource(
        screen_sale_cash_lag_days=20,
        financing_tranches=[
            FinancingTranche(lender="A", principal=100, annual_rate_pct=3),
            FinancingTranche(lender="B", principal=200, annual_rate_pct=2, day_count="ACT/360"),
        ],
    )
    option = PortfolioSaleOption.model_validate(
        {
            "option_id": "o1",
            "label": "NBP day-ahead",
            "delivery_mode": "VIRTUAL_HUB_SALE",
            "target_point_name": "NBP",
            "capacity_status": "KNOWN",
            "sale_price_gbp_mwh": 40.0,
            "route_cost_gbp_mwh": 1.0,
            "capacity_limit_mwh_per_day": 1000,
            "screen_sale_cash_lag_days": 20,
        }
    )
    result = optimize_resource_pool(
        PortfolioOptimizationScenario(
            portfolio_id="p",
            resources=[resource],
            sale_options=[option],
            annual_financing_rate_pct=5.0,
        )
    )
    allocation = result.allocations[0]
    assert allocation.financing_rate_source == "contract_tranches"
    assert allocation.financing_rate_pct is None
    assert [row["lender"] for row in allocation.financing_tranches] == ["A", "B"]
    assert allocation.early_cash_value_gbp_mwh == pytest.approx(
        sum(row["early_cash_value_gbp_mwh"] for row in allocation.financing_tranches), abs=1e-4
    )
