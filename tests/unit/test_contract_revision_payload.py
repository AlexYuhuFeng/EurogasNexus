"""Focused tests for the S1a immutable contract revision economic payload.

These tests lock the foundation of
``docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md`` section 3.1 without
touching persistence: every captured field, display metadata separation, the
canonical hash contract (key order, decimal ambient context), legacy float
provenance, null-not-zero, malformed notes, non-finite/bool refusals, the
decimal storage guards and a strict canonical roundtrip that rejects
noncanonical spellings.
"""

from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError, fields
from datetime import date
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from eurogas_nexus.domain.ontology.vocabulary import (
    BusinessDayConvention,
    PaymentAnchorEvent,
    PaymentFlowDirection,
    PaymentOffsetDayKind,
)
from eurogas_nexus.domain.research.cash_valuation import CashFlowLegCategory
from eurogas_nexus.domain.route_cost import contract_revision
from eurogas_nexus.domain.route_cost.contract_revision import (
    CANONICAL_DECIMAL_NOT_CANONICAL,
    CONTRACT_REVISION_SCHEMA_VERSION,
    CONTRACT_REVISION_SCHEMA_VERSION_V2,
    DECIMAL_STORAGE_BOUNDS_EXCEEDED,
    LEGACY_NOTES_NOT_STRUCTURED,
    LEGACY_STRUCTURED_VALUE_CONFLICT,
    MAX_DECIMAL_COEFFICIENT_DIGITS,
    MAX_DECIMAL_PLAIN_TEXT_LENGTH,
    SOURCE_PRECISION_EXACT_DECIMAL,
    SOURCE_PRECISION_LEGACY_FLOAT64,
    ContractRevisionPayloadError,
    UpstreamContractEconomicSnapshot,
    map_legacy_contract_payload,
)
from eurogas_nexus.domain.route_cost.payment_terms import (
    AnchoredPaymentRule,
    ContractPaymentTerms,
    ExplicitPaymentDate,
    PaymentScheduleItem,
)

_NOTE_COSTS = {
    "variable_cost_gbp_mwh": 0.75,
    "regas_fee_gbp_mwh": 1.25,
    "fuel_loss_allowance_pct": 1.5,
}


def _legacy_payload(**overrides: object) -> dict[str, object]:
    """Return a full legacy contract payload in the repository read shape."""

    notes = {
        "source": "web_contract_capture",
        "decision_support_only": True,
        "operator_notes": "operator draft decision support",
        "source_reference": "contract-scan-1",
        **_NOTE_COSTS,
    }
    payload: dict[str, object] = {
        "contract_id": "ttf-supply-2025",
        "contract_name": "TTF supply 2025",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": 125.5,
        "contract_price_gbp_mwh": 29.75,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2.0,
        "nomination_tolerance_pct": 1.0,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
        "annual_financing_rate_pct": 6.0,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": ["NBP", "TTF"],
        "eligible_sale_modes": ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
        "notes": json.dumps(notes, sort_keys=True),
    }
    payload.update(overrides)
    return payload


def _snapshot(**overrides: object) -> UpstreamContractEconomicSnapshot:
    """Build one exact-decimal snapshot directly (valid unless overridden)."""

    values: dict[str, object] = {
        "contract_id": "ttf-supply-2025",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": Decimal("125.5"),
        "contract_price_gbp_mwh": Decimal("29.75"),
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": Decimal("2"),
        "nomination_tolerance_pct": Decimal("1"),
        "annual_financing_rate_pct": Decimal("6"),
        "allowed_exit_points": ("NBP", "TTF"),
        "eligible_sale_modes": ("TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"),
    }
    values.update(overrides)
    return UpstreamContractEconomicSnapshot(**values)  # type: ignore[arg-type]


def _mapped_snapshot(payload: dict[str, object]) -> UpstreamContractEconomicSnapshot:
    return map_legacy_contract_payload(payload).economic_snapshot


def _refusal_code(payload: dict[str, object]) -> str:
    with pytest.raises(ContractRevisionPayloadError) as excinfo:
        map_legacy_contract_payload(payload)
    return excinfo.value.code


def test_snapshot_field_set_is_the_reviewed_payload_contract() -> None:
    assert [field.name for field in fields(UpstreamContractEconomicSnapshot)] == [
        "contract_id",
        "resource_type",
        "delivery_point_name",
        "gas_year",
        "delivery_quantity_mwh_per_day",
        "contract_price_gbp_mwh",
        "settlement_frequency",
        "upstream_payment_lag_days",
        "screen_sale_cash_lag_days",
        "delivery_tolerance_pct",
        "nomination_tolerance_pct",
        "annual_financing_rate_pct",
        "allowed_exit_points",
        "eligible_sale_modes",
        "tolerance_risk_allowance_gbp_mwh",
        "owned_entry_capacity_mwh_per_day",
        "owned_exit_capacity_mwh_per_day",
        "variable_cost_gbp_mwh",
        "regas_fee_gbp_mwh",
        "fuel_loss_allowance_pct",
        "numeric_source_precision",
        "mapping_issues",
        "schema_version",
        "payment_terms",
    ]


def test_mapping_captures_every_current_economic_field() -> None:
    payload = _legacy_payload()
    mapped = map_legacy_contract_payload(payload)
    snapshot = mapped.economic_snapshot

    assert snapshot.contract_id == "ttf-supply-2025"
    assert snapshot.resource_type == "PIPELINE_IMPORT"
    assert snapshot.delivery_point_name == "TTF"
    assert snapshot.gas_year == "2025+"
    assert snapshot.delivery_quantity_mwh_per_day == Decimal("125.5")
    assert snapshot.contract_price_gbp_mwh == Decimal("29.75")
    assert snapshot.settlement_frequency == "monthly"
    assert snapshot.upstream_payment_lag_days == 20
    assert snapshot.screen_sale_cash_lag_days == 1
    assert snapshot.delivery_tolerance_pct == Decimal("2")
    assert snapshot.nomination_tolerance_pct == Decimal("1")
    assert snapshot.tolerance_risk_allowance_gbp_mwh == Decimal("0.1")
    assert snapshot.annual_financing_rate_pct == Decimal("6")
    assert snapshot.owned_entry_capacity_mwh_per_day is None
    assert snapshot.owned_exit_capacity_mwh_per_day is None
    assert snapshot.allowed_exit_points == ("NBP", "TTF")
    assert snapshot.eligible_sale_modes == (
        "TARGET_MARKET_SALE",
        "LOCAL_MARKET_SALE",
    )
    assert snapshot.variable_cost_gbp_mwh == Decimal("0.75")
    assert snapshot.regas_fee_gbp_mwh == Decimal("1.25")
    assert snapshot.fuel_loss_allowance_pct == Decimal("1.5")
    assert snapshot.schema_version == CONTRACT_REVISION_SCHEMA_VERSION
    assert snapshot.numeric_source_precision == SOURCE_PRECISION_LEGACY_FLOAT64
    assert snapshot.mapping_issues == ()
    assert mapped.display_metadata.contract_name == "TTF supply 2025"
    assert mapped.display_metadata.operator_notes == payload["notes"]


def test_snapshot_states_payment_terms_unavailable_without_inventing_dates() -> None:
    snapshot = _mapped_snapshot(_legacy_payload())

    assert snapshot.payment_terms is None
    assert snapshot.canonical_document()["payment_terms"] is None
    assert snapshot.numeric_source_precision == SOURCE_PRECISION_LEGACY_FLOAT64
    # The legacy lags stay whole-day integers; no date, day count or calendar
    # is derived from them and no effective/recorded date enters the payload.
    assert isinstance(snapshot.upstream_payment_lag_days, int)
    assert isinstance(snapshot.screen_sale_cash_lag_days, int)
    date_like_fields = [
        field.name
        for field in fields(UpstreamContractEconomicSnapshot)
        if "date" in field.name or field.name.endswith("_utc")
    ]
    assert date_like_fields == []


def test_canonical_document_serializes_exact_decimal_strings() -> None:
    snapshot = _mapped_snapshot(_legacy_payload())
    document = snapshot.canonical_document()

    assert document["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION
    assert document["contract_id"] == "ttf-supply-2025"
    assert document["delivery_quantity_mwh_per_day"] == "125.5"
    assert document["contract_price_gbp_mwh"] == "29.75"
    assert document["tolerance_risk_allowance_gbp_mwh"] == "0.1"
    assert document["owned_entry_capacity_mwh_per_day"] is None
    assert document["allowed_exit_points"] == ["NBP", "TTF"]
    assert document["eligible_sale_modes"] == [
        "TARGET_MARKET_SALE",
        "LOCAL_MARKET_SALE",
    ]
    assert document["payment_terms"] is None
    assert json.loads(snapshot.canonical_json()) == document
    assert snapshot.content_hash().startswith("sha256:")
    assert len(snapshot.content_hash()) == len("sha256:") + 64


def test_hash_is_stable_across_payload_mapping_key_order() -> None:
    payload = _legacy_payload()
    reversed_order = {key: payload[key] for key in sorted(payload, reverse=True)}

    first = _mapped_snapshot(payload)
    second = _mapped_snapshot(reversed_order)

    assert first.canonical_json() == second.canonical_json()
    assert first.content_hash() == second.content_hash()


def test_hash_is_stable_across_ambient_decimal_context() -> None:
    baseline = _mapped_snapshot(_legacy_payload())

    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        stressed = _mapped_snapshot(_legacy_payload())

    assert stressed.canonical_json() == baseline.canonical_json()
    assert stressed.content_hash() == baseline.content_hash()


def test_display_metadata_changes_do_not_change_the_economic_hash() -> None:
    base = map_legacy_contract_payload(_legacy_payload())
    renamed = map_legacy_contract_payload(
        _legacy_payload(contract_name="Renamed TTF supply")
    )
    annotated = map_legacy_contract_payload(
        _legacy_payload(
            notes=json.dumps(
                {
                    "operator_notes": "different operator prose entirely",
                    "source_reference": "contract-scan-2",
                    **_NOTE_COSTS,
                },
                sort_keys=True,
            )
        )
    )

    assert renamed.display_metadata.contract_name == "Renamed TTF supply"
    assert renamed.display_metadata != base.display_metadata
    assert renamed.economic_snapshot.content_hash() == base.economic_snapshot.content_hash()
    assert annotated.display_metadata != base.display_metadata
    assert annotated.economic_snapshot.content_hash() == base.economic_snapshot.content_hash()


def test_economic_changes_change_the_hash() -> None:
    base_hash = _mapped_snapshot(_legacy_payload()).content_hash()

    repriced = _mapped_snapshot(_legacy_payload(contract_price_gbp_mwh=30.25))
    recosted_notes = _mapped_snapshot(
        _legacy_payload(
            notes=json.dumps({"variable_cost_gbp_mwh": 0.85}, sort_keys=True)
        )
    )

    assert repriced.content_hash() != base_hash
    assert recosted_notes.content_hash() != base_hash
    assert recosted_notes.variable_cost_gbp_mwh == Decimal("0.85")


def test_legacy_float_conversion_is_labeled_and_isolated() -> None:
    snapshot = _mapped_snapshot(
        _legacy_payload(tolerance_risk_allowance_gbp_mwh=0.1)
    )

    assert snapshot.numeric_source_precision == SOURCE_PRECISION_LEGACY_FLOAT64
    # The shortest round-trip string is captured; the binary float's exact value
    # (and therefore the original typed decimal) is not recoverable, and the
    # precision label says so.
    assert snapshot.tolerance_risk_allowance_gbp_mwh == Decimal("0.1")
    assert snapshot.tolerance_risk_allowance_gbp_mwh != Decimal(0.1)

    # Float conversion is isolated to the legacy mapper: the payload contract
    # itself refuses a float so it can never masquerade as an exact decimal.
    with pytest.raises(ContractRevisionPayloadError) as excinfo:
        _snapshot(contract_price_gbp_mwh=29.75)
    assert excinfo.value.code == "number_not_decimal"

    # ``legacy_float64`` is the capture precision ceiling, not a claim that
    # every value was literally a float: a numeric string in the structured
    # notes is captured losslessly under the same ceiling label.
    from_notes_string = _mapped_snapshot(
        _legacy_payload(
            notes=json.dumps({"variable_cost_gbp_mwh": "1.10"}, sort_keys=True)
        )
    )
    assert from_notes_string.variable_cost_gbp_mwh == Decimal("1.10")
    assert from_notes_string.numeric_source_precision == SOURCE_PRECISION_LEGACY_FLOAT64


def test_missing_optional_values_stay_null_and_zero_is_a_value() -> None:
    absent = _mapped_snapshot(
        _legacy_payload(
            owned_entry_capacity_mwh_per_day=None,
            tolerance_risk_allowance_gbp_mwh=None,
            notes=None,
        )
    )
    zeroed = _mapped_snapshot(
        _legacy_payload(
            owned_entry_capacity_mwh_per_day=0.0,
            tolerance_risk_allowance_gbp_mwh=0.0,
            notes=json.dumps({"variable_cost_gbp_mwh": 0}, sort_keys=True),
        )
    )

    assert absent.owned_entry_capacity_mwh_per_day is None
    assert absent.tolerance_risk_allowance_gbp_mwh is None
    assert absent.variable_cost_gbp_mwh is None
    assert absent.regas_fee_gbp_mwh is None
    assert zeroed.owned_entry_capacity_mwh_per_day == Decimal("0.0")
    assert zeroed.owned_entry_capacity_mwh_per_day is not None
    assert zeroed.tolerance_risk_allowance_gbp_mwh == Decimal("0.0")
    assert zeroed.variable_cost_gbp_mwh == Decimal("0")
    assert zeroed.content_hash() != absent.content_hash()


def test_malformed_notes_are_recorded_and_do_not_erase_costs() -> None:
    truncated_json = _mapped_snapshot(
        _legacy_payload(notes='{"variable_cost_gbp_mwh": ')
    )
    assert truncated_json.variable_cost_gbp_mwh is None
    assert truncated_json.regas_fee_gbp_mwh is None
    assert truncated_json.fuel_loss_allowance_pct is None
    assert truncated_json.mapping_issues == (LEGACY_NOTES_NOT_STRUCTURED,)

    not_an_object = _mapped_snapshot(_legacy_payload(notes="[1, 2, 3]"))
    assert not_an_object.mapping_issues == (LEGACY_NOTES_NOT_STRUCTURED,)

    # An explicit top-level cost survives unparseable notes: costs are never
    # silently erased, and the notes problem stays visible.
    explicit = _mapped_snapshot(
        _legacy_payload(notes="operator free text", variable_cost_gbp_mwh=0.75)
    )
    assert explicit.variable_cost_gbp_mwh == Decimal("0.75")
    assert explicit.mapping_issues == (LEGACY_NOTES_NOT_STRUCTURED,)


def test_conflicting_structured_cost_values_are_recorded_not_guessed() -> None:
    conflict = _mapped_snapshot(_legacy_payload(regas_fee_gbp_mwh=1.0))
    agreed = _mapped_snapshot(_legacy_payload(regas_fee_gbp_mwh=1.25))

    # Current parser precedence: the top-level payload field wins, but the
    # disagreement is recorded instead of silently discarded.
    assert conflict.regas_fee_gbp_mwh == Decimal("1.0")
    assert conflict.mapping_issues == (LEGACY_STRUCTURED_VALUE_CONFLICT,)
    assert agreed.regas_fee_gbp_mwh == Decimal("1.25")
    assert agreed.mapping_issues == ()


def test_ordered_lists_are_preserved_and_copied_into_fresh_tuples() -> None:
    exit_points = ["NBP", "TTF"]
    sale_modes = ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"]
    mapped = map_legacy_contract_payload(
        _legacy_payload(allowed_exit_points=exit_points, eligible_sale_modes=sale_modes)
    )
    snapshot = mapped.economic_snapshot

    # Caller-owned lists may be mutated afterwards: the snapshot is unaffected.
    exit_points.append("ZEE")
    exit_points[0] = "XXX"
    sale_modes.clear()

    assert isinstance(snapshot.allowed_exit_points, tuple)
    assert snapshot.allowed_exit_points == ("NBP", "TTF")
    assert snapshot.eligible_sale_modes == (
        "TARGET_MARKET_SALE",
        "LOCAL_MARKET_SALE",
    )
    assert snapshot.canonical_document()["allowed_exit_points"] == ["NBP", "TTF"]

    # Fresh document copies too: mutating them cannot reach the snapshot.
    document = snapshot.canonical_document()
    document["allowed_exit_points"].append("ZEE")  # type: ignore[union-attr]
    assert snapshot.allowed_exit_points == ("NBP", "TTF")

    with pytest.raises(FrozenInstanceError):
        snapshot.contract_price_gbp_mwh = Decimal("1")  # type: ignore[misc]


def test_legacy_mapping_does_not_clamp_a_stored_negative_price() -> None:
    """The current write path refuses negative prices (``Field(ge=0)``).

    The mapper neither accepts them as policy nor silently flattens them the way
    the optimizer's ``non_negative_number`` does: a stored anomaly is captured
    verbatim so a governed write path can refuse it explicitly later.
    """

    snapshot = _mapped_snapshot(_legacy_payload(contract_price_gbp_mwh=-3.5))

    assert snapshot.contract_price_gbp_mwh == Decimal("-3.5")


def test_legacy_numbers_refuse_bool_non_finite_and_invalid_text() -> None:
    assert _refusal_code(_legacy_payload(variable_cost_gbp_mwh=True)) == (
        "number_bool_rejected"
    )
    assert _refusal_code(
        _legacy_payload(notes=json.dumps({"variable_cost_gbp_mwh": math.nan}))
    ) == "number_non_finite"
    assert _refusal_code(_legacy_payload(regas_fee_gbp_mwh=float("inf"))) == (
        "number_non_finite"
    )
    assert _refusal_code(_legacy_payload(regas_fee_gbp_mwh="not-a-number")) == (
        "number_text_invalid"
    )
    assert _refusal_code(_legacy_payload(upstream_payment_lag_days=20.0)) == (
        "lag_days_not_int"
    )


def test_snapshot_constructor_refuses_bool_float_and_non_finite() -> None:
    with pytest.raises(ContractRevisionPayloadError) as bool_error:
        _snapshot(contract_price_gbp_mwh=True)
    assert bool_error.value.code == "number_bool_rejected"

    with pytest.raises(ContractRevisionPayloadError) as float_error:
        _snapshot(delivery_quantity_mwh_per_day=125.5)
    assert float_error.value.code == "number_not_decimal"

    for non_finite in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(ContractRevisionPayloadError) as finite_error:
            _snapshot(variable_cost_gbp_mwh=non_finite)
        assert finite_error.value.code == "number_non_finite"


def test_constructor_refuses_decimals_outside_the_storage_guard() -> None:
    """Pathological coefficients/exponents refuse before any formatting.

    ``format(Decimal("1e999999999"), "f")`` would try to allocate a gigabyte of
    zeros; the guard inspects the exponent tuple first and refuses cheaply.
    """

    for value in (
        Decimal("1e999999999"),
        Decimal("-1e999999999"),
        Decimal("1e-999999999"),
        Decimal("-1e-999999999"),
        # Zero is not exempt: a huge negative exponent still pads fractional
        # zeros, and a huge positive exponent is a spelling this schema never
        # produces.
        Decimal("0e999999999"),
        Decimal("0e-999999999"),
    ):
        with pytest.raises(ContractRevisionPayloadError) as excinfo:
            _snapshot(contract_price_gbp_mwh=value)
        assert excinfo.value.code == DECIMAL_STORAGE_BOUNDS_EXCEEDED

    over_limit_coefficient = Decimal("1" * (MAX_DECIMAL_COEFFICIENT_DIGITS + 1))
    with pytest.raises(ContractRevisionPayloadError) as coefficient_error:
        _snapshot(contract_price_gbp_mwh=over_limit_coefficient)
    assert coefficient_error.value.code == DECIMAL_STORAGE_BOUNDS_EXCEEDED

    over_limit_exponent = Decimal("1e" + str(MAX_DECIMAL_PLAIN_TEXT_LENGTH))
    with pytest.raises(ContractRevisionPayloadError) as exponent_error:
        _snapshot(contract_price_gbp_mwh=over_limit_exponent)
    assert exponent_error.value.code == DECIMAL_STORAGE_BOUNDS_EXCEEDED

    # Inclusive storage guards, not market rules: the largest allowed
    # coefficient and the longest allowed plain text still build.
    at_coefficient_limit = _snapshot(
        contract_price_gbp_mwh=Decimal("1" * MAX_DECIMAL_COEFFICIENT_DIGITS)
    )
    assert len(at_coefficient_limit.contract_price_gbp_mwh.as_tuple().digits) == (
        MAX_DECIMAL_COEFFICIENT_DIGITS
    )
    at_plain_length_limit = Decimal("1e" + str(MAX_DECIMAL_PLAIN_TEXT_LENGTH - 1))
    assert (
        _snapshot(
            contract_price_gbp_mwh=at_plain_length_limit
        ).contract_price_gbp_mwh
        == at_plain_length_limit
    )


def test_storage_guard_and_serialization_are_ambient_context_independent() -> None:
    precise = Decimal("1.23456789012345678901234567890123456789")
    baseline = _snapshot(
        contract_price_gbp_mwh=precise,
        delivery_quantity_mwh_per_day=Decimal("1e-30"),
    )

    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        context.rounding = ROUND_DOWN
        stressed = _snapshot(
            contract_price_gbp_mwh=precise,
            delivery_quantity_mwh_per_day=Decimal("1e-30"),
        )
        with pytest.raises(ContractRevisionPayloadError) as excinfo:
            _snapshot(contract_price_gbp_mwh=Decimal("1e999999999"))
        assert excinfo.value.code == DECIMAL_STORAGE_BOUNDS_EXCEEDED

    assert stressed.canonical_json() == baseline.canonical_json()
    assert stressed.content_hash() == baseline.content_hash()


def test_mapping_refuses_missing_required_and_malformed_fields() -> None:
    missing_price = _legacy_payload()
    del missing_price["contract_price_gbp_mwh"]
    assert _refusal_code(missing_price) == "number_field_missing"

    assert _refusal_code(_legacy_payload(contract_id="   ")) == "text_field_blank"
    assert _refusal_code(_legacy_payload(gas_year=None)) == "text_field_missing"
    assert _refusal_code(_legacy_payload(allowed_exit_points=None)) == (
        "list_field_missing"
    )
    assert _refusal_code(_legacy_payload(eligible_sale_modes="TARGET_MARKET_SALE")) == (
        "text_list_not_sequence"
    )
    assert _refusal_code(_legacy_payload(allowed_exit_points=["NBP", 7])) == (
        "text_list_item_not_string"
    )


def test_canonical_roundtrip_is_lossless_and_strict() -> None:
    snapshot = _mapped_snapshot(_legacy_payload())
    document = snapshot.canonical_document()
    rebuilt = UpstreamContractEconomicSnapshot.from_canonical_document(document)

    assert rebuilt == snapshot
    assert rebuilt.content_hash() == snapshot.content_hash()
    assert rebuilt.payment_terms is None
    assert rebuilt.numeric_source_precision == SOURCE_PRECISION_LEGACY_FLOAT64

    parsed = json.loads(snapshot.canonical_json())
    assert UpstreamContractEconomicSnapshot.from_canonical_document(parsed) == snapshot

    with pytest.raises(ContractRevisionPayloadError) as extra_field:
        UpstreamContractEconomicSnapshot.from_canonical_document(
            {**document, "unexpected": 1}
        )
    assert extra_field.value.code == "canonical_field_set_mismatch"

    with pytest.raises(ContractRevisionPayloadError) as lossy_number:
        UpstreamContractEconomicSnapshot.from_canonical_document(
            {**document, "contract_price_gbp_mwh": 29.75}
        )
    assert lossy_number.value.code == "canonical_decimal_not_string"

    with pytest.raises(ContractRevisionPayloadError) as non_finite:
        UpstreamContractEconomicSnapshot.from_canonical_document(
            {**document, "contract_price_gbp_mwh": "NaN"}
        )
    assert non_finite.value.code == "number_non_finite"

    with pytest.raises(ContractRevisionPayloadError) as payment_terms:
        UpstreamContractEconomicSnapshot.from_canonical_document(
            {**document, "payment_terms": {"anchor_event": "invoice_date"}}
        )
    assert payment_terms.value.code == "canonical_payment_terms_present"

    with pytest.raises(ContractRevisionPayloadError) as wrong_version:
        UpstreamContractEconomicSnapshot.from_canonical_document(
            {**document, "schema_version": "upstream-contract-revision/v3"}
        )
    assert wrong_version.value.code == "canonical_schema_version_unknown"


def test_canonical_decode_rejects_noncanonical_decimal_spellings() -> None:
    snapshot = _mapped_snapshot(_legacy_payload())
    document = snapshot.canonical_document()
    assert document["contract_price_gbp_mwh"] == "29.75"

    for spelling in (
        " 29.75",  # leading whitespace was previously stripped
        "29.75 ",  # trailing whitespace
        "+29.75",  # explicit plus sign
        "2_9.75",  # digit-group underscore
        "2.975e1",  # exponent notation
        "2.975E+1",
        "2975e-2",
    ):
        with pytest.raises(ContractRevisionPayloadError) as excinfo:
            UpstreamContractEconomicSnapshot.from_canonical_document(
                {**document, "contract_price_gbp_mwh": spelling}
            )
        assert excinfo.value.code == CANONICAL_DECIMAL_NOT_CANONICAL, spelling

    # Huge exponents are refused by the storage guard before any formatting,
    # including zero with a huge exponent in either direction.
    for spelling in (
        "1e999999999",
        "-1e999999999",
        "1e-999999999",
        "0e999999999",
        "0e-999999999",
    ):
        with pytest.raises(ContractRevisionPayloadError) as excinfo:
            UpstreamContractEconomicSnapshot.from_canonical_document(
                {**document, "contract_price_gbp_mwh": spelling}
            )
        assert excinfo.value.code == DECIMAL_STORAGE_BOUNDS_EXCEEDED, spelling

    # Round trip: the serialized text decodes to a value that serializes back
    # to exactly the same text, including a round-trip-equal respelling.
    rebuilt = UpstreamContractEconomicSnapshot.from_canonical_document(document)
    assert rebuilt.canonical_document() == document
    respelled = UpstreamContractEconomicSnapshot.from_canonical_document(
        {**document, "contract_price_gbp_mwh": "29.750"}
    )
    assert respelled.canonical_document()["contract_price_gbp_mwh"] == "29.750"


def test_exact_decimal_snapshots_are_labelled_exact() -> None:
    exact = _snapshot()

    assert exact.numeric_source_precision == SOURCE_PRECISION_EXACT_DECIMAL
    assert exact.content_hash() != _mapped_snapshot(_legacy_payload()).content_hash()


def test_structured_note_field_names_match_the_legacy_repository() -> None:
    """Boundary guard: the domain copy of the legacy notes keys cannot drift."""

    from eurogas_nexus.db.repositories.route_cost import _STRUCTURED_NOTE_FIELDS

    assert (
        contract_revision._STRUCTURED_ECONOMIC_NOTE_FIELDS
        == _STRUCTURED_NOTE_FIELDS
    )


# ---------------------------------------------------------------------------
# Revision v2 compatibility (domain-only step, no storage/write/read wiring)
# ---------------------------------------------------------------------------

#: Untrusted marker: refusals must never echo it back.
_SENTINEL = "sentinel-value-that-must-never-be-echoed"

#: Golden v2 canonical bytes: the v1 field set with the strict nested
#: ``contract-payment-terms/v1`` document. Any change to this literal means the
#: v2 layout or the nested document shape was silently altered.
_REVISION_V2_GOLDEN_JSON = (
    '{"allowed_exit_points":["NBP","TTF"],"annual_financing_rate_pct":"6",'
    '"contract_id":"ttf-supply-2025","contract_price_gbp_mwh":"29.75",'
    '"delivery_point_name":"TTF","delivery_quantity_mwh_per_day":"125.5",'
    '"delivery_tolerance_pct":"2","eligible_sale_modes":["TARGET_MARKET_SALE",'
    '"LOCAL_MARKET_SALE"],"fuel_loss_allowance_pct":null,"gas_year":"2025+",'
    '"mapping_issues":[],"nomination_tolerance_pct":"1",'
    '"numeric_source_precision":"exact_decimal",'
    '"owned_entry_capacity_mwh_per_day":null,"owned_exit_capacity_mwh_per_day":null,'
    '"payment_terms":{"items":[{"cash_flow_category":"cargo_purchase",'
    '"date_specification":{"final_payable_date":"2026-11-30","kind":"EXPLICIT_DATE",'
    '"source_reference":"invoice INV-2026-0042"},"flow_direction":"OUTFLOW",'
    '"item_id":"item-1","source_reference":"contract schedule 1"},'
    '{"cash_flow_category":"cargo_sale",'
    '"date_specification":{"anchor_event":"INVOICE_DATE","anchor_offset_days":20,'
    '"business_day_convention":"FOLLOWING",'
    '"calendar_reference":"uk-bank-holidays-2026","kind":"ANCHORED_RULE",'
    '"offset_day_kind":"BUSINESS_DAYS","source_reference":"contract clause 7.2"},'
    '"flow_direction":"INFLOW","item_id":"item-2",'
    '"source_reference":"contract clause 7.2"}],'
    '"quantity_basis_reference":"invoice_quantity",'
    '"schema_version":"contract-payment-terms/v1"},"regas_fee_gbp_mwh":null,'
    '"resource_type":"PIPELINE_IMPORT",'
    '"schema_version":"upstream-contract-revision/v2","screen_sale_cash_lag_days":1,'
    '"settlement_frequency":"monthly","tolerance_risk_allowance_gbp_mwh":null,'
    '"upstream_payment_lag_days":20,"variable_cost_gbp_mwh":null}'
)
_REVISION_V2_GOLDEN_HASH = (
    "sha256:335c0bfde35817ae0c52b51da58aa85ac48bd3ef79ce949ec5fd2e5c9e4c5988"
)


def _v2_terms() -> ContractPaymentTerms:
    """Build one valid declared schedule covering both date shapes."""

    return ContractPaymentTerms(
        quantity_basis_reference="invoice_quantity",
        items=(
            PaymentScheduleItem(
                item_id="item-1",
                cash_flow_category=CashFlowLegCategory.CARGO_PURCHASE,
                flow_direction=PaymentFlowDirection.OUTFLOW,
                source_reference="contract schedule 1",
                date_specification=ExplicitPaymentDate(
                    final_payable_date=date(2026, 11, 30),
                    source_reference="invoice INV-2026-0042",
                ),
            ),
            PaymentScheduleItem(
                item_id="item-2",
                cash_flow_category=CashFlowLegCategory.CARGO_SALE,
                flow_direction=PaymentFlowDirection.INFLOW,
                source_reference="contract clause 7.2",
                date_specification=AnchoredPaymentRule(
                    anchor_event=PaymentAnchorEvent.INVOICE_DATE,
                    anchor_offset_days=20,
                    offset_day_kind=PaymentOffsetDayKind.BUSINESS_DAYS,
                    business_day_convention=BusinessDayConvention.FOLLOWING,
                    calendar_reference="uk-bank-holidays-2026",
                    source_reference="contract clause 7.2",
                ),
            ),
        ),
    )


def _v2_snapshot(terms: ContractPaymentTerms | None = None) -> UpstreamContractEconomicSnapshot:
    """Build one exact-decimal v2 snapshot (null terms unless given)."""

    return _snapshot(
        schema_version=CONTRACT_REVISION_SCHEMA_VERSION_V2,
        payment_terms=terms,
    )


def _nested_reversed_keys(value: object) -> object:
    """Return a JSON-ish structure with every dict key order reversed."""

    if isinstance(value, dict):
        return {key: _nested_reversed_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_nested_reversed_keys(entry) for entry in value]
    return value


def test_default_construction_and_legacy_mapping_stay_v1() -> None:
    """v2 is never produced by default and never converted in memory."""

    direct = _snapshot()
    mapped = _mapped_snapshot(_legacy_payload())

    for snapshot in (direct, mapped):
        assert snapshot.schema_version == CONTRACT_REVISION_SCHEMA_VERSION
        assert snapshot.payment_terms is None
        assert snapshot.canonical_document()["payment_terms"] is None


def test_v2_canonical_bytes_and_hash_are_pinned() -> None:
    snapshot = _v2_snapshot(_v2_terms())

    assert snapshot.canonical_json() == _REVISION_V2_GOLDEN_JSON
    assert snapshot.content_hash() == _REVISION_V2_GOLDEN_HASH

    document = json.loads(_REVISION_V2_GOLDEN_JSON)
    assert document["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert document["payment_terms"]["schema_version"] == (  # type: ignore[index]
        "contract-payment-terms/v1"
    )
    rebuilt = UpstreamContractEconomicSnapshot.from_canonical_document(document)
    assert rebuilt.canonical_json() == _REVISION_V2_GOLDEN_JSON
    assert rebuilt.content_hash() == _REVISION_V2_GOLDEN_HASH


def test_v2_with_declared_terms_roundtrips_byte_identically() -> None:
    terms = _v2_terms()
    # Exact precision and recorded order survive the nested v2 document.
    precise = Decimal("29.75000000000000000000000000000000000001")
    snapshot = _snapshot(
        contract_price_gbp_mwh=precise,
        schema_version=CONTRACT_REVISION_SCHEMA_VERSION_V2,
        payment_terms=terms,
    )

    document = snapshot.canonical_document()
    assert document["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert document["payment_terms"] == terms.canonical_document()
    assert document["contract_price_gbp_mwh"] == (
        "29.75000000000000000000000000000000000001"
    )
    assert document["eligible_sale_modes"] == [
        "TARGET_MARKET_SALE",
        "LOCAL_MARKET_SALE",
    ]

    parsed = json.loads(snapshot.canonical_json())
    rebuilt = UpstreamContractEconomicSnapshot.from_canonical_document(parsed)
    assert rebuilt == snapshot
    assert rebuilt.payment_terms == terms
    assert rebuilt.canonical_json() == snapshot.canonical_json()
    assert rebuilt.content_hash() == snapshot.content_hash()

    # Key order never matters, including inside the nested terms document.
    from_shuffled = UpstreamContractEconomicSnapshot.from_canonical_document(
        _nested_reversed_keys(parsed)  # type: ignore[arg-type]
    )
    assert from_shuffled.canonical_json() == snapshot.canonical_json()
    assert from_shuffled.content_hash() == snapshot.content_hash()


def test_v2_null_terms_roundtrip_and_hash_separates_version_and_terms() -> None:
    v1 = _snapshot()
    v2_null = _v2_snapshot()
    v2_terms = _v2_snapshot(_v2_terms())

    assert v2_null.canonical_document()["payment_terms"] is None
    rebuilt = UpstreamContractEconomicSnapshot.from_canonical_document(
        json.loads(v2_null.canonical_json())
    )
    assert rebuilt == v2_null
    assert rebuilt.canonical_json() == v2_null.canonical_json()
    assert rebuilt.content_hash() == v2_null.content_hash()

    # The schema version is part of the hash, and null is not "the same as"
    # declared terms: three distinct snapshots, three distinct hashes.
    hashes = {v1.content_hash(), v2_null.content_hash(), v2_terms.content_hash()}
    assert len(hashes) == 3


def test_v1_refuses_terms_and_v2_refuses_untyped_terms_without_echoing() -> None:
    terms = _v2_terms()

    # v1 (also the default) refuses non-null terms; the caller must ask for v2.
    with pytest.raises(ContractRevisionPayloadError) as via_v1:
        _snapshot(payment_terms=terms)
    assert via_v1.value.code == "payment_terms_present"

    # A raw mapping is never accepted as declared terms, in either version.
    for schema_version in (CONTRACT_REVISION_SCHEMA_VERSION, CONTRACT_REVISION_SCHEMA_VERSION_V2):
        with pytest.raises(ContractRevisionPayloadError) as raw_mapping:
            _snapshot(
                schema_version=schema_version,
                payment_terms={"quantity_basis_reference": _SENTINEL, "items": []},
            )
        expected = (
            "payment_terms_present"
            if schema_version == CONTRACT_REVISION_SCHEMA_VERSION
            else "payment_terms_not_typed"
        )
        assert raw_mapping.value.code == expected
        assert _SENTINEL not in str(raw_mapping.value)


def test_v2_canonical_decode_fails_closed_on_invalid_terms() -> None:
    document = _v2_snapshot().canonical_document()

    invalid_values: list[object] = [
        [],  # a list is never a terms document
        "contract-payment-terms/v1",  # a bare version string is not a document
        {},  # empty field set
        {"schema_version": _SENTINEL},  # untrusted version value
    ]
    nested = _v2_terms().canonical_document()
    nested["unexpected"] = _SENTINEL
    invalid_values.append(nested)

    for invalid in invalid_values:
        with pytest.raises(ContractRevisionPayloadError) as excinfo:
            UpstreamContractEconomicSnapshot.from_canonical_document(
                {**document, "payment_terms": invalid}
            )
        assert excinfo.value.code == "canonical_payment_terms_invalid"
        assert _SENTINEL not in str(excinfo.value)


def test_every_version_requires_the_payment_terms_field() -> None:
    """A missing field is a field-set violation, never parent inheritance."""

    for snapshot in (_mapped_snapshot(_legacy_payload()), _v2_snapshot()):
        document = snapshot.canonical_document()
        without_terms = {
            key: value for key, value in document.items() if key != "payment_terms"
        }
        with pytest.raises(ContractRevisionPayloadError) as excinfo:
            UpstreamContractEconomicSnapshot.from_canonical_document(without_terms)
        assert excinfo.value.code == "canonical_field_set_mismatch"
        assert "payment_terms" in excinfo.value.detail


def test_unknown_versions_fail_closed_without_echoing_untrusted_content() -> None:
    with pytest.raises(ContractRevisionPayloadError) as construction:
        _snapshot(schema_version=_SENTINEL)
    assert construction.value.code == "schema_version_unknown"
    assert _SENTINEL not in str(construction.value)

    v1_document = _mapped_snapshot(_legacy_payload()).canonical_document()
    with pytest.raises(ContractRevisionPayloadError) as decode:
        UpstreamContractEconomicSnapshot.from_canonical_document(
            {**v1_document, "schema_version": _SENTINEL}
        )
    assert decode.value.code == "canonical_schema_version_unknown"
    assert _SENTINEL not in str(decode.value)


def test_v2_terms_stay_immutable_and_documents_are_fresh_copies() -> None:
    terms = _v2_terms()
    snapshot = _v2_snapshot(terms)

    with pytest.raises(FrozenInstanceError):
        snapshot.payment_terms = None  # type: ignore[assignment]

    document = snapshot.canonical_document()
    document["payment_terms"]["items"].append({"item_id": "forged"})  # type: ignore[index,union-attr]
    document["payment_terms"]["items"][0]["item_id"] = "rewritten"  # type: ignore[index,union-attr]
    assert snapshot.canonical_document()["payment_terms"] == terms.canonical_document()


def test_with_declared_payment_terms_reencodes_mapped_economics_as_v2() -> None:
    """S2b's only conversion: unchanged mapped economics plus declared terms."""

    mapped = _mapped_snapshot(_legacy_payload())
    terms = _v2_terms()
    converted = contract_revision.with_declared_payment_terms(mapped, terms)

    # A new immutable value; the mapped v1 snapshot is untouched.
    assert converted is not mapped
    assert mapped.schema_version == CONTRACT_REVISION_SCHEMA_VERSION
    assert mapped.payment_terms is None
    assert converted.schema_version == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert converted.payment_terms == terms

    # Every economic field, the precision label and the mapping issues survive.
    original_document = mapped.canonical_document()
    converted_document = converted.canonical_document()
    for key, value in original_document.items():
        if key in {"schema_version", "payment_terms"}:
            continue
        assert converted_document[key] == value, key
    assert converted_document["payment_terms"] == terms.canonical_document()

    # The v2 bytes decode back to the identical declaration and hash.
    rebuilt = UpstreamContractEconomicSnapshot.from_canonical_document(
        converted_document
    )
    assert rebuilt.canonical_json() == converted.canonical_json()
    assert rebuilt.content_hash() == converted.content_hash()
    assert converted.content_hash() not in {
        mapped.content_hash(),
        _v2_snapshot().content_hash(),
    }


def test_with_declared_payment_terms_refuses_untyped_terms_without_echoing() -> None:
    mapped = _mapped_snapshot(_legacy_payload())
    raw_document = {**_v2_terms().canonical_document(), "note": _SENTINEL}

    with pytest.raises(ContractRevisionPayloadError) as refused:
        contract_revision.with_declared_payment_terms(mapped, raw_document)  # type: ignore[arg-type]

    assert refused.value.code == "payment_terms_not_typed"
    assert _SENTINEL not in str(refused.value)
