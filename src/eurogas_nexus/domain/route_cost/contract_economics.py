"""Contract-specific route economics and option comparison."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, Field

from eurogas_nexus.domain.route_cost.enums import TariffDirection
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff
from eurogas_nexus.domain.route_cost.tariff_selection import select_latest_tariff
from eurogas_nexus.domain.route_cost.uk_rules import (
    UK_BACTON_GDN_EXIT_POINT_NAME,
    UK_EASINGTON_POINT_NAME,
)

PENCE_PER_KWH_DAY_TO_GBP_PER_MWH = 10.0
NTS_COMMODITY_CHARGE_GBP_MWH = 0.206


class EasingtonContractScenario(BaseModel):
    contract_id: str
    contract_name: str = "Easington beach delivery contract"
    gas_year: str
    delivery_quantity_mwh_per_day: float
    contract_price_gbp_mwh: float
    nbp_sale_price_gbp_mwh: float
    physical_exit_sale_price_gbp_mwh: float
    physical_exit_point_name: str = UK_BACTON_GDN_EXIT_POINT_NAME
    delivery_tolerance_pct: float
    nomination_tolerance_pct: float
    tolerance_risk_allowance_gbp_mwh: float | None = None
    settlement_frequency: str = "monthly"
    upstream_payment_lag_days: int = 20
    screen_sale_cash_lag_days: int = 1
    annual_financing_rate_pct: float = 6.0
    owned_entry_capacity_mwh_per_day: float | None = None
    owned_exit_capacity_mwh_per_day: float | None = None
    allowed_exit_points: list[str] = Field(default_factory=lambda: [UK_BACTON_GDN_EXIT_POINT_NAME])
    eligible_sale_modes: list[str] = Field(
        default_factory=lambda: ["VIRTUAL_HUB_SALE", "PHYSICAL_DELIVERY"]
    )
    existing_capacity_profile_source: str = "operator-input"


class EasingtonOptionPnl(BaseModel):
    option_id: str
    label: str
    business_model: str
    sale_price_gbp_mwh: float
    contract_cost_gbp_mwh: float
    entry_capacity_charge_gbp_mwh: float
    exit_capacity_charge_gbp_mwh: float
    commodity_charge_gbp_mwh: float
    tolerance_risk_allowance_gbp_mwh: float
    early_cash_value_gbp_mwh: float = 0.0
    total_charges_gbp_mwh: float
    net_margin_gbp_mwh: float
    net_pnl_gbp_per_day: float
    source_refs: list[str] = Field(default_factory=list)
    route_legs: list[dict] = Field(default_factory=list)
    tariff_status_summary: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = False


class EasingtonContractOptionsResult(BaseModel):
    contract_id: str
    gas_year: str
    delivery_point_name: str = UK_EASINGTON_POINT_NAME
    delivery_quantity_mwh_per_day: float
    delivery_tolerance_pct: float
    nomination_tolerance_pct: float
    delivery_tolerance_mwh: float
    nomination_tolerance_mwh: float
    options: list[EasingtonOptionPnl]
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = False


def compare_easington_contract_options(
    scenario: EasingtonContractScenario,
    tariffs: Sequence[CapacityTariff] | None = None,
) -> EasingtonContractOptionsResult:
    """Compare NBP virtual sale and physical exit delivery for an Easington contract."""

    from eurogas_nexus.domain.route_cost.uk_demo_data import demo_uk_capacity_tariffs

    available_tariffs = list(tariffs or demo_uk_capacity_tariffs())
    missing_inputs: list[str] = []
    warnings: list[str] = []
    if scenario.tolerance_risk_allowance_gbp_mwh is None:
        missing_inputs.append("TOLERANCE_RISK_ALLOWANCE_NOT_PROVIDED")
    tolerance_allowance = scenario.tolerance_risk_allowance_gbp_mwh or 0.0

    options: list[EasingtonOptionPnl] = []
    if "VIRTUAL_HUB_SALE" in scenario.eligible_sale_modes:
        options.append(
            _build_option(
                scenario,
                available_tariffs,
                option_id="nbp_virtual_sale",
                label="NBP virtual sale",
                business_model="VIRTUAL_HUB_SALE",
                sale_price=scenario.nbp_sale_price_gbp_mwh,
                exit_point_name=None,
                tolerance_allowance=tolerance_allowance,
            )
        )
    if "PHYSICAL_DELIVERY" in scenario.eligible_sale_modes:
        options.append(
            _build_option(
                scenario,
                available_tariffs,
                option_id="physical_exit_delivery",
                label=f"Physical exit delivery to {scenario.physical_exit_point_name}",
                business_model="PHYSICAL_DELIVERY",
                sale_price=scenario.physical_exit_sale_price_gbp_mwh,
                exit_point_name=scenario.physical_exit_point_name,
                tolerance_allowance=tolerance_allowance,
            )
        )

    if any("INDICATIVE" in option.tariff_status_summary for option in options):
        warnings.append("INDICATIVE_TARIFF_USED")

    return EasingtonContractOptionsResult(
        contract_id=scenario.contract_id,
        gas_year=scenario.gas_year,
        delivery_quantity_mwh_per_day=scenario.delivery_quantity_mwh_per_day,
        delivery_tolerance_pct=scenario.delivery_tolerance_pct,
        nomination_tolerance_pct=scenario.nomination_tolerance_pct,
        delivery_tolerance_mwh=round(
            scenario.delivery_quantity_mwh_per_day * scenario.delivery_tolerance_pct / 100,
            4,
        ),
        nomination_tolerance_mwh=round(
            scenario.delivery_quantity_mwh_per_day * scenario.nomination_tolerance_pct / 100,
            4,
        ),
        options=sorted(options, key=lambda item: item.net_pnl_gbp_per_day, reverse=True),
        missing_inputs=missing_inputs,
        warnings=warnings,
        source_refs=sorted({ref for option in options for ref in option.source_refs}),
        research_only=True,
        human_review_required=bool(
            missing_inputs
            or warnings
            or any(o.human_review_required for o in options)
        ),
    )


def _build_option(
    scenario: EasingtonContractScenario,
    tariffs: Sequence[CapacityTariff],
    *,
    option_id: str,
    label: str,
    business_model: str,
    sale_price: float,
    exit_point_name: str | None,
    tolerance_allowance: float,
) -> EasingtonOptionPnl:
    entry = select_latest_tariff(
        tariffs,
        country="UK",
        tso="National Gas NTS",
        point_name=UK_EASINGTON_POINT_NAME,
        direction=TariffDirection.ENTRY,
        gas_year=scenario.gas_year,
        capacity_product=scenario_capacity_product(),
        firmness=scenario_firmness(),
    )
    exit_selection = None
    if exit_point_name:
        exit_selection = select_latest_tariff(
            tariffs,
            country="UK",
            tso="National Gas NTS",
            point_name=exit_point_name,
            direction=TariffDirection.EXIT,
            gas_year=scenario.gas_year,
            capacity_product=scenario_capacity_product(),
            firmness=scenario_firmness(),
        )

    warnings = [*entry.warnings]
    if exit_selection:
        warnings.extend(exit_selection.warnings)
    status_counter: Counter[str] = Counter()
    source_refs: list[str] = []

    entry_charge = 0.0
    if entry.selected_tariff:
        entry_charge = _tariff_to_gbp_mwh(entry.selected_tariff)
        status_counter[entry.selected_tariff.tariff_status.value] += 1
        source_refs.extend(entry.selected_tariff.source_refs)
    else:
        warnings.append("ENTRY_TARIFF_MISSING")

    exit_charge = 0.0
    if exit_selection and exit_selection.selected_tariff:
        exit_charge = _tariff_to_gbp_mwh(exit_selection.selected_tariff)
        status_counter[exit_selection.selected_tariff.tariff_status.value] += 1
        source_refs.extend(exit_selection.selected_tariff.source_refs)
    elif exit_point_name:
        warnings.append("EXIT_TARIFF_MISSING")

    early_cash_value = _early_cash_value_gbp_mwh(scenario)
    commodity_charge = _commodity_charge_for_option(business_model)
    total_charges = round(
        entry_charge
        + exit_charge
        + commodity_charge
        + tolerance_allowance
        - early_cash_value,
        4,
    )
    margin = round(sale_price - scenario.contract_price_gbp_mwh - total_charges, 4)
    pnl = round(margin * scenario.delivery_quantity_mwh_per_day, 4)

    return EasingtonOptionPnl(
        option_id=option_id,
        label=label,
        business_model=business_model,
        sale_price_gbp_mwh=sale_price,
        contract_cost_gbp_mwh=scenario.contract_price_gbp_mwh,
        entry_capacity_charge_gbp_mwh=entry_charge,
        exit_capacity_charge_gbp_mwh=exit_charge,
        commodity_charge_gbp_mwh=commodity_charge,
        tolerance_risk_allowance_gbp_mwh=tolerance_allowance,
        early_cash_value_gbp_mwh=early_cash_value,
        total_charges_gbp_mwh=total_charges,
        net_margin_gbp_mwh=margin,
        net_pnl_gbp_per_day=pnl,
        source_refs=list(dict.fromkeys(source_refs)),
        route_legs=_route_legs_for_option(business_model, exit_point_name),
        tariff_status_summary=dict(status_counter),
        warnings=list(dict.fromkeys(warnings)),
        human_review_required=bool(warnings),
    )


def _tariff_to_gbp_mwh(tariff: CapacityTariff) -> float:
    if tariff.currency != "GBP" or tariff.unit != "p/kWh/day":
        raise ValueError("Only GBP p/kWh/day National Gas tariffs are supported.")
    return round(tariff.tariff_value * PENCE_PER_KWH_DAY_TO_GBP_PER_MWH, 4)


def _early_cash_value_gbp_mwh(scenario: EasingtonContractScenario) -> float:
    lag_days = max(scenario.upstream_payment_lag_days - scenario.screen_sale_cash_lag_days, 0)
    annual_rate = scenario.annual_financing_rate_pct / 100
    return round(scenario.contract_price_gbp_mwh * annual_rate * lag_days / 365, 4)


def _commodity_charge_for_option(business_model: str) -> float:
    if business_model == "PHYSICAL_DELIVERY":
        return round(NTS_COMMODITY_CHARGE_GBP_MWH * 2, 4)
    return NTS_COMMODITY_CHARGE_GBP_MWH


def _route_legs_for_option(business_model: str, exit_point_name: str | None) -> list[dict]:
    if business_model == "VIRTUAL_HUB_SALE":
        return [
            {"step": "entry_capacity", "point": UK_EASINGTON_POINT_NAME},
            {"step": "virtual_hub_sale", "point": "NBP"},
        ]
    return [
        {"step": "entry_capacity", "point": UK_EASINGTON_POINT_NAME},
        {"step": "exit_capacity", "point": exit_point_name},
        {"step": "physical_delivery", "point": exit_point_name},
    ]


def scenario_capacity_product():
    from eurogas_nexus.domain.route_cost.enums import CapacityProduct

    return CapacityProduct.DAILY


def scenario_firmness():
    from eurogas_nexus.domain.route_cost.enums import Firmness

    return Firmness.FIRM
