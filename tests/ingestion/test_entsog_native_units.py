"""Focused native-rate contract tests; no providers, database, or network."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from eurogas_nexus.ingestion.entsog_native_units import (
    NORMALIZER_VERSION,
    EntsogNativeUnitError,
    parse_entsog_native_rate,
)


def _assert_refused(value_text, unit_text, code):
    with pytest.raises(EntsogNativeUnitError) as caught:
        parse_entsog_native_rate(value_text, unit_text)
    assert isinstance(caught.value, ValueError)
    assert caught.value.code == code


def test_record_is_frozen_versioned_and_preserves_source_lexical_text():
    value_text = "  1.2300  "
    unit_text = " kWh/d "
    rate = parse_entsog_native_rate(value_text, unit_text)

    assert rate.value_text == value_text
    assert rate.unit_text == unit_text
    assert rate.native_value == Decimal("1.2300")
    assert rate.normalized_unit == "kWh/day"
    assert rate.quantity_kind == "energy"
    assert rate.rate_basis == "day"
    assert rate.energy_kwh_per_day == Decimal("1.2300")
    assert rate.volume_mcm_per_day is None
    assert rate.normalizer_version == NORMALIZER_VERSION == "entsog-native-units-v1"

    with pytest.raises(FrozenInstanceError):
        rate.value_text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("value_text", "unit_text", "normalized_unit", "expected"),
    [
        ("1", "kWh/d", "kWh/day", "1"),
        ("2.50", "kWh/day", "kWh/day", "2.50"),
        ("1", "MWh/d", "MWh/day", "1000"),
        ("1.25", "MWh/day", "MWh/day", "1250"),
        ("-2.5", "MWh/day", "MWh/day", "-2500"),
    ],
)
def test_energy_day_rates_are_kwh_per_day_and_never_volume(
    value_text, unit_text, normalized_unit, expected
):
    rate = parse_entsog_native_rate(value_text, unit_text)

    assert rate.native_value == Decimal(value_text)
    assert rate.quantity_kind == "energy"
    assert rate.rate_basis == "day"
    assert rate.normalized_unit == normalized_unit
    assert rate.energy_kwh_per_day == Decimal(expected)
    assert rate.volume_mcm_per_day is None


@pytest.mark.parametrize(
    ("value_text", "unit_text", "normalized_unit", "expected"),
    [
        ("1", "kWh/h", "kWh/hour", "24"),
        ("0.5", "kWh/h", "kWh/hour", "12"),
        ("1", "MWh/h", "MWh/hour", "24000"),
        ("-1.5", "MWh/h", "MWh/hour", "-36000"),
    ],
)
def test_hourly_energy_rates_use_exactly_24_hours_per_day(
    value_text, unit_text, normalized_unit, expected
):
    rate = parse_entsog_native_rate(value_text, unit_text)

    assert rate.quantity_kind == "energy"
    assert rate.rate_basis == "hour"
    assert rate.normalized_unit == normalized_unit
    assert rate.energy_kwh_per_day == Decimal(expected)
    assert rate.volume_mcm_per_day is None


@pytest.mark.parametrize(
    ("value_text", "unit_text", "normalized_unit", "expected"),
    [
        ("1", "m3/d", "m3/day", "0.000001"),
        ("1500000", "m3/day", "m3/day", "1.5"),
        ("1", "m3/h", "m3/hour", "0.000024"),
        ("1", "mcm/d", "mcm/day", "1"),
        ("1.5", "mcm/day", "mcm/day", "1.5"),
        ("1", "mcm/h", "mcm/hour", "24"),
        ("-2", "m3/h", "m3/hour", "-0.000048"),
    ],
)
def test_volume_rates_are_mcm_per_day_and_never_energy(
    value_text, unit_text, normalized_unit, expected
):
    rate = parse_entsog_native_rate(value_text, unit_text)

    assert rate.quantity_kind == "volume"
    assert rate.normalized_unit == normalized_unit
    assert rate.volume_mcm_per_day == Decimal(expected)
    assert rate.energy_kwh_per_day is None


@pytest.mark.parametrize(
    ("unit_text", "normalized_unit", "quantity_kind", "rate_basis"),
    [
        ("m\u00b3/d", "m3/day", "volume", "day"),
        ("m\u00b3/day", "m3/day", "volume", "day"),
        ("MWH/DAY", "MWh/day", "energy", "day"),
        ("KWH/H", "kWh/hour", "energy", "hour"),
        ("m3/DAY", "m3/day", "volume", "day"),
    ],
)
def test_reviewed_aliases_and_case_are_normalized(
    unit_text, normalized_unit, quantity_kind, rate_basis
):
    rate = parse_entsog_native_rate("1", unit_text)

    assert rate.normalized_unit == normalized_unit
    assert rate.quantity_kind == quantity_kind
    assert rate.rate_basis == rate_basis


def test_signed_precision_and_trailing_zeroes_are_not_rounded_or_reformatted():
    raw_value = "  -0.0000000000000000000000000000012300  "
    rate = parse_entsog_native_rate(raw_value, "kWh/d")
    expected = Decimal("-0.0000000000000000000000000000012300")

    assert rate.value_text == raw_value
    assert rate.native_value.as_tuple() == expected.as_tuple()
    assert rate.energy_kwh_per_day is not None
    assert rate.energy_kwh_per_day.as_tuple() == expected.as_tuple()


def test_zero_keeps_its_decimal_scale_and_negative_sign():
    positive_zero = parse_entsog_native_rate("0.0000", "kWh/day")
    assert positive_zero.native_value.as_tuple() == Decimal("0.0000").as_tuple()
    assert positive_zero.energy_kwh_per_day == Decimal(0)
    assert positive_zero.energy_kwh_per_day is not None
    assert not positive_zero.energy_kwh_per_day.is_signed()

    negative_zero = parse_entsog_native_rate("-0.000", "m3/d")
    assert negative_zero.native_value.as_tuple() == Decimal("-0.000").as_tuple()
    assert negative_zero.native_value.is_signed()
    assert negative_zero.volume_mcm_per_day == Decimal(0)


def test_precision_beyond_default_28_digits_survives_identity_and_scaling():
    raw_kwh = "1234567890123456789012345678.12345678901234567890"
    kwh_rate = parse_entsog_native_rate(raw_kwh, "kWh/day")

    assert str(kwh_rate.native_value) == raw_kwh
    assert str(kwh_rate.energy_kwh_per_day) == raw_kwh

    raw_mwh = "1.123456789012345678901234567890123456789"
    mwh_rate = parse_entsog_native_rate(raw_mwh, "MWh/d")
    expected = Decimal("1123.456789012345678901234567890123456789")

    assert str(mwh_rate.native_value) == raw_mwh
    assert mwh_rate.energy_kwh_per_day == expected
    assert len(mwh_rate.energy_kwh_per_day.as_tuple().digits) >= 40


def test_energy_output_never_populates_a_volume_field():
    for unit_text in ("kWh/d", "kWh/h", "MWh/day", "MWh/h"):
        rate = parse_entsog_native_rate("1", unit_text)
        assert rate.quantity_kind == "energy"
        assert rate.energy_kwh_per_day is not None
        assert rate.volume_mcm_per_day is None


@pytest.mark.parametrize(
    ("value_text", "code"),
    [
        (None, "invalid_value_type"),
        (True, "invalid_value_type"),
        (1, "invalid_value_type"),
        (1.0, "invalid_value_type"),
        ("", "blank_value"),
        ("   ", "blank_value"),
        ("NaN", "non_finite_value"),
        ("+Infinity", "non_finite_value"),
        ("-inf", "non_finite_value"),
        ("12,5", "invalid_numeric_string"),
        ("1_000", "invalid_numeric_string"),
        ("0x10", "invalid_numeric_string"),
        ("1e", "invalid_numeric_string"),
        ("1e37", "value_out_of_bounds"),
        ("1e-1000", "value_out_of_bounds"),
        ("9" * 129, "value_too_long"),
    ],
)
def test_invalid_value_inputs_are_refused_with_stable_typed_codes(value_text, code):
    _assert_refused(value_text, "kWh/d", code)


@pytest.mark.parametrize(
    ("unit_text", "code"),
    [
        (None, "missing_unit"),
        ("   ", "missing_unit"),
        (1.5, "invalid_unit_type"),
        ("MW", "unsupported_unit"),
        ("kWh", "unsupported_unit"),
        ("m3", "unsupported_unit"),
        ("kWh/m3", "unsupported_unit"),
        ("therm/day", "unsupported_unit"),
        ("x" * 33, "unit_too_long"),
    ],
)
def test_missing_unknown_amount_and_power_units_are_refused(unit_text, code):
    _assert_refused("1", unit_text, code)
