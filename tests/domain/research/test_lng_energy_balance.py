"""Focused tests for explicit LNG cargo energy-stage accounting.

All inputs are synthetic and explicitly labelled. The reference chain is:

    100 MWh -> 96 MWh, consumed 3 MWh, physical loss 1 MWh
     96 MWh -> 90 MWh, consumed 4 MWh, physical loss 2 MWh

Total consumed is 7 MWh, physical loss is 3 MWh and total reduction is 10 MWh.
No value is inferred and no conservation difference is quantized away.
"""

from __future__ import annotations

import decimal
from dataclasses import replace
from decimal import Decimal

import pytest

from eurogas_nexus.domain.research.lng_energy_balance import (
    LNG_ENERGY_BALANCE_MODEL_VERSION,
    MAX_ENERGY_STAGE_COUNT,
    LngEnergyBalanceError,
    LngEnergyBalanceInput,
    LngEnergyStage,
    LngEnergyStageKind,
    compute_lng_energy_balance,
)

BASIS = "synthetic-test-basis:gcV-mwh"
STAGE_1_SOURCE = "synthetic-test-input:stage-shipping-1"
STAGE_2_SOURCE = "synthetic-test-input:stage-regas-1"


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


def _balance(
    *,
    stages: object | None = None,
    purchased: str = "100",
    delivered: str = "90",
    energy_unit: str = "MWh",
    model_version: str = LNG_ENERGY_BALANCE_MODEL_VERSION,
) -> LngEnergyBalanceInput:
    """Build the synthetic reference balance with optional overrides."""

    return LngEnergyBalanceInput(
        purchased_energy_mwh=Decimal(purchased),
        delivered_energy_mwh=Decimal(delivered),
        energy_basis_reference=BASIS,
        energy_unit=energy_unit,
        stages=_reference_stages() if stages is None else stages,  # type: ignore[arg-type]
        model_version=model_version,
    )


def _codes(input_: LngEnergyBalanceInput) -> tuple[str, ...]:
    """Return stable refusal codes for one energy-balance input."""

    with pytest.raises(LngEnergyBalanceError) as info:
        compute_lng_energy_balance(input_)
    return info.value.codes


def test_explicit_chain_separates_consumption_loss_and_total_reduction() -> None:
    result = compute_lng_energy_balance(_balance())

    assert result.model_version == LNG_ENERGY_BALANCE_MODEL_VERSION
    assert result.purchased_energy_mwh == Decimal("100")
    assert result.delivered_energy_mwh == Decimal("90")
    assert result.total_consumed_energy_mwh == Decimal("7")
    assert result.physical_loss_energy_mwh == Decimal("3")
    assert result.total_reduction_energy_mwh == Decimal("10")
    assert result.total_reduction_energy_mwh != result.physical_loss_energy_mwh
    assert result.total_reduction_energy_mwh == (
        result.total_consumed_energy_mwh + result.physical_loss_energy_mwh
    )
    assert result.stage_count == 2
    assert result.source_references == tuple(
        sorted((STAGE_1_SOURCE, STAGE_2_SOURCE))
    )
    assert result.research_only is True
    assert result.human_review_required is True


def test_one_stage_with_explicit_zero_consumption_and_loss_is_valid() -> None:
    stage = _stage("transfer-1", "100", "100", "0", "0")
    result = compute_lng_energy_balance(
        _balance(stages=(stage,), purchased="100", delivered="100")
    )

    assert result.total_consumed_energy_mwh == Decimal("0")
    assert result.physical_loss_energy_mwh == Decimal("0")
    assert result.total_reduction_energy_mwh == Decimal("0")
    assert result.stage_count == 1


def test_missing_stages_are_refused_and_do_not_default_to_zero() -> None:
    assert _codes(_balance(stages=())) == ("STAGE_COUNT_INVALID",)


def test_stage_count_limit_is_enforced() -> None:
    stages = tuple(
        _stage(f"transfer-{position}", "100", "100", "0", "0")
        for position in range(MAX_ENERGY_STAGE_COUNT + 1)
    )

    assert _codes(_balance(stages=stages, delivered="100")) == ("STAGE_COUNT_EXCEEDED",)


def test_conservation_is_exact_and_not_quantized_away() -> None:
    # The 0.00001 MWh inconsistency rounds to the same 4-decimal amount but is
    # still refused: conservation is compared exactly, not on a money quantum.
    stage = _stage("transfer-1", "100.00001", "100.00000", "0", "0")
    codes = _codes(_balance(stages=(stage,), purchased="100.00001", delivered="100.00000"))

    assert "STAGE_CONSERVATION_FAILED" in codes
    assert "TOTAL_REDUCTION_RECONCILIATION_FAILED" in codes


def test_chain_must_be_adjacent_exactly() -> None:
    stages = (
        _stage("shipping-1", "100", "96", "3", "1"),
        _stage("regas-1", "95", "90", "3", "2"),
    )

    codes = _codes(_balance(stages=stages))
    assert "STAGE_CHAIN_DISCONTINUOUS" in codes


def test_duplicate_stage_ids_are_refused() -> None:
    stages = (
        _stage("shipping-1", "100", "96", "3", "1"),
        _stage("shipping-1", "96", "90", "4", "2"),
    )

    assert _codes(_balance(stages=stages)) == ("STAGE_ID_DUPLICATE",)


def test_chain_start_and_end_must_match_declared_quantities() -> None:
    start_codes = _codes(_balance(purchased="101"))
    assert "STAGE_CHAIN_START_MISMATCH" in start_codes
    assert "TOTAL_REDUCTION_RECONCILIATION_FAILED" in start_codes

    end_codes = _codes(_balance(delivered="89"))
    assert "STAGE_CHAIN_END_MISMATCH" in end_codes
    assert "TOTAL_REDUCTION_RECONCILIATION_FAILED" in end_codes


@pytest.mark.parametrize(
    ("field_name", "value", "expected_code"),
    [
        ("input_energy_mwh", Decimal("0"), "STAGE_INPUT_ENERGY_NOT_POSITIVE"),
        ("input_energy_mwh", Decimal("-1"), "STAGE_INPUT_ENERGY_NOT_POSITIVE"),
        ("input_energy_mwh", Decimal("NaN"), "STAGE_INPUT_ENERGY_NOT_FINITE"),
        ("input_energy_mwh", Decimal("Infinity"), "STAGE_INPUT_ENERGY_NOT_FINITE"),
        ("input_energy_mwh", 100.0, "STAGE_INPUT_ENERGY_NOT_DECIMAL"),
        ("input_energy_mwh", 100, "STAGE_INPUT_ENERGY_NOT_DECIMAL"),
        ("input_energy_mwh", True, "STAGE_INPUT_ENERGY_NOT_DECIMAL"),
        ("input_energy_mwh", Decimal("1e13"), "STAGE_INPUT_ENERGY_OVERFLOW"),
        ("input_energy_mwh", Decimal("1e-13"), "STAGE_INPUT_ENERGY_BELOW_MINIMUM"),
        ("output_energy_mwh", Decimal("0"), "STAGE_OUTPUT_ENERGY_NOT_POSITIVE"),
        ("output_energy_mwh", Decimal("-1"), "STAGE_OUTPUT_ENERGY_NOT_POSITIVE"),
        ("consumed_energy_mwh", Decimal("-1"), "STAGE_CONSUMED_ENERGY_NEGATIVE"),
        ("consumed_energy_mwh", Decimal("NaN"), "STAGE_CONSUMED_ENERGY_NOT_FINITE"),
        (
            "physical_loss_energy_mwh",
            Decimal("-1"),
            "STAGE_PHYSICAL_LOSS_ENERGY_NEGATIVE",
        ),
        (
            "physical_loss_energy_mwh",
            Decimal("1e13"),
            "STAGE_PHYSICAL_LOSS_ENERGY_OVERFLOW",
        ),
    ],
)
def test_invalid_stage_amounts_are_refused(
    field_name: str, value: object, expected_code: str
) -> None:
    stage = replace(_reference_stages()[0], **{field_name: value})

    assert _codes(_balance(stages=(stage,))) == (expected_code,)


def test_zero_with_an_out_of_range_decimal_exponent_is_refused() -> None:
    stage = replace(
        _reference_stages()[0],
        consumed_energy_mwh=Decimal("0E-100"),
    )

    assert _codes(_balance(stages=(stage,))) == (
        "STAGE_CONSUMED_ENERGY_EXPONENT_LIMIT",
    )


def test_bounded_34_digit_coefficient_is_accepted_and_35_is_refused() -> None:
    high_precision = "0.1234567890123456789012345678901234"
    valid_stage = _stage("transfer-1", high_precision, high_precision, "0", "0")
    result = compute_lng_energy_balance(
        _balance(
            stages=(valid_stage,),
            purchased=high_precision,
            delivered=high_precision,
        )
    )
    assert result.delivered_energy_mwh == Decimal(high_precision)

    too_precise = "0.12345678901234567890123456789012345"
    invalid_stage = _stage("transfer-1", too_precise, high_precision, "0", "0")
    assert _codes(
        _balance(
            stages=(invalid_stage,),
            purchased=high_precision,
            delivered=high_precision,
        )
    ) == ("STAGE_INPUT_ENERGY_COEFFICIENT_LIMIT",)


def test_invalid_stage_kind_and_provenance_are_refused() -> None:
    invalid_kind = replace(_reference_stages()[0], kind="shipping")
    assert _codes(_balance(stages=(invalid_kind,))) == ("STAGE_KIND_INVALID",)

    missing_source = replace(_reference_stages()[0], source_references=())
    assert _codes(_balance(stages=(missing_source,))) == (
        "STAGE_SOURCE_REFERENCE_MISSING",
    )

    invalid_source = replace(
        _reference_stages()[0], source_references=("",)
    )
    assert _codes(_balance(stages=(invalid_source,))) == (
        "STAGE_SOURCE_REFERENCE_INVALID",
    )

    non_sequence_source = replace(
        _reference_stages()[0], source_references="synthetic-test-input:stage"
    )
    assert _codes(_balance(stages=(non_sequence_source,))) == (
        "STAGE_SOURCE_REFERENCES_INVALID",
    )


def test_non_sequence_stage_container_is_refused() -> None:
    assert _codes(_balance(stages=iter(_reference_stages()))) == ("STAGES_INVALID",)


@pytest.mark.parametrize(
    ("value", "expected_code"),
    [
        ("MMBtu", "ENERGY_UNIT_UNSUPPORTED"),
        ("mwh", "ENERGY_UNIT_UNSUPPORTED"),
        (None, "ENERGY_UNIT_UNSUPPORTED"),
    ],
)
def test_unsupported_energy_units_are_refused(
    value: object, expected_code: str
) -> None:
    assert _codes(_balance(energy_unit=value)) == (expected_code,)  # type: ignore[arg-type]


def test_unsupported_model_version_is_refused() -> None:
    assert _codes(_balance(model_version="lng-energy-balance/v0")) == (
        "MODEL_VERSION_UNSUPPORTED",
    )


def test_missing_energy_basis_is_refused() -> None:
    input_ = replace(_balance(), energy_basis_reference="   ")
    assert _codes(input_) == ("ENERGY_BASIS_REFERENCE_MISSING",)


def test_results_are_independent_of_the_ambient_decimal_context() -> None:
    expected = compute_lng_energy_balance(_balance())

    ambient = decimal.getcontext()
    saved = ambient.copy()
    try:
        ambient.prec = 6
        ambient.rounding = decimal.ROUND_UP
        ambient.Emax = 10
        ambient.Emin = -10
        ambient.traps[decimal.Inexact] = True
        ambient.traps[decimal.Rounded] = True
        actual = compute_lng_energy_balance(_balance())
    finally:
        decimal.setcontext(saved)

    assert actual == expected
    assert actual.total_consumed_energy_mwh == Decimal("7")
    assert actual.physical_loss_energy_mwh == Decimal("3")
    assert actual.total_reduction_energy_mwh == Decimal("10")


def test_energy_error_is_a_value_error_with_stable_codes() -> None:
    error = LngEnergyBalanceError([("CODE-X", "detail"), ("CODE-Y", "more")])

    assert isinstance(error, ValueError)
    assert error.codes == ("CODE-X", "CODE-Y")
