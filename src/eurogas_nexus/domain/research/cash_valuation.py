"""Shared dated cash valuation capability — the single cash-flow engine.

One deterministic job, implemented exactly once in the repository: normalize
explicitly supplied, signed, dated cash-flow legs of any business context
(LNG cargo, pipeline supply, storage, portfolio, ...) into one reporting
currency with explicit per-leg FX, and discount every leg with an explicitly
supplied discount factor. This is decision support only; it is not accounting,
custody or settlement, and its outputs are deliberately named
``total_undiscounted_cash_*`` and ``net_present_value_*`` — never netback,
margin or mark-to-market.

唯一职责（共享能力边界 / shared-capability boundary）:
- 全仓唯一的"显式现金流腿 → 报告货币归一化 → 显式贴现"实现；业务模块
  （LNG 船货、管道供应、储气、组合等）只能通过本引擎计算，禁止复制算术；
- 业务上下文只以显式 ``CanonicalId``（``ontology/semantic_kernel.py``）引用
  传入：引擎不要求 cargo/terminal 等任何特定业务实体，也从不发明实体；
- 不推断 FX 汇率、不推断贴现曲线（DF(估值日)=1，其余全部必须显式提供）；
- 已实现（过去日期）现金流直接拒绝：这是未来现金流估值，不做已实现 PnL 汇总；
- 不含能量换算、损失扣减、netback/MTM/毛利定义、API、持久化与真实商业输入。

Business adapters (for example ``domain/research/lng_cash_valuation.py``)
validate their own mandatory references first, delegate here, and map the
result back to their own dataclasses with their own model version and lineage;
they must not re-implement any arithmetic or rounding.

Implementation rules:
- Monetary values are ``Decimal`` only; floats, ints, bools and strings never
  convert implicitly.
- Validation refusals raise :class:`CashValuationError` with stable
  UPPER_SNAKE codes; one signed leg is counted exactly once and duplicate leg
  ids are refused.
- All arithmetic runs inside an explicit local decimal context (precision 34,
  ROUND_HALF_EVEN) and reporting-currency amounts are quantized to
  ``MONEY_QUANTUM``, so results do not depend on the ambient decimal context.
- No market/FX/discount source is ever defaulted or fetched: the caller
  supplies every amount, rate, factor and provenance reference.

Ontology reuse and boundary (no lossy conversion):
- Business context reuses :class:`CanonicalId` (``concept:value``) from
  ``domain/ontology/semantic_kernel.py``: a typed, immutable reference, not a
  new datastore, table or graph.
- The semantic kernel's ``Money``/``PriceBasis``/``FxConversionRef`` are
  deliberately *not* used for the arithmetic contract: their magnitude/rate
  fields are ``float``, which would be a lossy conversion for exact ``Decimal``
  cash arithmetic. Reconciling that boundary belongs to the later audited API
  integration (see ``docs/architecture/CASH_VALUATION_CAPABILITY.md``).

Compact sources and docs:
- capability doc: ``docs/architecture/CASH_VALUATION_CAPABILITY.md``;
- action mapping: ``ActionKind.COMPUTE_CASH_FLOW`` (ANALYTICAL) in
  ``domain/ontology/actions.py``;
- peer research services: ``domain/research/netback.py`` and
  ``domain/research/route_cost.py``;
- ownership row: ``docs/architecture/MODULE_OWNERSHIP_MATRIX.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    localcontext,
)
from enum import StrEnum

from eurogas_nexus.domain.ontology.semantic_kernel import CanonicalId

CASH_VALUATION_MODEL_VERSION = "cash-valuation/v1"

# Explicit monetary precision/rounding. Results must not depend on the ambient
# decimal context; the quantum matches the 4-decimal rounding of peer research
# services (netback/route_cost).
MONEY_QUANTUM = Decimal("0.0001")
WORKING_PRECISION = 34

# Deterministic magnitude guards. These are input-sanity limits, not market
# conventions: no FX or discount convention is inferred anywhere.
MAX_ABS_CASH_AMOUNT = Decimal("1e15")
MIN_FX_RATE = Decimal("1e-12")
MAX_FX_RATE = Decimal("1e12")
MIN_DISCOUNT_FACTOR = Decimal("1e-12")
MAX_DISCOUNT_FACTOR = Decimal("1e12")

_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

_ASSUMPTIONS: tuple[str, ...] = (
    "Signed legs: inflow positive, outflow negative; each leg is counted exactly once.",
    "FX comes only from explicit per-leg rates in reporting-currency-per-leg-currency"
    " direction; same-currency legs use exactly 1 and no rate is ever defaulted.",
    "Discount factors come only from explicit per-payment-date inputs with source, curve"
    " and as-of provenance; no curve or day-count convention is inferred.",
    "DF(valuation date) is exactly 1 by construction and past-dated flows are refused:"
    " this is a future cash valuation, not a realized-PnL roll-up.",
    "Arithmetic uses an explicit local decimal context (precision 34, ROUND_HALF_EVEN);"
    " reporting-currency amounts are quantized to 0.0001.",
    "The net present value is a discounted future cash-flow value only; it is not a"
    " netback, mark-to-market, margin, accounting or settlement figure.",
)

_BASELINE_WARNINGS: tuple[str, ...] = (
    "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
    "NPV_IS_NOT_NETBACK_MARK_TO_MARKET_OR_MARGIN",
)


class CashFlowLegCategory(StrEnum):
    """Cash-flow leg categories of the shared valuation vocabulary.

    Single reviewed definition (``tests/contract/test_domain_enum_ontology_gate.py``
    records the ontology review): values marked (reused) already exist in the
    research cost-component taxonomy
    (``domain/research/models.py::CostComponentType``); the remaining values
    name cargo cash flows that taxonomy does not cover. This is a cash-flow
    vocabulary, not gas-market ontology vocabulary, and its values are frozen:
    business modules (LNG adapter, cargo economics composition) match on these
    values, so extending them is an ontology-review decision, not a local edit.
    """

    CARGO_PURCHASE = "cargo_purchase"
    CARGO_SALE = "cargo_sale"
    SHIPPING = "shipping"
    TRANSPORT = "transport"  # (reused)
    REGAS = "regas"  # (reused)
    STORAGE = "storage"  # (reused)
    FUEL = "fuel"  # (reused)
    DEMURRAGE = "demurrage"
    BOIL_OFF = "boil_off"
    OTHER = "other"  # (reused)


class CashValuationError(ValueError):
    """Deterministic refusal of invalid dated cash valuation input.

    Attributes:
        violations: Ordered ``(code, detail)`` pairs of every detected
            violation; ``code`` is the stable machine-readable code.
        codes: The stable validation codes in input order.
    """

    def __init__(self, violations: list[tuple[str, str]]) -> None:
        """Build the refusal from ordered ``(code, detail)`` violations."""

        self.violations = tuple(violations)
        self.codes = tuple(code for code, _ in violations)
        super().__init__("; ".join(f"{code} ({detail})" for code, detail in violations))


@dataclass(frozen=True)
class CashValuationFxInput:
    """Explicit FX rate for one non-reporting-currency leg.

    Attributes:
        rate_reporting_per_leg: Reporting-currency amount per one leg-currency
            unit (for example EUR per USD when reporting in EUR); a positive
            finite ``Decimal``. Rates are never defaulted.
        source_reference: Mandatory provenance of the quoted rate.
        as_of: Quote date; mandatory and never after the valuation date.
    """

    rate_reporting_per_leg: Decimal
    source_reference: str
    as_of: date


@dataclass(frozen=True)
class CashValuationLegInput:
    """One signed, dated cash-flow leg of a cash valuation.

    The leg carries no business entity of its own: it belongs to the valuation,
    whose business context is declared once on :class:`CashValuationInput` as
    typed canonical references.

    Attributes:
        leg_id: Unique identity of the leg within the valuation; duplicates
            are refused so nothing is counted twice.
        category: Cash-flow category from the shared, reviewed
            :class:`CashFlowLegCategory` vocabulary.
        payment_date: Cash date; never before the valuation date.
        signed_amount: ``Decimal`` amount in ``currency``; inflow positive,
            outflow negative; zero is refused.
        currency: Uppercase three-letter code of the leg amount.
        source_reference: Mandatory provenance of the amount.
        fx: Explicit FX input for cross-currency legs; must be absent when
            ``currency`` equals the reporting currency (factor is then 1).
        description: Optional human label; never used in arithmetic.
    """

    leg_id: str
    category: CashFlowLegCategory
    payment_date: date
    signed_amount: Decimal
    currency: str
    source_reference: str
    fx: CashValuationFxInput | None = None
    description: str = ""


@dataclass(frozen=True)
class CashValuationDiscountFactorInput:
    """Explicit discount factor supplied for one payment date.

    Attributes:
        payment_date: Cash date this factor discounts; one factor per date.
        factor: Positive finite ``Decimal``; values above 1 are allowed
            (negative rates) and are never blanket-rejected.
        curve_reference: Mandatory curve/identifier the factor came from.
        source_reference: Mandatory provenance of the factor.
        as_of: Factor date; mandatory and never after the valuation date.
    """

    payment_date: date
    factor: Decimal
    curve_reference: str
    source_reference: str
    as_of: date


@dataclass(frozen=True)
class CashValuationInput:
    """Typed, versioned input of one future-cash valuation.

    Attributes:
        business_context: Mandatory, non-empty tuple of typed
            :class:`CanonicalId` references naming the business entities the
            valuation belongs to (for example ``contract``/``cargo``/
            ``terminal``/``resource`` for LNG, ``portfolio``/``pipeline``/
            ``storage`` elsewhere). The engine requires no particular entity
            kind and never invents one; duplicates are refused.
        valuation_date: Valuation date; every leg is at or after it and
            DF(valuation_date) is exactly 1.
        reporting_currency: Mandatory uppercase three-letter reporting
            currency code.
        legs: Explicit signed cash-flow legs.
        discount_factors: Explicit per-payment-date discount factors with
            provenance.
        model_version: Model version; any other value is refused.
    """

    business_context: tuple[CanonicalId, ...]
    valuation_date: date
    reporting_currency: str
    legs: tuple[CashValuationLegInput, ...]
    discount_factors: tuple[CashValuationDiscountFactorInput, ...]
    model_version: str = CASH_VALUATION_MODEL_VERSION


@dataclass(frozen=True)
class CashValuationLegValuation:
    """One normalized, discounted signed cash-flow leg.

    Attributes:
        leg_id: Echoed unique leg identity.
        category: Echoed cash-flow category.
        payment_date: Echoed cash date.
        currency: Echoed leg currency.
        signed_amount: Echoed signed amount in ``currency``.
        cash_amount_reporting_ccy: Normalized undiscounted amount in the
            reporting currency.
        present_value_reporting_ccy: Discounted amount in the reporting
            currency.
        discount_factor: Applied explicit discount factor.
        discount_curve_reference: Curve provenance of the applied factor.
        discount_source_reference: Source provenance of the applied factor.
        discount_as_of: As-of date of the applied factor.
        source_reference: Echoed amount provenance.
        fx_rate_reporting_per_leg: Applied rate; exactly 1 for same-currency
            legs.
        fx_source_reference: Provenance of the applied FX rate, or None for
            same-currency legs.
        fx_as_of: As-of date of the applied FX rate, or None.
        description: Echoed optional human label.
    """

    leg_id: str
    category: CashFlowLegCategory
    payment_date: date
    currency: str
    signed_amount: Decimal
    cash_amount_reporting_ccy: Decimal
    present_value_reporting_ccy: Decimal
    discount_factor: Decimal
    discount_curve_reference: str
    discount_source_reference: str
    discount_as_of: date
    source_reference: str
    fx_rate_reporting_per_leg: Decimal
    fx_source_reference: str | None
    fx_as_of: date | None
    description: str = ""


@dataclass(frozen=True)
class CashValuationResult:
    """Typed, versioned result of one cash valuation.

    Deterministic by construction: no wall-clock field is included, so equal
    inputs always produce equal results.

    Attributes:
        model_version: Version of the producing engine.
        business_context: Echoed typed business-context references.
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
    business_context: tuple[CanonicalId, ...]
    valuation_date: date
    reporting_currency: str
    leg_valuations: tuple[CashValuationLegValuation, ...]
    total_undiscounted_cash_reporting_ccy: Decimal
    net_present_value_reporting_ccy: Decimal
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    source_references: tuple[str, ...]
    lineage: tuple[str, ...]
    research_only: bool = True
    human_review_required: bool = True


def compute_cash_valuation(input_: CashValuationInput) -> CashValuationResult:
    """Value explicit signed cash-flow legs in the reporting currency.

    把显式提供的带符号现金流腿按显式 FX 与显式贴现因子归一化为报告货币金额，
    输出未贴现现金合计与现值合计；业务上下文只作为显式 CanonicalId 引用回显，
    不影响算术；不推断曲线、不默认汇率、不汇总已实现现金流。

    Args:
        input_: Validated typed input with business-context references,
            valuation date, reporting currency, signed legs and explicit
            discount factors.

    Returns:
        A deterministic result with per-leg normalized cash amount and present
        value, total undiscounted cash, NPV, provenance and always-on
        research warnings.

    Raises:
        CashValuationError: When any input violates the deterministic
            validation rules (stable codes in ``codes``).
    """

    if not isinstance(input_, CashValuationInput):
        raise CashValuationError(
            [
                (
                    "INPUT_TYPE_INVALID",
                    "input must be a CashValuationInput instance",
                )
            ]
        )
    # 显式物化容器：生成器等一次性可迭代对象绝不能导致"第二次迭代为空"的静默错误结果。
    container_violations: list[tuple[str, str]] = []
    if not isinstance(input_.legs, (tuple, list)):
        container_violations.append(
            ("LEGS_INVALID", "legs must be a tuple or list of CashValuationLegInput")
        )
        legs: tuple[CashValuationLegInput, ...] = ()
    else:
        legs = tuple(input_.legs)
    if not isinstance(input_.discount_factors, (tuple, list)):
        container_violations.append(
            (
                "DISCOUNT_FACTORS_INVALID",
                "discount_factors must be a tuple or list of"
                " CashValuationDiscountFactorInput",
            )
        )
        discount_factors: tuple[CashValuationDiscountFactorInput, ...] = ()
    else:
        discount_factors = tuple(input_.discount_factors)
    if not isinstance(input_.business_context, (tuple, list)):
        container_violations.append(
            (
                "BUSINESS_CONTEXT_INVALID",
                "business_context must be a tuple or list of CanonicalId references",
            )
        )
        business_context: tuple[object, ...] = ()
    else:
        business_context = tuple(input_.business_context)
    violations = container_violations + _collect_violations(
        input_, business_context, legs, discount_factors
    )
    if violations:
        raise CashValuationError(violations)

    discount_by_date = {item.payment_date: item for item in discount_factors}
    leg_valuations: list[CashValuationLegValuation] = []
    with localcontext(_valuation_decimal_context()):
        try:
            for leg in legs:
                discount = discount_by_date[leg.payment_date]
                fx_rate = Decimal(1) if leg.fx is None else leg.fx.rate_reporting_per_leg
                cash = _quantize_money(leg.signed_amount * fx_rate)
                present_value = _quantize_money(cash * discount.factor)
                leg_valuations.append(
                    CashValuationLegValuation(
                        leg_id=leg.leg_id,
                        category=leg.category,
                        payment_date=leg.payment_date,
                        currency=leg.currency,
                        signed_amount=leg.signed_amount,
                        cash_amount_reporting_ccy=cash,
                        present_value_reporting_ccy=present_value,
                        discount_factor=discount.factor,
                        discount_curve_reference=discount.curve_reference,
                        discount_source_reference=discount.source_reference,
                        discount_as_of=discount.as_of,
                        source_reference=leg.source_reference,
                        fx_rate_reporting_per_leg=fx_rate,
                        fx_source_reference=leg.fx.source_reference if leg.fx else None,
                        fx_as_of=leg.fx.as_of if leg.fx else None,
                        description=leg.description,
                    )
                )
            total_cash = _quantize_money(
                sum((item.cash_amount_reporting_ccy for item in leg_valuations), Decimal(0))
            )
            net_present_value = _quantize_money(
                sum((item.present_value_reporting_ccy for item in leg_valuations), Decimal(0))
            )
        except DecimalException as exc:
            raise CashValuationError(
                [
                    (
                        "NUMERIC_EVALUATION_OVERFLOW",
                        f"deterministic decimal evaluation failed: {exc}",
                    )
                ]
            ) from exc

    warnings = list(_BASELINE_WARNINGS)
    if net_present_value < 0:
        warnings.append("NEGATIVE_NET_PRESENT_VALUE")

    return CashValuationResult(
        model_version=input_.model_version,
        business_context=tuple(business_context),
        valuation_date=input_.valuation_date,
        reporting_currency=input_.reporting_currency,
        leg_valuations=tuple(leg_valuations),
        total_undiscounted_cash_reporting_ccy=total_cash,
        net_present_value_reporting_ccy=net_present_value,
        assumptions=_ASSUMPTIONS,
        warnings=tuple(warnings),
        source_references=_supplied_source_references(legs, discount_factors),
        lineage=("cash-valuation", CASH_VALUATION_MODEL_VERSION),
        research_only=True,
        human_review_required=True,
    )


def _collect_violations(
    input_: CashValuationInput,
    business_context: tuple[object, ...],
    legs: tuple[CashValuationLegInput, ...],
    discount_factors: tuple[CashValuationDiscountFactorInput, ...],
) -> list[tuple[str, str]]:
    """Collect every deterministic input violation in fixed validation order.

    校验顺序固定（模型版本 → 业务上下文 → 估值日/币种 → 贴现因子 → 现金流腿 →
    交叉引用），使拒绝结果可复现、可定位；任何 violations 非空即整体拒绝。
    """

    violations: list[tuple[str, str]] = []
    if input_.model_version != CASH_VALUATION_MODEL_VERSION:
        violations.append(
            (
                "MODEL_VERSION_UNSUPPORTED",
                f"model_version={input_.model_version!r}; "
                f"supported={CASH_VALUATION_MODEL_VERSION!r}",
            )
        )
    _validate_business_context(business_context, violations)

    date_ok = _is_plain_date(input_.valuation_date)
    if not date_ok:
        violations.append(
            (
                "VALUATION_DATE_INVALID",
                "valuation_date must be a calendar date (a datetime is not a valuation date)",
            )
        )
    currency_ok = _is_currency_code(input_.reporting_currency)
    if not currency_ok:
        violations.append(
            (
                "REPORTING_CURRENCY_INVALID",
                f"reporting_currency={input_.reporting_currency!r} must be an uppercase"
                " three-letter ISO-4217-style code",
            )
        )
    if not legs:
        violations.append(
            ("NO_CASH_FLOW_LEGS", "at least one signed cash-flow leg is required")
        )

    valuation_date = input_.valuation_date if date_ok else None
    reporting_currency = input_.reporting_currency if currency_ok else None
    discount_by_date = _validate_discount_factors(discount_factors, valuation_date, violations)
    _validate_legs(
        legs,
        valuation_date,
        reporting_currency,
        discount_by_date,
        violations,
    )
    return violations


def _validate_business_context(
    business_context: tuple[object, ...],
    violations: list[tuple[str, str]],
) -> None:
    """Validate the typed, non-empty, duplicate-free business context.

    业务上下文必须是非空的 ``CanonicalId`` 引用序列：引擎据此把估值归属到
    已声明的业务实体，绝不接受裸字符串（不做静默强制转换），也绝不发明实体。
    """

    if not business_context:
        violations.append(
            (
                "BUSINESS_CONTEXT_MISSING",
                "at least one business-context reference (CanonicalId) is required so the"
                " valuation is attributed to a declared business entity",
            )
        )
        return
    seen: set[CanonicalId] = set()
    for position, reference in enumerate(business_context):
        label = f"business_context[{position}]"
        if not isinstance(reference, CanonicalId):
            violations.append(
                (
                    "BUSINESS_CONTEXT_REFERENCE_INVALID",
                    f"{label} must be a CanonicalId (concept:value), got"
                    f" {type(reference).__name__}; plain strings are never coerced",
                )
            )
            continue
        if not isinstance(reference.concept, str) or not reference.concept.strip():
            violations.append(
                (
                    "BUSINESS_CONTEXT_REFERENCE_INVALID",
                    f"{label}.concept must be a non-empty ontology concept name",
                )
            )
            continue
        if not isinstance(reference.value, str) or not reference.value.strip():
            violations.append(
                (
                    "BUSINESS_CONTEXT_REFERENCE_INVALID",
                    f"{label}.value must be a non-empty entity reference",
                )
            )
            continue
        if reference in seen:
            violations.append(
                (
                    "BUSINESS_CONTEXT_REFERENCE_DUPLICATE",
                    f"{label}={reference} is supplied more than once; one entity reference"
                    " is counted exactly once",
                )
            )
        seen.add(reference)


def _validate_discount_factors(
    discount_factors: tuple[CashValuationDiscountFactorInput, ...],
    valuation_date: date | None,
    violations: list[tuple[str, str]],
) -> dict[date, CashValuationDiscountFactorInput]:
    """Validate explicit discount factors and index them by payment date."""

    index: dict[date, CashValuationDiscountFactorInput] = {}
    for position, item in enumerate(discount_factors):
        label = f"discount_factors[{position}]"
        if not _is_plain_date(item.payment_date):
            violations.append(
                (
                    "DISCOUNT_FACTOR_PAYMENT_DATE_INVALID",
                    f"{label}.payment_date must be a calendar date",
                )
            )
        else:
            if item.payment_date in index:
                violations.append(
                    (
                        "DISCOUNT_FACTOR_PAYMENT_DATE_DUPLICATE",
                        f"{label}.payment_date={item.payment_date.isoformat()} is supplied"
                        " more than once; one factor per cash date",
                    )
                )
            else:
                index[item.payment_date] = item
            if valuation_date is not None:
                if item.payment_date < valuation_date:
                    violations.append(
                        (
                            "DISCOUNT_FACTOR_PAYMENT_DATE_BEFORE_VALUATION",
                            f"{label}.payment_date={item.payment_date.isoformat()} is before"
                            f" valuation_date={valuation_date.isoformat()}; past-dated"
                            " discounting is out of scope",
                        )
                    )
                elif (
                    item.payment_date == valuation_date
                    and isinstance(item.factor, Decimal)
                    and item.factor.is_finite()
                    and item.factor != Decimal(1)
                ):
                    violations.append(
                        (
                            "DISCOUNT_FACTOR_AT_VALUATION_DATE_NOT_ONE",
                            f"{label}.factor={item.factor} at the valuation date must be"
                            " exactly 1",
                        )
                    )
        _validate_decimal(
            item.factor,
            f"{label}.factor",
            "DISCOUNT_FACTOR",
            MIN_DISCOUNT_FACTOR,
            MAX_DISCOUNT_FACTOR,
            violations,
        )
        if not isinstance(item.curve_reference, str) or not item.curve_reference.strip():
            violations.append(
                (
                    "DISCOUNT_FACTOR_CURVE_MISSING",
                    f"{label}.curve_reference is mandatory; no curve is invented",
                )
            )
        if not isinstance(item.source_reference, str) or not item.source_reference.strip():
            violations.append(
                ("DISCOUNT_FACTOR_SOURCE_MISSING", f"{label}.source_reference is mandatory")
            )
        _validate_as_of(
            item.as_of,
            valuation_date,
            f"{label}.as_of",
            "DISCOUNT_FACTOR_AS_OF_INVALID",
            "DISCOUNT_FACTOR_AS_OF_IN_FUTURE",
            violations,
        )
    return index


def _validate_legs(
    legs: tuple[CashValuationLegInput, ...],
    valuation_date: date | None,
    reporting_currency: str | None,
    discount_by_date: dict[date, CashValuationDiscountFactorInput],
    violations: list[tuple[str, str]],
) -> None:
    """Validate leg identity, amount, currency, dates, provenance and FX."""

    seen_leg_ids: set[str] = set()
    for position, leg in enumerate(legs):
        label = f"legs[{position}]"
        if not isinstance(leg.leg_id, str) or not leg.leg_id.strip():
            violations.append(
                (
                    "LEG_ID_MISSING",
                    f"{label}.leg_id must be a non-empty unique id",
                )
            )
        else:
            label = f"legs[{position}] ({leg.leg_id})"
            if leg.leg_id in seen_leg_ids:
                violations.append(
                    (
                        "DUPLICATE_LEG_ID",
                        f"{label}.leg_id is supplied more than once; one signed leg is"
                        " counted exactly once",
                    )
                )
            seen_leg_ids.add(leg.leg_id)
        if not isinstance(leg.category, CashFlowLegCategory):
            violations.append(
                (
                    "LEG_CATEGORY_INVALID",
                    f"{label}.category must be a CashFlowLegCategory member",
                )
            )
        _validate_decimal(
            leg.signed_amount,
            f"{label}.signed_amount",
            "LEG_AMOUNT",
            None,
            MAX_ABS_CASH_AMOUNT,
            violations,
        )
        currency_ok = _is_currency_code(leg.currency)
        if not currency_ok:
            violations.append(
                (
                    "LEG_CURRENCY_INVALID",
                    f"{label}.currency={leg.currency!r} must be an uppercase three-letter"
                    " ISO-4217-style code",
                )
            )
        if not isinstance(leg.source_reference, str) or not leg.source_reference.strip():
            violations.append(
                ("LEG_SOURCE_REFERENCE_MISSING", f"{label}.source_reference is mandatory")
            )
        if not _is_plain_date(leg.payment_date):
            violations.append(
                (
                    "LEG_PAYMENT_DATE_INVALID",
                    f"{label}.payment_date must be a calendar date",
                )
            )
        elif valuation_date is not None:
            if leg.payment_date < valuation_date:
                violations.append(
                    (
                        "LEG_PAYMENT_DATE_BEFORE_VALUATION",
                        f"{label}.payment_date={leg.payment_date.isoformat()} is before"
                        f" valuation_date={valuation_date.isoformat()}; this engine"
                        " values future cash only and refuses to roll up realized flows",
                    )
                )
            elif leg.payment_date not in discount_by_date:
                violations.append(
                    (
                        "DISCOUNT_FACTOR_MISSING_FOR_LEG_PAYMENT_DATE",
                        f"{label}: no explicitly supplied discount factor for"
                        f" {leg.payment_date.isoformat()}",
                    )
                )
        if currency_ok and reporting_currency is not None:
            _validate_leg_fx(leg, reporting_currency, valuation_date, label, violations)


def _validate_leg_fx(
    leg: CashValuationLegInput,
    reporting_currency: str,
    valuation_date: date | None,
    label: str,
    violations: list[tuple[str, str]],
) -> None:
    """Validate the cross-currency FX rule for one leg."""

    if leg.currency == reporting_currency:
        if leg.fx is not None:
            violations.append(
                (
                    "FX_NOT_APPLICABLE_SAME_CURRENCY",
                    f"{label}.fx must be absent for same-currency legs; the factor is"
                    " exactly 1 by construction",
                )
            )
        return
    if leg.fx is None:
        violations.append(
            (
                "FX_RATE_MISSING_FOR_CROSS_CURRENCY_LEG",
                f"{label}.fx is mandatory because currency {leg.currency!r} differs from"
                f" reporting currency {reporting_currency!r}; rates are never defaulted",
            )
        )
        return
    _validate_decimal(
        leg.fx.rate_reporting_per_leg,
        f"{label}.fx.rate_reporting_per_leg",
        "FX_RATE",
        MIN_FX_RATE,
        MAX_FX_RATE,
        violations,
    )
    if not isinstance(leg.fx.source_reference, str) or not leg.fx.source_reference.strip():
        violations.append(
            ("FX_SOURCE_MISSING", f"{label}.fx.source_reference is mandatory")
        )
    _validate_as_of(
        leg.fx.as_of,
        valuation_date,
        f"{label}.fx.as_of",
        "FX_AS_OF_INVALID",
        "FX_AS_OF_IN_FUTURE",
        violations,
    )


def _validate_decimal(
    value: object,
    label: str,
    code_prefix: str,
    minimum: Decimal | None,
    maximum: Decimal,
    violations: list[tuple[str, str]],
) -> None:
    """Validate one explicit ``Decimal`` monetary/rate value.

    ``minimum`` marks a rate/factor: the value must be positive and inside the
    supported magnitude range. ``minimum=None`` marks a signed amount, where
    zero is refused but both signs are valid; ``maximum`` guards deterministic
    overflow in both cases.
    """

    if not isinstance(value, Decimal):
        violations.append(
            (
                f"{code_prefix}_NOT_DECIMAL",
                f"{label} must be an explicit Decimal, got {type(value).__name__}",
            )
        )
        return
    if not value.is_finite():
        violations.append((f"{code_prefix}_NOT_FINITE", f"{label} must be finite"))
        return
    if value == 0:
        violations.append((f"{code_prefix}_ZERO", f"{label} must be non-zero"))
        return
    if minimum is None:
        if value.copy_abs() > maximum:
            violations.append(
                (
                    f"{code_prefix}_OVERFLOW",
                    f"{label}={value} exceeds the supported magnitude {maximum}",
                )
            )
        return
    if value < 0:
        violations.append(
            (f"{code_prefix}_NOT_POSITIVE", f"{label} must be positive")
        )
    elif value < minimum or value > maximum:
        violations.append(
            (
                f"{code_prefix}_OVERFLOW",
                f"{label}={value} is outside the supported magnitude range"
                f" [{minimum}, {maximum}]",
            )
        )


def _validate_as_of(
    value: object,
    valuation_date: date | None,
    label: str,
    invalid_code: str,
    future_code: str,
    violations: list[tuple[str, str]],
) -> None:
    """Validate a mandatory provenance date that cannot be in the future."""

    if not _is_plain_date(value):
        violations.append((invalid_code, f"{label} must be a calendar date"))
        return
    if valuation_date is not None and value > valuation_date:
        violations.append(
            (
                future_code,
                f"{label}={value.isoformat()} is after"
                f" valuation_date={valuation_date.isoformat()}; future-dated provenance"
                " is refused",
            )
        )


def _is_plain_date(value: object) -> bool:
    """Whether ``value`` is a calendar date and not a ``datetime`` or None."""

    if isinstance(value, datetime):
        return False
    return isinstance(value, date)


def _is_currency_code(value: object) -> bool:
    """Whether ``value`` is an uppercase three-letter ISO-4217-style code."""

    return isinstance(value, str) and _CURRENCY_PATTERN.fullmatch(value) is not None


def _valuation_decimal_context() -> Context:
    """Build a fresh explicit decimal context for deterministic arithmetic."""

    return Context(prec=WORKING_PRECISION, rounding=ROUND_HALF_EVEN, Emax=999_999, Emin=-999_999)


def _quantize_money(value: Decimal) -> Decimal:
    """Quantize a reporting-currency amount to the explicit monetary quantum."""

    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _supplied_source_references(
    legs: tuple[CashValuationLegInput, ...],
    discount_factors: tuple[CashValuationDiscountFactorInput, ...],
) -> tuple[str, ...]:
    """Return the sorted unique provenance the caller actually supplied."""

    sources = {leg.source_reference for leg in legs}
    sources.update(leg.fx.source_reference for leg in legs if leg.fx is not None)
    sources.update(item.source_reference for item in discount_factors)
    return tuple(sorted(sources))
