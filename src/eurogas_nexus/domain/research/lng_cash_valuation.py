"""LNG cargo cash valuation adapter — research-only decision support.

Bounded business adapter over the shared dated cash valuation engine
(``domain/research/cash_valuation.py``): it validates the mandatory LNG
references, maps them to typed ``CanonicalId`` business-context references,
delegates every amount/FX/discount calculation to the single shared engine,
and maps the engine result back to this module's original dataclasses, model
version, lineage and assumptions. It contains no arithmetic of its own.

One deterministic job: normalize explicitly supplied, signed, dated cash-flow
legs of a single LNG cargo into the reporting currency and discount every leg
with an explicitly supplied discount factor. This is decision support only; it
is not complete LNG business economics, accounting, custody or settlement, and
its outputs are deliberately named ``total_undiscounted_cash_*`` and
``net_present_value_*`` — never netback, margin or mark-to-market.

唯一职责（research boundary / 研究边界）:
- 只做"LNG 船货显式现金流腿 → 共享引擎归一化 → 结果映射回 LNG 数据类"这一步；
- 算术、四舍五入与数值拒绝语义全部由 ``cash_valuation`` 独占实现，本模块零算术；
- 不推断 FX 汇率、不推断贴现曲线（DF(估值日)=1，其余全部必须显式提供）；
- 已实现（过去日期）现金流直接拒绝：这是未来现金流估值，不做已实现 PnL 汇总；
- 不含船量/能量换算、boil-off/损失扣减、netback/MTM/毛利定义、终端就绪度评估、
  成本重复计数的业务判断、API、持久化与真实商业输入。

Shared definitions (single implementation, re-exported here for compatibility):
- ``LngCashLegCategory`` is the shared ``CashFlowLegCategory``;
- ``LngCashFxInput``/``LngCashLegInput``/``LngCashDiscountFactorInput``/
  ``LngCashLegValuation`` are the shared engine's dataclasses;
- ``LngCashValuationError`` is the shared ``CashValuationError``, so callers
  catch one refusal type with the same stable UPPER_SNAKE codes.

Business-context mapping (exact, documented in
``docs/architecture/CASH_VALUATION_CAPABILITY.md``): ``contract_id`` ->
``CanonicalId("contract", ...)``, ``cargo_id`` -> ``CanonicalId("cargo", ...)``,
``terminal_id`` -> ``CanonicalId("terminal", ...)``, ``resource_id`` ->
``CanonicalId("resource", ...)``; the reverse mapping reads the shared result,
not the input, so provenance is preserved end to end.

Not yet composed (follow-up / 后续): delivered-volume and regas economics must
be composed with this adapter by a later bounded task instead of being
duplicated here.

Compact sources and docs:
- shared engine: ``domain/research/cash_valuation.py``;
- capability doc: ``docs/architecture/CASH_VALUATION_CAPABILITY.md``;
- peer research services: ``domain/research/netback.py`` and
  ``domain/research/route_cost.py``;
- regas readiness inputs: ``domain/route_cost/lng_regas.py``;
- programme scope record: ``docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md``;
- ownership row: ``docs/architecture/MODULE_OWNERSHIP_MATRIX.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from eurogas_nexus.domain.ontology.semantic_kernel import CanonicalId
from eurogas_nexus.domain.research.cash_valuation import (
    MAX_ABS_CASH_AMOUNT,
    MAX_DISCOUNT_FACTOR,
    MAX_FX_RATE,
    MIN_DISCOUNT_FACTOR,
    MIN_FX_RATE,
    MONEY_QUANTUM,
    WORKING_PRECISION,
    CashFlowLegCategory,
    CashValuationDiscountFactorInput,
    CashValuationError,
    CashValuationFxInput,
    CashValuationInput,
    CashValuationLegInput,
    CashValuationLegValuation,
    compute_cash_valuation,
)

# 兼容面显式声明：既有调用方的全部导入路径保持不变（数值常量仍可从这里导入）。
__all__ = [
    "LNG_CASH_VALUATION_MODEL_VERSION",
    "LngCargoCashValuationInput",
    "LngCargoCashValuationResult",
    "LngCashDiscountFactorInput",
    "LngCashFxInput",
    "LngCashLegCategory",
    "LngCashLegInput",
    "LngCashLegValuation",
    "LngCashValuationError",
    "MAX_ABS_CASH_AMOUNT",
    "MAX_DISCOUNT_FACTOR",
    "MAX_FX_RATE",
    "MIN_DISCOUNT_FACTOR",
    "MIN_FX_RATE",
    "MONEY_QUANTUM",
    "WORKING_PRECISION",
    "compute_lng_cargo_cash_valuation",
]

LNG_CASH_VALUATION_MODEL_VERSION = "lng-cargo-cash-valuation/v1"

# 单一词表 / 单一错误类型 / 单一腿数据类：全部指向共享引擎定义，避免重复枚举。
LngCashLegCategory = CashFlowLegCategory
LngCashValuationError = CashValuationError
LngCashFxInput = CashValuationFxInput
LngCashLegInput = CashValuationLegInput
LngCashDiscountFactorInput = CashValuationDiscountFactorInput
LngCashLegValuation = CashValuationLegValuation

# LNG 业务上下文 → 共享 CanonicalId 概念的确定性映射；映射顺序即校验顺序。
_LNG_CONTEXT_FIELDS: tuple[tuple[str, str], ...] = (
    ("contract_id", "contract"),
    ("cargo_id", "cargo"),
    ("terminal_id", "terminal"),
    ("resource_id", "resource"),
)


@dataclass(frozen=True)
class LngCargoCashValuationInput:
    """Typed, versioned input of one LNG cargo future-cash valuation.

    Attributes:
        contract_id: Mandatory contract reference.
        cargo_id: Mandatory cargo reference.
        terminal_id: Mandatory terminal reference.
        resource_id: Mandatory supply-resource reference.
        valuation_date: Valuation date; every leg is at or after it and
            DF(valuation_date) is exactly 1.
        reporting_currency: Mandatory uppercase three-letter reporting
            currency code.
        legs: Explicit signed cash-flow legs.
        discount_factors: Explicit per-payment-date discount factors with
            provenance.
        model_version: Model version; any other value is refused.
    """

    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    valuation_date: date
    reporting_currency: str
    legs: tuple[LngCashLegInput, ...]
    discount_factors: tuple[LngCashDiscountFactorInput, ...]
    model_version: str = LNG_CASH_VALUATION_MODEL_VERSION


@dataclass(frozen=True)
class LngCargoCashValuationResult:
    """Typed, versioned research result of one LNG cargo cash valuation.

    Deterministic by construction: no wall-clock field is included, so equal
    inputs always produce equal results. Produced by delegating to the shared
    ``cash_valuation`` engine; the leg amounts and present values are its
    output, mapped back to this module's dataclasses.

    Attributes:
        model_version: Version of the producing model.
        contract_id: Echoed contract reference.
        cargo_id: Echoed cargo reference.
        terminal_id: Echoed terminal reference.
        resource_id: Echoed supply-resource reference.
        valuation_date: Echoed valuation date.
        reporting_currency: Echoed reporting currency.
        leg_valuations: Per-leg normalized cash amount and present value.
        total_undiscounted_cash_reporting_ccy: Sum of leg cash amounts.
        net_present_value_reporting_ccy: Sum of leg present values.
        assumptions: Explicit model assumptions.
        warnings: Always populated research warnings.
        source_references: Sorted unique provenance supplied by the caller.
        lineage: Calculation lineage tokens.
        research_only: Always True.
        human_review_required: Always True.
    """

    model_version: str
    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    valuation_date: date
    reporting_currency: str
    leg_valuations: tuple[LngCashLegValuation, ...]
    total_undiscounted_cash_reporting_ccy: Decimal
    net_present_value_reporting_ccy: Decimal
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    source_references: tuple[str, ...]
    lineage: tuple[str, ...]
    research_only: bool = True
    human_review_required: bool = True


def compute_lng_cargo_cash_valuation(
    input_: LngCargoCashValuationInput,
) -> LngCargoCashValuationResult:
    """Value explicit signed LNG cargo cash-flow legs via the shared engine.

    先校验 LNG 必填引用（contract/cargo/terminal/resource）与模型版本，再把整张
    显式现金流表交给全仓唯一的 ``cash_valuation`` 引擎计算，并将结果映射回本模块
    的 LNG 数据类、模型版本、lineage 与假设；本函数不含任何算术或四舍五入。

    Args:
        input_: Validated typed input with mandatory LNG references, valuation
            date, reporting currency, signed legs and explicit discount
            factors.

    Returns:
        A deterministic result with per-leg normalized cash amount and present
        value, total undiscounted cash, NPV, provenance and always-on
        research warnings.

    Raises:
        LngCashValuationError: When any input violates the deterministic
            validation rules (stable codes in ``codes``); the codes, including
            the shared engine's, are unchanged from the bounded primitive.
    """

    if not isinstance(input_, LngCargoCashValuationInput):
        raise LngCashValuationError(
            [
                (
                    "INPUT_TYPE_INVALID",
                    "input must be a LngCargoCashValuationInput instance",
                )
            ]
        )
    violations: list[tuple[str, str]] = []
    if input_.model_version != LNG_CASH_VALUATION_MODEL_VERSION:
        violations.append(
            (
                "MODEL_VERSION_UNSUPPORTED",
                f"model_version={input_.model_version!r}; "
                f"supported={LNG_CASH_VALUATION_MODEL_VERSION!r}",
            )
        )
    context_references: list[CanonicalId] = []
    for field_name, concept in _LNG_CONTEXT_FIELDS:
        value = getattr(input_, field_name)
        if not isinstance(value, str) or not value.strip():
            violations.append(
                ("REFERENCE_MISSING", f"{field_name} must be a non-empty reference")
            )
        else:
            context_references.append(CanonicalId(concept, value))
    if violations:
        raise LngCashValuationError(violations)

    engine_result = compute_cash_valuation(
        CashValuationInput(
            business_context=tuple(context_references),
            valuation_date=input_.valuation_date,
            reporting_currency=input_.reporting_currency,
            legs=input_.legs,
            discount_factors=input_.discount_factors,
        )
    )
    context_values = {
        reference.concept: reference.value for reference in engine_result.business_context
    }
    return LngCargoCashValuationResult(
        model_version=input_.model_version,
        contract_id=context_values["contract"],
        cargo_id=context_values["cargo"],
        terminal_id=context_values["terminal"],
        resource_id=context_values["resource"],
        valuation_date=engine_result.valuation_date,
        reporting_currency=engine_result.reporting_currency,
        leg_valuations=engine_result.leg_valuations,
        total_undiscounted_cash_reporting_ccy=(
            engine_result.total_undiscounted_cash_reporting_ccy
        ),
        net_present_value_reporting_ccy=engine_result.net_present_value_reporting_ccy,
        assumptions=engine_result.assumptions,
        warnings=engine_result.warnings,
        source_references=engine_result.source_references,
        lineage=("lng-cargo-cash-valuation", LNG_CASH_VALUATION_MODEL_VERSION),
        research_only=engine_result.research_only,
        human_review_required=engine_result.human_review_required,
    )
