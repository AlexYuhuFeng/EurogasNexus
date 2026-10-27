'''Focused tests for the exact capacity-billing research primitive.

All inputs are synthetic and explicitly labeled. Hand checks prove that a
capacity charge is billed on booked capacity energy and that cost per delivered
MWh divides by delivered energy, never by booked capacity.
'''

from __future__ import annotations

import decimal
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from eurogas_nexus.domain.research.capacity_billing import (
    CAPACITY_BILLING_MODEL_VERSION,
    EUR_CAPACITY_TARIFF_UNIT,
    GBP_CAPACITY_TARIFF_UNIT,
    PENCE_CAPACITY_TARIFF_UNIT,
    CapacityBillingError,
    CapacityBillingInput,
    compute_capacity_billing,
)

START = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
REFERENCES = (
    'synthetic-test-input:booking-1',
    'synthetic-test-input:tariff-1',
)


def _capacity_input(
    *,
    scenario_id: str = 'scenario-synthetic-1',
    tariff_id: str = 'tariff-synthetic-1',
    rate: str = '2',
    currency: str = 'EUR',
    unit: str = EUR_CAPACITY_TARIFF_UNIT,
    booked: str = '10',
    delivered: str = '115',
    billed: str = '230',
    hours: int = 23,
    start: datetime = START,
    end: datetime | None = None,
    refs: tuple[str, ...] = REFERENCES,
) -> CapacityBillingInput:
    '''Build an explicitly synthetic capacity-billing input.'''

    if end is None:
        end = start + timedelta(hours=hours)
    return CapacityBillingInput(
        scenario_id=scenario_id,
        tariff_id=tariff_id,
        tariff_rate=Decimal(rate),
        currency=currency,
        tariff_unit=unit,
        booked_capacity_mwh_per_h=Decimal(booked),
        delivered_energy_mwh=Decimal(delivered),
        billed_capacity_energy_mwh=Decimal(billed),
        billing_start=start,
        billing_end=end,
        source_references=refs,
    )


def _codes(case: CapacityBillingInput) -> tuple[str, ...]:
    '''Return the stable refusal codes of one invalid input.'''

    with pytest.raises(CapacityBillingError) as info:
        compute_capacity_billing(case)
    return info.value.codes


def test_23_hour_capacity_billing_golden_case() -> None:
    result = compute_capacity_billing(_capacity_input())

    assert result.model_version == CAPACITY_BILLING_MODEL_VERSION
    assert result.scenario_id == 'scenario-synthetic-1'
    assert result.tariff_id == 'tariff-synthetic-1'
    assert result.duration_hours == Decimal('23')
    assert result.total_cost == Decimal('460.0000')
    assert result.cost_per_delivered_mwh == Decimal('4.0000')
    assert result.currency == 'EUR'
    assert result.research_only is True
    assert result.human_review_required is True
    assert result.physical_readiness == 'NOT_ASSESSED'
    assert result.provenance == tuple(sorted(REFERENCES))
    assert result.basis.tariff_rate == Decimal('2')
    assert result.basis.duration_microseconds == 23 * 3_600_000_000
    assert result.basis.billing_start_utc == START


def test_25_hour_capacity_billing_golden_case() -> None:
    result = compute_capacity_billing(
        _capacity_input(hours=25, billed='250', delivered='125')
    )

    assert result.duration_hours == Decimal('25')
    assert result.total_cost == Decimal('500.0000')
    assert result.cost_per_delivered_mwh == Decimal('4.0000')


def test_pence_capacity_billing_golden_case() -> None:
    result = compute_capacity_billing(
        _capacity_input(
            rate='0.035827',
            currency='GBP',
            unit=PENCE_CAPACITY_TARIFF_UNIT,
            hours=24,
            billed='240',
            delivered='120',
        )
    )

    assert result.currency == 'GBP'
    assert result.duration_hours == Decimal('24')
    assert result.total_cost == Decimal('85.9848')
    assert result.cost_per_delivered_mwh == Decimal('0.7165')
    assert result.cost_per_delivered_mwh != Decimal('0.3583')


def test_gbp_per_capacity_unit_is_supported() -> None:
    result = compute_capacity_billing(
        _capacity_input(currency='GBP', unit=GBP_CAPACITY_TARIFF_UNIT)
    )

    assert result.currency == 'GBP'
    assert result.total_cost == Decimal('460.0000')


@pytest.mark.parametrize(
    ('rate', 'expected_total'),
    (
        ('0.00005', '0.0000'),
        ('0.00015', '0.0002'),
        ('0.00025', '0.0002'),
    ),
)
def test_half_even_rounding_of_capacity_cost(
    rate: str, expected_total: str
) -> None:
    result = compute_capacity_billing(
        _capacity_input(hours=1, rate=rate, booked='1', billed='1', delivered='1')
    )

    assert result.total_cost == Decimal(expected_total)
    assert result.cost_per_delivered_mwh == Decimal(expected_total)


def test_result_independent_of_ambient_decimal_context_and_traps() -> None:
    expected = compute_capacity_billing(_capacity_input())

    ambient = decimal.getcontext()
    saved = ambient.copy()
    try:
        ambient.prec = 6
        ambient.rounding = decimal.ROUND_UP
        ambient.Emax = 10
        ambient.Emin = -10
        ambient.traps[decimal.Inexact] = True
        ambient.traps[decimal.Rounded] = True
        actual = compute_capacity_billing(_capacity_input())
    finally:
        decimal.setcontext(saved)

    assert actual == expected
    assert actual.total_cost == Decimal('460.0000')


def test_one_microsecond_interval_is_exact_under_hostile_ambient_context() -> None:
    case = _capacity_input(
        start=START,
        end=START + timedelta(microseconds=1),
        booked='3600000000',
        billed='1',
        delivered='1',
        rate='2',
    )
    expected = compute_capacity_billing(case)
    assert expected.basis.duration_microseconds == 1
    assert expected.total_cost == Decimal('2.0000')
    assert expected.cost_per_delivered_mwh == Decimal('2.0000')
    assert expected.currency == 'EUR'

    ambient = decimal.getcontext()
    saved = ambient.copy()
    try:
        ambient.prec = 1
        ambient.rounding = decimal.ROUND_UP
        ambient.Emax = 1
        ambient.Emin = -1
        for trap in (
            decimal.Inexact,
            decimal.Rounded,
            decimal.Subnormal,
            decimal.Underflow,
        ):
            ambient.traps[trap] = True
        actual = compute_capacity_billing(case)
    finally:
        decimal.setcontext(saved)

    assert actual == expected
    assert actual.basis.duration_microseconds == 1


def test_near_coefficient_limit_inconsistent_billed_energy_is_refused() -> None:
    # This 30-digit billed value is the 30-significant-digit rounding of a
    # precision-34 product for the one-microsecond window, but exact
    # cross-multiplication still exposes the inconsistency.
    billed = '1.' + '0' * 8 + '13' + '8' * 18 + '9'
    case = _capacity_input(
        start=START,
        end=START + timedelta(microseconds=1),
        booked='3600000005',
        billed=billed,
        delivered='1',
        rate='1',
    )

    assert _codes(case) == ('BILLED_CAPACITY_ENERGY_INCONSISTENT',)


def test_total_cost_beyond_shared_cash_bound_is_refused() -> None:
    case = _capacity_input(
        rate='1000000000000',
        booked='1000.1',
        billed='1000.1',
        delivered='1000.1',
        hours=1,
    )

    assert _codes(case) == ('TOTAL_COST_OVERFLOW',)


def test_cost_per_delivered_mwh_beyond_shared_cash_bound_is_refused() -> None:
    case = _capacity_input(
        start=START,
        end=START + timedelta(microseconds=1),
        booked='3600000000',
        billed='1',
        delivered='1e-30',
        rate='2',
    )

    assert _codes(case) == ('COST_PER_DELIVERED_MWH_OVERFLOW',)


def test_caller_cannot_spoof_result_model_version() -> None:
    class _CallerVersion(str):
        pass

    caller_version = _CallerVersion(CAPACITY_BILLING_MODEL_VERSION)
    result = compute_capacity_billing(
        replace(_capacity_input(), model_version=caller_version)
    )

    assert result.model_version is CAPACITY_BILLING_MODEL_VERSION


@pytest.mark.parametrize(
    ('field', 'value', 'expected_code'),
    (
        ('tariff_rate', Decimal('1e13'), 'TARIFF_RATE_OVERFLOW'),
        (
            'booked_capacity_mwh_per_h',
            Decimal('1e13'),
            'BOOKED_CAPACITY_MWH_PER_H_OVERFLOW',
        ),
        (
            'delivered_energy_mwh',
            Decimal('1e19'),
            'DELIVERED_ENERGY_MWH_OVERFLOW',
        ),
        (
            'billed_capacity_energy_mwh',
            Decimal('1e19'),
            'BILLED_CAPACITY_ENERGY_MWH_OVERFLOW',
        ),
    ),
)
def test_finite_magnitude_bounds_are_checked_before_arithmetic(
    field: str, value: Decimal, expected_code: str
) -> None:
    assert _codes(replace(_capacity_input(), **{field: value})) == (expected_code,)


def test_decimal_exponent_and_coefficient_bounds_are_checked() -> None:
    tiny = replace(_capacity_input(), tariff_rate=Decimal('1e-31'))
    assert _codes(tiny) == ('TARIFF_RATE_EXPONENT_OUT_OF_RANGE',)

    too_many_digits = Decimal('1.' + '0' * 29 + '1')
    large_coefficient = replace(_capacity_input(), tariff_rate=too_many_digits)
    assert _codes(large_coefficient) == ('TARIFF_RATE_COEFFICIENT_TOO_LARGE',)


@pytest.mark.parametrize('rate', (2.0, 2, True, '2', None))
def test_non_decimal_tariff_rate_is_refused(rate: object) -> None:
    assert _codes(replace(_capacity_input(), tariff_rate=rate)) == (
        'TARIFF_RATE_NOT_DECIMAL',
    )


@pytest.mark.parametrize(
    'rate',
    (
        Decimal('NaN'),
        Decimal('sNaN'),
        Decimal('Infinity'),
        Decimal('-Infinity'),
    ),
)
def test_nonfinite_tariff_rate_is_refused(rate: Decimal) -> None:
    assert _codes(replace(_capacity_input(), tariff_rate=rate)) == (
        'TARIFF_RATE_NOT_FINITE',
    )


def test_duplicate_blank_and_malformed_provenance_is_refused() -> None:
    assert _codes(replace(_capacity_input(), source_references=('',))) == (
        'SOURCE_REFERENCE_INVALID',
    )
    assert _codes(
        replace(
            _capacity_input(),
            source_references=('synthetic-test-input:a', 'synthetic-test-input:a'),
        )
    ) == ('SOURCE_REFERENCE_DUPLICATE',)
    assert _codes(replace(_capacity_input(), source_references=())) == (
        'SOURCE_REFERENCES_MISSING',
    )
    assert _codes(
        replace(
            _capacity_input(),
            source_references=['synthetic-test-input:a'],
        )
    ) == ('SOURCE_REFERENCES_INVALID',)
    assert _codes(
        replace(_capacity_input(), source_references=('bad source',))
    ) == ('SOURCE_REFERENCE_INVALID',)


def test_invalid_duration_and_naive_datetimes_are_refused() -> None:
    assert _codes(replace(_capacity_input(), billing_end=START)) == (
        'BILLING_PERIOD_INVALID',
    )
    assert _codes(
        replace(_capacity_input(), billing_end=START - timedelta(hours=1))
    ) == ('BILLING_PERIOD_INVALID',)
    assert _codes(
        replace(_capacity_input(), billing_start=datetime(2026, 1, 1))
    ) == ('BILLING_START_INVALID',)
    assert _codes(
        replace(_capacity_input(), billing_end=datetime(2026, 1, 1))
    ) == ('BILLING_END_INVALID',)
    assert _codes(
        replace(_capacity_input(), billing_end=START + timedelta(hours=87841))
    ) == ('BILLING_DURATION_OVERFLOW',)


def test_equivalent_offsets_use_utc_duration_not_local_wall_clock() -> None:
    start = datetime(2026, 3, 29, 1, 0, tzinfo=timezone(timedelta(hours=1)))
    end = datetime(2026, 3, 29, 3, 0, tzinfo=timezone(timedelta(hours=2)))
    result = compute_capacity_billing(
        _capacity_input(
            start=start,
            end=end,
            booked='10',
            billed='10',
            delivered='5',
        )
    )

    assert result.duration_hours == Decimal('1')
    assert result.total_cost == Decimal('20.0000')


def test_billed_capacity_energy_must_equal_booked_capacity_times_duration() -> None:
    assert _codes(
        replace(
            _capacity_input(),
            billed_capacity_energy_mwh=Decimal('231'),
        )
    ) == ('BILLED_CAPACITY_ENERGY_INCONSISTENT',)


def test_delivered_energy_cannot_exceed_billed_capacity_energy() -> None:
    assert _codes(
        replace(
            _capacity_input(),
            delivered_energy_mwh=Decimal('231'),
        )
    ) == ('DELIVERED_ENERGY_EXCEEDS_BILLED_CAPACITY',)


def test_unsupported_units_currencies_and_mismatches_are_refused() -> None:
    assert _codes(
        replace(_capacity_input(), tariff_unit='EUR/MWh')
    ) == ('TARIFF_UNIT_UNSUPPORTED',)
    assert _codes(
        replace(_capacity_input(), currency='USD')
    ) == ('CURRENCY_UNSUPPORTED',)
    assert _codes(
        replace(
            _capacity_input(),
            tariff_unit=PENCE_CAPACITY_TARIFF_UNIT,
            currency='EUR',
        )
    ) == ('TARIFF_UNIT_CURRENCY_MISMATCH',)
    assert _codes(replace(_capacity_input(), currency='GBP')) == (
        'TARIFF_UNIT_CURRENCY_MISMATCH',
    )


@pytest.mark.parametrize(
    ('field', 'value', 'expected_code'),
    (
        (
            'booked_capacity_mwh_per_h',
            Decimal('0'),
            'BOOKED_CAPACITY_MWH_PER_H_NOT_POSITIVE',
        ),
        (
            'booked_capacity_mwh_per_h',
            Decimal('-10'),
            'BOOKED_CAPACITY_MWH_PER_H_NOT_POSITIVE',
        ),
        (
            'delivered_energy_mwh',
            Decimal('0'),
            'DELIVERED_ENERGY_MWH_NOT_POSITIVE',
        ),
        (
            'delivered_energy_mwh',
            Decimal('-1'),
            'DELIVERED_ENERGY_MWH_NOT_POSITIVE',
        ),
        (
            'billed_capacity_energy_mwh',
            Decimal('0'),
            'BILLED_CAPACITY_ENERGY_MWH_NOT_POSITIVE',
        ),
        (
            'billed_capacity_energy_mwh',
            Decimal('-230'),
            'BILLED_CAPACITY_ENERGY_MWH_NOT_POSITIVE',
        ),
        ('tariff_rate', Decimal('-0.1'), 'TARIFF_RATE_NEGATIVE'),
    ),
)
def test_negative_and_zero_capacity_values_are_refused(
    field: str, value: Decimal, expected_code: str
) -> None:
    assert _codes(replace(_capacity_input(), **{field: value})) == (expected_code,)


def test_zero_declared_tariff_is_valid_and_never_inferred() -> None:
    result = compute_capacity_billing(_capacity_input(rate='0'))

    assert result.tariff_rate == Decimal('0')
    assert result.total_cost == Decimal('0.0000')
    assert result.cost_per_delivered_mwh == Decimal('0.0000')
    assert result.research_only is True
    assert result.human_review_required is True


def test_malformed_ids_are_refused() -> None:
    assert _codes(
        replace(_capacity_input(), scenario_id='bad scenario')
    ) == ('SCENARIO_ID_INVALID',)
    assert _codes(replace(_capacity_input(), tariff_id='')) == (
        'TARIFF_ID_INVALID',
    )


def test_unsupported_model_version_and_wrong_input_type_are_refused() -> None:
    assert _codes(
        replace(_capacity_input(), model_version='capacity-billing/v2')
    ) == ('MODEL_VERSION_UNSUPPORTED',)

    with pytest.raises(CapacityBillingError) as info:
        compute_capacity_billing(object())  # type: ignore[arg-type]
    assert info.value.codes == ('INPUT_TYPE_INVALID',)


def test_capacity_billing_error_is_a_value_error_with_stable_codes() -> None:
    error = CapacityBillingError([('CODE-X', 'detail text'), ('CODE-Y', 'more')])

    assert isinstance(error, ValueError)
    assert error.codes == ('CODE-X', 'CODE-Y')
    assert error.code == 'CODE-X'
    assert 'CODE-X (detail text)' in str(error)


def test_precision_34_rounded_duration_product_is_not_an_exact_energy_match() -> None:
    """A rounded duration-hour product must not hide a sub-microsecond mismatch.

    In cross-multiplied units the exact booked-capacity * duration product
    exceeds the billed energy by 1e-18; dividing by 3,600,000,000
    microseconds/hour gives an excess of 1/(3.6e9 * 10^18) MWh. At Decimal
    precision 34 that product rounds to the billed value exactly, so a
    comparison made on the rounded display duration would accept it. The
    domain's exact integer cross-multiplication must still refuse. No float is
    used to build the fixture, and the domain must not inherit the ambient
    decimal context, however hostile.
    """

    duration_microseconds = 3_600_000_001
    booked = '144000012.959999996400000001'
    billed = '144000013'
    case = _capacity_input(
        start=START,
        end=START + timedelta(microseconds=duration_microseconds),
        booked=booked,
        billed=billed,
        delivered='1',
        rate='1',
    )

    # Independent demonstration of the rounding trap: the precision-34
    # duration-hours display value times the booked capacity is numerically
    # equal to the billed energy, yet the exact basis differs.
    with decimal.localcontext(
        decimal.Context(prec=34, rounding=decimal.ROUND_HALF_EVEN)
    ):
        duration_hours = Decimal(duration_microseconds) / Decimal(3_600_000_000)
        rounded_product = Decimal(booked) * duration_hours
    assert rounded_product == Decimal(billed)

    ambient = decimal.getcontext()
    saved = ambient.copy()
    try:
        ambient.prec = 6
        ambient.rounding = decimal.ROUND_UP
        ambient.Emax = 10
        ambient.Emin = -10
        ambient.traps[decimal.Inexact] = True
        ambient.traps[decimal.Rounded] = True
        assert _codes(case) == ('BILLED_CAPACITY_ENERGY_INCONSISTENT',)
    finally:
        decimal.setcontext(saved)
