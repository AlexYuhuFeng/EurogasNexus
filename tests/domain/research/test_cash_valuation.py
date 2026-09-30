"""Focused tests for the shared dated cash valuation capability.

All inputs are synthetic and explicitly labeled ("synthetic-test-input:..."):
no market or provider data is invented and nothing outside the supplied
provenance may appear in the result. The hand-calculated reference schedule is
deliberately free of any LNG identifier: a portfolio/pipeline supply case with
EUR purchase -100 at the valuation date and DF 1; USD sale +150 converted at
EUR/USD 0.8 with DF 0.95; EUR storage cost -10 with DF 0.95 => undiscounted
cash 10, NPV 4.5 — the same schedule the LNG adapter values, so the two
engines are proven to share exactly one arithmetic implementation.
"""

from __future__ import annotations

import ast
import decimal
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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
    compute_cash_valuation,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CASH_VALUATION_SOURCE = (
    REPO_ROOT / "src" / "eurogas_nexus" / "domain" / "research" / "cash_valuation.py"
)
LNG_ADAPTER_SOURCE = (
    REPO_ROOT / "src" / "eurogas_nexus" / "domain" / "research" / "lng_cash_valuation.py"
)

VALUATION_DATE = date(2026, 9, 29)
SALE_DATE = date(2026, 11, 30)
COST_DATE = date(2026, 12, 31)

PURCHASE_SOURCE = "synthetic-test-input:purchase-1"
SALE_SOURCE = "synthetic-test-input:sale-1"
FX_SOURCE = "synthetic-test-input:fx-1"
STORAGE_SOURCE = "synthetic-test-input:storage-1"
DF_SOURCE = "synthetic-test-input:df-1"
DF_CURVE = "synthetic-test-curve:eur-usd-flat"

PORTFOLIO = CanonicalId("portfolio", "portfolio-synthetic-1")
PIPELINE = CanonicalId("pipeline", "pipeline-synthetic-1")
STORAGE = CanonicalId("storage", "storage-synthetic-1")


def _leg(
    leg_id: str,
    category: CashFlowLegCategory,
    signed_amount: str,
    payment_date: date,
    currency: str = "EUR",
    source_reference: str = "synthetic-test-input:leg-1",
    fx: CashValuationFxInput | None = None,
) -> CashValuationLegInput:
    """Build one explicitly labeled synthetic leg."""

    return CashValuationLegInput(
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
) -> CashValuationDiscountFactorInput:
    """Build one explicitly labeled synthetic discount factor."""

    return CashValuationDiscountFactorInput(
        payment_date=payment_date,
        factor=Decimal(factor),
        curve_reference=curve_reference,
        source_reference=source_reference,
        as_of=as_of,
    )


def _hand_case_input(
    business_context: tuple[CanonicalId, ...] = (PORTFOLIO, PIPELINE),
) -> CashValuationInput:
    """Hand-calculated reference case: cash 10, NPV 4.5, no LNG id anywhere."""

    return CashValuationInput(
        business_context=business_context,
        valuation_date=VALUATION_DATE,
        reporting_currency="EUR",
        legs=(
            _leg(
                "supply-purchase-1",
                CashFlowLegCategory.OTHER,
                "-100",
                VALUATION_DATE,
                source_reference=PURCHASE_SOURCE,
            ),
            _leg(
                "hub-sale-1",
                CashFlowLegCategory.OTHER,
                "150",
                SALE_DATE,
                currency="USD",
                source_reference=SALE_SOURCE,
                fx=CashValuationFxInput(
                    rate_reporting_per_leg=Decimal("0.8"),
                    source_reference=FX_SOURCE,
                    as_of=VALUATION_DATE - timedelta(days=1),
                ),
            ),
            _leg(
                "storage-cost-1",
                CashFlowLegCategory.STORAGE,
                "-10",
                COST_DATE,
                source_reference=STORAGE_SOURCE,
            ),
        ),
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "0.95"),
            _discount_factor(COST_DATE, "0.95"),
        ),
    )


def _codes(input_: CashValuationInput) -> tuple[str, ...]:
    """Return the stable refusal codes of one invalid input."""

    with pytest.raises(CashValuationError) as info:
        compute_cash_valuation(input_)
    return info.value.codes


def test_business_context_schedule_values_without_any_lng_identifier() -> None:
    result = compute_cash_valuation(_hand_case_input())

    assert result.model_version == CASH_VALUATION_MODEL_VERSION
    assert result.business_context == (PORTFOLIO, PIPELINE)
    assert result.valuation_date == VALUATION_DATE
    assert result.reporting_currency == "EUR"
    assert result.research_only is True
    assert result.human_review_required is True
    # 业务上下文里没有任何 LNG id：共享引擎不需要 cargo/terminal 也能估值。
    assert all(
        "lng" not in reference.value and "cargo" not in reference.concept
        for reference in result.business_context
    )

    legs = {leg.leg_id: leg for leg in result.leg_valuations}
    assert set(legs) == {"supply-purchase-1", "hub-sale-1", "storage-cost-1"}
    purchase = legs["supply-purchase-1"]
    assert purchase.cash_amount_reporting_ccy == Decimal("-100.0000")
    assert purchase.present_value_reporting_ccy == Decimal("-100.0000")
    assert purchase.fx_rate_reporting_per_leg == Decimal(1)
    assert purchase.fx_source_reference is None
    sale = legs["hub-sale-1"]
    assert sale.currency == "USD"
    assert sale.fx_rate_reporting_per_leg == Decimal("0.8")
    assert sale.fx_source_reference == FX_SOURCE
    assert sale.fx_as_of == VALUATION_DATE - timedelta(days=1)
    assert sale.cash_amount_reporting_ccy == Decimal("120.0000")
    assert sale.present_value_reporting_ccy == Decimal("114.0000")
    assert sale.discount_factor == Decimal("0.95")
    assert sale.discount_curve_reference == DF_CURVE
    assert sale.discount_as_of == VALUATION_DATE
    assert legs["storage-cost-1"].category is CashFlowLegCategory.STORAGE
    assert legs["storage-cost-1"].cash_amount_reporting_ccy == Decimal("-10.0000")
    assert legs["storage-cost-1"].present_value_reporting_ccy == Decimal("-9.5000")

    # Hand calculation: -100 + 150*0.8 - 10 = 10; -100 + 114 - 9.5 = 4.5.
    assert result.total_undiscounted_cash_reporting_ccy == Decimal("10.0000")
    assert result.net_present_value_reporting_ccy == Decimal("4.5000")
    assert result.lineage == ("cash-valuation", CASH_VALUATION_MODEL_VERSION)
    assert result.warnings == (
        "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
        "NPV_IS_NOT_NETBACK_MARK_TO_MARKET_OR_MARGIN",
    )
    assert any("not a netback" in assumption for assumption in result.assumptions)
    assert result.source_references == tuple(
        sorted({PURCHASE_SOURCE, SALE_SOURCE, FX_SOURCE, STORAGE_SOURCE, DF_SOURCE})
    )


def test_changing_the_business_context_does_not_change_any_arithmetic() -> None:
    portfolio_case = compute_cash_valuation(_hand_case_input())
    storage_case = compute_cash_valuation(
        _hand_case_input(business_context=(STORAGE, CanonicalId("portfolio", "portfolio-2")))
    )

    assert portfolio_case.business_context != storage_case.business_context
    assert (
        portfolio_case.total_undiscounted_cash_reporting_ccy
        == storage_case.total_undiscounted_cash_reporting_ccy
    )
    assert (
        portfolio_case.net_present_value_reporting_ccy
        == storage_case.net_present_value_reporting_ccy
    )
    assert portfolio_case.leg_valuations == storage_case.leg_valuations
    assert portfolio_case.source_references == storage_case.source_references


def test_cross_currency_fx_direction_is_reporting_currency_per_leg_currency() -> None:
    original = _hand_case_input()
    restated = replace(
        original,
        legs=(
            original.legs[0],
            replace(
                original.legs[1],
                fx=CashValuationFxInput(
                    rate_reporting_per_leg=Decimal("1.25"),
                    source_reference=FX_SOURCE,
                    as_of=VALUATION_DATE - timedelta(days=1),
                ),
            ),
            original.legs[2],
        ),
    )
    result = compute_cash_valuation(restated)
    sale = {leg.leg_id: leg for leg in result.leg_valuations}["hub-sale-1"]

    # 150 USD x 1.25 EUR/USD = 187.5, discounted at 0.95 -> 178.125.
    assert sale.cash_amount_reporting_ccy == Decimal("187.5000")
    assert sale.present_value_reporting_ccy == Decimal("178.1250")


def test_fx_rules_are_not_defaulted_or_silently_ignored() -> None:
    original = _hand_case_input()
    without_fx = replace(
        original,
        legs=(original.legs[0], replace(original.legs[1], fx=None), original.legs[2]),
    )
    redundant_fx = replace(
        original,
        legs=(
            replace(
                original.legs[0],
                fx=CashValuationFxInput(
                    rate_reporting_per_leg=Decimal("1"),
                    source_reference=FX_SOURCE,
                    as_of=VALUATION_DATE,
                ),
            ),
            original.legs[1],
            original.legs[2],
        ),
    )

    assert _codes(without_fx) == ("FX_RATE_MISSING_FOR_CROSS_CURRENCY_LEG",)
    assert _codes(redundant_fx) == ("FX_NOT_APPLICABLE_SAME_CURRENCY",)


def test_business_context_must_be_typed_canonical_references() -> None:
    assert _codes(_hand_case_input(business_context=())) == ("BUSINESS_CONTEXT_MISSING",)
    assert _codes(_hand_case_input(business_context=("portfolio:synthetic-1",))) == (  # type: ignore[arg-type]
        "BUSINESS_CONTEXT_REFERENCE_INVALID",
    )
    assert _codes(
        _hand_case_input(business_context=(CanonicalId("portfolio", "  "),))
    ) == ("BUSINESS_CONTEXT_REFERENCE_INVALID",)
    assert _codes(_hand_case_input(business_context=(PORTFOLIO, PORTFOLIO))) == (
        "BUSINESS_CONTEXT_REFERENCE_DUPLICATE",
    )
    codes = _codes(_hand_case_input(business_context="portfolio:x"))  # type: ignore[arg-type]
    assert codes == ("BUSINESS_CONTEXT_INVALID", "BUSINESS_CONTEXT_MISSING")


def test_time_semantics_are_unchanged_from_the_bounded_primitive() -> None:
    original = _hand_case_input()
    same_day = replace(
        original,
        legs=(_leg("same-day-1", CashFlowLegCategory.OTHER, "-5", VALUATION_DATE),),
        discount_factors=(_discount_factor(VALUATION_DATE, "0.99"),),
    )
    past_dated = replace(
        original,
        legs=(
            *original.legs,
            _leg(
                "realized-sale-1",
                CashFlowLegCategory.OTHER,
                "5",
                VALUATION_DATE - timedelta(days=1),
                source_reference="synthetic-test-input:realized-1",
            ),
        ),
    )
    uncovered = replace(
        original,
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(SALE_DATE, "0.95"),
        ),
    )

    assert _codes(same_day) == ("DISCOUNT_FACTOR_AT_VALUATION_DATE_NOT_ONE",)
    with pytest.raises(CashValuationError) as info:
        compute_cash_valuation(past_dated)
    assert info.value.codes == ("LEG_PAYMENT_DATE_BEFORE_VALUATION",)
    detail = next(
        detail
        for code, detail in info.value.violations
        if code == "LEG_PAYMENT_DATE_BEFORE_VALUATION"
    )
    assert "future cash only" in detail
    assert _codes(uncovered) == ("DISCOUNT_FACTOR_MISSING_FOR_LEG_PAYMENT_DATE",)


def test_decimal_only_amounts_and_stable_model_version_refusal() -> None:
    original = _hand_case_input()
    float_amount = replace(
        original,
        legs=(replace(original.legs[0], signed_amount=150.0),),
        discount_factors=(_discount_factor(VALUATION_DATE, "1"),),
    )
    unsupported = replace(original, model_version="cash-valuation/v99")

    assert _codes(float_amount) == ("LEG_AMOUNT_NOT_DECIMAL",)
    assert _codes(unsupported) == ("MODEL_VERSION_UNSUPPORTED",)
    with pytest.raises(CashValuationError) as info:
        compute_cash_valuation(object())  # type: ignore[arg-type]
    assert info.value.codes == ("INPUT_TYPE_INVALID",)


def test_negative_net_present_value_still_warns() -> None:
    original = _hand_case_input()
    outflow = replace(
        original,
        legs=(
            _leg("supply-purchase-1", CashFlowLegCategory.OTHER, "-100", VALUATION_DATE),
            _leg("storage-cost-1", CashFlowLegCategory.STORAGE, "-30", COST_DATE),
        ),
        discount_factors=(
            _discount_factor(VALUATION_DATE, "1"),
            _discount_factor(COST_DATE, "0.95"),
        ),
    )
    result = compute_cash_valuation(outflow)

    assert result.total_undiscounted_cash_reporting_ccy == Decimal("-130.0000")
    assert result.net_present_value_reporting_ccy == Decimal("-128.5000")
    assert "NEGATIVE_NET_PRESENT_VALUE" in result.warnings


def test_results_are_independent_of_the_ambient_decimal_context() -> None:
    expected = compute_cash_valuation(_hand_case_input())

    ambient = decimal.getcontext()
    saved = ambient.copy()
    try:
        ambient.prec = 6
        ambient.rounding = decimal.ROUND_UP
        ambient.Emax = 10
        ambient.Emin = -10
        ambient.traps[decimal.Inexact] = True
        actual = compute_cash_valuation(_hand_case_input())
    finally:
        decimal.setcontext(saved)

    assert actual == expected
    assert actual.net_present_value_reporting_ccy == Decimal("4.5000")
    assert actual.total_undiscounted_cash_reporting_ccy == Decimal("10.0000")


_ARITHMETIC_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)


def _arithmetic_binop_count(path: Path) -> int:
    """Count numeric arithmetic operations (not, for example, PEP 604 unions)."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ARITHMETIC_OPS)
    )


def test_one_shared_arithmetic_implementation_and_no_lng_duplicate() -> None:
    cash_tree = ast.parse(
        CASH_VALUATION_SOURCE.read_text(encoding="utf-8"), filename=str(CASH_VALUATION_SOURCE)
    )
    quantizers = [
        node.name
        for node in ast.walk(cash_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_quantize_money"
    ]

    assert quantizers == ["_quantize_money"]
    assert "localcontext(" in CASH_VALUATION_SOURCE.read_text(encoding="utf-8")
    assert _arithmetic_binop_count(CASH_VALUATION_SOURCE) > 0
    # 适配器不得再出现任何算术表达式或十进制上下文：调用共享引擎即唯一实现。
    assert _arithmetic_binop_count(LNG_ADAPTER_SOURCE) == 0
    assert "localcontext" not in LNG_ADAPTER_SOURCE.read_text(encoding="utf-8")


def test_datetime_valuation_date_is_refused_not_silently_truncated() -> None:
    bad = replace(_hand_case_input(), valuation_date=datetime(2026, 9, 29, 12, 0))

    assert _codes(bad) == ("VALUATION_DATE_INVALID",)
