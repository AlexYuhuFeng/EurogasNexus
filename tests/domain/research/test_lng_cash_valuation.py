"""Focused tests for the LNG cargo cash valuation primitive.

All inputs are synthetic and explicitly labeled ("synthetic-test-input:..."):
no market or provider data is invented and nothing outside the supplied
provenance may appear in the result. The hand-calculated reference case is:
EUR purchase -100 at the valuation date with DF 1; USD sale +150 converted at
EUR/USD 0.8 with DF 0.95; EUR cost -10 with DF 0.95 => undiscounted cash 10,
NPV 4.5.
"""

from __future__ import annotations

import decimal
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from eurogas_nexus.domain.ontology.semantic_kernel import CanonicalId
from eurogas_nexus.domain.research.cash_valuation import (
    CASH_VALUATION_MODEL_VERSION,
    CashFlowLegCategory,
    CashValuationDiscountFactorInput,
    CashValuationError,
    CashValuationFxInput,
    CashValuationInput,
    CashValuationLegInput,
    CashValuationLegValuation,
    compute_cash_valuation,
)
from eurogas_nexus.domain.research.lng_cash_valuation import (
    LNG_CASH_VALUATION_MODEL_VERSION,
    LngCargoCashValuationInput,
    LngCashDiscountFactorInput,
    LngCashFxInput,
    LngCashLegCategory,
    LngCashLegInput,
    LngCashLegValuation,
    LngCashValuationError,
    compute_lng_cargo_cash_valuation,
)
from eurogas_nexus.domain.research.models import CostComponentType

VALUATION_DATE = date(2026, 9, 29)


def test_amount_limit_is_independent_of_ambient_decimal_precision() -> None:
    original = _hand_case_input()
    oversized = replace(original.legs[0], signed_amount=Decimal("1000000000000000.1"))
    candidate = replace(original, legs=(oversized, *original.legs[1:]))
    with decimal.localcontext() as context:
        context.prec = 2
        assert "LEG_AMOUNT_OVERFLOW" in _codes(candidate)


SALE_DATE = date(2026, 11, 30)
COST_DATE = date(2026, 12, 31)
PURCHASE_SOURCE = "synthetic-test-input:purchase-1"
SALE_SOURCE = "synthetic-test-input:sale-1"
FX_SOURCE = "synthetic-test-input:fx-1"
REGAS_SOURCE = "synthetic-test-input:regas-1"
DF_SOURCE = "synthetic-test-input:df-1"
DF_CURVE = "synthetic-test-curve:eur-usd-flat"


def _leg(
    leg_id: str,
    category: LngCashLegCategory,
    signed_amount: str,
    payment_date: date,
    currency: str = "EUR",
    source_reference: str = "synthetic-test-input:leg-1",
    fx: LngCashFxInput | None = None,
) -> LngCashLegInput:
    """Build one explicitly labeled synthetic leg."""

    return LngCashLegInput(
        leg_id=leg_id,
        category=category,
        payment_date=payment_date,
        signed_amount=Decimal(signed_amount),
        currency=currency,
        source_reference=source_reference,
        fx=fx,
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


def _hand_case_input() -> LngCargoCashValuationInput:
    """Hand-calculated reference case: cash 10, NPV 4.5, fully synthetic."""

    return LngCargoCashValuationInput(
        contract_id="contract-synthetic-lng-1",
        cargo_id="cargo-synthetic-1",
        terminal_id="terminal-synthetic-regas-1",
        resource_id="resource-synthetic-supply-1",
        valuation_date=VALUATION_DATE,
        reporting_currency="EUR",
        legs=(
            _leg(
                "cargo-purchase-1",
                LngCashLegCategory.CARGO_PURCHASE,
                "-100",
                VALUATION_DATE,
                source_reference=PURCHASE_SOURCE,
            ),
            _leg(
                "hub-sale-1",
                LngCashLegCategory.CARGO_SALE,
                "150",
                SALE_DATE,
                currency="USD",
                source_reference=SALE_SOURCE,
                fx=LngCashFxInput(
                    rate_reporting_per_leg=Decimal("0.8"),
                    source_reference=FX_SOURCE,
                    as_of=VALUATION_DATE - timedelta(days=1),
                ),
            ),
            _leg(
                "regas-cost-1",
                LngCashLegCategory.REGAS,
                "-10",
                COST_DATE,
                source_reference=REGAS_SOURCE,
            ),
        ),
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "0.95"),
            _discount_factor(COST_DATE, "0.95"),
        ),
    )


def _codes(input_: LngCargoCashValuationInput) -> tuple[str, ...]:
    """Return the stable refusal codes of one invalid input."""

    with pytest.raises(LngCashValuationError) as info:
        compute_lng_cargo_cash_valuation(input_)
    return info.value.codes


def test_hand_calculated_case_normalizes_converts_and_discounts() -> None:
    result = compute_lng_cargo_cash_valuation(_hand_case_input())

    assert result.model_version == LNG_CASH_VALUATION_MODEL_VERSION
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
    assert result.valuation_date == VALUATION_DATE
    assert result.reporting_currency == "EUR"
    assert result.research_only is True
    assert result.human_review_required is True

    legs = {leg.leg_id: leg for leg in result.leg_valuations}
    assert set(legs) == {"cargo-purchase-1", "hub-sale-1", "regas-cost-1"}
    purchase = legs["cargo-purchase-1"]
    assert purchase.cash_amount_reporting_ccy == Decimal("-100.0000")
    assert purchase.present_value_reporting_ccy == Decimal("-100.0000")
    assert purchase.fx_rate_reporting_per_leg == Decimal(1)
    assert purchase.fx_source_reference is None
    sale = legs["hub-sale-1"]
    assert sale.category is LngCashLegCategory.CARGO_SALE
    assert sale.currency == "USD"
    assert sale.fx_rate_reporting_per_leg == Decimal("0.8")
    assert sale.fx_source_reference == FX_SOURCE
    assert sale.cash_amount_reporting_ccy == Decimal("120.0000")
    assert sale.present_value_reporting_ccy == Decimal("114.0000")
    assert sale.discount_factor == Decimal("0.95")
    assert sale.discount_curve_reference == DF_CURVE
    assert sale.discount_as_of == VALUATION_DATE
    assert legs["regas-cost-1"].cash_amount_reporting_ccy == Decimal("-10.0000")
    assert legs["regas-cost-1"].present_value_reporting_ccy == Decimal("-9.5000")

    # Hand calculation: -100 + 150*0.8 - 10 = 10; -100 + 114 - 9.5 = 4.5.
    assert result.total_undiscounted_cash_reporting_ccy == Decimal("10.0000")
    assert result.net_present_value_reporting_ccy == Decimal("4.5000")


def test_provenance_contains_only_supplied_sources_and_always_on_warnings() -> None:
    result = compute_lng_cargo_cash_valuation(_hand_case_input())

    assert result.source_references == tuple(
        sorted({PURCHASE_SOURCE, SALE_SOURCE, FX_SOURCE, REGAS_SOURCE, DF_SOURCE})
    )
    # 没有凭空发明的市场数据/曲线：来源集合只包含调用方显式提供的引用。
    assert all("curve" not in reference for reference in result.source_references)
    assert result.warnings == (
        "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
        "NPV_IS_NOT_NETBACK_MARK_TO_MARKET_OR_MARGIN",
    )
    assert any("not a netback" in assumption for assumption in result.assumptions)
    assert result.lineage[-1] == LNG_CASH_VALUATION_MODEL_VERSION


def test_leg_present_values_reconcile_to_npv_without_double_counting() -> None:
    result = compute_lng_cargo_cash_valuation(_hand_case_input())

    assert len({leg.leg_id for leg in result.leg_valuations}) == len(result.leg_valuations)
    assert sum(
        (leg.cash_amount_reporting_ccy for leg in result.leg_valuations), Decimal(0)
    ) == result.total_undiscounted_cash_reporting_ccy
    assert sum(
        (leg.present_value_reporting_ccy for leg in result.leg_valuations), Decimal(0)
    ) == result.net_present_value_reporting_ccy
    # 重复计一次腿会得到 9.0；手工计算的 4.5 证明每条腿只计一次。
    assert result.net_present_value_reporting_ccy != Decimal("9.0000")


def test_single_leg_is_counted_exactly_once() -> None:
    single = replace(
        _hand_case_input(),
        legs=(_leg("only-leg-1", LngCashLegCategory.OTHER, "7.25", VALUATION_DATE),),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )
    result = compute_lng_cargo_cash_valuation(single)

    assert result.total_undiscounted_cash_reporting_ccy == Decimal("7.2500")
    assert result.net_present_value_reporting_ccy == Decimal("7.2500")


def test_same_day_leg_requires_explicit_discount_factor_of_one() -> None:
    same_day = replace(
        _hand_case_input(),
        legs=(_leg("same-day-1", LngCashLegCategory.CARGO_PURCHASE, "-5", VALUATION_DATE),),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )
    result = compute_lng_cargo_cash_valuation(same_day)
    leg = result.leg_valuations[0]

    assert leg.discount_factor == Decimal(1)
    assert leg.present_value_reporting_ccy == leg.cash_amount_reporting_ccy == Decimal("-5.0000")

    not_one = replace(same_day, discount_factors=(_discount_factor(VALUATION_DATE, "0.99"),))
    assert _codes(not_one) == ("DISCOUNT_FACTOR_AT_VALUATION_DATE_NOT_ONE",)


def test_negative_cash_flows_are_supported_and_negative_npv_warns() -> None:
    outflow = replace(
        _hand_case_input(),
        legs=(
            _leg("cargo-purchase-1", LngCashLegCategory.CARGO_PURCHASE, "-100", VALUATION_DATE),
            _leg("regas-cost-1", LngCashLegCategory.REGAS, "-30", COST_DATE),
        ),
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(COST_DATE, "0.95"),
        ),
    )
    result = compute_lng_cargo_cash_valuation(outflow)

    assert result.total_undiscounted_cash_reporting_ccy == Decimal("-130.0000")
    assert result.net_present_value_reporting_ccy == Decimal("-128.5000")
    assert "NEGATIVE_NET_PRESENT_VALUE" in result.warnings


def test_discount_factor_above_one_is_allowed_not_blanket_rejected() -> None:
    negative_rate = replace(
        _hand_case_input(),
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "1.05"),
            _discount_factor(COST_DATE, "0.95"),
        ),
    )
    result = compute_lng_cargo_cash_valuation(negative_rate)
    sale = {leg.leg_id: leg for leg in result.leg_valuations}["hub-sale-1"]

    assert sale.present_value_reporting_ccy == Decimal("126.0000")
    assert result.net_present_value_reporting_ccy == Decimal("16.5000")


def test_cross_currency_leg_without_fx_rate_is_refused() -> None:
    hand_case = _hand_case_input()
    without_fx = replace(
        hand_case,
        legs=(
            hand_case.legs[0],
            _leg(
                "hub-sale-1",
                LngCashLegCategory.CARGO_SALE,
                "150",
                SALE_DATE,
                currency="USD",
                source_reference=SALE_SOURCE,
            ),
            hand_case.legs[2],
        ),
    )

    assert _codes(without_fx) == ("FX_RATE_MISSING_FOR_CROSS_CURRENCY_LEG",)


def test_missing_fx_provenance_is_refused() -> None:
    hand_case = _hand_case_input()
    no_source = replace(
        hand_case,
        legs=(
            hand_case.legs[0],
            replace(
                hand_case.legs[1],
                fx=LngCashFxInput(
                    rate_reporting_per_leg=Decimal("0.8"),
                    source_reference="   ",
                    as_of=VALUATION_DATE - timedelta(days=1),
                ),
            ),
            hand_case.legs[2],
        ),
    )
    future_as_of = replace(
        hand_case,
        legs=(
            hand_case.legs[0],
            replace(
                hand_case.legs[1],
                fx=LngCashFxInput(
                    rate_reporting_per_leg=Decimal("0.8"),
                    source_reference=FX_SOURCE,
                    as_of=VALUATION_DATE + timedelta(days=1),
                ),
            ),
            hand_case.legs[2],
        ),
    )

    assert _codes(no_source) == ("FX_SOURCE_MISSING",)
    assert _codes(future_as_of) == ("FX_AS_OF_IN_FUTURE",)


@pytest.mark.parametrize(
    ("rate", "expected_code"),
    [
        (150.0, "FX_RATE_NOT_DECIMAL"),
        (Decimal("NaN"), "FX_RATE_NOT_FINITE"),
        (Decimal("Infinity"), "FX_RATE_NOT_FINITE"),
        (Decimal("0"), "FX_RATE_ZERO"),
        (Decimal("-0.5"), "FX_RATE_NOT_POSITIVE"),
        (Decimal("1e13"), "FX_RATE_OVERFLOW"),
    ],
)
def test_invalid_fx_rates_fail_with_stable_codes(rate: object, expected_code: str) -> None:
    hand_case = _hand_case_input()
    bad_rate = replace(
        hand_case,
        legs=(
            hand_case.legs[0],
            replace(
                hand_case.legs[1],
                fx=LngCashFxInput(
                    rate_reporting_per_leg=rate,
                    source_reference=FX_SOURCE,
                    as_of=VALUATION_DATE - timedelta(days=1),
                ),
            ),
            hand_case.legs[2],
        ),
    )

    assert _codes(bad_rate) == (expected_code,)


def test_same_currency_leg_rejects_cross_currency_fx_input() -> None:
    redundant_fx = replace(
        _hand_case_input(),
        legs=(
            _leg(
                "cargo-purchase-1",
                LngCashLegCategory.CARGO_PURCHASE,
                "-100",
                VALUATION_DATE,
                source_reference=PURCHASE_SOURCE,
                fx=LngCashFxInput(
                    rate_reporting_per_leg=Decimal("1"),
                    source_reference=FX_SOURCE,
                    as_of=VALUATION_DATE,
                ),
            ),
        ),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )

    assert _codes(redundant_fx) == ("FX_NOT_APPLICABLE_SAME_CURRENCY",)


def test_missing_discount_factor_provenance_is_refused() -> None:
    hand_case = _hand_case_input()
    for field_name, value, expected_code in (
        ("curve_reference", "  ", "DISCOUNT_FACTOR_CURVE_MISSING"),
        ("source_reference", "", "DISCOUNT_FACTOR_SOURCE_MISSING"),
        ("as_of", VALUATION_DATE + timedelta(days=1), "DISCOUNT_FACTOR_AS_OF_IN_FUTURE"),
    ):
        discount_factors = (
            hand_case.discount_factors[0],
            replace(hand_case.discount_factors[1], **{field_name: value}),
            hand_case.discount_factors[2],
        )
        bad = replace(hand_case, discount_factors=discount_factors)
        assert _codes(bad) == (expected_code,)


def test_missing_discount_factor_for_a_leg_payment_date_is_refused() -> None:
    hand_case = _hand_case_input()
    incomplete = replace(
        hand_case,
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "0.95"),
        ),
    )

    assert _codes(incomplete) == ("DISCOUNT_FACTOR_MISSING_FOR_LEG_PAYMENT_DATE",)


def test_duplicate_discount_factor_payment_date_is_refused() -> None:
    hand_case = _hand_case_input()
    duplicated = replace(
        hand_case,
        discount_factors=(
            *hand_case.discount_factors,
            _discount_factor(SALE_DATE, "0.95"),
        ),
    )

    assert _codes(duplicated) == ("DISCOUNT_FACTOR_PAYMENT_DATE_DUPLICATE",)


@pytest.mark.parametrize(
    ("factor", "expected_code"),
    [
        (Decimal("0"), "DISCOUNT_FACTOR_ZERO"),
        (Decimal("-0.5"), "DISCOUNT_FACTOR_NOT_POSITIVE"),
        (Decimal("NaN"), "DISCOUNT_FACTOR_NOT_FINITE"),
        (Decimal("1e13"), "DISCOUNT_FACTOR_OVERFLOW"),
    ],
)
def test_invalid_discount_factor_values_fail_with_stable_codes(
    factor: object, expected_code: str
) -> None:
    hand_case = _hand_case_input()
    bad_factor = replace(
        hand_case,
        discount_factors=(
            hand_case.discount_factors[0],
            hand_case.discount_factors[1],
            replace(hand_case.discount_factors[2], factor=factor),
        ),
    )

    assert _codes(bad_factor) == (expected_code,)


def test_duplicate_leg_id_is_refused() -> None:
    hand_case = _hand_case_input()
    duplicated = replace(
        hand_case,
        legs=(
            *hand_case.legs,
            _leg(
                "cargo-purchase-1",
                LngCashLegCategory.OTHER,
                "5",
                COST_DATE,
                source_reference="synthetic-test-input:duplicate-1",
            ),
        ),
    )

    assert _codes(duplicated) == ("DUPLICATE_LEG_ID",)


def test_past_dated_leg_is_refused_not_rolled_up() -> None:
    hand_case = _hand_case_input()
    past_dated = replace(
        hand_case,
        legs=(
            *_hand_case_input().legs,
            _leg(
                "realized-sale-1",
                LngCashLegCategory.CARGO_SALE,
                "5",
                VALUATION_DATE - timedelta(days=1),
                source_reference="synthetic-test-input:realized-1",
            ),
        ),
    )

    with pytest.raises(LngCashValuationError) as info:
        compute_lng_cargo_cash_valuation(past_dated)
    assert info.value.codes == ("LEG_PAYMENT_DATE_BEFORE_VALUATION",)
    detail = next(
        detail
        for code, detail in info.value.violations
        if code == "LEG_PAYMENT_DATE_BEFORE_VALUATION"
    )
    # 边界必须显式记录：本原语只估未来现金流，拒绝已实现（过去日期）现金流。
    assert "future cash only" in detail


def test_past_dated_discount_factor_is_refused() -> None:
    hand_case = _hand_case_input()
    past_factor = replace(
        hand_case,
        discount_factors=(
            _discount_factor(VALUATION_DATE - timedelta(days=1), "0.99"),
            *hand_case.discount_factors,
        ),
    )

    assert _codes(past_factor) == ("DISCOUNT_FACTOR_PAYMENT_DATE_BEFORE_VALUATION",)


@pytest.mark.parametrize(
    ("amount", "expected_code"),
    [
        (150.0, "LEG_AMOUNT_NOT_DECIMAL"),
        (150, "LEG_AMOUNT_NOT_DECIMAL"),
        (True, "LEG_AMOUNT_NOT_DECIMAL"),
        ("150", "LEG_AMOUNT_NOT_DECIMAL"),
        (Decimal("NaN"), "LEG_AMOUNT_NOT_FINITE"),
        (Decimal("sNaN"), "LEG_AMOUNT_NOT_FINITE"),
        (Decimal("Infinity"), "LEG_AMOUNT_NOT_FINITE"),
        (Decimal("0"), "LEG_AMOUNT_ZERO"),
        (Decimal("-0.0000"), "LEG_AMOUNT_ZERO"),
        (Decimal("1e16"), "LEG_AMOUNT_OVERFLOW"),
        (Decimal("-1e16"), "LEG_AMOUNT_OVERFLOW"),
    ],
)
def test_invalid_leg_amounts_fail_with_stable_codes(amount: object, expected_code: str) -> None:
    bad_amount = replace(
        _hand_case_input(),
        legs=(
            LngCashLegInput(
                leg_id="bad-amount-1",
                category=LngCashLegCategory.CARGO_SALE,
                payment_date=VALUATION_DATE,
                signed_amount=amount,
                currency="EUR",
                source_reference="synthetic-test-input:bad-amount-1",
            ),
        ),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )

    assert _codes(bad_amount) == (expected_code,)


@pytest.mark.parametrize("currency", ["eur", "EURO", "EU", "", "E1R", "USDD"])
def test_invalid_leg_currency_is_refused(currency: str) -> None:
    bad_currency = replace(
        _hand_case_input(),
        legs=(
            _leg(
                "leg-1",
                LngCashLegCategory.OTHER,
                "1",
                VALUATION_DATE,
                currency=currency,
                source_reference="synthetic-test-input:leg-1",
            ),
        ),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )

    assert _codes(bad_currency) == ("LEG_CURRENCY_INVALID",)


def test_invalid_reporting_currency_is_refused() -> None:
    assert _codes(replace(_hand_case_input(), reporting_currency="eur")) == (
        "REPORTING_CURRENCY_INVALID",
    )


@pytest.mark.parametrize("bad_date", [datetime(2026, 9, 29, 12, 0), "2026-09-29", None])
def test_invalid_leg_payment_dates_are_refused(bad_date: object) -> None:
    hand_case = _hand_case_input()
    bad_date_input = replace(
        hand_case,
        legs=(replace(hand_case.legs[0], payment_date=bad_date),),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )

    assert _codes(bad_date_input) == ("LEG_PAYMENT_DATE_INVALID",)


def test_datetime_valuation_date_is_refused() -> None:
    bad = replace(_hand_case_input(), valuation_date=datetime(2026, 9, 29, 12, 0))

    assert _codes(bad) == ("VALUATION_DATE_INVALID",)


@pytest.mark.parametrize("field_name", ["contract_id", "cargo_id", "terminal_id", "resource_id"])
def test_missing_required_reference_is_refused(field_name: str) -> None:
    assert _codes(replace(_hand_case_input(), **{field_name: "   "})) == ("REFERENCE_MISSING",)


def test_missing_legs_are_refused() -> None:
    assert _codes(replace(_hand_case_input(), legs=())) == ("NO_CASH_FLOW_LEGS",)


def test_non_sequence_containers_are_refused() -> None:
    # 生成器/None/标量若不显式拒绝，会在第二次迭代时静默变为空并给出错误结果。
    assert _codes(replace(_hand_case_input(), legs=iter(()))) == (
        "LEGS_INVALID",
        "NO_CASH_FLOW_LEGS",
    )
    codes = _codes(replace(_hand_case_input(), discount_factors="x"))
    assert codes[0] == "DISCOUNT_FACTORS_INVALID"
    assert set(codes[1:]) == {"DISCOUNT_FACTOR_MISSING_FOR_LEG_PAYMENT_DATE"}
    assert len(codes) == 4


def test_list_containers_are_normalized_to_the_same_result() -> None:
    hand_case = _hand_case_input()
    as_lists = replace(
        hand_case,
        legs=list(hand_case.legs),
        discount_factors=list(hand_case.discount_factors),
    )

    assert compute_lng_cargo_cash_valuation(as_lists) == compute_lng_cargo_cash_valuation(
        hand_case
    )


def test_missing_leg_identity_and_source_are_refused() -> None:
    hand_case = _hand_case_input()
    no_id = replace(
        hand_case,
        legs=(_leg("", LngCashLegCategory.OTHER, "1", VALUATION_DATE),),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )
    no_source = replace(
        hand_case,
        legs=(
            _leg(
                "leg-1",
                LngCashLegCategory.OTHER,
                "1",
                VALUATION_DATE,
                source_reference="",
            ),
        ),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )

    assert _codes(no_id) == ("LEG_ID_MISSING",)
    assert _codes(no_source) == ("LEG_SOURCE_REFERENCE_MISSING",)


def test_non_enum_category_is_refused() -> None:
    bad_category = replace(
        _hand_case_input(),
        legs=(
            LngCashLegInput(
                leg_id="category-leg-1",
                category="cargo_sale",
                payment_date=VALUATION_DATE,
                signed_amount=Decimal("1"),
                currency="EUR",
                source_reference="synthetic-test-input:category-1",
            ),
        ),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )

    assert _codes(bad_category) == ("LEG_CATEGORY_INVALID",)


def test_unsupported_model_version_is_refused() -> None:
    unsupported = replace(_hand_case_input(), model_version="lng-cargo-cash-valuation/v99")

    assert _codes(unsupported) == ("MODEL_VERSION_UNSUPPORTED",)


def test_wrong_input_type_is_refused_with_a_stable_code() -> None:
    with pytest.raises(LngCashValuationError) as info:
        compute_lng_cargo_cash_valuation(object())  # type: ignore[arg-type]

    assert info.value.codes == ("INPUT_TYPE_INVALID",)


def test_valuation_error_is_a_value_error_with_stable_codes() -> None:
    error = LngCashValuationError([("CODE-X", "detail text"), ("CODE-Y", "more detail")])

    assert isinstance(error, ValueError)
    assert error.codes == ("CODE-X", "CODE-Y")
    assert "CODE-X (detail text)" in str(error)


def test_results_are_independent_of_the_ambient_decimal_context() -> None:
    expected = compute_lng_cargo_cash_valuation(_hand_case_input())

    ambient = decimal.getcontext()
    saved = ambient.copy()
    try:
        ambient.prec = 6
        ambient.rounding = decimal.ROUND_UP
        ambient.Emax = 10
        ambient.Emin = -10
        ambient.traps[decimal.Inexact] = True
        actual = compute_lng_cargo_cash_valuation(_hand_case_input())
    finally:
        decimal.setcontext(saved)

    assert actual == expected
    assert actual.net_present_value_reporting_ccy == Decimal("4.5000")
    assert actual.total_undiscounted_cash_reporting_ccy == Decimal("10.0000")


def test_category_enum_reuses_existing_cost_taxonomy_values() -> None:
    existing_values = {component.value for component in CostComponentType}
    reused = {"fuel", "transport", "regas", "storage", "other"}
    category_values = {category.value for category in LngCashLegCategory}

    assert reused <= existing_values
    assert reused <= category_values
    assert {"cargo_purchase", "cargo_sale", "shipping", "demurrage", "boil_off"} <= (
        category_values
    )


# ---------------------------------------------------------------------------
# Shared-engine adapter compatibility (bounded extraction)
# ---------------------------------------------------------------------------


def test_lng_module_reexports_the_single_shared_definitions() -> None:
    # 一个词表、一个错误类型、一套腿数据类：LNG 模块只做别名，不复制定义。
    assert LngCashLegCategory is CashFlowLegCategory
    assert LngCashValuationError is CashValuationError
    assert LngCashFxInput is CashValuationFxInput
    assert LngCashLegInput is CashValuationLegInput
    assert LngCashDiscountFactorInput is CashValuationDiscountFactorInput
    assert LngCashLegValuation is CashValuationLegValuation


def test_lng_adapter_still_requires_its_mandatory_lng_context_and_input_type() -> None:
    assert _codes(replace(_hand_case_input(), contract_id="   ")) == ("REFERENCE_MISSING",)
    assert _codes(replace(_hand_case_input(), cargo_id="")) == ("REFERENCE_MISSING",)

    # 共享引擎的通用输入（无 LNG id）绝不能被 LNG 入口静默接受。
    generic = CashValuationInput(
        business_context=(CanonicalId("portfolio", "portfolio-synthetic-1"),),
        valuation_date=VALUATION_DATE,
        reporting_currency="EUR",
        legs=(
            CashValuationLegInput(
                leg_id="only-leg-1",
                category=CashFlowLegCategory.OTHER,
                payment_date=VALUATION_DATE,
                signed_amount=Decimal("7.25"),
                currency="EUR",
                source_reference="synthetic-test-input:leg-1",
            ),
        ),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )
    with pytest.raises(LngCashValuationError) as info:
        compute_lng_cargo_cash_valuation(generic)  # type: ignore[arg-type]
    assert info.value.codes == ("INPUT_TYPE_INVALID",)


def test_lng_result_maps_shared_engine_output_field_for_field() -> None:
    lng_result = compute_lng_cargo_cash_valuation(_hand_case_input())
    engine_result = compute_cash_valuation(
        CashValuationInput(
            business_context=(
                CanonicalId("contract", "contract-synthetic-lng-1"),
                CanonicalId("cargo", "cargo-synthetic-1"),
                CanonicalId("terminal", "terminal-synthetic-regas-1"),
                CanonicalId("resource", "resource-synthetic-supply-1"),
            ),
            valuation_date=VALUATION_DATE,
            reporting_currency="EUR",
            legs=_hand_case_input().legs,
            discount_factors=_hand_case_input().discount_factors,
        )
    )

    assert (
        lng_result.total_undiscounted_cash_reporting_ccy
        == engine_result.total_undiscounted_cash_reporting_ccy
    )
    assert lng_result.net_present_value_reporting_ccy == (
        engine_result.net_present_value_reporting_ccy
    )
    assert lng_result.leg_valuations == engine_result.leg_valuations
    assert lng_result.assumptions == engine_result.assumptions
    assert lng_result.warnings == engine_result.warnings
    assert lng_result.source_references == engine_result.source_references
    # LNG 业务身份与版本保持原样：result/modelversion/lineage 均向后兼容。
    assert engine_result.model_version == CASH_VALUATION_MODEL_VERSION
    assert lng_result.model_version == LNG_CASH_VALUATION_MODEL_VERSION
    assert lng_result.lineage == ("lng-cargo-cash-valuation", LNG_CASH_VALUATION_MODEL_VERSION)
    assert (lng_result.contract_id, lng_result.cargo_id) == (
        "contract-synthetic-lng-1",
        "cargo-synthetic-1",
    )


def test_lng_refusals_from_the_shared_engine_stay_lng_catchable() -> None:
    hand_case = _hand_case_input()
    incomplete = replace(
        hand_case,
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "0.95"),
        ),
    )

    with pytest.raises(LngCashValuationError) as info:
        compute_lng_cargo_cash_valuation(incomplete)

    assert isinstance(info.value, CashValuationError)
    assert info.value.codes == ("DISCOUNT_FACTOR_MISSING_FOR_LEG_PAYMENT_DATE",)
