"""Pure point-in-time demand-target mapping tests.

Every row here is a synthetic source revision used only to exercise mapping and
refusal semantics. No test fits a demand model, claims accuracy, opens a database
or activates a source.
"""

from __future__ import annotations

import json
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
    RevisionOrderPolicy,
    build_demand_target_rows,
)
from eurogas_nexus.db.repositories.demand_rest import _to_record
from eurogas_nexus.domain.ontology.vocabulary import DemandTargetQuality, TargetScope
from eurogas_nexus.domain.research.weather_demand import _resolve_targets
from eurogas_nexus.ingestion.national_gas_rest import (
    API_URL,
    D1_PUBLICATION_ID,
    parse_national_gas_rest,
)

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


REST_WINDOW_FROM = date(2026, 10, 21)
REST_WINDOW_TO = date(2026, 10, 27)


def rest_payload(
    *rows: dict[str, object],
    publication_id: str = D1_PUBLICATION_ID,
    publication_name: str = "Demand Actual, NTS, D+1",
) -> bytes:
    """Build a synthetic REST response; provenance is produced by the real parser."""

    return json.dumps(
        [
            {
                "publicationId": publication_id,
                "publicationName": publication_name,
                "publications": list(rows),
            }
        ],
        separators=(",", ":"),
    ).encode("utf-8")


def rest_row(
    *,
    applicable_at: str = "2026-10-22T10:20:01+00:00",
    generated_at: str | None = None,
    created_at: str | None = None,
    applicable_for: str = GAS_DAY.isoformat(),
    value: str = "176.708",
    quality: str = "",
    substituted: str = "N",
) -> dict[str, object]:
    """One synthetic provider row with all three clocks aligned by default."""

    return {
        "applicableAt": applicable_at,
        "applicableFor": applicable_for,
        "value": value,
        "generatedTimeStamp": generated_at or applicable_at,
        "qualityIndicator": quality,
        "substituted": substituted,
        "createdDate": created_at or applicable_at,
    }


def rest_records(
    *rows: dict[str, object],
    received: datetime = RECEIVED,
    available: datetime | None = None,
    publication_id: str = D1_PUBLICATION_ID,
    publication_name: str = "Demand Actual, NTS, D+1",
):
    """Parse synthetic source text and persist it through the real repository mapper."""

    publications = parse_national_gas_rest(
        rest_payload(
            *rows,
            publication_id=publication_id,
            publication_name=publication_name,
        ),
        date_from=REST_WINDOW_FROM,
        date_to=REST_WINDOW_TO,
        received_at_utc=received,
        available_at_utc=available,
        publication_ids=[publication_id],
    )
    return [_to_record(publication) for publication in publications]


def build_rest(records, **overrides: object):
    arguments: dict[str, object] = {
        "source_format": "REST",
        "revision_order_policy": (
            RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
        ),
    }
    arguments.update(overrides)
    return build(records, **arguments)


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


def test_default_policy_still_refuses_actual_rest_same_receipt_tie():
    rows = rest_records(
        rest_row(applicable_at="2026-10-22T09:20:01+00:00", value="100"),
        rest_row(applicable_at="2026-10-22T11:20:01+00:00", value="101"),
    )

    with pytest.raises(DemandTargetAmbiguityError) as caught:
        build(rows, source_format="REST")

    assert caught.value.code == "AMBIGUOUS_RECEIPT_TIE"
    assert "ambiguous target selection" in str(caught.value)


def test_opt_in_returns_same_receipt_revisions_and_earlier_cutoff_has_no_leak():
    rows = rest_records(
        rest_row(applicable_at="2026-10-22T09:20:01+00:00", value="100"),
        rest_row(applicable_at="2026-10-22T11:20:01+00:00", value="101"),
    )
    mapped = build_rest(rows)

    assert len(mapped.rows) == 2
    assert [row.revision for row in mapped.rows] == [1, 2]
    assert [row.revision_id for row in mapped.rows] == [
        row.record_id for row in rows
    ]
    assert all(row.available_at == RECEIVED for row in mapped.rows)
    assert [row.source_ref.rsplit(":", 1)[-1] for row in mapped.rows] == [
        RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1.value,
        RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1.value,
    ]

    before_receipt = _resolve_targets(mapped.rows, RECEIVED - timedelta(minutes=1))
    assert before_receipt == {}
    at_receipt = _resolve_targets(mapped.rows, RECEIVED)
    assert at_receipt[GAS_DAY].revision_id == rows[1].record_id
    assert at_receipt[GAS_DAY].revision == 2


def test_later_receipt_of_older_applicability_does_not_supersede_newer_source():
    newer = rest_records(
        rest_row(applicable_at="2026-10-22T11:20:01+00:00", value="201"),
        received=RECEIVED,
    )[0]
    older_late = rest_records(
        rest_row(applicable_at="2026-10-22T09:20:01+00:00", value="200"),
        received=RECEIVED + timedelta(hours=6),
    )[0]
    mapped = build_rest(
        [newer, older_late],
        available_at_utc=RECEIVED + timedelta(hours=9),
    )

    assert [row.revision_id for row in mapped.rows] == [
        older_late.record_id,
        newer.record_id,
    ]
    assert [row.revision for row in mapped.rows] == [1, 2]
    assert mapped.provenance_by_record_id[older_late.record_id].derived_revision == 1
    assert mapped.provenance_by_record_id[newer.record_id].derived_revision == 2

    before_older_receipt = _resolve_targets(mapped.rows, RECEIVED + timedelta(hours=1))
    after_both = _resolve_targets(mapped.rows, RECEIVED + timedelta(hours=9))
    assert before_older_receipt[GAS_DAY].revision_id == newer.record_id
    assert after_both[GAS_DAY].revision_id == newer.record_id
    assert after_both[GAS_DAY].revision == 2


def test_opt_in_source_ref_and_provenance_bind_the_chosen_method():
    source = rest_records(rest_row())[0]
    mapped = build_rest([source])
    method = RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1.value

    row = mapped.rows[0]
    provenance = mapped.provenance_by_record_id[source.record_id]
    assert row.source_ref == (
        f"NATIONAL_GAS:REST:{source.source_publication_id}:{method}"
    )
    assert provenance.revision_order_basis == method
    assert provenance.source_order_method_basis == method
    assert provenance.source_order_basis == method
    assert provenance.source_order_at_utc == datetime(
        2026, 10, 22, 10, 20, 1, tzinfo=UTC
    )
    assert row.available_at == RECEIVED
    assert row.revision_id == source.record_id
    assert source.received_at_utc == RECEIVED
    assert source.available_at_utc == RECEIVED

    default = build([source], source_format="REST")
    assert default.rows[0].source_ref == (
        f"NATIONAL_GAS:REST:{source.source_publication_id}"
    )
    default_provenance = default.provenance_by_record_id[source.record_id]
    assert default_provenance.revision_order_basis == "DERIVED_RECEIPT_ORDER"
    assert default_provenance.source_order_at_utc is None
    assert default_provenance.source_order_method_basis is None


def test_offset_equivalent_source_clocks_are_one_consensus_instant():
    source = rest_records(
        rest_row(
            applicable_at="2026-10-22T12:20:01+02:00",
            generated_at="2026-10-22T11:20:01+01:00",
            created_at="2026-10-22T10:20:01+00:00",
        )
    )[0]
    mapped = build_rest([source])

    assert len(mapped.rows) == 1
    provenance = mapped.provenance_by_record_id[source.record_id]
    assert provenance.source_order_at_utc == datetime(
        2026, 10, 22, 10, 20, 1, tzinfo=UTC
    )
    assert source.rest_provenance["applicable_at_raw"] == "2026-10-22T12:20:01+02:00"
    assert source.rest_provenance["generated_at_raw"] == "2026-10-22T11:20:01+01:00"
    assert source.rest_provenance["created_at_raw"] == "2026-10-22T10:20:01+00:00"


def test_equal_source_instant_with_competing_publications_remains_ambiguous():
    rows = rest_records(
        rest_row(applicable_at="2026-10-22T10:20:01+00:00", value="300"),
        rest_row(applicable_at="2026-10-22T11:20:01+01:00", value="301"),
    )

    with pytest.raises(DemandTargetAmbiguityError) as caught:
        build_rest(rows)
    assert "source applicability instant" in str(caught.value)

    with pytest.raises(DemandTargetAmbiguityError):
        build_rest(list(reversed(rows)))


def test_opt_in_refuses_missing_and_malformed_rest_provenance():
    missing = rest_records(rest_row())[0]
    missing.rest_provenance = None
    missing_result = build_rest([missing])
    assert missing_result.rows == ()
    assert missing_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.REST_ORDER_PROVENANCE_MISSING
    )

    malformed = rest_records(rest_row())[0]
    provenance = dict(malformed.rest_provenance)
    provenance.pop("created_at_utc")
    malformed.rest_provenance = provenance
    malformed_result = build_rest([malformed])
    assert malformed_result.rows == ()
    assert malformed_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.SOURCE_CLOCK_MISSING
    )

    schema_drift = rest_records(rest_row())[0]
    provenance = dict(schema_drift.rest_provenance)
    provenance.pop("evidence_basis")
    schema_drift.rest_provenance = provenance
    schema_drift_result = build_rest([schema_drift])
    assert schema_drift_result.rows == ()
    assert schema_drift_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.REST_ORDER_PROVENANCE_MALFORMED
    )


def test_opt_in_refuses_non_rest_source_identity():
    wrong_url = rest_records(rest_row())[0]
    wrong_url.source_url = "https://example.test/not-national-gas"
    url_result = build_rest([wrong_url])
    assert url_result.rows == ()
    assert url_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH
    )

    wrong_schema = rest_records(rest_row())[0]
    wrong_schema.hash_schema = "national_gas_actual_demand.v1"
    schema_result = build_rest([wrong_schema])
    assert schema_result.rows == ()
    assert schema_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.REST_ORDER_IDENTITY_MISMATCH
    )


def test_opt_in_refuses_disagreeing_clocks_instead_of_using_a_maximum():
    source = rest_records(rest_row())[0]
    provenance = dict(source.rest_provenance)
    provenance["generated_at_utc"] = "2026-10-22T10:21:01+00:00"
    source.rest_provenance = provenance

    result = build_rest([source])

    assert result.rows == ()
    assert result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.SOURCE_CLOCK_INCONSISTENT
    )


def test_opt_in_refuses_naive_source_clock_without_falling_back_to_receipt():
    source = rest_records(rest_row())[0]
    provenance = dict(source.rest_provenance)
    provenance["applicable_at_raw"] = "2026-10-22T10:20:01"
    source.rest_provenance = provenance
    source.applicable_at_raw = "2026-10-22T10:20:01"

    result = build_rest([source])

    assert result.rows == ()
    assert result.diagnostics[0].code is DemandTargetDiagnosticCode.NAIVE_SOURCE_CLOCK


def test_opt_in_refuses_source_clock_after_actual_receipt():
    source = rest_records(
        rest_row(applicable_at="2026-10-22T13:20:01+00:00"),
        received=RECEIVED,
    )[0]

    result = build_rest([source])

    assert result.rows == ()
    assert result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.SOURCE_CLOCK_AFTER_RECEIPT
    )


def test_opt_in_refuses_csv_inference_explicitly():
    with pytest.raises(DemandTargetInputValidationError):
        build(
            [record()],
            revision_order_policy=(
                RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
            ),
        )

    with pytest.raises(DemandTargetInputValidationError):
        build([record()], revision_order_policy="UNSUPPORTED_POLICY")


def test_opt_in_keeps_amended_d6_and_substituted_quality_distinctions():
    amended = rest_records(rest_row(quality="A"))[0]
    amended_result = build_rest([amended])
    assert amended_result.rows == ()
    assert amended_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.SOURCE_QUALITY_AMENDED
    )

    d6 = rest_records(
        rest_row(),
        publication_id="PUBOB652",
        publication_name="Demand Actual, NTS, D+6",
    )[0]
    d6_result = build_rest([d6], provider_item_id="PUBOB652")
    assert d6_result.rows == ()
    assert d6_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.UNRESOLVED_TARGET_QUALITY
    )

    substituted = rest_records(rest_row(substituted="Y"))[0]
    substituted_result = build_rest([substituted])
    assert len(substituted_result.rows) == 1
    assert substituted_result.rows[0].quality is DemandTargetQuality.PROVISIONAL
    assert substituted.rest_provenance["is_substituted"] is True
    assert substituted_result.rows[0].quality not in {
        DemandTargetQuality.ACTUAL,
        DemandTargetQuality.ESTIMATED,
    }
    assert API_URL == substituted.source_url
