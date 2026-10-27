"""Focused tests for the LNG economics-only path.

The synthetic golden is:

- purchased 100 MWh at EUR20/MWh;
- delivered 90 MWh sold at EUR30/MWh;
- a separately invoiced EUR150 downstream cash cost;
- purchase and downstream cash at the valuation date, sale at 2026-11-30 with
  an explicit discount factor 0.975.

Cargo margin is EUR550 and NPV is EUR482.50. The two explicit energy stages are
100 -> 96 (consumed 3, physical loss 1) then 96 -> 90 (consumed 4, physical loss
2), so total consumed is 7 MWh, physical loss 3 MWh and total reduction 10 MWh.
No physical scenario, slot, terminal right or readiness result exists.
"""

from __future__ import annotations

import decimal
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from eurogas_nexus.domain.ontology.vocabulary import DeliveryMode
from eurogas_nexus.domain.research import lng_cargo_economics as economics_module
from eurogas_nexus.domain.research.lng_cargo_economics import (
    LNG_CARGO_ECONOMICS_MODEL_VERSION,
    LNG_ECONOMICS_ONLY_MODEL_VERSION,
    LngCargoDownstreamCostInput,
    LngCargoEconomicsError,
    LngCargoEconomicsInput,
    LngDownstreamChargeBasis,
    LngEconomicsOnlyCostInput,
    LngEconomicsOnlyError,
    LngEconomicsOnlyInput,
    LngEconomicsOnlyResult,
    compute_lng_cargo_economics,
    compute_lng_economics_only,
)
from eurogas_nexus.domain.research.lng_cash_valuation import (
    LngCashDiscountFactorInput,
    LngCashLegCategory,
)
from eurogas_nexus.domain.research.lng_energy_balance import (
    LngEnergyStage,
    LngEnergyStageKind,
)
from eurogas_nexus.domain.route_cost.lng_regas import LngRegasScenario

VALUATION_DATE = date(2026, 9, 29)
SALE_DATE = date(2026, 11, 30)

PURCHASE_SOURCE = "synthetic-test-input:purchase-price-1"
SALE_SOURCE = "synthetic-test-input:sale-price-1"
COST_SOURCE = "synthetic-test-input:invoiced-cost-1"
DF_SOURCE = "synthetic-test-input:df-1"
DF_CURVE = "synthetic-test-curve:eur-flat"
STAGE_1_SOURCE = "synthetic-test-input:stage-shipping-1"
STAGE_2_SOURCE = "synthetic-test-input:stage-regas-1"


def _discount_factor(
    payment_date: date = VALUATION_DATE,
    factor: str = "1",
    curve_reference: str = DF_CURVE,
    source_reference: str = DF_SOURCE,
    as_of: date = VALUATION_DATE,
) -> LngCashDiscountFactorInput:
    """Build one explicitly labelled synthetic discount factor."""

    return LngCashDiscountFactorInput(
        payment_date=payment_date,
        factor=Decimal(factor),
        curve_reference=curve_reference,
        source_reference=source_reference,
        as_of=as_of,
    )


def _cost(
    cost_id: str = "regas-1",
    category: LngCashLegCategory = LngCashLegCategory.REGAS,
    amount_eur: str = "150",
    payment_date: date = VALUATION_DATE,
    source_reference: str = COST_SOURCE,
    charge_basis: LngDownstreamChargeBasis = (
        LngDownstreamChargeBasis.INVOICED_CASH
    ),
) -> LngEconomicsOnlyCostInput:
    """Build one explicitly invoiced synthetic downstream cost."""

    return LngEconomicsOnlyCostInput(
        cost_id=cost_id,
        category=category,
        amount_eur=Decimal(amount_eur),
        payment_date=payment_date,
        source_reference=source_reference,
        charge_basis=charge_basis,
    )


def _stage(
    stage_id: str,
    input_energy: str,
    output_energy: str,
    consumed_energy: str,
    physical_loss: str,
    kind: LngEnergyStageKind = LngEnergyStageKind.SHIPPING,
    source_references: tuple[str, ...] = (STAGE_1_SOURCE,),
) -> LngEnergyStage:
    """Build one explicitly labelled synthetic energy stage."""

    return LngEnergyStage(
        stage_id=stage_id,
        kind=kind,
        input_energy_mwh=Decimal(input_energy),
        output_energy_mwh=Decimal(output_energy),
        consumed_energy_mwh=Decimal(consumed_energy),
        physical_loss_energy_mwh=Decimal(physical_loss),
        source_references=source_references,
    )


def _reference_stages() -> tuple[LngEnergyStage, ...]:
    """Two-stage reference chain with separate consumption and loss."""

    return (
        _stage("shipping-1", "100", "96", "3", "1", LngEnergyStageKind.SHIPPING),
        _stage(
            "regas-1",
            "96",
            "90",
            "4",
            "2",
            LngEnergyStageKind.REGASIFICATION,
            (STAGE_2_SOURCE,),
        ),
    )


def _economics_only(**overrides: object) -> LngEconomicsOnlyInput:
    """Build the synthetic golden economics-only input with overrides."""

    data: dict[str, object] = {
        "contract_id": "contract-synthetic-lng-1",
        "cargo_id": "cargo-synthetic-1",
        "terminal_id": "terminal-synthetic-regas-1",
        "resource_id": "resource-synthetic-supply-1",
        "valuation_date": VALUATION_DATE,
        "reporting_currency": "EUR",
        "energy_basis_reference": "synthetic-basis:gcV-energy-mwh",
        "energy_unit": "MWh",
        "purchased_energy_mwh": Decimal("100"),
        "delivered_energy_mwh": Decimal("90"),
        "purchase_unit_price_eur_per_mwh": Decimal("20"),
        "sale_unit_price_eur_per_mwh": Decimal("30"),
        "purchase_price_source_reference": PURCHASE_SOURCE,
        "sale_price_source_reference": SALE_SOURCE,
        "purchase_basis": "DES",
        "purchase_included_cost_items": (),
        "cost_scope_statement": (
            "Synthetic scope: the DES purchase price covers the cargo only; regas is"
            " invoiced separately below."
        ),
        "purchase_payment_date": VALUATION_DATE,
        "sale_payment_date": SALE_DATE,
        "downstream_costs": (_cost(),),
        "energy_stages": _reference_stages(),
        "discount_factors": (
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "0.975"),
        ),
    }
    data.update(overrides)
    return LngEconomicsOnlyInput(**data)  # type: ignore[arg-type]


def _codes(input_: LngEconomicsOnlyInput) -> tuple[str, ...]:
    """Return stable refusal codes for one economics-only input."""

    with pytest.raises(LngEconomicsOnlyError) as info:
        compute_lng_economics_only(input_)
    return info.value.codes


def _scenario(**overrides: object) -> LngRegasScenario:
    """Build one independently valid synthetic regas scenario."""

    data: dict[str, object] = {
        "contract_id": "contract-synthetic-lng-1",
        "cargo_id": "cargo-synthetic-1",
        "terminal_id": "terminal-synthetic-regas-1",
        "terminal_name": "Synthetic Regas Terminal",
        "terminal_access_confirmed": True,
        "terminal_access_reference": "synthetic-test-input:terminal-access-1",
        "cargo_size_mwh": 100.0,
        "cargo_arrival_window_start_utc": datetime(2026, 9, 29, tzinfo=UTC),
        "cargo_arrival_window_end_utc": datetime(2026, 9, 30, tzinfo=UTC),
        "regas_slot_start_utc": datetime(2026, 9, 29, tzinfo=UTC),
        "regas_slot_end_utc": datetime(2026, 9, 30, tzinfo=UTC),
        "terminal_sendout_capacity_mwh_per_day": 300.0,
        "terminal_capacity_source_system": "synthetic-test-input:capacity-1",
        "pricing_method": "TTF",
        "index_name": "synthetic-test-index",
        "delivery_mode": DeliveryMode.TERMINAL_TITLE_TRANSFER,
    }
    data.update(overrides)
    return LngRegasScenario(**data)


def _legacy_cost() -> LngCargoDownstreamCostInput:
    """Build the equivalent legacy downstream cost input."""

    return LngCargoDownstreamCostInput(
        cost_id="regas-1",
        category=LngCashLegCategory.REGAS,
        amount_eur=Decimal("150"),
        payment_date=VALUATION_DATE,
        source_reference=COST_SOURCE,
    )


def _legacy_input() -> LngCargoEconomicsInput:
    """Build an independently valid strict-path input for parity checks."""

    return LngCargoEconomicsInput(
        contract_id="contract-synthetic-lng-1",
        cargo_id="cargo-synthetic-1",
        terminal_id="terminal-synthetic-regas-1",
        resource_id="resource-synthetic-supply-1",
        readiness_scenario=_scenario(),
        valuation_date=VALUATION_DATE,
        energy_basis_reference="synthetic-basis:gcV-energy-mwh",
        purchased_energy_mwh=Decimal("100"),
        delivered_energy_mwh=Decimal("90"),
        purchase_unit_price_eur_per_mwh=Decimal("20"),
        sale_unit_price_eur_per_mwh=Decimal("30"),
        purchase_price_source_reference=PURCHASE_SOURCE,
        sale_price_source_reference=SALE_SOURCE,
        purchase_basis="DES",
        purchase_included_cost_items=(),
        cost_scope_statement=(
            "Synthetic scope: the DES purchase price covers the cargo only; regas is"
            " invoiced separately below."
        ),
        purchase_payment_date=VALUATION_DATE,
        sale_payment_date=SALE_DATE,
        downstream_costs=(_legacy_cost(),),
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "0.975"),
        ),
    )


def test_golden_margin_npv_and_energy_are_explicit() -> None:
    result = compute_lng_economics_only(_economics_only())

    assert result.model_version == LNG_ECONOMICS_ONLY_MODEL_VERSION
    assert result.reporting_currency == "EUR"
    assert result.energy_unit == "MWh"
    assert result.purchase_outlay_eur == Decimal("2000.0000")
    assert result.sale_proceeds_eur == Decimal("2700.0000")
    assert result.total_downstream_costs_eur == Decimal("150.0000")
    assert result.unit_netback_eur_per_purchased_mwh == Decimal("25.5000")
    assert result.sale_basis_eur_per_delivered_mwh == Decimal("30.0000")
    assert result.cargo_margin_eur == Decimal("550.0000")
    assert result.total_undiscounted_cash_eur == Decimal("550.0000")
    assert result.net_present_value_eur == Decimal("482.5000")
    assert result.cash_valuation.net_present_value_reporting_ccy == Decimal(
        "482.5000"
    )
    assert result.total_consumed_energy_mwh == Decimal("7")
    assert result.physical_loss_energy_mwh == Decimal("3")
    assert result.total_reduction_energy_mwh == Decimal("10")
    assert result.total_reduction_energy_mwh != result.physical_loss_energy_mwh
    assert result.energy_balance.total_consumed_energy_mwh == Decimal("7")
    assert result.energy_balance.physical_loss_energy_mwh == Decimal("3")
    assert result.energy_balance.total_reduction_energy_mwh == Decimal("10")


def test_physical_readiness_is_explicitly_not_assessed() -> None:
    result = compute_lng_economics_only(_economics_only())

    assert result.physical_readiness == "NOT_ASSESSED"
    assert result.readiness_assessed is False
    assert result.research_only is True
    assert result.human_review_required is True
    assert not hasattr(result, "readiness")
    assert isinstance(result, LngEconomicsOnlyResult)
    assert "readiness_scenario" not in LngEconomicsOnlyInput.__dataclass_fields__
    assert (
        "PROFITABLE_ECONOMICS_IS_NOT_DELIVERY_FEASIBILITY_TERMINAL_SLOT_STORAGE_RIGHTS_OR_"
        "NOMINATION_AUTHORITY"
    ) in result.warnings
    assert "PHYSICAL_READINESS_NOT_ASSESSED" in result.warnings
    assert all("READINESS_WARNING" not in warning for warning in result.warnings)


def test_economics_only_never_invokes_the_readiness_assessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*args: object, **kwargs: object) -> object:
        raise AssertionError("economics-only path must not assess physical readiness")

    monkeypatch.setattr(economics_module, "assess_lng_regas_readiness", _explode)

    result = compute_lng_economics_only(_economics_only())
    assert result.cargo_margin_eur == Decimal("550.0000")


def test_legacy_missing_readiness_refusal_is_preserved() -> None:
    blocked = _legacy_input()
    blocked = replace(
        blocked,
        readiness_scenario=_scenario(terminal_access_confirmed=None),
    )

    with pytest.raises(LngCargoEconomicsError) as info:
        compute_lng_cargo_economics(blocked)
    assert info.value.codes == ("READINESS_BLOCKED",)


def test_new_monetary_result_equals_the_strict_path_with_valid_readiness() -> None:
    strict = compute_lng_cargo_economics(_legacy_input())
    economics_only = compute_lng_economics_only(_economics_only())

    for field_name in (
        "purchase_outlay_eur",
        "sale_proceeds_eur",
        "total_downstream_costs_eur",
        "unit_netback_eur_per_purchased_mwh",
        "sale_basis_eur_per_delivered_mwh",
        "cargo_margin_eur",
        "margin_reconciliation_gap_eur",
        "margin_reconciliation_tolerance_eur",
        "net_present_value_eur",
        "total_undiscounted_cash_eur",
    ):
        assert getattr(economics_only, field_name) == getattr(strict, field_name)

    assert economics_only.cash_valuation.leg_valuations == (
        strict.cash_valuation.leg_valuations
    )
    assert economics_only.cash_valuation.total_undiscounted_cash_reporting_ccy == (
        strict.cash_valuation.total_undiscounted_cash_reporting_ccy
    )
    assert economics_only.cash_valuation.net_present_value_reporting_ccy == (
        strict.cash_valuation.net_present_value_reporting_ccy
    )
    assert strict.model_version == LNG_CARGO_ECONOMICS_MODEL_VERSION
    assert strict.energy_loss_mwh == Decimal("10.0000")


def test_cash_and_energy_reconcile_without_extra_energy_expense() -> None:
    result = compute_lng_economics_only(_economics_only())

    assert result.cargo_margin_eur == (
        result.sale_proceeds_eur
        - result.total_downstream_costs_eur
        - result.purchase_outlay_eur
    )
    assert result.margin_reconciliation_gap_eur == Decimal("0.0000")
    assert result.total_consumed_energy_mwh + result.physical_loss_energy_mwh == (
        result.total_reduction_energy_mwh
    )
    assert result.purchased_energy_mwh - result.delivered_energy_mwh == (
        result.total_reduction_energy_mwh
    )
    cash_leg_ids = {
        leg.leg_id for leg in result.cash_valuation.leg_valuations
    }
    assert cash_leg_ids == {
        "cargo-purchase",
        "cargo-sale",
        "downstream-cost:regas-1",
    }
    assert len(result.cash_valuation.leg_valuations) == 3


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"reporting_currency": "USD"}, "REPORTING_CURRENCY_UNSUPPORTED"),
        ({"energy_unit": "MMBtu"}, "ENERGY_UNIT_UNSUPPORTED"),
        ({"energy_unit": "mwh"}, "ENERGY_UNIT_UNSUPPORTED"),
        ({"model_version": "lng-economics-only/v0"}, "MODEL_VERSION_UNSUPPORTED"),
    ],
)
def test_unsupported_declarations_and_versions_are_refused(
    overrides: dict[str, object], expected_code: str
) -> None:
    assert _codes(_economics_only(**overrides)) == (expected_code,)


def test_signed_sale_price_is_preserved_and_disclosed() -> None:
    result = compute_lng_economics_only(
        _economics_only(sale_unit_price_eur_per_mwh=Decimal("-30"))
    )

    assert result.sale_proceeds_eur == Decimal("-2700.0000")
    assert result.unit_netback_eur_per_purchased_mwh == Decimal("-28.5000")
    assert result.cargo_margin_eur == Decimal("-4850.0000")
    assert result.net_present_value_eur == Decimal("-4782.5000")
    assert "NEGATIVE_CARGO_MARGIN" in result.warnings
    assert "NEGATIVE_UNIT_NETBACK" in result.warnings
    assert "NEGATIVE_NET_PRESENT_VALUE" in result.warnings


def test_zero_cash_leg_is_omitted_with_disclosure() -> None:
    result = compute_lng_economics_only(
        _economics_only(purchase_unit_price_eur_per_mwh=Decimal("0"))
    )

    assert "OMITTED_ZERO_CASH_LEG:cargo-purchase" in result.warnings
    assert "cargo-purchase" not in {
        leg.leg_id for leg in result.cash_valuation.leg_valuations
    }
    assert result.purchase_outlay_eur == Decimal("0.0000")
    assert result.cargo_margin_eur == Decimal("2550.0000")
    assert result.net_present_value_eur == Decimal("2482.5000")


def test_included_purchase_category_cannot_be_itemized_again() -> None:
    shipping = _cost(
        "shipping-1",
        LngCashLegCategory.SHIPPING,
        "25",
        source_reference="synthetic-test-input:shipping-cost-1",
    )

    codes = _codes(
        _economics_only(
            purchase_included_cost_items=(LngCashLegCategory.SHIPPING,),
            downstream_costs=(_cost(), shipping),
        )
    )
    assert codes == ("DOWNSTREAM_COST_DOUBLES_INCLUDED_PURCHASE_COST",)


def test_in_kind_and_unknown_charges_are_refused_as_cash() -> None:
    in_kind = _cost(charge_basis=LngDownstreamChargeBasis.IN_KIND)
    assert _codes(_economics_only(downstream_costs=(in_kind,))) == (
        "IN_KIND_COST_NOT_A_CASH_CHARGE",
    )

    unknown = _cost(charge_basis=LngDownstreamChargeBasis.UNKNOWN)
    assert _codes(_economics_only(downstream_costs=(unknown,))) == (
        "CHARGE_BASIS_NOT_INVOICED_CASH",
    )

    plain_string = replace(_cost(), charge_basis="invoiced_cash")
    assert _codes(_economics_only(downstream_costs=(plain_string,))) == (
        "CHARGE_BASIS_INVALID",
    )


def test_duplicate_cost_ids_and_missing_provenance_are_refused() -> None:
    duplicate = _cost(cost_id="regas-1", source_reference="synthetic-test-input:dup-1")
    assert _codes(
        _economics_only(downstream_costs=(_cost(), duplicate))
    ) == ("DUPLICATE_COST_ID",)

    missing_source = _cost(source_reference="   ")
    assert _codes(_economics_only(downstream_costs=(missing_source,))) == (
        "COST_SOURCE_REFERENCE_MISSING",
    )


@pytest.mark.parametrize(
    ("overrides", "expected_codes"),
    [
        (
            {
                "sale_payment_date": SALE_DATE,
                "discount_factors": (_discount_factor(),),
            },
            ("DISCOUNT_FACTOR_MISSING_FOR_PAYMENT_DATE",),
        ),
        (
            {"sale_payment_date": VALUATION_DATE - timedelta(days=1)},
            ("SALE_PAYMENT_DATE_BEFORE_VALUATION",),
        ),
        (
            {
                "downstream_costs": (
                    _cost(payment_date=VALUATION_DATE - timedelta(days=1)),
                )
            },
            ("COST_PAYMENT_DATE_BEFORE_VALUATION",),
        ),
        (
            {
                "discount_factors": (
                    _discount_factor(VALUATION_DATE, "0"),
                    _discount_factor(SALE_DATE, "0.975"),
                )
            },
            (
                "CASH_PRIMITIVE_REFUSED:DISCOUNT_FACTOR_AT_VALUATION_DATE_NOT_ONE",
                "CASH_PRIMITIVE_REFUSED:DISCOUNT_FACTOR_ZERO",
            ),
        ),
        (
            {
                "discount_factors": (
                    _discount_factor(
                        VALUATION_DATE,
                        "1",
                        as_of=VALUATION_DATE + timedelta(days=1),
                    ),
                    _discount_factor(SALE_DATE, "0.975"),
                )
            },
            ("CASH_PRIMITIVE_REFUSED:DISCOUNT_FACTOR_AS_OF_IN_FUTURE",),
        ),
    ],
)
def test_missing_invalid_discount_and_dated_cash_are_refused(
    overrides: dict[str, object], expected_codes: tuple[str, ...]
) -> None:
    assert _codes(_economics_only(**overrides)) == expected_codes


def test_invalid_stage_is_propagated_without_monetary_computation() -> None:
    stages = (
        _stage("shipping-1", "100", "96", "3", "1"),
        _stage("regas-1", "96", "90", "-1", "2"),
    )

    assert _codes(_economics_only(energy_stages=stages)) == (
        "STAGE_CONSUMED_ENERGY_NEGATIVE",
    )


def test_one_stage_explicit_zero_consumption_and_loss_is_valid() -> None:
    stage = _stage("transfer-1", "100", "100", "0", "0")
    result = compute_lng_economics_only(
        _economics_only(
            purchased_energy_mwh=Decimal("100"),
            delivered_energy_mwh=Decimal("100"),
            energy_stages=(stage,),
        )
    )

    assert result.total_consumed_energy_mwh == Decimal("0")
    assert result.physical_loss_energy_mwh == Decimal("0")
    assert result.total_reduction_energy_mwh == Decimal("0")
    assert result.cargo_margin_eur == Decimal("850.0000")


def test_missing_stage_or_non_decimal_cost_amount_is_refused() -> None:
    assert _codes(_economics_only(energy_stages=())) == ("STAGE_COUNT_INVALID",)

    non_decimal_cost = replace(_cost(), amount_eur=150)
    assert _codes(_economics_only(downstream_costs=(non_decimal_cost,))) == (
        "COST_AMOUNT_NOT_DECIMAL",
    )


def test_input_type_is_refused_with_the_new_stable_code() -> None:
    with pytest.raises(LngEconomicsOnlyError) as info:
        compute_lng_economics_only(object())  # type: ignore[arg-type]

    assert info.value.codes == ("INPUT_TYPE_INVALID",)


def test_results_are_independent_of_the_ambient_decimal_context() -> None:
    expected = compute_lng_economics_only(_economics_only())

    ambient = decimal.getcontext()
    saved = ambient.copy()
    try:
        ambient.prec = 6
        ambient.rounding = decimal.ROUND_UP
        ambient.Emax = 10
        ambient.Emin = -10
        ambient.traps[decimal.Inexact] = True
        ambient.traps[decimal.Rounded] = True
        actual = compute_lng_economics_only(_economics_only())
    finally:
        decimal.setcontext(saved)

    assert actual == expected
    assert actual.cargo_margin_eur == Decimal("550.0000")
    assert actual.net_present_value_eur == Decimal("482.5000")
    assert actual.total_consumed_energy_mwh == Decimal("7")
    assert actual.physical_loss_energy_mwh == Decimal("3")


def test_source_references_include_cash_and_explicit_stage_provenance() -> None:
    result = compute_lng_economics_only(_economics_only())

    assert result.source_references == tuple(
        sorted(
            {
                PURCHASE_SOURCE,
                SALE_SOURCE,
                COST_SOURCE,
                DF_SOURCE,
                STAGE_1_SOURCE,
                STAGE_2_SOURCE,
            }
        )
    )
    assert result.lineage[0] == "lng-economics-only"
    assert result.lineage[1] == LNG_ECONOMICS_ONLY_MODEL_VERSION
    assert result.lineage[-1] == "lng-cargo-cash-valuation/v1"
