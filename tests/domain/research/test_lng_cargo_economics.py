"""Focused tests for the LNG cargo economics composition.

All inputs are synthetic and explicitly labeled ("synthetic-test-input:..."):
no market or provider data is invented. The hand-calculated reference case is:
purchased 100 MWh at EUR20/MWh (on purchased energy), delivered 90 MWh sold at
EUR30/MWh (on delivered energy), regas EUR100 + transport EUR50 itemized EUR
totals, all dated at the valuation date with DF 1 => sale proceeds 2700,
downstream costs 150, purchase outlay 2000, unit netback 25.5 per purchased
MWh, cargo margin 550, NPV 550. The 10 MWh energy loss is disclosed and never
monetized as an additional expense.
"""

from __future__ import annotations

import decimal
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from eurogas_nexus.domain.ontology.vocabulary import DeliveryMode
from eurogas_nexus.domain.research.lng_cargo_economics import (
    LNG_CARGO_ECONOMICS_MODEL_VERSION,
    LngCargoDownstreamCostInput,
    LngCargoEconomicsError,
    LngCargoEconomicsInput,
    compute_lng_cargo_economics,
)
from eurogas_nexus.domain.research.lng_cash_valuation import (
    LNG_CASH_VALUATION_MODEL_VERSION,
    LngCashDiscountFactorInput,
    LngCashLegCategory,
)
from eurogas_nexus.domain.route_cost.lng_regas import LngRegasScenario

VALUATION_DATE = date(2026, 9, 29)
SALE_DATE = date(2026, 11, 30)

PURCHASE_SOURCE = "synthetic-test-input:purchase-price-1"
SALE_SOURCE = "synthetic-test-input:sale-price-1"
REGAS_SOURCE = "synthetic-test-input:regas-cost-1"
TRANSPORT_SOURCE = "synthetic-test-input:transport-cost-1"
ZERO_COST_SOURCE = "synthetic-test-input:zero-cost-1"
DF_SOURCE = "synthetic-test-input:df-1"
DF_CURVE = "synthetic-test-curve:eur-flat"


def _scenario(**overrides) -> LngRegasScenario:
    """Build one explicitly labeled synthetic regas scenario that is READY."""

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


def _cost(
    cost_id: str,
    category: LngCashLegCategory,
    amount_eur: str,
    payment_date: date,
    source_reference: str,
) -> LngCargoDownstreamCostInput:
    """Build one explicitly labeled synthetic downstream cost item."""

    return LngCargoDownstreamCostInput(
        cost_id=cost_id,
        category=category,
        amount_eur=Decimal(amount_eur),
        payment_date=payment_date,
        source_reference=source_reference,
    )


def _discount_factor(
    payment_date: date = VALUATION_DATE,
    factor: str = "1",
    curve_reference: str = DF_CURVE,
    source_reference: str = DF_SOURCE,
    as_of: date = VALUATION_DATE,
) -> LngCashDiscountFactorInput:
    """Build one explicitly labeled synthetic discount factor."""

    return LngCashDiscountFactorInput(
        payment_date=payment_date,
        factor=Decimal(factor),
        curve_reference=curve_reference,
        source_reference=source_reference,
        as_of=as_of,
    )


def _reference_costs() -> tuple[LngCargoDownstreamCostInput, ...]:
    """Reference itemized downstream costs: regas 100 + transport 50 EUR."""

    return (
        _cost("regas-1", LngCashLegCategory.REGAS, "100", VALUATION_DATE, REGAS_SOURCE),
        _cost("transport-1", LngCashLegCategory.TRANSPORT, "50", VALUATION_DATE, TRANSPORT_SOURCE),
    )


def _economics(**overrides) -> LngCargoEconomicsInput:
    """Build the hand-calculated synthetic reference case, with overrides."""

    data: dict[str, object] = {
        "contract_id": "contract-synthetic-lng-1",
        "cargo_id": "cargo-synthetic-1",
        "terminal_id": "terminal-synthetic-regas-1",
        "resource_id": "resource-synthetic-supply-1",
        "readiness_scenario": _scenario(),
        "valuation_date": VALUATION_DATE,
        "energy_basis_reference": "synthetic-basis:gcV-energy-mwh",
        "purchased_energy_mwh": Decimal("100"),
        "delivered_energy_mwh": Decimal("90"),
        "purchase_unit_price_eur_per_mwh": Decimal("20"),
        "sale_unit_price_eur_per_mwh": Decimal("30"),
        "purchase_price_source_reference": PURCHASE_SOURCE,
        "sale_price_source_reference": SALE_SOURCE,
        "purchase_basis": "DES",
        "purchase_included_cost_items": (),
        "cost_scope_statement": (
            "Synthetic scope: the DES purchase price covers the cargo only; regas and"
            " downstream transport are itemized separately below."
        ),
        "purchase_payment_date": VALUATION_DATE,
        "sale_payment_date": VALUATION_DATE,
        "downstream_costs": _reference_costs(),
        "discount_factors": (_discount_factor(VALUATION_DATE, "1"),),
    }
    data.update(overrides)
    return LngCargoEconomicsInput(**data)  # type: ignore[arg-type]


def _codes(input_: LngCargoEconomicsInput) -> tuple[str, ...]:
    """Return the stable refusal codes of one invalid composition input."""

    with pytest.raises(LngCargoEconomicsError) as info:
        compute_lng_cargo_economics(input_)
    return info.value.codes


def test_fractional_cost_rounding_reconciles_margin_to_cash() -> None:
    costs = tuple(replace(cost, amount_eur=Decimal("0.00006")) for cost in _reference_costs())
    result = compute_lng_cargo_economics(_economics(downstream_costs=costs))
    assert result.cargo_margin_eur == result.cash_valuation.total_undiscounted_cash_reporting_ccy


def test_reference_case_computes_netback_margin_costs_and_npv() -> None:
    result = compute_lng_cargo_economics(_economics())

    assert result.model_version == LNG_CARGO_ECONOMICS_MODEL_VERSION
    assert result.reporting_currency == "EUR"
    assert (
        result.contract_id,
        result.cargo_id,
        result.terminal_id,
        result.resource_id,
    ) == (
        "contract-synthetic-lng-1",
        "cargo-synthetic-1",
        "terminal-synthetic-regas-1",
        "resource-synthetic-supply-1",
    )
    assert result.purchased_energy_mwh == Decimal("100")
    assert result.delivered_energy_mwh == Decimal("90")
    assert result.purchase_outlay_eur == Decimal("2000.0000")
    assert result.sale_proceeds_eur == Decimal("2700.0000")
    assert result.total_downstream_costs_eur == Decimal("150.0000")
    # Unit netback is per purchased MWh: (2700 - 150) / 100 = 25.5.
    assert result.unit_netback_eur_per_purchased_mwh == Decimal("25.5000")
    # Cargo margin: 2700 - 150 - 2000 = 550.
    assert result.cargo_margin_eur == Decimal("550.0000")
    assert result.margin_reconciliation_gap_eur == Decimal("0.0000")
    assert result.margin_reconciliation_tolerance_eur == Decimal("0.0052")
    # NPV reuses the bounded cash primitive; all dates at DF 1 => 550.
    assert result.net_present_value_eur == Decimal("550.0000")
    assert result.total_undiscounted_cash_eur == Decimal("550.0000")
    assert result.cash_valuation.net_present_value_reporting_ccy == Decimal("550.0000")
    assert result.cash_valuation.reporting_currency == "EUR"
    assert result.research_only is True
    assert result.human_review_required is True


def test_loss_is_disclosed_and_never_added_as_an_expense() -> None:
    result = compute_lng_cargo_economics(_economics())

    assert result.energy_loss_mwh == Decimal("10.0000")
    assert "ENERGY_LOSS_DISCLOSED_NOT_ADDITIONALLY_MONETIZED" in result.warnings
    # The loss is only the energy difference: costs stay 150 and margin 550.
    assert result.total_downstream_costs_eur == Decimal("150.0000")
    assert result.cargo_margin_eur == Decimal("550.0000")


def test_sale_basis_keeps_the_delivered_denominator_separate() -> None:
    result = compute_lng_cargo_economics(_economics())

    # Sale proceeds per delivered MWh: 2700 / 90 = 30, never 2700 / 100.
    assert result.sale_basis_eur_per_delivered_mwh == Decimal("30.0000")
    assert result.unit_netback_eur_per_purchased_mwh == Decimal("25.5000")
    assert result.unit_netback_eur_per_purchased_mwh != Decimal("28.3333")


def test_dated_discount_factors_change_npv_not_margin_or_undiscounted_cash() -> None:
    dated = _economics(
        sale_payment_date=SALE_DATE,
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "0.9"),
        ),
    )
    result = compute_lng_cargo_economics(dated)

    # -2000 + 2700*0.9 - 100 - 50 = 280; margin stays undiscounted at 550.
    assert result.net_present_value_eur == Decimal("280.0000")
    assert result.total_undiscounted_cash_eur == Decimal("550.0000")
    assert result.cargo_margin_eur == Decimal("550.0000")


def test_ready_readiness_warnings_are_propagated_not_blocking() -> None:
    result = compute_lng_cargo_economics(_economics())

    assert result.readiness.missing_inputs == []
    assert result.readiness.cargo_id == "cargo-synthetic-1"
    assert "BOIL_OFF_ALLOWANCE_NOT_PROVIDED" in result.readiness.warnings
    # Readiness warnings do not block a valued result; they are propagated.
    assert "READINESS_WARNING:BOIL_OFF_ALLOWANCE_NOT_PROVIDED" in result.warnings
    assert result.warnings == (
        "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
        "NO_TRADE_EXECUTION_NOMINATION_OR_SETTLEMENT",
        "EUR_ONLY_NO_FX_CONVERSION_PERFORMED",
        "READINESS_WARNING:BOIL_OFF_ALLOWANCE_NOT_PROVIDED",
        "READINESS_WARNING:REGAS_FEE_NOT_PROVIDED",
        "ENERGY_LOSS_DISCLOSED_NOT_ADDITIONALLY_MONETIZED",
    )


def test_blocked_readiness_fails_closed_before_any_valued_result() -> None:
    blocked = _economics(readiness_scenario=_scenario(terminal_access_confirmed=None))

    with pytest.raises(LngCargoEconomicsError) as info:
        compute_lng_cargo_economics(blocked)
    assert info.value.codes == ("READINESS_BLOCKED",)
    detail = next(
        detail for code, detail in info.value.violations if code == "READINESS_BLOCKED"
    )
    assert "TERMINAL_ACCESS_NOT_CONFIRMED" in detail


def test_readiness_reference_mismatch_is_refused() -> None:
    mismatched = _economics(readiness_scenario=_scenario(cargo_id="cargo-synthetic-2"))

    assert _codes(mismatched) == ("READINESS_REFERENCE_MISMATCH",)


def test_readiness_energy_quantity_mismatch_is_refused() -> None:
    mismatched = _economics(readiness_scenario=_scenario(cargo_size_mwh=101.0))

    assert _codes(mismatched) == ("READINESS_ENERGY_QUANTITY_MISMATCH",)


def test_included_purchase_cost_cannot_be_itemized_again() -> None:
    double_counted = _economics(
        purchase_basis="DES",
        purchase_included_cost_items=(LngCashLegCategory.SHIPPING,),
        downstream_costs=(
            *_reference_costs(),
            _cost(
                "shipping-1",
                LngCashLegCategory.SHIPPING,
                "25",
                VALUATION_DATE,
                "synthetic-test-input:shipping-cost-1",
            ),
        ),
    )

    assert _codes(double_counted) == ("DOWNSTREAM_COST_DOUBLES_INCLUDED_PURCHASE_COST",)


def test_duplicate_cost_ids_are_refused() -> None:
    duplicated = _economics(
        downstream_costs=(
            *_reference_costs(),
            _cost(
                "regas-1",
                LngCashLegCategory.OTHER,
                "1",
                VALUATION_DATE,
                "synthetic-test-input:duplicate-cost-1",
            ),
        )
    )

    assert _codes(duplicated) == ("DUPLICATE_COST_ID",)


@pytest.mark.parametrize(
    ("field_name", "value", "expected_code"),
    [
        ("purchased_energy_mwh", Decimal("0"), "PURCHASED_ENERGY_NOT_POSITIVE"),
        ("purchased_energy_mwh", Decimal("-1"), "PURCHASED_ENERGY_NOT_POSITIVE"),
        ("purchased_energy_mwh", Decimal("NaN"), "PURCHASED_ENERGY_NOT_FINITE"),
        ("purchased_energy_mwh", Decimal("Infinity"), "PURCHASED_ENERGY_NOT_FINITE"),
        ("purchased_energy_mwh", 100.0, "PURCHASED_ENERGY_NOT_DECIMAL"),
        ("purchased_energy_mwh", None, "PURCHASED_ENERGY_NOT_DECIMAL"),
        ("purchased_energy_mwh", Decimal("1e13"), "PURCHASED_ENERGY_OVERFLOW"),
        ("delivered_energy_mwh", Decimal("0"), "DELIVERED_ENERGY_NOT_POSITIVE"),
        ("delivered_energy_mwh", Decimal("-5"), "DELIVERED_ENERGY_NOT_POSITIVE"),
        ("delivered_energy_mwh", Decimal("NaN"), "DELIVERED_ENERGY_NOT_FINITE"),
        ("delivered_energy_mwh", "90", "DELIVERED_ENERGY_NOT_DECIMAL"),
        ("delivered_energy_mwh", None, "DELIVERED_ENERGY_NOT_DECIMAL"),
        ("delivered_energy_mwh", Decimal("101"), "DELIVERED_ENERGY_EXCEEDS_PURCHASED"),
    ],
)
def test_invalid_or_nonfinite_energy_volumes_are_refused(
    field_name: str, value: object, expected_code: str
) -> None:
    assert _codes(_economics(**{field_name: value})) == (expected_code,)


@pytest.mark.parametrize(
    ("field_name", "value", "expected_code"),
    [
        ("purchase_unit_price_eur_per_mwh", None, "PURCHASE_UNIT_PRICE_NOT_DECIMAL"),
        ("purchase_unit_price_eur_per_mwh", "20", "PURCHASE_UNIT_PRICE_NOT_DECIMAL"),
        (
            "purchase_unit_price_eur_per_mwh",
            Decimal("NaN"),
            "PURCHASE_UNIT_PRICE_NOT_FINITE",
        ),
        (
            "purchase_unit_price_eur_per_mwh",
            Decimal("1e10"),
            "PURCHASE_UNIT_PRICE_OVERFLOW",
        ),
        ("sale_unit_price_eur_per_mwh", None, "SALE_UNIT_PRICE_NOT_DECIMAL"),
        (
            "sale_unit_price_eur_per_mwh",
            Decimal("Infinity"),
            "SALE_UNIT_PRICE_NOT_FINITE",
        ),
        ("sale_unit_price_eur_per_mwh", Decimal("-1e10"), "SALE_UNIT_PRICE_OVERFLOW"),
    ],
)
def test_invalid_or_nonfinite_unit_prices_are_refused(
    field_name: str, value: object, expected_code: str
) -> None:
    # Missing/invalid prices are refused, never defaulted to zero or any value.
    assert _codes(_economics(**{field_name: value})) == (expected_code,)


@pytest.mark.parametrize(
    ("field_name", "value", "expected_code"),
    [
        ("purchase_price_source_reference", "", "PURCHASE_PRICE_SOURCE_REFERENCE_MISSING"),
        ("sale_price_source_reference", "   ", "SALE_PRICE_SOURCE_REFERENCE_MISSING"),
        ("energy_basis_reference", "", "ENERGY_BASIS_REFERENCE_MISSING"),
        ("purchase_basis", None, "PURCHASE_BASIS_INVALID"),
        ("purchase_basis", "CIF", "PURCHASE_BASIS_INVALID"),
        ("purchase_basis", "des", "PURCHASE_BASIS_INVALID"),
        ("cost_scope_statement", "   ", "COST_SCOPE_STATEMENT_MISSING"),
        ("valuation_date", datetime(2026, 9, 29, 12, 0), "VALUATION_DATE_INVALID"),
        ("model_version", "lng-cargo-economics/v0", "MODEL_VERSION_UNSUPPORTED"),
    ],
)
def test_missing_or_invalid_declared_fields_are_refused_not_defaulted(
    field_name: str, value: object, expected_code: str
) -> None:
    assert _codes(_economics(**{field_name: value})) == (expected_code,)


@pytest.mark.parametrize("field_name", ["contract_id", "cargo_id", "terminal_id", "resource_id"])
def test_missing_reference_is_refused(field_name: str) -> None:
    assert _codes(_economics(**{field_name: "   "})) == ("REFERENCE_MISSING",)


@pytest.mark.parametrize(
    ("included_items", "expected_code"),
    [
        (("shipping",), "PURCHASE_INCLUDED_COST_ITEM_INVALID"),
        ((LngCashLegCategory.CARGO_PURCHASE,), "PURCHASE_INCLUDED_COST_ITEM_INVALID"),
        ((LngCashLegCategory.CARGO_SALE,), "PURCHASE_INCLUDED_COST_ITEM_INVALID"),
        (
            (LngCashLegCategory.SHIPPING, LngCashLegCategory.SHIPPING),
            "PURCHASE_INCLUDED_COST_ITEM_DUPLICATE",
        ),
        ("shipping", "PURCHASE_INCLUDED_COST_ITEMS_INVALID"),
    ],
)
def test_invalid_included_purchase_cost_items_are_refused(
    included_items: object, expected_code: str
) -> None:
    assert _codes(_economics(purchase_included_cost_items=included_items)) == (expected_code,)


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"cost_id": "  "}, "COST_ID_MISSING"),
        ({"category": "regas"}, "COST_CATEGORY_INVALID"),
        ({"category": LngCashLegCategory.CARGO_PURCHASE}, "COST_CATEGORY_INVALID"),
        ({"category": LngCashLegCategory.CARGO_SALE}, "COST_CATEGORY_INVALID"),
        ({"amount_eur": None}, "COST_AMOUNT_NOT_DECIMAL"),
        ({"amount_eur": Decimal("-1")}, "COST_AMOUNT_NEGATIVE"),
        ({"amount_eur": Decimal("NaN")}, "COST_AMOUNT_NOT_FINITE"),
        ({"amount_eur": Decimal("1e16")}, "COST_AMOUNT_OVERFLOW"),
        ({"source_reference": ""}, "COST_SOURCE_REFERENCE_MISSING"),
        ({"payment_date": None}, "COST_PAYMENT_DATE_INVALID"),
        ({"payment_date": datetime(2026, 9, 29, 12, 0)}, "COST_PAYMENT_DATE_INVALID"),
        (
            {"payment_date": VALUATION_DATE - timedelta(days=1)},
            "COST_PAYMENT_DATE_BEFORE_VALUATION",
        ),
    ],
)
def test_invalid_downstream_cost_items_are_refused(
    overrides: dict[str, object], expected_code: str
) -> None:
    base = _cost("regas-1", LngCashLegCategory.REGAS, "100", VALUATION_DATE, REGAS_SOURCE)
    bad = replace(base, **overrides)
    assert _codes(_economics(downstream_costs=(bad, *_reference_costs()[1:]))) == (
        expected_code,
    )


def test_non_cost_item_objects_are_refused() -> None:
    assert _codes(_economics(downstream_costs=("not-a-cost",))) == (
        "DOWNSTREAM_COST_ITEM_INVALID",
    )


@pytest.mark.parametrize(
    ("field_name", "value", "expected_code"),
    [
        ("purchase_payment_date", None, "PURCHASE_PAYMENT_DATE_INVALID"),
        ("purchase_payment_date", datetime(2026, 9, 29, 12, 0), "PURCHASE_PAYMENT_DATE_INVALID"),
        (
            "purchase_payment_date",
            VALUATION_DATE - timedelta(days=1),
            "PURCHASE_PAYMENT_DATE_BEFORE_VALUATION",
        ),
        ("sale_payment_date", None, "SALE_PAYMENT_DATE_INVALID"),
        (
            "sale_payment_date",
            VALUATION_DATE - timedelta(days=1),
            "SALE_PAYMENT_DATE_BEFORE_VALUATION",
        ),
    ],
)
def test_invalid_or_past_payment_dates_are_refused(
    field_name: str, value: object, expected_code: str
) -> None:
    assert _codes(_economics(**{field_name: value})) == (expected_code,)


def test_missing_discount_factor_for_a_declared_payment_date_is_refused() -> None:
    uncovered = _economics(
        sale_payment_date=SALE_DATE,
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )

    assert _codes(uncovered) == ("DISCOUNT_FACTOR_MISSING_FOR_PAYMENT_DATE",)


@pytest.mark.parametrize(
    ("discount_factors", "expected_code"),
    [
        (
            (_discount_factor(VALUATION_DATE, "0"),),
            (
                "CASH_PRIMITIVE_REFUSED:DISCOUNT_FACTOR_AT_VALUATION_DATE_NOT_ONE",
                "CASH_PRIMITIVE_REFUSED:DISCOUNT_FACTOR_ZERO",
            ),
        ),
        (
            (_discount_factor(VALUATION_DATE, "1", as_of=VALUATION_DATE + timedelta(days=1)),),
            ("CASH_PRIMITIVE_REFUSED:DISCOUNT_FACTOR_AS_OF_IN_FUTURE",),
        ),
    ],
)
def test_cash_primitive_refusals_are_propagated_with_a_stable_prefix(
    discount_factors: tuple[LngCashDiscountFactorInput, ...],
    expected_code: tuple[str, ...],
) -> None:
    # The composition does not re-implement discount-factor validation: the
    # bounded cash primitive is the single validating implementation.
    assert _codes(_economics(discount_factors=discount_factors)) == expected_code


def test_non_sequence_containers_are_refused() -> None:
    assert _codes(_economics(downstream_costs=iter(()))) == ("DOWNSTREAM_COSTS_INVALID",)
    assert _codes(_economics(discount_factors="x")) == (
        "DISCOUNT_FACTORS_INVALID",
        "DISCOUNT_FACTOR_MISSING_FOR_PAYMENT_DATE",
    )


def test_zero_purchase_price_omits_the_zero_leg_and_discloses_it() -> None:
    zero_purchase = _economics(purchase_unit_price_eur_per_mwh=Decimal("0"))
    result = compute_lng_cargo_economics(zero_purchase)

    assert "OMITTED_ZERO_CASH_LEG:cargo-purchase" in result.warnings
    assert "cargo-purchase" not in {leg.leg_id for leg in result.cash_valuation.leg_valuations}
    assert result.purchase_outlay_eur == Decimal("0.0000")
    assert result.cargo_margin_eur == Decimal("2550.0000")
    assert result.unit_netback_eur_per_purchased_mwh == Decimal("25.5000")
    assert result.net_present_value_eur == Decimal("2550.0000")
    # The margin reconciliation still holds with an omitted zero purchase leg.
    assert result.margin_reconciliation_gap_eur == Decimal("0.0000")


def test_zero_amount_cost_item_is_omitted_and_disclosed() -> None:
    with_zero_cost = _economics(
        downstream_costs=(
            *_reference_costs(),
            _cost("zero-cost-1", LngCashLegCategory.OTHER, "0", VALUATION_DATE, ZERO_COST_SOURCE),
        )
    )
    result = compute_lng_cargo_economics(with_zero_cost)

    assert "OMITTED_ZERO_CASH_LEG:downstream-cost:zero-cost-1" in result.warnings
    leg_ids = {leg.leg_id for leg in result.cash_valuation.leg_valuations}
    assert "downstream-cost:zero-cost-1" not in leg_ids
    assert result.total_downstream_costs_eur == Decimal("150.0000")
    assert result.net_present_value_eur == Decimal("550.0000")


def test_all_zero_cash_flows_are_refused_explicitly() -> None:
    all_zero = _economics(
        purchase_unit_price_eur_per_mwh=Decimal("0"),
        sale_unit_price_eur_per_mwh=Decimal("0"),
        downstream_costs=(),
    )

    assert _codes(all_zero) == ("NO_NONZERO_CASH_LEGS",)


def test_negative_sale_price_is_allowed_and_disclosed() -> None:
    negative_sale = _economics(sale_unit_price_eur_per_mwh=Decimal("-30"))
    result = compute_lng_cargo_economics(negative_sale)

    assert result.sale_proceeds_eur == Decimal("-2700.0000")
    assert result.unit_netback_eur_per_purchased_mwh == Decimal("-28.5000")
    assert result.cargo_margin_eur == Decimal("-4850.0000")
    assert result.net_present_value_eur == Decimal("-4850.0000")
    assert "NEGATIVE_CARGO_MARGIN" in result.warnings
    assert "NEGATIVE_UNIT_NETBACK" in result.warnings
    assert "NEGATIVE_NET_PRESENT_VALUE" in result.warnings


def test_results_are_independent_of_the_ambient_decimal_context() -> None:
    expected = compute_lng_cargo_economics(_economics())

    ambient = decimal.getcontext()
    saved = ambient.copy()
    try:
        ambient.prec = 6
        ambient.rounding = decimal.ROUND_UP
        ambient.Emax = 10
        ambient.Emin = -10
        ambient.traps[decimal.Inexact] = True
        actual = compute_lng_cargo_economics(_economics())
    finally:
        decimal.setcontext(saved)

    assert actual == expected
    assert actual.unit_netback_eur_per_purchased_mwh == Decimal("25.5000")
    assert actual.cargo_margin_eur == Decimal("550.0000")
    assert actual.net_present_value_eur == Decimal("550.0000")


def test_repeated_calls_are_deterministic() -> None:
    assert compute_lng_cargo_economics(_economics()) == compute_lng_cargo_economics(_economics())


def test_provenance_contains_only_supplied_sources() -> None:
    result = compute_lng_cargo_economics(_economics())

    assert result.source_references == tuple(
        sorted({PURCHASE_SOURCE, SALE_SOURCE, REGAS_SOURCE, TRANSPORT_SOURCE, DF_SOURCE})
    )
    assert all("curve" not in reference for reference in result.source_references)


def test_cash_valuation_is_composed_from_exactly_one_leg_per_declared_cash_flow() -> None:
    result = compute_lng_cargo_economics(_economics())

    leg_ids = [leg.leg_id for leg in result.cash_valuation.leg_valuations]
    assert leg_ids == [
        "cargo-purchase",
        "cargo-sale",
        "downstream-cost:regas-1",
        "downstream-cost:transport-1",
    ]
    assert result.cash_valuation.lineage[-1] == LNG_CASH_VALUATION_MODEL_VERSION
    assert result.lineage == (
        "lng-cargo-economics",
        LNG_CARGO_ECONOMICS_MODEL_VERSION,
        LNG_CASH_VALUATION_MODEL_VERSION,
    )
    assert result.purchase_basis == "DES"
    assert result.purchase_included_cost_items == ()
    assert result.energy_basis_reference == "synthetic-basis:gcV-energy-mwh"


def test_wrong_input_type_is_refused_with_a_stable_code() -> None:
    with pytest.raises(LngCargoEconomicsError) as info:
        compute_lng_cargo_economics(object())  # type: ignore[arg-type]

    assert info.value.codes == ("INPUT_TYPE_INVALID",)


def test_economics_error_is_a_value_error_with_stable_codes() -> None:
    error = LngCargoEconomicsError([("CODE-X", "detail text"), ("CODE-Y", "more detail")])

    assert isinstance(error, ValueError)
    assert error.codes == ("CODE-X", "CODE-Y")
    assert "CODE-X (detail text)" in str(error)
