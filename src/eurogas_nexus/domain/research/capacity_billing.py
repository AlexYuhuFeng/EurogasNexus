'''Exact capacity-billing research primitive (capacity-billing/v1).

This module computes one explicitly supplied capacity tariff over one explicit
UTC billing window. It is research-only decision support: it does not establish
booked rights, technical deliverability, invoice authority or executable
arbitrage.

Supported tariff units are exactly:
- EUR/(MWh/h)/h with EUR;
- GBP/(MWh/h)/h with GBP;
- p/(kWh/h)/h with GBP, using the exact factor 1000 kWh/MWh / 100 p/GBP = 10.

Bounds are checked on original inputs before exact rational arithmetic:
- tariff rate <= 1e12;
- booked capacity <= 1e12 MWh/h;
- delivered and billed energy <= 1e18 MWh;
- duration <= 87840 hours (ten 366-day years);
- each Decimal has at most 30 coefficient digits and absolute exponent <= 30;
- final total cost and cost per delivered MWh are <= the shared
  MAX_ABS_CASH_AMOUNT of 1e15.

Billed capacity energy is checked by exact cross-multiplication:
    billed_capacity_energy_mwh * 3600000000 ==
    booked_capacity_mwh_per_h * duration_microseconds.
A rounded repeating duration_hours is never used for that check. duration_hours
is a WORKING_PRECISION-34 display value; exact microseconds are retained in the
basis.

Money is rounded from an exact Fraction to the shared MONEY_QUANTUM (0.0001)
with ROUND_HALF_EVEN. Decimal evaluation uses a fresh local context isolated
from the ambient decimal context. This is bounded exact-rational arithmetic
plus documented precision-limited duration display, not unlimited precision.
'''

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)
from fractions import Fraction

from eurogas_nexus.domain.research.cash_valuation import (
    MAX_ABS_CASH_AMOUNT,
    MONEY_QUANTUM,
    WORKING_PRECISION,
)

CAPACITY_BILLING_MODEL_VERSION = 'capacity-billing/v1'

EUR_CAPACITY_TARIFF_UNIT = 'EUR/(MWh/h)/h'
GBP_CAPACITY_TARIFF_UNIT = 'GBP/(MWh/h)/h'
PENCE_CAPACITY_TARIFF_UNIT = 'p/(kWh/h)/h'

MAX_TARIFF_RATE = Decimal('1e12')
MAX_BOOKED_CAPACITY_MWH_PER_H = Decimal('1e12')
MAX_ENERGY_MWH = Decimal('1e18')
MAX_DURATION_HOURS = Decimal('87840')
MAX_DECIMAL_COEFFICIENT_DIGITS = 30
MAX_DECIMAL_EXPONENT_ABS = 30

_MICROSECONDS_PER_HOUR = 3_600_000_000
_MAX_DURATION_MICROSECONDS = 87_840 * _MICROSECONDS_PER_HOUR
_KWH_PER_MWH = 1000
_PENCE_PER_GBP = 100

_MONEY_QUANTUM_FRACTION = Fraction(MONEY_QUANTUM)
_MAX_CASH_FRACTION = Fraction(MAX_ABS_CASH_AMOUNT)

_SUPPORTED_UNIT_SPECS: dict[str, tuple[str, Fraction]] = {
    EUR_CAPACITY_TARIFF_UNIT: ('EUR', Fraction(1, 1)),
    GBP_CAPACITY_TARIFF_UNIT: ('GBP', Fraction(1, 1)),
    PENCE_CAPACITY_TARIFF_UNIT: (
        'GBP',
        Fraction(_KWH_PER_MWH, _PENCE_PER_GBP),
    ),
}
_SUPPORTED_CURRENCIES = frozenset(('EUR', 'GBP'))

_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$')
_REFERENCE_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$')

_ASSUMPTIONS = (
    'Tariff rate applies only to the explicitly supplied booked capacity and billing window.',
    (
        'Duration is measured in UTC from exact integer microseconds; '
        'local wall-clock subtraction is never used.'
    ),
    (
        'Billed capacity energy is validated by exact integer cross-multiplication; '
        'duration_hours is a precision-limited display value.'
    ),
    (
        'Cost per delivered MWh divides the invoiced capacity cost by delivered '
        'energy; it is not an energy-price conversion.'
    ),
    (
        'The pence basis uses exactly 1000 kWh/MWh divided by 100 pence/GBP; '
        'no FX or annual/month/day approximation is applied.'
    ),
    (
        'This primitive does not establish booked rights, technical deliverability, '
        'invoice authority or executable arbitrage.'
    ),
)

_WARNINGS = (
    'RESEARCH_ONLY_DECISION_SUPPORT_NOT_INVOICE_OR_SETTLEMENT',
    'CAPACITY_BILLING_DOES_NOT_ESTABLISH_BOOKED_RIGHTS_OR_DELIVERABILITY',
)


class CapacityBillingError(ValueError):
    '''Deterministic refusal of invalid capacity-billing input or arithmetic.

    Attributes:
        violations: Ordered (code, detail) pairs of every detected violation.
        codes: Stable uppercase validation/calculation codes in input order.
    '''

    def __init__(self, violations: list[tuple[str, str]]) -> None:
        '''Build the refusal from ordered (code, detail) violations.'''

        self.violations = tuple(violations)
        self.codes = tuple(code for code, _ in violations)
        super().__init__('; '.join(f'{code} ({detail})' for code, detail in violations))

    @property
    def code(self) -> str:
        '''Return the first stable refusal code.'''

        return self.codes[0] if self.codes else ''


@dataclass(frozen=True)
class CapacityBillingBasis:
    '''Raw explicit basis of one capacity-billing calculation.'''

    tariff_rate: Decimal
    tariff_unit: str
    booked_capacity_mwh_per_h: Decimal
    billed_capacity_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    billing_start_utc: datetime
    billing_end_utc: datetime
    duration_microseconds: int


@dataclass(frozen=True)
class CapacityBillingInput:
    '''Typed, explicit-capacity-tariff input for one billing period.

    All numerical values are explicit Decimal objects. No default tariff, FX,
    annualization, calendar approximation, booking or utilization assumption is
    inferred from any other value.
    '''

    scenario_id: str
    tariff_id: str
    tariff_rate: Decimal
    currency: str
    tariff_unit: str
    booked_capacity_mwh_per_h: Decimal
    delivered_energy_mwh: Decimal
    billed_capacity_energy_mwh: Decimal
    billing_start: datetime
    billing_end: datetime
    source_references: tuple[str, ...]
    model_version: str = CAPACITY_BILLING_MODEL_VERSION


@dataclass(frozen=True)
class CapacityBillingResult:
    '''Typed result of one exact capacity-billing calculation.

    The result is research-only decision support. It intentionally records no
    booked right, technical deliverability, invoice authority or executable
    arbitrage conclusion.
    '''

    scenario_id: str
    tariff_id: str
    tariff_rate: Decimal
    tariff_unit: str
    booked_capacity_mwh_per_h: Decimal
    billed_capacity_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    billing_start: datetime
    billing_end: datetime
    duration_hours: Decimal
    total_cost: Decimal
    cost_per_delivered_mwh: Decimal
    currency: str
    model_version: str
    provenance: tuple[str, ...]
    basis: CapacityBillingBasis
    assumptions: tuple[str, ...] = _ASSUMPTIONS
    warnings: tuple[str, ...] = _WARNINGS
    lineage: tuple[str, ...] = ('capacity-billing', CAPACITY_BILLING_MODEL_VERSION)
    research_only: bool = True
    human_review_required: bool = True
    physical_readiness: str = 'NOT_ASSESSED'

    @property
    def raw_basis(self) -> CapacityBillingBasis:
        '''Return the raw explicit calculation basis.'''

        return self.basis

    @property
    def billing_basis(self) -> CapacityBillingBasis:
        '''Return the raw explicit calculation basis.'''

        return self.basis

    @property
    def source_references(self) -> tuple[str, ...]:
        '''Return the caller-supplied provenance references.'''

        return self.provenance

    @property
    def total_invoiced_cost(self) -> Decimal:
        '''Return the invoiced capacity cost in the result currency.'''

        return self.total_cost


def compute_capacity_billing(input_: CapacityBillingInput) -> CapacityBillingResult:
    '''Compute one exact capacity charge over one explicit UTC billing window.

    Args:
        input_: CapacityBillingInput with explicit tariff, capacity, energy,
            billing window and provenance.

    Returns:
        A deterministic capacity-billing result with raw basis, duration,
        invoiced capacity cost, cost per delivered MWh and research-only flags.

    Raises:
        CapacityBillingError: When any input violates the deterministic rules
            or Decimal evaluation overflows the supported bounds.
    '''

    if not isinstance(input_, CapacityBillingInput):
        raise CapacityBillingError(
            [
                (
                    'INPUT_TYPE_INVALID',
                    'input must be a CapacityBillingInput instance',
                )
            ]
        )

    violations, duration_microseconds, start_utc, end_utc = _collect_violations(input_)
    if violations:
        raise CapacityBillingError(violations)
    if duration_microseconds is None or start_utc is None or end_utc is None:
        raise CapacityBillingError(
            [
                (
                    'BILLING_PERIOD_INVALID',
                    'a positive aware billing period is required',
                )
            ]
        )

    conversion_factor = _SUPPORTED_UNIT_SPECS[input_.tariff_unit][1]

    try:
        with localcontext(_billing_decimal_context()):
            duration_hours = (
                Decimal(duration_microseconds) / Decimal(_MICROSECONDS_PER_HOUR)
            )

            total_exact = (
                Fraction(input_.tariff_rate)
                * Fraction(input_.billed_capacity_energy_mwh)
                * conversion_factor
            )
            if total_exact > _MAX_CASH_FRACTION:
                raise CapacityBillingError(
                    [
                        (
                            'TOTAL_COST_OVERFLOW',
                            f'total cost exceeds shared MAX_ABS_CASH_AMOUNT={MAX_ABS_CASH_AMOUNT}',
                        )
                    ]
                )

            total_cost = _round_fraction_to_money(total_exact)
            if total_cost.copy_abs() > MAX_ABS_CASH_AMOUNT:
                raise CapacityBillingError(
                    [
                        (
                            'TOTAL_COST_OVERFLOW',
                            f'total_cost={total_cost} exceeds {MAX_ABS_CASH_AMOUNT}',
                        )
                    ]
                )

            cost_per_exact = (
                Fraction(total_cost) / Fraction(input_.delivered_energy_mwh)
            )
            if cost_per_exact > _MAX_CASH_FRACTION:
                raise CapacityBillingError(
                    [
                        (
                            'COST_PER_DELIVERED_MWH_OVERFLOW',
                            'cost per delivered MWh exceeds the shared cash bound',
                        )
                    ]
                )

            cost_per_delivered_mwh = _round_fraction_to_money(cost_per_exact)
            if cost_per_delivered_mwh.copy_abs() > MAX_ABS_CASH_AMOUNT:
                raise CapacityBillingError(
                    [
                        (
                            'COST_PER_DELIVERED_MWH_OVERFLOW',
                            (
                                f'cost_per_delivered_mwh={cost_per_delivered_mwh} '
                                f'exceeds {MAX_ABS_CASH_AMOUNT}'
                            ),
                        )
                    ]
                )
    except DecimalException as exc:
        raise CapacityBillingError(
            [
                (
                    'NUMERIC_EVALUATION_OVERFLOW',
                    f'deterministic decimal evaluation failed: {exc}',
                )
            ]
        ) from exc

    basis = CapacityBillingBasis(
        tariff_rate=input_.tariff_rate,
        tariff_unit=input_.tariff_unit,
        booked_capacity_mwh_per_h=input_.booked_capacity_mwh_per_h,
        billed_capacity_energy_mwh=input_.billed_capacity_energy_mwh,
        delivered_energy_mwh=input_.delivered_energy_mwh,
        billing_start_utc=start_utc,
        billing_end_utc=end_utc,
        duration_microseconds=duration_microseconds,
    )
    return CapacityBillingResult(
        scenario_id=input_.scenario_id,
        tariff_id=input_.tariff_id,
        tariff_rate=input_.tariff_rate,
        tariff_unit=input_.tariff_unit,
        booked_capacity_mwh_per_h=input_.booked_capacity_mwh_per_h,
        billed_capacity_energy_mwh=input_.billed_capacity_energy_mwh,
        delivered_energy_mwh=input_.delivered_energy_mwh,
        billing_start=start_utc,
        billing_end=end_utc,
        duration_hours=duration_hours,
        total_cost=total_cost,
        cost_per_delivered_mwh=cost_per_delivered_mwh,
        currency=input_.currency,
        model_version=CAPACITY_BILLING_MODEL_VERSION,
        provenance=tuple(sorted(input_.source_references)),
        basis=basis,
        assumptions=_ASSUMPTIONS,
        warnings=_WARNINGS,
        lineage=('capacity-billing', CAPACITY_BILLING_MODEL_VERSION),
        research_only=True,
        human_review_required=True,
        physical_readiness='NOT_ASSESSED',
    )


def _collect_violations(
    input_: CapacityBillingInput,
) -> tuple[list[tuple[str, str]], int | None, datetime | None, datetime | None]:
    '''Collect deterministic violations before arithmetic.'''

    violations: list[tuple[str, str]] = []
    if input_.model_version != CAPACITY_BILLING_MODEL_VERSION:
        violations.append(
            (
                'MODEL_VERSION_UNSUPPORTED',
                f'declared model_version={input_.model_version!r} does not match '
                f'the implementation constant {CAPACITY_BILLING_MODEL_VERSION!r}',
            )
        )

    _validate_identifier(
        input_.scenario_id,
        'scenario_id',
        'SCENARIO_ID_INVALID',
        violations,
    )
    _validate_identifier(
        input_.tariff_id,
        'tariff_id',
        'TARIFF_ID_INVALID',
        violations,
    )
    _validate_source_references(input_.source_references, violations)

    currency_ok = _validate_currency(input_.currency, violations)
    unit_ok = _validate_tariff_unit(input_.tariff_unit, violations)
    if currency_ok and unit_ok:
        expected_currency = _SUPPORTED_UNIT_SPECS[input_.tariff_unit][0]
        if input_.currency != expected_currency:
            violations.append(
                (
                    'TARIFF_UNIT_CURRENCY_MISMATCH',
                    f'tariff_unit={input_.tariff_unit!r} requires '
                    f'currency={expected_currency!r}, got {input_.currency!r}',
                )
            )

    valid: dict[str, bool] = {}
    for label, value, code_prefix, allow_zero, maximum in (
        (
            'tariff_rate',
            input_.tariff_rate,
            'TARIFF_RATE',
            True,
            MAX_TARIFF_RATE,
        ),
        (
            'booked_capacity_mwh_per_h',
            input_.booked_capacity_mwh_per_h,
            'BOOKED_CAPACITY_MWH_PER_H',
            False,
            MAX_BOOKED_CAPACITY_MWH_PER_H,
        ),
        (
            'delivered_energy_mwh',
            input_.delivered_energy_mwh,
            'DELIVERED_ENERGY_MWH',
            False,
            MAX_ENERGY_MWH,
        ),
        (
            'billed_capacity_energy_mwh',
            input_.billed_capacity_energy_mwh,
            'BILLED_CAPACITY_ENERGY_MWH',
            False,
            MAX_ENERGY_MWH,
        ),
    ):
        valid[label] = _validate_decimal(
            value,
            label,
            code_prefix,
            allow_zero=allow_zero,
            maximum=maximum,
            violations=violations,
        )

    start_utc = _validate_aware_datetime(
        input_.billing_start,
        'billing_start',
        'BILLING_START_INVALID',
        violations,
    )
    end_utc = _validate_aware_datetime(
        input_.billing_end,
        'billing_end',
        'BILLING_END_INVALID',
        violations,
    )

    duration_microseconds: int | None = None
    if start_utc is not None and end_utc is not None:
        if end_utc <= start_utc:
            violations.append(
                (
                    'BILLING_PERIOD_INVALID',
                    f'billing_end={end_utc.isoformat()} must be after '
                    f'billing_start={start_utc.isoformat()}',
                )
            )
        else:
            duration_microseconds = _duration_microseconds(start_utc, end_utc)
            if duration_microseconds > _MAX_DURATION_MICROSECONDS:
                violations.append(
                    (
                        'BILLING_DURATION_OVERFLOW',
                        f'duration_microseconds={duration_microseconds} exceeds '
                        f'{MAX_DURATION_HOURS} hours',
                    )
                )
            elif valid['booked_capacity_mwh_per_h'] and valid['billed_capacity_energy_mwh']:
                billed_basis = (
                    Fraction(input_.billed_capacity_energy_mwh)
                    * _MICROSECONDS_PER_HOUR
                )
                booked_basis = (
                    Fraction(input_.booked_capacity_mwh_per_h)
                    * duration_microseconds
                )
                if billed_basis != booked_basis:
                    violations.append(
                        (
                            'BILLED_CAPACITY_ENERGY_INCONSISTENT',
                            'billed_capacity_energy_mwh must equal '
                            'booked_capacity_mwh_per_h * actual duration',
                        )
                    )

    if (
        valid['delivered_energy_mwh']
        and valid['billed_capacity_energy_mwh']
        and input_.delivered_energy_mwh > input_.billed_capacity_energy_mwh
    ):
        violations.append(
            (
                'DELIVERED_ENERGY_EXCEEDS_BILLED_CAPACITY',
                f'delivered_energy_mwh={input_.delivered_energy_mwh} exceeds '
                f'billed_capacity_energy_mwh={input_.billed_capacity_energy_mwh}',
            )
        )

    return violations, duration_microseconds, start_utc, end_utc


def _validate_identifier(
    value: object,
    label: str,
    code: str,
    violations: list[tuple[str, str]],
) -> None:
    '''Validate one mandatory, bounded, non-whitespace identifier string.'''

    if not isinstance(value, str) or not value:
        violations.append((code, f'{label} must be a non-empty string identifier'))
        return
    if _ID_PATTERN.fullmatch(value) is None:
        violations.append(
            (
                code,
                f'{label}={value!r} is malformed; expected an identifier with no whitespace',
            )
        )


def _validate_source_references(
    value: object,
    violations: list[tuple[str, str]],
) -> None:
    '''Validate mandatory non-empty tuple provenance with no duplicates.'''

    if not isinstance(value, tuple):
        violations.append(
            (
                'SOURCE_REFERENCES_INVALID',
                'source_references must be a tuple of source-reference strings',
            )
        )
        return
    if not value:
        violations.append(
            (
                'SOURCE_REFERENCES_MISSING',
                'at least one explicit source reference is required',
            )
        )
        return

    seen: set[str] = set()
    for position, reference in enumerate(value):
        label = f'source_references[{position}]'
        if not isinstance(reference, str) or not reference:
            violations.append(
                (
                    'SOURCE_REFERENCE_INVALID',
                    f'{label} must be a non-empty string reference',
                )
            )
            continue
        if _REFERENCE_PATTERN.fullmatch(reference) is None:
            violations.append(
                (
                    'SOURCE_REFERENCE_INVALID',
                    f'{label}={reference!r} is malformed',
                )
            )
            continue
        if reference in seen:
            violations.append(
                (
                    'SOURCE_REFERENCE_DUPLICATE',
                    f'{label}={reference!r} is supplied more than once',
                )
            )
        seen.add(reference)


def _validate_currency(
    value: object,
    violations: list[tuple[str, str]],
) -> bool:
    '''Validate the exact supported currency code.'''

    if isinstance(value, str) and value in _SUPPORTED_CURRENCIES:
        return True
    violations.append(
        (
            'CURRENCY_UNSUPPORTED',
            f'currency={value!r} is not one of {sorted(_SUPPORTED_CURRENCIES)!r}',
        )
    )
    return False


def _validate_tariff_unit(
    value: object,
    violations: list[tuple[str, str]],
) -> bool:
    '''Validate the exact supported capacity tariff unit.'''

    if isinstance(value, str) and value in _SUPPORTED_UNIT_SPECS:
        return True
    violations.append(
        (
            'TARIFF_UNIT_UNSUPPORTED',
            f'tariff_unit={value!r} is not one of '
            f'{sorted(_SUPPORTED_UNIT_SPECS)!r}',
        )
    )
    return False


def _validate_decimal(
    value: object,
    label: str,
    code_prefix: str,
    *,
    allow_zero: bool,
    maximum: Decimal,
    violations: list[tuple[str, str]],
) -> bool:
    '''Validate one bounded explicit Decimal before exact arithmetic.'''

    if not isinstance(value, Decimal):
        violations.append(
            (
                f'{code_prefix}_NOT_DECIMAL',
                f'{label} must be an explicit Decimal, got {type(value).__name__}',
            )
        )
        return False
    if not value.is_finite():
        violations.append((f'{code_prefix}_NOT_FINITE', f'{label} must be finite'))
        return False
    if allow_zero:
        if value < 0:
            violations.append(
                (f'{code_prefix}_NEGATIVE', f'{label} must be nonnegative')
            )
            return False
    elif value <= 0:
        violations.append(
            (f'{code_prefix}_NOT_POSITIVE', f'{label} must be positive')
        )
        return False

    decimal_tuple = value.as_tuple()
    exponent = decimal_tuple.exponent
    if not isinstance(exponent, int) or abs(exponent) > MAX_DECIMAL_EXPONENT_ABS:
        violations.append(
            (
                f'{code_prefix}_EXPONENT_OUT_OF_RANGE',
                f'{label}={value} has exponent {exponent!r}; supported absolute '
                f'exponent is at most {MAX_DECIMAL_EXPONENT_ABS}',
            )
        )
        return False
    if len(decimal_tuple.digits) > MAX_DECIMAL_COEFFICIENT_DIGITS:
        violations.append(
            (
                f'{code_prefix}_COEFFICIENT_TOO_LARGE',
                f'{label}={value} has {len(decimal_tuple.digits)} coefficient '
                f'digits; supported maximum is {MAX_DECIMAL_COEFFICIENT_DIGITS}',
            )
        )
        return False
    if value.copy_abs() > maximum:
        violations.append(
            (
                f'{code_prefix}_OVERFLOW',
                f'{label}={value} exceeds the supported magnitude {maximum}',
            )
        )
        return False
    return True


def _validate_aware_datetime(
    value: object,
    label: str,
    code: str,
    violations: list[tuple[str, str]],
) -> datetime | None:
    '''Validate an aware datetime with a usable offset and convert it to UTC.'''

    if not isinstance(value, datetime):
        violations.append((code, f'{label} must be an aware datetime'))
        return None
    if value.tzinfo is None:
        violations.append((code, f'{label} must be timezone-aware'))
        return None
    try:
        offset = value.utcoffset()
    except (OverflowError, TypeError, ValueError):
        offset = None
    if not isinstance(offset, timedelta):
        violations.append((code, f'{label} must have a valid UTC offset'))
        return None
    if abs(offset) >= timedelta(hours=24):
        violations.append((code, f'{label} has an invalid UTC offset {offset}'))
        return None
    try:
        return value.astimezone(UTC)
    except (OverflowError, OSError, TypeError, ValueError):
        violations.append((code, f'{label} cannot be converted to UTC'))
        return None


def _duration_microseconds(start_utc: datetime, end_utc: datetime) -> int:
    '''Return the exact positive UTC duration in integer microseconds.'''

    delta = end_utc - start_utc
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _billing_decimal_context() -> Context:
    '''Build a fresh explicit context isolated from caller precision/traps.'''

    context = Context(
        prec=WORKING_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emax=999_999,
        Emin=-999_999,
    )
    context.traps[InvalidOperation] = True
    context.traps[DivisionByZero] = True
    context.traps[Overflow] = True
    context.traps[Underflow] = False
    context.traps[Inexact] = False
    context.traps[Rounded] = False
    context.traps[Subnormal] = False
    return context


def _round_fraction_to_money(value: Fraction) -> Decimal:
    '''Round an exact Fraction to the shared money quantum half-even.'''

    negative = value < 0
    magnitude = -value if negative else value
    scaled = magnitude / _MONEY_QUANTUM_FRACTION
    units, remainder = divmod(scaled.numerator, scaled.denominator)
    doubled = remainder * 2
    if doubled > scaled.denominator or (
        doubled == scaled.denominator and units % 2
    ):
        units += 1
    if negative:
        units = -units
    return Decimal(units) * MONEY_QUANTUM
