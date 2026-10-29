"""Focused RFC0005 native payload projection tests; no DB or network."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from eurogas_nexus.application.physical_native_rates import (
    NATIVE_RATE_JSON_KEYS,
    NativeRateProjectionError,
    project_native_rate_row,
    row_volume_admissible,
    serialize_native_rate,
    validate_native_rate_payload,
)
from eurogas_nexus.ingestion.entsog_native_units import (
    NORMALIZER_VERSION,
    EntsogNativeRate,
    parse_entsog_native_rate,
)

_AUTO = object()


def _payload(value_text: str, unit_text: str) -> dict[str, str | None]:
    return serialize_native_rate(parse_entsog_native_rate(value_text, unit_text))


def _lineage(receipt: str = "2026-06-01T12:00:00+00:00") -> dict[str, str]:
    return {
        "raw_archive_id": "raw-0123456789abcdef",
        "archive_id": "raw-0123456789abcdef",
        "payload_sha256": "a" * 64,
        "source_receipt_at_utc": receipt,
    }


def _row(
    *,
    volume_field: str = "flow_mcm_d",
    volume: object = 1.5,
    quantity_kind: str = "volume",
    native_payload: object = _AUTO,
    normalizer_version: object = _AUTO,
    metadata: dict[str, object] | None = None,
    start: object = None,
    end: object = None,
    observed: object = None,
) -> SimpleNamespace:
    payload = native_payload
    if payload is _AUTO:
        if quantity_kind == "volume":
            payload = _payload("1.5", "mcm/d")
        elif quantity_kind == "energy":
            payload = _payload("1000", "kWh/d")
        else:
            payload = None
    version = normalizer_version
    if version is _AUTO:
        version = NORMALIZER_VERSION if payload is not None else None

    row_metadata: dict[str, object] = {}
    if metadata:
        row_metadata.update(metadata)
    values = {
        "observation_id": "entsog-flow-1",
        "source_record_id": "provider-record-1",
        "point_id": "point-1",
        "point_name": "Point One",
        "direction": "entry",
        "source_system": "ENTSOG",
        "source_reference": "entsog-operationaldatas;offset=0;limit=1",
        "freshness": "live",
        "research_only": True,
        "period_start_utc": start
        if start is not None
        else datetime(2026, 6, 1, tzinfo=UTC),
        "period_end_utc": end
        if end is not None
        else datetime(2026, 6, 2, tzinfo=UTC),
        "observed_at_utc": observed
        if observed is not None
        else datetime(2026, 6, 1, 12, tzinfo=UTC),
        "metadata_json": row_metadata,
        "normalizer_version": version,
        "native_rate_json": payload,
        volume_field: volume,
    }
    if volume_field == "flow_mcm_d":
        values["kind"] = "actual"
    else:
        values["capacity_type"] = "firm_technical"
    return SimpleNamespace(**values)


def _assert_refused(callable_, code: str) -> NativeRateProjectionError:
    with pytest.raises(NativeRateProjectionError) as caught:
        callable_()
    assert caught.value.code == code
    assert isinstance(caught.value, ValueError)
    return caught.value


def test_serialize_uses_exact_keys_and_exact_decimal_strings() -> None:
    rate = parse_entsog_native_rate(
        "1234567890123456789012345678.12345678901234567890",
        "MWh/d",
    )
    payload = serialize_native_rate(rate)

    assert tuple(payload) == NATIVE_RATE_JSON_KEYS
    assert payload["value_text"] == rate.value_text
    assert payload["unit_text"] == rate.unit_text
    assert payload["native_value"] == "1234567890123456789012345678.12345678901234567890"
    assert payload["native_value"] == str(rate.native_value)
    assert payload["energy_kwh_per_day"] == str(rate.energy_kwh_per_day)
    assert payload["volume_mcm_per_day"] is None
    assert payload["quantity_kind"] == "energy"
    assert payload["rate_basis"] == "day"
    assert payload["normalizer_version"] == NORMALIZER_VERSION
    assert all(
        isinstance(payload[key], str)
        for key in ("native_value", "energy_kwh_per_day")
    )


def test_zero_and_negative_zero_survive_serialization() -> None:
    positive_rate = parse_entsog_native_rate("0.0000", "kWh/day")
    negative_rate = parse_entsog_native_rate("-0.000", "m3/d")
    positive = serialize_native_rate(positive_rate)
    negative = serialize_native_rate(negative_rate)

    assert positive["native_value"] == "0.0000"
    assert positive["energy_kwh_per_day"] == "0.0000"
    assert positive["volume_mcm_per_day"] is None
    assert negative["native_value"] == "-0.000"
    assert negative["volume_mcm_per_day"] == str(negative_rate.volume_mcm_per_day)
    assert negative["energy_kwh_per_day"] is None


def test_round_trip_validation_returns_the_recomputed_record() -> None:
    payload = _payload("1.5", "mcm/h")
    rate = validate_native_rate_payload(payload, NORMALIZER_VERSION)

    assert rate.quantity_kind == "volume"
    assert rate.rate_basis == "hour"
    assert rate.volume_mcm_per_day is not None
    assert serialize_native_rate(rate) == payload


@pytest.mark.parametrize(
    ("key", "forged"),
    [
        ("native_value", "1.6"),
        ("energy_kwh_per_day", "1.5"),
        ("volume_mcm_per_day", "1.50"),
        ("normalized_unit", "mcm/day"),
        ("quantity_kind", "energy"),
        ("rate_basis", "day"),
        ("value_text", "2.0"),
        ("unit_text", "m3/d"),
    ],
)
def test_validate_refuses_every_forged_field(key: str, forged: object) -> None:
    payload = _payload("1.5", "mcm/h")
    payload[key] = forged

    _assert_refused(
        lambda: validate_native_rate_payload(payload, NORMALIZER_VERSION),
        "invalid_native_rate_payload",
    )


def test_validate_refuses_forged_dimension_even_with_canonical_none() -> None:
    payload = _payload("1.5", "mcm/h")
    payload["native_value"] = "2.5"

    _assert_refused(
        lambda: validate_native_rate_payload(payload, NORMALIZER_VERSION),
        "invalid_native_rate_payload",
    )


@pytest.mark.parametrize("forged", [1.5, 1, True, None])
def test_decimal_fields_must_be_strings_not_numbers_or_none(forged: object) -> None:
    payload = _payload("1.5", "mcm/h")
    payload["native_value"] = forged

    _assert_refused(
        lambda: validate_native_rate_payload(payload, NORMALIZER_VERSION),
        "invalid_native_rate_payload",
    )


def test_applicable_canonical_quantity_must_not_be_none() -> None:
    payload = _payload("1.5", "mcm/h")
    payload["volume_mcm_per_day"] = None

    _assert_refused(
        lambda: validate_native_rate_payload(payload, NORMALIZER_VERSION),
        "invalid_native_rate_payload",
    )


def test_nonapplicable_canonical_quantity_must_be_none_not_a_number() -> None:
    payload = _payload("1000", "kWh/d")
    payload["volume_mcm_per_day"] = "0"

    _assert_refused(
        lambda: validate_native_rate_payload(payload, NORMALIZER_VERSION),
        "invalid_native_rate_payload",
    )


def test_validate_refuses_missing_extra_and_unknown_version_keys() -> None:
    payload = _payload("1.5", "mcm/h")
    missing = dict(payload)
    del missing["rate_basis"]
    extra = {**payload, "legacy_volume": "1.5"}

    _assert_refused(
        lambda: validate_native_rate_payload(missing, NORMALIZER_VERSION),
        "invalid_native_rate_payload",
    )
    _assert_refused(
        lambda: validate_native_rate_payload(extra, NORMALIZER_VERSION),
        "invalid_native_rate_payload",
    )
    _assert_refused(
        lambda: validate_native_rate_payload(payload, "entsog-native-units-v2"),
        "unsupported_normalizer_version",
    )


def test_forged_payload_version_is_an_unsupported_version_refusal() -> None:
    payload = _payload("1.5", "mcm/h")
    payload["normalizer_version"] = "entsog-native-units-v2"

    _assert_refused(
        lambda: validate_native_rate_payload(payload, NORMALIZER_VERSION),
        "unsupported_normalizer_version",
    )


def test_validation_error_does_not_echo_the_payload() -> None:
    payload = _payload("1.5", "mcm/h")
    payload["value_text"] = "secret-forged-value"
    error = _assert_refused(
        lambda: validate_native_rate_payload(payload, NORMALIZER_VERSION),
        "invalid_native_rate_source",
    )

    assert "secret-forged-value" not in str(error)
    assert payload["value_text"] not in error.message


def test_serialize_recomputes_a_manually_constructed_frozen_dataclass() -> None:
    forged = EntsogNativeRate(
        value_text="1.5",
        unit_text="mcm/h",
        native_value=Decimal("2.5"),
        normalized_unit="mcm/hour",
        quantity_kind="volume",
        rate_basis="hour",
        energy_kwh_per_day=None,
        volume_mcm_per_day=Decimal("36"),
    )

    _assert_refused(
        lambda: serialize_native_rate(forged),
        "invalid_native_rate_payload",
    )


def test_serialize_revalidates_forged_frozen_dataclass_fields() -> None:
    rate = parse_entsog_native_rate("1.5", "mcm/h")

    forged_canonical = replace(rate, volume_mcm_per_day=Decimal("99"))
    _assert_refused(
        lambda: serialize_native_rate(forged_canonical),
        "invalid_native_rate_payload",
    )

    forged_spelling = replace(rate, native_value=Decimal("1.5000"))
    _assert_refused(
        lambda: serialize_native_rate(forged_spelling),
        "invalid_native_rate_payload",
    )

    forged_source = replace(rate, value_text="2.0")
    _assert_refused(
        lambda: serialize_native_rate(forged_source),
        "invalid_native_rate_payload",
    )

    forged_version = replace(rate)
    object.__setattr__(forged_version, "normalizer_version", "entsog-native-units-v2")
    _assert_refused(
        lambda: serialize_native_rate(forged_version),
        "unsupported_normalizer_version",
    )


def test_entsog_legacy_null_columns_ignore_metadata_payload() -> None:
    fallback = _payload("1.5", "mcm/d")
    row = _row(
        volume=123.0,
        native_payload=None,
        metadata={"native_rate_json": fallback},
    )

    assert row_volume_admissible(row, volume_field="flow_mcm_d") is False
    _assert_refused(
        lambda: project_native_rate_row(row, volume_field="flow_mcm_d"),
        "native_rate_missing",
    )


def test_metadata_native_payload_is_not_consulted_for_a_valid_row() -> None:
    row = _row(
        volume=1.5,
        metadata={"native_rate_json": _payload("999", "mcm/d")},
    )

    assert row_volume_admissible(row, volume_field="flow_mcm_d") is True
    projected = project_native_rate_row(row, volume_field="flow_mcm_d")
    assert projected["native_rate_json"] == _payload("1.5", "mcm/d")


def test_entsog_native_volume_must_match_the_stored_float_exactly() -> None:
    assert row_volume_admissible(_row(volume=1.5), volume_field="flow_mcm_d") is True
    assert (
        row_volume_admissible(_row(volume=1.5000000001), volume_field="flow_mcm_d")
        is False
    )
    assert row_volume_admissible(_row(volume=0.0), volume_field="flow_mcm_d") is False


def test_entsog_native_zero_volume_matches_a_stored_zero_float() -> None:
    row = _row(volume=0.0, native_payload=_payload("0.0000", "mcm/d"))

    assert row_volume_admissible(row, volume_field="flow_mcm_d") is True


def test_entsog_native_energy_is_never_volume_even_with_bogus_legacy_value() -> None:
    row = _row(volume=999.0, quantity_kind="energy")

    assert row_volume_admissible(row, volume_field="flow_mcm_d") is False


def test_non_entsog_legacy_volume_requires_a_finite_number() -> None:
    row = _row(volume=12.5, native_payload=None)
    row.source_system = "GIE"

    assert row_volume_admissible(row, volume_field="flow_mcm_d") is True
    for value in (float("nan"), float("inf"), None, True, "12.5"):
        row.flow_mcm_d = value
        assert row_volume_admissible(row, volume_field="flow_mcm_d") is False


def test_entsog_source_comparison_is_case_insensitive() -> None:
    legacy = _row(volume=123.0, native_payload=None)
    legacy.source_system = "entsog"

    assert row_volume_admissible(legacy, volume_field="flow_mcm_d") is False
    _assert_refused(
        lambda: project_native_rate_row(legacy, volume_field="flow_mcm_d"),
        "native_rate_missing",
    )

    native = _row(volume=1.5)
    native.source_system = "eNtSoG"
    assert row_volume_admissible(native, volume_field="flow_mcm_d") is True


def test_row_version_unknown_and_column_payload_mismatch_are_refused() -> None:
    unknown_row = _row(volume=1.5)
    unknown_row.normalizer_version = "unknown-v9"
    _assert_refused(
        lambda: row_volume_admissible(unknown_row, volume_field="flow_mcm_d"),
        "unsupported_normalizer_version",
    )
    _assert_refused(
        lambda: project_native_rate_row(unknown_row, volume_field="flow_mcm_d"),
        "unsupported_normalizer_version",
    )

    mismatched_row = _row(volume=1.5)
    mismatched_row.normalizer_version = "entsog-native-units-v2"
    _assert_refused(
        lambda: row_volume_admissible(mismatched_row, volume_field="flow_mcm_d"),
        "unsupported_normalizer_version",
    )

    payload_mismatch = _row(volume=1.5)
    payload_mismatch.native_rate_json = {
        **payload_mismatch.native_rate_json,
        "normalizer_version": "entsog-native-units-v2",
    }
    _assert_refused(
        lambda: row_volume_admissible(payload_mismatch, volume_field="flow_mcm_d"),
        "unsupported_normalizer_version",
    )
    _assert_refused(
        lambda: project_native_rate_row(payload_mismatch, volume_field="flow_mcm_d"),
        "unsupported_normalizer_version",
    )


def test_partial_native_column_pair_is_a_typed_refusal() -> None:
    for payload, version in (
        (None, NORMALIZER_VERSION),
        (_payload("1.5", "mcm/d"), None),
    ):
        row = _row(native_payload=payload, normalizer_version=version)
        _assert_refused(
            lambda row=row: row_volume_admissible(
                row, volume_field="flow_mcm_d"
            ),
            "native_rate_incomplete",
        )
        _assert_refused(
            lambda row=row: project_native_rate_row(
                row, volume_field="flow_mcm_d"
            ),
            "native_rate_incomplete",
        )


def test_tampered_native_column_payload_is_a_typed_refusal() -> None:
    row = _row(volume=1.5)
    row.native_rate_json = {
        **row.native_rate_json,
        "volume_mcm_per_day": "99",
    }
    _assert_refused(
        lambda: row_volume_admissible(row, volume_field="flow_mcm_d"),
        "invalid_native_rate_payload",
    )
    _assert_refused(
        lambda: project_native_rate_row(row, volume_field="flow_mcm_d"),
        "invalid_native_rate_payload",
    )


def test_capacity_volume_field_is_explicit_and_required() -> None:
    row = _row(volume_field="capacity_mcm_d", volume=1.5)

    assert row_volume_admissible(row, volume_field="capacity_mcm_d") is True
    _assert_refused(
        lambda: row_volume_admissible(row, volume_field="capacity"),
        "unsupported_volume_field",
    )


def test_project_volume_row_preserves_identities_times_and_lineage() -> None:
    row = _row(volume=1.5, metadata=_lineage())
    projected = project_native_rate_row(row, volume_field="flow_mcm_d")

    assert projected["observation_id"] == "entsog-flow-1"
    assert projected["source_record_id"] == "provider-record-1"
    assert projected["point_id"] == "point-1"
    assert projected["point_name"] == "Point One"
    assert projected["direction"] == "entry"
    assert projected["kind"] == "actual"
    assert projected["source_system"] == "ENTSOG"
    assert projected["source_reference"] == "entsog-operationaldatas;offset=0;limit=1"
    assert projected["research_only"] is True
    assert projected["quantity_basis"] == "native"
    assert projected["normalizer_version"] == NORMALIZER_VERSION
    assert projected["period_start_utc"] == "2026-06-01T00:00:00+00:00"
    assert projected["period_end_utc"] == "2026-06-02T00:00:00+00:00"
    assert projected["observed_at_utc"] == "2026-06-01T12:00:00+00:00"
    assert projected["raw_archive_id"] == "raw-0123456789abcdef"
    assert projected["payload_sha256"] == "a" * 64
    assert projected["received_at_utc"] == "2026-06-01T12:00:00+00:00"
    assert projected["native_rate_json"] == _payload("1.5", "mcm/d")
    assert "flow_mcm_d" not in projected


def test_project_energy_row_keeps_native_volume_none_and_no_legacy_volume() -> None:
    row = _row(volume=123456.0, quantity_kind="energy", metadata=_lineage())
    projected = project_native_rate_row(row, volume_field="flow_mcm_d")

    native = projected["native_rate_json"]
    assert native["quantity_kind"] == "energy"
    assert native["energy_kwh_per_day"] == "1000"
    assert native["volume_mcm_per_day"] is None
    assert "flow_mcm_d" not in projected


def test_project_capacity_row_reports_capacity_type() -> None:
    row = _row(volume_field="capacity_mcm_d", volume=1.5, metadata=_lineage())
    projected = project_native_rate_row(row, volume_field="capacity_mcm_d")

    assert projected["capacity_type"] == "firm_technical"
    assert "kind" not in projected


def test_project_refuses_non_entsog_and_legacy_entsog_rows() -> None:
    non_entsog = _row(volume=1.5, metadata=_lineage())
    non_entsog.source_system = "GIE"
    _assert_refused(
        lambda: project_native_rate_row(non_entsog, volume_field="flow_mcm_d"),
        "native_rate_source_unsupported",
    )

    legacy = _row(volume=1.5, native_payload=None, metadata=_lineage())
    _assert_refused(
        lambda: project_native_rate_row(legacy, volume_field="flow_mcm_d"),
        "native_rate_missing",
    )


def test_project_refuses_a_volume_mismatch_and_tampering() -> None:
    row = _row(volume=1.5001, metadata=_lineage())
    _assert_refused(
        lambda: project_native_rate_row(row, volume_field="flow_mcm_d"),
        "native_rate_volume_mismatch",
    )

    tampered = _row(volume=1.5, metadata=_lineage())
    tampered.native_rate_json["energy_kwh_per_day"] = "1"
    _assert_refused(
        lambda: project_native_rate_row(tampered, volume_field="flow_mcm_d"),
        "invalid_native_rate_payload",
    )


def test_project_refuses_missing_period_timestamps() -> None:
    missing_start = _row(metadata=_lineage())
    missing_start.period_start_utc = None
    _assert_refused(
        lambda: project_native_rate_row(missing_start, volume_field="flow_mcm_d"),
        "native_rate_period_missing",
    )

    missing_end = _row(metadata=_lineage())
    missing_end.period_end_utc = None
    _assert_refused(
        lambda: project_native_rate_row(missing_end, volume_field="flow_mcm_d"),
        "native_rate_period_missing",
    )


def test_project_refuses_non_increasing_periods() -> None:
    equal = _row(metadata=_lineage())
    equal.period_end_utc = equal.period_start_utc
    _assert_refused(
        lambda: project_native_rate_row(equal, volume_field="flow_mcm_d"),
        "native_rate_period_invalid",
    )

    reversed_period = _row(metadata=_lineage())
    reversed_period.period_end_utc = datetime(2026, 5, 31, tzinfo=UTC)
    _assert_refused(
        lambda: project_native_rate_row(reversed_period, volume_field="flow_mcm_d"),
        "native_rate_period_invalid",
    )


def test_generic_utc_labels_and_boolean_flags_do_not_authorize_naive_periods() -> None:
    metadata = {
        **_lineage(),
        "timezone": "UTC",
        "time_basis": "UTC",
        "sqlite_naive_utc": True,
        "naive_times_are_utc": True,
    }
    row = _row(metadata=metadata)
    row.period_start_utc = datetime(2026, 6, 1)
    row.period_end_utc = datetime(2026, 6, 2)

    _assert_refused(
        lambda: project_native_rate_row(row, volume_field="flow_mcm_d"),
        "native_rate_naive_datetime",
    )


def test_generic_utc_labels_and_boolean_flags_do_not_authorize_naive_observed() -> None:
    row = _row(metadata={"timezone": "UTC", "sqlite_naive_utc": True})
    row.observed_at_utc = datetime(2026, 6, 1, 12)

    _assert_refused(
        lambda: project_native_rate_row(row, volume_field="flow_mcm_d"),
        "native_rate_naive_datetime",
    )


def test_naive_periods_require_matching_aware_normalized_edges() -> None:
    row = _row(
        metadata={
            **_lineage(),
            "normalized_period_start_utc": "2026-06-01T00:00:00+00:00",
            "normalized_period_end_utc": "2026-06-02T00:00:00+00:00",
        }
    )
    row.period_start_utc = datetime(2026, 6, 1)
    row.period_end_utc = datetime(2026, 6, 2)

    projected = project_native_rate_row(row, volume_field="flow_mcm_d")
    assert projected["period_start_utc"] == "2026-06-01T00:00:00+00:00"
    assert projected["period_end_utc"] == "2026-06-02T00:00:00+00:00"


def test_naive_periods_refuse_wrong_or_naive_normalized_edges() -> None:
    wrong_instant = _row(
        metadata={
            **_lineage(),
            "normalized_period_start_utc": "2026-06-01T00:00:01+00:00",
        }
    )
    wrong_instant.period_start_utc = datetime(2026, 6, 1)
    _assert_refused(
        lambda: project_native_rate_row(wrong_instant, volume_field="flow_mcm_d"),
        "native_rate_naive_datetime",
    )

    naive_evidence = _row(
        metadata={
            **_lineage(),
            "normalized_period_start_utc": "2026-06-01T00:00:00",
        }
    )
    naive_evidence.period_start_utc = datetime(2026, 6, 1)
    _assert_refused(
        lambda: project_native_rate_row(naive_evidence, volume_field="flow_mcm_d"),
        "native_rate_naive_datetime",
    )

    wrong_edge = _row(
        metadata={
            **_lineage(),
            "normalized_period_end_utc": "2026-06-02T00:00:00+00:00",
        }
    )
    wrong_edge.period_start_utc = datetime(2026, 6, 1)
    wrong_edge.period_end_utc = datetime(2026, 6, 2)
    _assert_refused(
        lambda: project_native_rate_row(wrong_edge, volume_field="flow_mcm_d"),
        "native_rate_naive_datetime",
    )


def test_naive_observed_requires_matching_aware_receipt() -> None:
    receipt_evidence = _row(metadata=_lineage("2026-06-01T12:00:00+00:00"))
    receipt_evidence.observed_at_utc = datetime(2026, 6, 1, 12)
    projected = project_native_rate_row(receipt_evidence, volume_field="flow_mcm_d")
    assert projected["observed_at_utc"] == "2026-06-01T12:00:00+00:00"

    received_evidence = _row(
        metadata={"received_at_utc": "2026-06-01T12:00:00+00:00"}
    )
    received_evidence.observed_at_utc = datetime(2026, 6, 1, 12)
    projected = project_native_rate_row(received_evidence, volume_field="flow_mcm_d")
    assert projected["observed_at_utc"] == "2026-06-01T12:00:00+00:00"

    row_evidence = _row(metadata={})
    row_evidence.received_at_utc = datetime(2026, 6, 1, 12, tzinfo=UTC)
    row_evidence.observed_at_utc = datetime(2026, 6, 1, 12)
    projected = project_native_rate_row(row_evidence, volume_field="flow_mcm_d")
    assert projected["observed_at_utc"] == "2026-06-01T12:00:00+00:00"

    mismatched = _row(metadata=_lineage("2026-06-01T12:00:01+00:00"))
    mismatched.observed_at_utc = datetime(2026, 6, 1, 12)
    _assert_refused(
        lambda: project_native_rate_row(mismatched, volume_field="flow_mcm_d"),
        "native_rate_naive_datetime",
    )


def test_naive_receipts_need_an_aware_receipt_crosscheck() -> None:
    cross_checked = _row(
        metadata={
            "received_at_utc": "2026-06-01T12:00:00+00:00",
            "source_receipt_at_utc": "2026-06-01T12:00:00",
        }
    )
    projected = project_native_rate_row(cross_checked, volume_field="flow_mcm_d")
    assert projected["received_at_utc"] == "2026-06-01T12:00:00+00:00"

    all_naive = _row(
        metadata={
            "received_at_utc": "2026-06-01T12:00:00",
            "source_receipt_at_utc": "2026-06-01T12:00:00",
        }
    )
    _assert_refused(
        lambda: project_native_rate_row(all_naive, volume_field="flow_mcm_d"),
        "native_rate_naive_datetime",
    )


def test_project_preserves_aware_offsets_and_does_not_invent_observed_time() -> None:
    row = _row(
        metadata={},
        start=datetime(2026, 6, 1, 2, tzinfo=timezone(timedelta(hours=2))),
        end=datetime(2026, 6, 2, 2, tzinfo=timezone(timedelta(hours=2))),
    )
    row.observed_at_utc = None

    projected = project_native_rate_row(row, volume_field="flow_mcm_d")
    assert projected["period_start_utc"] == "2026-06-01T00:00:00+00:00"
    assert projected["period_end_utc"] == "2026-06-02T00:00:00+00:00"
    assert projected["observed_at_utc"] is None
    assert projected["received_at_utc"] is None


def test_project_does_not_mutate_the_input_row_or_legacy_volume() -> None:
    row = _row(volume=1.5, metadata=_lineage())
    original_metadata = row.metadata_json
    original_payload = row.native_rate_json
    original_volume = row.flow_mcm_d

    projected = project_native_rate_row(row, volume_field="flow_mcm_d")

    assert row.flow_mcm_d == original_volume == 1.5
    assert row.metadata_json is original_metadata
    assert row.native_rate_json is original_payload
    assert projected["native_rate_json"] == original_payload
