"""Pure mapper tests for the explicit demand-target label clock.

These cases use synthetic National Gas revisions only. They prove mapper
field/basis mechanics; they do not prove historical public availability,
provider-history accuracy, genuine OOS or production use.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from eurogas_nexus.application.research.demand_target_inputs import (
    DemandTargetAmbiguityError,
    DemandTargetDiagnosticCode,
    DemandTargetInputValidationError,
    RevisionOrderPolicy,
    build_demand_target_rows,
)
from eurogas_nexus.db.repositories.demand_rest import _to_record
from eurogas_nexus.domain.ontology.vocabulary import DemandTargetQuality
from eurogas_nexus.domain.research.weather_demand import (
    DEMAND_TARGET_LABEL_METHOD_VERSION,
    DemandTargetLabelBasis,
    DemandTargetLabelEvidence,
    DemandTargetLabelFact,
    _target_label_policy_hash_for_basis,
)
from eurogas_nexus.ingestion.national_gas_rest import (
    API_URL,
    D1_PUBLICATION_ID,
    parse_national_gas_rest,
)

GAS_DAY = date(2026, 10, 21)
RECEIVED = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
REST_WINDOW_FROM = date(2026, 10, 21)
REST_WINDOW_TO = date(2026, 10, 27)
REST_ORDER = RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
RETROSPECTIVE = (
    DemandTargetLabelBasis.RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH
)


def record(**overrides: object) -> SimpleNamespace:
    """One explicit CSV source row; values are synthetic mapper inputs only."""

    values: dict[str, object] = {
        "record_id": "csv-1",
        "source_publication_id": "pub-csv-1",
        "provider_item_id": "PUBOB637",
        "source_format": "CSV",
        "region": "GB_NTS",
        "term": "D+1",
        "gas_day": GAS_DAY,
        "value_text": "176.708",
        "unit": "mscm",
        "received_at_utc": RECEIVED,
        "available_at_utc": RECEIVED,
        "quality_indicator": None,
        "provisional_status": "PROVISIONAL_INITIAL",
        "is_provisional": True,
        "raw_sha256": "a" * 64,
        "value_is_blank": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def build(records: Any, **overrides: object):
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


def rest_payload(
    *rows: dict[str, object],
    publication_id: str = D1_PUBLICATION_ID,
    publication_name: str = "Demand Actual, NTS, D+1",
) -> bytes:
    """Build synthetic REST text; provenance is produced by the real parser."""

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
    """Parse synthetic source text and map it through the real repository mapper."""

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


def build_rest(records: Any, **overrides: object):
    arguments: dict[str, object] = {
        "source_format": "REST",
        "revision_order_policy": REST_ORDER,
        "target_label_basis": RETROSPECTIVE,
    }
    arguments.update(overrides)
    return build(records, **arguments)


def source_with_provenance(**updates: object):
    source = rest_records(rest_row())[0]
    provenance = dict(source.rest_provenance)
    provenance.update(updates)
    source.rest_provenance = provenance
    return source


class _UnreadableRecords:
    """A sequence that fails loudly if selection validation reads records."""

    def __len__(self) -> int:
        return 1

    def __getitem__(self, index: int) -> object:
        raise AssertionError("records were read before selection validation")

    def __iter__(self):
        raise AssertionError("records were read before selection validation")


def test_default_csv_values_ids_order_refs_and_label_fields_are_unchanged():
    first = record()
    later = record(
        record_id="csv-2",
        source_publication_id="pub-csv-2",
        value_text="180.500",
        received_at_utc=RECEIVED + timedelta(hours=6),
        available_at_utc=RECEIVED + timedelta(hours=6),
    )

    mapped = build(
        [later, first],
        available_at_utc=RECEIVED + timedelta(hours=9),
    )

    assert [row.gas_day for row in mapped.rows] == [GAS_DAY, GAS_DAY]
    assert [row.revision_id for row in mapped.rows] == ["csv-1", "csv-2"]
    assert [row.revision for row in mapped.rows] == [1, 2]
    assert [row.value for row in mapped.rows] == [176.708, 180.5]
    assert [row.unit for row in mapped.rows] == ["MSCM", "MSCM"]
    assert [row.quality for row in mapped.rows] == [
        DemandTargetQuality.PROVISIONAL,
        DemandTargetQuality.PROVISIONAL,
    ]
    assert [row.available_at for row in mapped.rows] == [
        RECEIVED,
        RECEIVED + timedelta(hours=6),
    ]
    assert [row.label_at for row in mapped.rows] == [None, None]
    assert [row.label_basis for row in mapped.rows] == [
        DemandTargetLabelBasis.ACTUAL_RECEIPT,
        DemandTargetLabelBasis.ACTUAL_RECEIPT,
    ]
    assert [row.source_ref for row in mapped.rows] == [
        "NATIONAL_GAS:CSV:pub-csv-1",
        "NATIONAL_GAS:CSV:pub-csv-2",
    ]
    for item in mapped.provenance_by_record_id.values():
        assert item.label_basis is DemandTargetLabelBasis.ACTUAL_RECEIPT
        assert item.label_at is None
        assert item.effective_label_at is None
        assert item.label_method_version is None
        assert item.label_policy_hash is None

    explicit_default = build(
        [later, first],
        available_at_utc=RECEIVED + timedelta(hours=9),
        target_label_basis=DemandTargetLabelBasis.ACTUAL_RECEIPT,
    )
    assert explicit_default == mapped


def test_default_rest_and_explicit_revision_order_do_not_imply_label_basis():
    newer_source = rest_records(
        rest_row(applicable_at="2026-10-22T11:20:01+00:00", value="201"),
        received=RECEIVED,
    )[0]
    older_source_late = rest_records(
        rest_row(applicable_at="2026-10-22T09:20:01+00:00", value="200"),
        received=RECEIVED + timedelta(hours=6),
    )[0]
    cutoff = RECEIVED + timedelta(hours=9)

    receipt_order = build(
        [newer_source, older_source_late],
        source_format="REST",
        available_at_utc=cutoff,
    )
    assert [row.revision_id for row in receipt_order.rows] == [
        newer_source.record_id,
        older_source_late.record_id,
    ]
    assert [row.source_ref for row in receipt_order.rows] == [
        f"NATIONAL_GAS:REST:{newer_source.source_publication_id}",
        f"NATIONAL_GAS:REST:{older_source_late.source_publication_id}",
    ]
    assert [row.label_at for row in receipt_order.rows] == [None, None]
    assert [row.label_basis for row in receipt_order.rows] == [
        DemandTargetLabelBasis.ACTUAL_RECEIPT,
        DemandTargetLabelBasis.ACTUAL_RECEIPT,
    ]
    for item in receipt_order.provenance_by_record_id.values():
        assert item.label_basis is DemandTargetLabelBasis.ACTUAL_RECEIPT
        assert item.label_at is None
        assert item.label_method_version is None
        assert item.label_policy_hash is None

    source_order = build(
        [newer_source, older_source_late],
        source_format="REST",
        revision_order_policy=REST_ORDER,
        available_at_utc=cutoff,
    )
    assert [row.revision_id for row in source_order.rows] == [
        older_source_late.record_id,
        newer_source.record_id,
    ]
    assert [row.revision for row in source_order.rows] == [1, 2]
    assert [row.value for row in source_order.rows] == [200.0, 201.0]
    assert [row.available_at for row in source_order.rows] == [
        RECEIVED + timedelta(hours=6),
        RECEIVED,
    ]
    assert [row.source_ref for row in source_order.rows] == [
        f"NATIONAL_GAS:REST:{older_source_late.source_publication_id}:"
        f"{REST_ORDER.value}",
        f"NATIONAL_GAS:REST:{newer_source.source_publication_id}:{REST_ORDER.value}",
    ]
    assert [row.label_at for row in source_order.rows] == [None, None]
    assert [row.label_basis for row in source_order.rows] == [
        DemandTargetLabelBasis.ACTUAL_RECEIPT,
        DemandTargetLabelBasis.ACTUAL_RECEIPT,
    ]
    for item in source_order.provenance_by_record_id.values():
        assert item.source_order_at_utc is not None
        assert item.label_basis is DemandTargetLabelBasis.ACTUAL_RECEIPT
        assert item.label_at is None
        assert item.label_method_version is None
        assert item.label_policy_hash is None


def test_nondefault_selection_refuses_csv_receipt_ranking_and_unknown_basis():
    cases = [
        {"source_format": "CSV", "target_label_basis": RETROSPECTIVE},
        {"source_format": "REST", "target_label_basis": RETROSPECTIVE},
        {
            "source_format": "REST",
            "revision_order_policy": "DERIVED_RECEIPT_ORDER",
            "target_label_basis": RETROSPECTIVE,
        },
        {
            "source_format": "REST",
            "revision_order_policy": REST_ORDER,
            "target_label_basis": "UNKNOWN_LABEL_BASIS",
        },
    ]

    for overrides in cases:
        with pytest.raises(DemandTargetInputValidationError):
            build(_UnreadableRecords(), **overrides)


def test_nondefault_maps_consensus_clock_and_preserves_receipt_and_identity():
    source = rest_records(
        rest_row(
            applicable_at="2026-10-22T12:20:01+02:00",
            generated_at="2026-10-22T11:20:01+01:00",
            created_at="2026-10-22T10:20:01+00:00",
        )
    )[0]

    mapped = build_rest([source])

    assert len(mapped.rows) == 1
    row = mapped.rows[0]
    expected_label = datetime(2026, 10, 22, 10, 20, 1, tzinfo=UTC)
    assert row.gas_day == GAS_DAY
    assert row.revision_id == source.record_id
    assert row.revision == 1
    assert row.available_at == RECEIVED
    assert row.value == 176.708
    assert row.unit == "MSCM"
    assert row.quality is DemandTargetQuality.PROVISIONAL
    assert row.label_at == expected_label
    assert row.label_basis is RETROSPECTIVE
    assert row.source_ref == (
        f"NATIONAL_GAS:REST:{source.source_publication_id}:"
        f"{REST_ORDER.value}:{RETROSPECTIVE.value}"
    )

    provenance = mapped.provenance_by_record_id[source.record_id]
    assert provenance.available_at == RECEIVED
    assert provenance.source_order_at_utc == expected_label
    assert provenance.revision_order_basis == REST_ORDER.value
    assert provenance.label_basis is RETROSPECTIVE
    assert provenance.target_label_basis is RETROSPECTIVE
    assert provenance.label_at == expected_label
    assert provenance.effective_label_at == expected_label
    assert provenance.label_method_version == DEMAND_TARGET_LABEL_METHOD_VERSION
    assert provenance.target_label_method == DEMAND_TARGET_LABEL_METHOD_VERSION
    assert provenance.label_policy_hash == _target_label_policy_hash_for_basis(
        RETROSPECTIVE
    )
    assert provenance.target_label_policy_hash == provenance.label_policy_hash
    assert provenance.derived_revision == 1
    assert provenance.selected is True

    fact = DemandTargetLabelFact.from_row(row)
    assert fact.revision_id == source.record_id
    assert fact.available_at == RECEIVED
    assert fact.label_at == expected_label
    assert fact.label_basis is RETROSPECTIVE
    assert fact.source_ref == row.source_ref

    evidence = DemandTargetLabelEvidence(
        basis=RETROSPECTIVE,
        policy_hash=provenance.label_policy_hash,
        analysis_as_of=CUTOFF,
        revision_facts=(fact,),
        final_truth=(fact,),
    )
    assert evidence.revision_facts == (fact,)
    assert evidence.final_truth == (fact,)

    assert source.received_at_utc == RECEIVED
    assert source.available_at_utc == RECEIVED
    assert source.rest_provenance["applicable_at_raw"] == "2026-10-22T12:20:01+02:00"
    assert API_URL == source.source_url

    string_basis = build_rest([source], target_label_basis=RETROSPECTIVE.value)
    assert string_basis == mapped


def test_nondefault_refuses_missing_source_clock():
    source = rest_records(rest_row())[0]
    provenance = dict(source.rest_provenance)
    provenance.pop("applicable_at_utc")
    source.rest_provenance = provenance

    result = build_rest([source])

    assert result.rows == ()
    assert result.provenance_by_record_id == {}
    assert result.diagnostics[0].code is DemandTargetDiagnosticCode.SOURCE_CLOCK_MISSING


def test_nondefault_refuses_naive_source_clock():
    source = source_with_provenance(
        applicable_at_raw="2026-10-22T10:20:01",
    )
    source.applicable_at_raw = "2026-10-22T10:20:01"

    result = build_rest([source])

    assert result.rows == ()
    assert result.diagnostics[0].code is DemandTargetDiagnosticCode.NAIVE_SOURCE_CLOCK


def test_nondefault_refuses_clocks_that_are_not_one_consensus_instant():
    inconsistent = source_with_provenance(
        generated_at_utc="2026-10-22T10:21:01+00:00",
    )
    inconsistent_result = build_rest([inconsistent])
    assert inconsistent_result.rows == ()
    assert inconsistent_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.SOURCE_CLOCK_INCONSISTENT
    )

    disagreeing = source_with_provenance(
        created_at_raw="2026-10-22T10:21:01+00:00",
        created_at_utc="2026-10-22T10:21:01+00:00",
        created_at_wall_clock_naive="2026-10-22T10:21:01",
    )
    disagreeing_result = build_rest([disagreeing])
    assert disagreeing_result.rows == ()
    assert disagreeing_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.SOURCE_CLOCKS_DISAGREE
    )


def test_nondefault_refuses_source_clock_after_actual_receipt():
    source = rest_records(
        rest_row(applicable_at="2026-10-22T13:20:01+00:00"),
        received=RECEIVED,
    )[0]

    result = build_rest([source])

    assert result.rows == ()
    assert result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.SOURCE_CLOCK_AFTER_RECEIPT
    )


def test_label_before_analysis_but_receipt_after_analysis_is_excluded():
    source = rest_records(
        rest_row(applicable_at="2026-10-22T10:20:01+00:00"),
        received=CUTOFF + timedelta(hours=1),
    )[0]

    result = build_rest([source], available_at_utc=CUTOFF)

    assert result.rows == ()
    assert result.provenance_by_record_id == {}
    assert result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.AVAILABLE_AFTER_CUTOFF
    )
    assert source.rest_provenance["applicable_at_utc"] == "2026-10-22T10:20:01+00:00"


def test_all_revisions_survive_and_rank_is_monotonic_with_label_clock():
    newer_source = rest_records(
        rest_row(applicable_at="2026-10-22T11:20:01+00:00", value="201"),
        received=RECEIVED,
    )[0]
    older_source_late = rest_records(
        rest_row(applicable_at="2026-10-22T09:20:01+00:00", value="200"),
        received=RECEIVED + timedelta(hours=6),
    )[0]

    mapped = build_rest(
        [newer_source, older_source_late],
        available_at_utc=RECEIVED + timedelta(hours=9),
    )

    assert [row.revision_id for row in mapped.rows] == [
        older_source_late.record_id,
        newer_source.record_id,
    ]
    assert [row.revision for row in mapped.rows] == [1, 2]
    assert [row.value for row in mapped.rows] == [200.0, 201.0]
    labels = [row.label_at for row in mapped.rows]
    assert labels == [
        datetime(2026, 10, 22, 9, 20, 1, tzinfo=UTC),
        datetime(2026, 10, 22, 11, 20, 1, tzinfo=UTC),
    ]
    assert all(
        previous < current
        for previous, current in zip(labels[:-1], labels[1:], strict=True)
    )
    assert [row.available_at for row in mapped.rows] == [
        RECEIVED + timedelta(hours=6),
        RECEIVED,
    ]
    assert mapped.provenance_by_record_id[older_source_late.record_id].selected is False
    assert mapped.provenance_by_record_id[newer_source.record_id].selected is True


def test_equal_consensus_source_instants_for_competing_publications_refuse():
    competing = rest_records(
        rest_row(applicable_at="2026-10-22T10:20:01+00:00", value="300"),
        rest_row(applicable_at="2026-10-22T11:20:01+01:00", value="301"),
    )

    with pytest.raises(DemandTargetAmbiguityError) as caught:
        build_rest(competing)

    assert "source applicability instant" in str(caught.value)
    with pytest.raises(DemandTargetAmbiguityError):
        build_rest(list(reversed(competing)))


def test_nondefault_keeps_quality_amended_provisional_and_d6_boundaries():
    amended = rest_records(rest_row(quality="A"))[0]
    amended_result = build_rest([amended])
    assert amended_result.rows == ()
    assert amended_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.SOURCE_QUALITY_AMENDED
    )

    provisional = rest_records(rest_row())[0]
    provisional_result = build_rest([provisional], allow_provisional_targets=False)
    assert provisional_result.rows == ()
    assert provisional_result.diagnostics[0].code is (
        DemandTargetDiagnosticCode.PROVISIONAL_TARGET_NOT_ALLOWED
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
