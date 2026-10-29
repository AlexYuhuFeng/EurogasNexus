"""Pure point-in-time demand-target mapping tests.

Every row here is a synthetic source revision used only to exercise mapping and
refusal semantics. No test fits a demand model, claims accuracy, opens a database
or activates a source.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from eurogas_nexus.application.research.demand_target_inputs import (
    DemandTargetAmbiguityError,
    DemandTargetDiagnosticCode,
    DemandTargetDuplicateConflict,
    DemandTargetInputValidationError,
    build_demand_target_rows,
)
from eurogas_nexus.domain.ontology.vocabulary import DemandTargetQuality, TargetScope
from eurogas_nexus.domain.research.weather_demand import _resolve_targets

GAS_DAY = date(2026, 10, 21)
RECEIVED = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def record(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "record_id": "rec-1",
        "source_publication_id": "pub-1",
        "provider_item_id": "PUBOB637",
        "series_key": "national-gas:actual:GB_NTS:D+1:CSV",
        "region": "GB_NTS",
        "term": "D+1",
        "label": "Demand Actual, NTS, D+1",
        "gas_day": GAS_DAY,
        "period_start_utc": datetime(2026, 10, 21, 5, 0, tzinfo=UTC),
        "period_end_utc": datetime(2026, 10, 22, 5, 0, tzinfo=UTC),
        "value_text": "176.708",
        "unit": "mscm",
        "received_at_utc": RECEIVED,
        "available_at_utc": RECEIVED,
        "ingested_at_utc": RECEIVED,
        "published_at_utc": None,
        "applicable_at_raw": "21/10/2026",
        "generated_at_raw": "22/10/2026 12:20:01",
        "applicable_at_naive": datetime(2026, 10, 21, 5, 0),
        "generated_at_naive": datetime(2026, 10, 22, 12, 20, 1),
        "quality_indicator": None,
        "provisional_status": "PROVISIONAL_INITIAL",
        "is_provisional": True,
        "raw_sha256": "a" * 64,
        "source_url": "https://example.test/national-gas",
        "hash_schema": "national_gas_actual_demand.v1",
        "value_is_blank": False,
        "source_format": "CSV",
        "rest_provenance": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def build(records, **overrides: object):
    arguments: dict[str, object] = {
        "provider_item_id": "PUBOB637",
        "source_format": "CSV",
        "gas_day_from": date(2026, 10, 1),
        "gas_day_to": date(2026, 10, 31),
        "available_at_utc": CUTOFF,
        "allow_provisional_targets": True,
    }
    arguments.update(overrides)
    return build_demand_target_rows(records, **arguments)


def test_d1_provisional_maps_only_with_explicit_permission_and_full_provenance():
    source = record()
    result = build([source])

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.gas_day == GAS_DAY
    assert row.scope is TargetScope.GB_NTS_THROUGHPUT
    assert row.region == "GB_NTS"
    assert row.unit == "MSCM"
    assert row.value == 176.708
    assert row.quality is DemandTargetQuality.PROVISIONAL
    assert row.revision == 1
    assert row.revision_id == "rec-1"
    assert row.available_at == RECEIVED
    assert row.source_ref == "NATIONAL_GAS:CSV:pub-1"

    provenance = result.provenance_by_record_id["rec-1"]
    assert provenance.source_publication_id == "pub-1"
    assert provenance.value_text == "176.708"
    assert provenance.value_decimal == Decimal("176.708")
    assert provenance.quality_indicator is None
    assert provenance.provisional_status == "PROVISIONAL_INITIAL"
    assert provenance.is_provisional is True
    assert provenance.raw_sha256 == "a" * 64
    assert provenance.derived_revision == 1
    assert provenance.revision_order_basis == "DERIVED_RECEIPT_ORDER"
    assert provenance.selected is True
    assert result.native_unit == "MSCM"
    assert result.scope is TargetScope.GB_NTS_THROUGHPUT
    assert result.diagnostics == ()


def test_provisional_target_requires_explicit_caller_permission():
    result = build([record()], allow_provisional_targets=False)

    assert result.rows == ()
    assert [item.code for item in result.diagnostics] == [
        DemandTargetDiagnosticCode.PROVISIONAL_TARGET_NOT_ALLOWED
    ]


def test_blank_is_missing_not_zero_and_exact_zero_is_legitimate():
    blank = build([record(record_id="blank", value_text="", value_is_blank=True)])
    assert blank.rows == ()
    assert blank.diagnostics[0].code is DemandTargetDiagnosticCode.BLANK_VALUE

    zero = build([record(record_id="zero", value_text="0.000")])
    assert len(zero.rows) == 1
    assert zero.rows[0].value == 0.0
    assert zero.provenance_by_record_id["zero"].value_decimal == Decimal("0.000")
    assert zero.provenance_by_record_id["zero"].value_text == "0.000"


def test_quality_a_is_amended_and_is_never_relabelled_actual():
    result = build([record(quality_indicator="A")])

    assert result.rows == ()
    assert [item.code for item in result.diagnostics] == [
        DemandTargetDiagnosticCode.SOURCE_QUALITY_AMENDED
    ]
    assert "AMENDED" in result.diagnostics[0].detail
    assert not result.provenance_by_record_id


def test_d6_unresolved_provisionality_is_refused_not_forced_to_actual_or_estimated():
    result = build(
        [
            record(
                provider_item_id="PUBOB652",
                term="D+6",
                is_provisional=None,
                provisional_status="UNRESOLVED_D_PLUS_6",
            )
        ],
        provider_item_id="PUBOB652",
    )

    assert result.rows == ()
    assert [item.code for item in result.diagnostics] == [
        DemandTargetDiagnosticCode.UNRESOLVED_TARGET_QUALITY
    ]
    assert all(
        row.quality not in {DemandTargetQuality.ACTUAL, DemandTargetQuality.ESTIMATED}
        for row in result.rows
    )


def test_source_format_provider_item_window_region_and_unit_are_rechecked():
    rows = [
        record(record_id="item", provider_item_id="PUBOB652"),
        record(record_id="format", source_format="REST"),
        record(record_id="day", gas_day=date(2026, 11, 1)),
        record(record_id="region", region="UK"),
        record(record_id="unit", unit="kwh"),
    ]
    result = build(rows)

    assert result.rows == ()
    assert {item.code for item in result.diagnostics} == {
        DemandTargetDiagnosticCode.PROVIDER_ITEM_MISMATCH,
        DemandTargetDiagnosticCode.SOURCE_FORMAT_MISMATCH,
        DemandTargetDiagnosticCode.GAS_DAY_OUTSIDE_WINDOW,
        DemandTargetDiagnosticCode.REGION_NOT_SUPPORTED,
        DemandTargetDiagnosticCode.UNIT_NOT_SUPPORTED,
    }


@pytest.mark.parametrize("value_text", ["-1", "NaN", "Infinity", "1e3", "+1", "01.2", "1."])
def test_invalid_native_values_are_refused(value_text: str):
    result = build([record(value_text=value_text)])

    assert result.rows == ()
    assert result.diagnostics[0].code is DemandTargetDiagnosticCode.INVALID_NATIVE_VALUE


def test_all_admitted_revisions_survive_cutoff_and_are_ranked_by_actual_availability():
    first = record(record_id="first", available_at_utc=RECEIVED)
    later = record(
        record_id="later",
        source_publication_id="pub-later",
        available_at_utc=RECEIVED + timedelta(hours=6),
        received_at_utc=RECEIVED + timedelta(hours=6),
    )

    before = build(
        [first, later],
        available_at_utc=RECEIVED + timedelta(hours=3),
    )
    assert [row.revision_id for row in before.rows] == ["first"]
    assert [row.revision for row in before.rows] == [1]
    assert [item.code for item in before.diagnostics] == [
        DemandTargetDiagnosticCode.AVAILABLE_AFTER_CUTOFF
    ]

    after = build([first, later], available_at_utc=RECEIVED + timedelta(hours=9))
    assert [row.revision_id for row in after.rows] == ["first", "later"]
    assert [row.revision for row in after.rows] == [1, 2]
    assert after.provenance_by_record_id["first"].selected is False
    assert after.provenance_by_record_id["first"].derived_revision == 1
    assert after.provenance_by_record_id["later"].selected is True
    assert after.provenance_by_record_id["later"].derived_revision == 2


def test_same_mapped_revisions_resolve_latest_at_each_fold_cutoff():
    first = record(record_id="first", available_at_utc=RECEIVED)
    later = record(
        record_id="later",
        source_publication_id="pub-later",
        available_at_utc=RECEIVED + timedelta(hours=6),
        received_at_utc=RECEIVED + timedelta(hours=6),
    )
    mapped = build([first, later], available_at_utc=RECEIVED + timedelta(hours=9))
    assert [row.revision_id for row in mapped.rows] == ["first", "later"]

    earlier_fold = _resolve_targets(mapped.rows, RECEIVED + timedelta(hours=3))
    later_fold = _resolve_targets(mapped.rows, RECEIVED + timedelta(hours=9))

    assert earlier_fold[GAS_DAY].revision_id == "first"
    assert earlier_fold[GAS_DAY].revision == 1
    assert later_fold[GAS_DAY].revision_id == "later"
    assert later_fold[GAS_DAY].revision == 2


def test_equal_receipt_for_distinct_publications_is_a_typed_ambiguity_refusal():
    competing = [
        record(record_id="z", source_publication_id="pub-z"),
        record(record_id="a", source_publication_id="pub-a"),
    ]

    with pytest.raises(DemandTargetAmbiguityError) as caught:
        build(competing)
    assert caught.value.code == "AMBIGUOUS_RECEIPT_TIE"
    assert "ambiguous target selection" in str(caught.value)


def test_ranking_is_deterministic_across_input_order():
    first = record(record_id="first", available_at_utc=RECEIVED)
    later = record(
        record_id="later",
        source_publication_id="pub-later",
        available_at_utc=RECEIVED + timedelta(hours=1),
        received_at_utc=RECEIVED + timedelta(hours=1),
    )
    cutoff = RECEIVED + timedelta(hours=2)

    forward = build([first, later], available_at_utc=cutoff)
    reverse = build([later, first], available_at_utc=cutoff)

    assert forward.rows == reverse.rows
    assert forward.provenance_by_record_id["first"] == reverse.provenance_by_record_id["first"]
    assert forward.provenance_by_record_id["later"] == reverse.provenance_by_record_id["later"]


def test_identical_duplicate_record_id_is_deduplicated_with_a_diagnostic():
    result = build([record(), record()])

    assert len(result.rows) == 1
    assert [item.code for item in result.diagnostics] == [
        DemandTargetDiagnosticCode.DUPLICATE_RECORD_ID
    ]


def test_conflicting_duplicate_record_id_is_refused():
    with pytest.raises(DemandTargetDuplicateConflict):
        build([record(value_text="1"), record(value_text="2")])


def test_availability_before_actual_receipt_cannot_be_claimed_historically():
    result = build(
        [
            record(
                available_at_utc=RECEIVED - timedelta(hours=1),
                received_at_utc=RECEIVED,
            )
        ]
    )

    assert result.rows == ()
    assert result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.AVAILABILITY_BEFORE_RECEIPT
    )


def test_naive_availability_is_refused_while_aware_offset_is_normalized():
    naive = build(
        [
            record(
                record_id="naive",
                available_at_utc=datetime(2026, 10, 22, 11, 0),
            )
        ]
    )
    assert naive.rows == ()
    assert naive.diagnostics[0].code is DemandTargetDiagnosticCode.NAIVE_AVAILABILITY

    offset_zone = timezone(timedelta(hours=2))
    cutoff = datetime(2026, 10, 22, 13, 0, tzinfo=offset_zone)
    offset = build(
        [
            record(
                available_at_utc=datetime(2026, 10, 22, 11, 0, tzinfo=offset_zone),
                received_at_utc=datetime(2026, 10, 22, 10, 0, tzinfo=offset_zone),
            )
        ],
        available_at_utc=cutoff,
    )
    assert len(offset.rows) == 1
    assert offset.rows[0].available_at == datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_item_id": "UNKNOWN"},
        {"source_format": "csv"},
        {"available_at_utc": datetime(2026, 10, 23, 12, 0)},
        {"gas_day_from": date(2026, 11, 1), "gas_day_to": date(2026, 10, 1)},
        {"allow_provisional_targets": 1},
        {"gas_day_from": datetime(2026, 10, 1, 0, 0, tzinfo=UTC)},
    ],
)
def test_explicit_selection_contract_rejects_partial_or_malformed_arguments(overrides):
    with pytest.raises(DemandTargetInputValidationError):
        build([record()], **overrides)


def test_result_and_provenance_mapping_are_immutable():
    result = build([record()])

    with pytest.raises(FrozenInstanceError):
        result.rows = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.provenance_by_record_id["rec-1"] = None  # type: ignore[index]
