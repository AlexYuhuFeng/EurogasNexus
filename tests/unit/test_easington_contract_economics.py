"""UK Easington contract option economics tests."""

from eurogas_nexus.domain.route_cost.contract_economics import (
    EasingtonContractScenario,
    compare_easington_contract_options,
)


def test_easington_contract_compares_nbp_and_physical_exit_options() -> None:
    result = compare_easington_contract_options(
        EasingtonContractScenario(
            contract_id="contract-easington-demo",
            gas_year="2025/26",
            delivery_quantity_mwh_per_day=10_000,
            contract_price_gbp_mwh=25.0,
            nbp_sale_price_gbp_mwh=28.0,
            physical_exit_sale_price_gbp_mwh=28.5,
            physical_exit_point_name="Bacton GDN (EA)",
            delivery_tolerance_pct=2.0,
            nomination_tolerance_pct=1.0,
            tolerance_risk_allowance_gbp_mwh=0.10,
        )
    )

    options = {option.option_id: option for option in result.options}
    nbp = options["nbp_virtual_sale"]
    physical = options["physical_exit_delivery"]

    assert result.contract_id == "contract-easington-demo"
    assert nbp.business_model == "VIRTUAL_HUB_SALE"
    assert physical.business_model == "PHYSICAL_DELIVERY"
    assert nbp.exit_capacity_charge_gbp_mwh == 0.0
    assert physical.exit_capacity_charge_gbp_mwh == 0.299
    assert physical.commodity_charge_gbp_mwh == 0.412
    assert nbp.early_cash_value_gbp_mwh == 0.0781
    assert nbp.net_pnl_gbp_per_day == 16861.0
    assert physical.net_pnl_gbp_per_day == 16811.0
    assert result.delivery_tolerance_mwh == 200.0
    assert result.nomination_tolerance_mwh == 100.0


def test_easington_contract_2026_27_indicative_requires_review() -> None:
    result = compare_easington_contract_options(
        EasingtonContractScenario(
            contract_id="contract-easington-2026",
            gas_year="2026/27",
            delivery_quantity_mwh_per_day=5_000,
            contract_price_gbp_mwh=25.0,
            nbp_sale_price_gbp_mwh=28.0,
            physical_exit_sale_price_gbp_mwh=28.5,
            physical_exit_point_name="Bacton GDN (EA)",
            delivery_tolerance_pct=2.0,
            nomination_tolerance_pct=1.0,
            tolerance_risk_allowance_gbp_mwh=0.10,
        )
    )

    assert result.human_review_required is True
    assert "INDICATIVE_TARIFF_USED" in result.warnings
    assert all(option.tariff_status_summary["INDICATIVE"] >= 1 for option in result.options)


def test_easington_contract_without_tolerance_allowance_reports_gap() -> None:
    result = compare_easington_contract_options(
        EasingtonContractScenario(
            contract_id="contract-easington-gap",
            gas_year="2025/26",
            delivery_quantity_mwh_per_day=5_000,
            contract_price_gbp_mwh=25.0,
            nbp_sale_price_gbp_mwh=28.0,
            physical_exit_sale_price_gbp_mwh=28.5,
            physical_exit_point_name="Bacton GDN (EA)",
            delivery_tolerance_pct=2.0,
            nomination_tolerance_pct=1.0,
        )
    )

    assert "TOLERANCE_RISK_ALLOWANCE_NOT_PROVIDED" in result.missing_inputs
    assert result.human_review_required is True
