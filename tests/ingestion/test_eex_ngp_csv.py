"""EEX TTF NGP CSV adapter tests — synthetic inputs only, no network or database.

The fixtures are hand-built to the operator-verified source shape (UTF-8 BOM, ``;`` delimiter,
five columns). No downloaded live price is recorded in this file; every value is an invented
placeholder.

Canonical mapping always requires two *separate* synthetic contracts in these tests, because the
adapter refuses to guess either the publication zone or the delivery gas-day calendar:

- ``_governed_contract()`` — a synthetic evidenced ``SourceTimezoneContract`` for ``Timestamp
  Let``;
- ``_gas_day_contract()`` — a synthetic evidenced ``EexNgpGasDayCalendarContract`` naming an
  existing registered calendar id.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from eurogas_nexus.domain.ingestion.source_timezone import (
    SourceTimezoneContract,
    contract_for,
)
from eurogas_nexus.domain.market.gas_day import EU_CAM_CALENDAR, EU_CAM_UTC_CALENDAR
from eurogas_nexus.domain.observations.market import ObservationFreshness
from eurogas_nexus.ingestion.eex_ngp import (
    SOURCE_DATASET,
    EexNgpGasDayCalendarContract,
    EexNgpParseError,
    eex_ttf_ngp_market_observations,
    parse_eex_ttf_ngp_csv,
)

RETRIEVED_AT = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)
HEADER = "Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let"
MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "eurogas_nexus" / "ingestion" / "eex_ngp.py"
)


def _csv(*rows: str) -> str:
    return "\ufeff" + "\n".join([HEADER, *rows]) + "\n"


def _governed_contract(*, zone: str = "Europe/Berlin") -> SourceTimezoneContract:
    """A synthetic, explicitly evidenced contract used only to exercise the canonical path."""

    return SourceTimezoneContract(
        source_system="EEX",
        datasets=(SOURCE_DATASET,),
        declared_zone=ZoneInfo(zone),
        evidence="synthetic test contract: exercise the governed-zone path only",
    )


def _gas_day_contract(*, calendar_id: str = EU_CAM_UTC_CALENDAR) -> EexNgpGasDayCalendarContract:
    """A synthetic, explicitly evidenced delivery calendar used only by these tests.

    The adapter never assumes a delivery calendar; a test that exercises canonical mapping must
    name an existing registered calendar id *and* state its (synthetic here) evidence.
    """

    return EexNgpGasDayCalendarContract(
        calendar_id=calendar_id,
        evidence="synthetic test contract: exercise the governed delivery-calendar path only",
    )


def test_verified_source_shape_maps_every_field() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv(
            "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
            "29/05/2026;0;0;Temporary NGP;29/05/2026 14:45",
        ),
        retrieved_at_utc=RETRIEVED_AT,
    )

    assert result.rejections == ()
    assert result.blank_lines_skipped == 0
    assert result.retrieved_at_utc == RETRIEVED_AT
    final, temporary = result.records
    assert final.row_number == 2
    assert final.gas_day.isoformat() == "2026-05-29"
    assert final.gas_day_raw == "29/05/2026"
    assert final.timestamp_raw == "29/05/2026 14:30"
    assert final.timestamp_local == datetime(2026, 5, 29, 14, 30)
    assert final.status == "final"
    assert final.status_raw == "Final NGP"
    assert final.is_provisional is False
    assert final.index_value == Decimal("31.400")
    assert final.index_volume == Decimal("1200.5")
    assert final.price_available is True
    assert final.unavailable_reason is None
    assert final.observation_id == "eex-ngp-ttf-2026-05-29-20260529T1430-final"

    assert temporary.is_provisional is True
    assert temporary.status == "temporary"
    assert temporary.unavailable_reason == "zero_volume"
    assert temporary.price_available is False


def test_no_provider_zone_yet_keeps_the_raw_timestamp_and_refuses_canonical_mapping() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
    )

    record = result.records[0]
    assert result.timezone_contract.declared_zone is None
    assert record.normalization_status == "pending_source_timezone"
    # The raw field survives untouched and no host-clock instant is invented.
    assert record.timestamp_raw == "29/05/2026 14:30"
    assert record.publication_time_utc is None
    assert record.normalization_status != "canonical"

    # The delivery calendar is supplied here, so the refusal below is the *timezone* blocker
    # alone: the two evidences are independent and neither substitutes for the other.
    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())
    assert refusal.value.code == "unproven_publication_timezone"


def test_the_repository_declares_no_eex_ngp_provider_zone_yet() -> None:
    contract = contract_for("EEX", SOURCE_DATASET)

    assert contract.declared_zone is None
    assert contract.evidence.strip()
    assert "EEX_NGP_SOURCE_CONTRACT.md" in contract.evidence


def test_a_governed_zone_contract_enables_canonical_market_observations() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    assert result.records[0].publication_time_utc == datetime(2026, 5, 29, 12, 30, tzinfo=UTC)

    rows = eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())

    assert len(rows) == 1
    row = rows[0]
    assert row["observation_id"] == "eex-ngp-ttf-2026-05-29-20260529T1430-final"
    assert row["market_venue"] == "EEX"
    assert row["product"] == "TTF NGP"
    assert row["price"] == 31.4
    assert row["unit"] == "EUR/MWh"
    assert row["currency"] == "EUR"
    assert row["period_start_utc"] == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert row["period_end_utc"] == datetime(2026, 5, 30, 4, 0, tzinfo=UTC)
    assert row["observed_at_utc"] == datetime(2026, 5, 29, 12, 30, tzinfo=UTC)
    assert row["source_system"] == "EEX"
    assert row["source_reference"] == "eex-ttf-ngp-15-mins"
    assert row["source_record_id"] == "2026-05-29-20260529T1430-final"
    assert row["research_only"] is True
    # No proven source freshness expectation: the row is never awarded "live" or a quality score.
    assert row["freshness"] == ObservationFreshness.UNKNOWN.value
    assert row["freshness"] != ObservationFreshness.FRESH.value
    assert row["quality_score"] == 0.0

    metadata = row["metadata_json"]
    # EEX vs simulated, and an index rather than a future/spot quote.
    assert metadata["simulated"] is False
    assert metadata["contract_type"] == "index"
    assert metadata["price_type"] == "index"
    assert metadata["executable_quote"] is False
    assert metadata["hub"] == "TTF"
    # Publication vs ingestion semantics, and the exact source fields.
    assert metadata["revision_status"] == "final"
    assert metadata["provisional"] is False
    assert metadata["publication_timestamp_raw"] == "29/05/2026 14:30"
    assert metadata["publication_time_utc"] == "2026-05-29T12:30:00+00:00"
    assert metadata["retrieved_at_utc"] == RETRIEVED_AT.isoformat()
    assert metadata["gas_day"] == "2026-05-29"
    assert metadata["gas_day_raw"] == "29/05/2026"
    assert metadata["gas_day_calendar"] == EU_CAM_UTC_CALENDAR
    assert metadata["gas_day_calendar_evidence"] == _gas_day_contract().evidence
    assert metadata["period_basis"] == "gas_day_declared_calendar"
    assert metadata["index_value_raw"] == "31.400"
    assert metadata["index_value_exact"] == "31.400"
    assert metadata["index_volume_mwh_exact"] == "1200.5"
    assert metadata["entitlement_scope"] == "licensed"
    assert metadata["certification_stage"] == "unverified"
    assert metadata["publication_timezone_evidence"] == _governed_contract().evidence
    assert metadata["freshness_basis"] == "no_proven_source_freshness_expectation"
    assert metadata["quality_assessed"] is False
    assert metadata["quality_score_basis"] == "unassessed"


def test_zero_and_missing_volume_rows_never_become_zero_prices() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv(
            "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
            "29/05/2026;0;0;Temporary NGP;29/05/2026 14:45",
            "29/05/2026;;1200.5;Final NGP;29/05/2026 15:00",
            "29/05/2026;31.5;;Final NGP;29/05/2026 15:15",
        ),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    _, zero, missing_value, missing_volume = result.records
    assert (zero.price_available, zero.unavailable_reason) == (False, "zero_volume")
    assert (missing_value.price_available, missing_value.unavailable_reason) == (
        False,
        "missing_index_value",
    )
    assert (missing_volume.price_available, missing_volume.unavailable_reason) == (
        False,
        "missing_index_volume",
    )

    rows = eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())

    # Only the row with a usable value and positive volume is mapped; nothing is fabricated.
    assert [row["observation_id"] for row in rows] == ["eex-ngp-ttf-2026-05-29-20260529T1430-final"]
    assert rows[0]["price"] == 31.4


def test_an_all_unavailable_payload_is_refused_rather_than_mapped_as_empty() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv("29/05/2026;0;0;Temporary NGP;29/05/2026 14:45"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    assert result.records[0].price_available is False
    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())
    assert refusal.value.code == "no_priced_rows"


def test_invalid_rows_are_rejected_with_reason_codes_and_no_canonical_output() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv(
            "29/05/2026;not-a-number;1200.5;Final NGP;29/05/2026 14:30",
            "29/05/2026;NaN;1200.5;Final NGP;29/05/2026 14:45",
            "29/05/2026;31.4;Infinity;Final NGP;29/05/2026 15:00",
            "29/05/2026;31.4;-5;Final NGP;29/05/2026 15:15",
            "32/13/2026;31.4;10;Final NGP;29/05/2026 15:30",
            "29/05/2026;31.4;10;Final NGP;29/05/2026 15:75",
            "29/05/2026;31.4;10;Settled NGP;29/05/2026 15:45",
            "29/05/2026;31.4",
            "29/05/2026;1e5;10;Final NGP;29/05/2026 16:00",
            "29/05/2026;31.4;1_000;Final NGP;29/05/2026 16:15",
        ),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    assert result.records == ()
    assert [rejection.row_number for rejection in result.rejections] == list(range(2, 12))
    assert [rejection.reason for rejection in result.rejections] == [
        "invalid_index_value",
        "invalid_index_value",
        "invalid_index_volume",
        "negative_index_volume",
        "invalid_gas_day",
        "invalid_timestamp",
        "unknown_status",
        "malformed_row",
        "invalid_index_value",
        "invalid_index_volume",
    ]
    assert "not-a-number" in result.rejections[0].detail

    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())
    assert refusal.value.code == "rejected_rows_present"


def test_a_non_verified_header_is_refused_whole() -> None:
    for payload in (
        "Gasday;IndexValue;IndexVolume;Status;Timestamp Let\n"
        "29/05/2026;31.4;10;Final NGP;29/05/2026 14:30\n",
        "Timestamp Let;Status;IndexVolume (MWh);IndexValue (€/MWh);Gasday\n"
        "29/05/2026 14:30;Final NGP;10;31.4;29/05/2026\n",
        HEADER + ";Extra\n29/05/2026;31.4;10;Final NGP;29/05/2026 14:30;x\n",
    ):
        with pytest.raises(EexNgpParseError) as refusal:
            parse_eex_ttf_ngp_csv(payload, retrieved_at_utc=RETRIEVED_AT)
        assert refusal.value.code == "unexpected_header"

    with pytest.raises(EexNgpParseError) as empty:
        parse_eex_ttf_ngp_csv("", retrieved_at_utc=RETRIEVED_AT)
    assert empty.value.code == "empty_payload"


def test_header_matching_ignores_case_padding_and_the_euro_spelling() -> None:
    payload = (
        " gasday ; indexvalue (EUR/MWh) ; indexvolume (MWh) ; status ; timestamp let \n"
        "29/05/2026;31.4;10;Final NGP;29/05/2026 14:30\n"
    )

    result = parse_eex_ttf_ngp_csv(payload, retrieved_at_utc=RETRIEVED_AT)

    assert [record.gas_day.isoformat() for record in result.records] == ["2026-05-29"]


def test_duplicate_rows_are_refused_rather_than_deduplicated() -> None:
    conflicting = (
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
        "29/05/2026;31.500;1300.0;Final NGP;29/05/2026 14:30",
    )
    identical = (
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
    )

    for rows in (conflicting, identical):
        with pytest.raises(EexNgpParseError) as refusal:
            parse_eex_ttf_ngp_csv(_csv(*rows), retrieved_at_utc=RETRIEVED_AT)
        assert refusal.value.code == "duplicate_observation_key"
        assert "2" in refusal.value.message and "3" in refusal.value.message


def test_final_and_temporary_revisions_never_share_a_key_or_overwrite_each_other() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv(
            "29/05/2026;31.100;900.0;Temporary NGP;29/05/2026 14:30",
            "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
        ),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    temporary, final = result.records
    assert temporary.observation_id == "eex-ngp-ttf-2026-05-29-20260529T1430-temporary"
    assert final.observation_id == "eex-ngp-ttf-2026-05-29-20260529T1430-final"
    assert temporary.observation_id != final.observation_id

    rows = eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())
    assert [row["metadata_json"]["provisional"] for row in rows] == [True, False]
    assert [row["metadata_json"]["revision_status"] for row in rows] == [
        "temporary",
        "final",
    ]


def test_blank_lines_are_skipped_and_counted() -> None:
    payload = HEADER + "\n\n29/05/2026;31.4;10;Final NGP;29/05/2026 14:30\n\n"

    result = parse_eex_ttf_ngp_csv(payload, retrieved_at_utc=RETRIEVED_AT)

    assert result.blank_lines_skipped == 2
    assert len(result.records) == 1


def test_regular_cet_and_cest_wall_clock_times_map_to_their_utc_instants() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv(
            "15/01/2026;31.4;10;Final NGP;15/01/2026 06:00",
            "29/05/2026;31.4;10;Final NGP;29/05/2026 06:00",
        ),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    assert result.rejections == ()
    published = {
        record.gas_day.isoformat(): record.publication_time_utc for record in result.records
    }
    # 06:00 CET is 05:00Z; 06:00 CEST is 04:00Z (the CAM gas-day boundaries).
    assert published["2026-01-15"] == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
    assert published["2026-05-29"] == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)


def test_dst_ambiguous_local_times_are_refused_rather_than_folded() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv("25/10/2026;31.4;10;Final NGP;25/10/2026 02:30"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    # 02:30 on the fall-back night round-trips for both offsets to two different UTC instants;
    # with no official fold rule the row is refused, never silently folded to fold=0.
    assert result.records == ()
    assert [(row.row_number, row.reason) for row in result.rejections] == [
        (2, "ambiguous_local_timestamp")
    ]
    assert "02:30" in result.rejections[0].detail

    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())
    assert refusal.value.code == "rejected_rows_present"

    # Without a proven zone nothing is placed — and nothing is guessed either.
    pending = parse_eex_ttf_ngp_csv(
        _csv("25/10/2026;31.4;10;Final NGP;25/10/2026 02:30"),
        retrieved_at_utc=RETRIEVED_AT,
    )
    assert pending.rejections == ()
    assert pending.records[0].normalization_status == "pending_source_timezone"
    assert pending.records[0].publication_time_utc is None


def test_dst_nonexistent_local_times_are_refused_rather_than_normalized() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv("29/03/2026;31.4;10;Final NGP;29/03/2026 02:30"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    # 02:30 on the spring-forward night exists on no offset (the round trip lands on a different
    # wall clock for both folds); with no official gap rule the row is refused, not shifted.
    assert result.records == ()
    assert [(row.row_number, row.reason) for row in result.rejections] == [
        (2, "nonexistent_local_timestamp")
    ]
    assert "02:30" in result.rejections[0].detail

    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())
    assert refusal.value.code == "rejected_rows_present"


def test_canonical_mapping_refuses_without_a_separately_evidenced_delivery_calendar() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    # The publication zone is proven above, but its evidence proves nothing about which delivery
    # day the source labels `Gasday`: the delivery calendar is an independent requirement.
    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result)
    assert refusal.value.code == "unproven_gas_day_calendar"

    unattested = EexNgpGasDayCalendarContract(calendar_id=EU_CAM_UTC_CALENDAR, evidence="   ")
    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=unattested)
    assert refusal.value.code == "unattested_gas_day_calendar"

    unregistered = EexNgpGasDayCalendarContract(
        calendar_id="EEX-NGP-UNVERIFIED", evidence="synthetic test evidence"
    )
    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=unregistered)
    assert refusal.value.code == "unregistered_gas_day_calendar"


def test_the_supplied_delivery_calendar_drives_the_canonical_period() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    cam_utc = eex_ttf_ngp_market_observations(
        result, gas_day_calendar_contract=_gas_day_contract()
    )[0]
    assert cam_utc["period_start_utc"] == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert cam_utc["period_end_utc"] == datetime(2026, 5, 30, 4, 0, tzinfo=UTC)

    # A different *existing* calendar id (synthetic evidence in this test) produces its own
    # boundary, so the supplied contract drives the mapping rather than decorating it.
    legacy = eex_ttf_ngp_market_observations(
        result, gas_day_calendar_contract=_gas_day_contract(calendar_id=EU_CAM_CALENDAR)
    )[0]
    assert legacy["period_start_utc"] == datetime(2026, 5, 29, 3, 0, tzinfo=UTC)
    assert legacy["metadata_json"]["gas_day_calendar"] == EU_CAM_CALENDAR


def test_an_old_payload_is_never_marked_live_or_awarded_quality() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv("02/01/2024;31.400;1200.5;Final NGP;02/01/2024 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    row = eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())[0]

    # An arbitrarily old payload (retrieved years after publication, no proven freshness
    # expectation) must not be advertised as live or as fully-scored quality.
    assert row["freshness"] == ObservationFreshness.UNKNOWN.value
    assert row["freshness"] != ObservationFreshness.FRESH.value
    assert row["quality_score"] == 0.0
    metadata = row["metadata_json"]
    assert metadata["freshness_basis"] == "no_proven_source_freshness_expectation"
    assert metadata["quality_assessed"] is False
    assert metadata["quality_score_basis"] == "unassessed"


def test_a_large_but_finite_index_value_still_maps() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv(f"29/05/2026;1{'0' * 300};10;Final NGP;29/05/2026 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    row = eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())[0]

    assert row["price"] == 1e300
    assert row["metadata_json"]["index_value_exact"] == f"1{'0' * 300}"


def test_an_index_value_that_overflows_the_canonical_float_is_refused() -> None:
    result = parse_eex_ttf_ngp_csv(
        _csv(f"29/05/2026;1{'0' * 1000};10;Final NGP;29/05/2026 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )

    # The exact decimal is valid and survives for the raw/audit fields...
    assert result.rejections == ()
    assert result.records[0].index_value == Decimal(f"1{'0' * 1000}")

    # ...but the canonical Float price column must never receive an infinite value.
    with pytest.raises(EexNgpParseError) as refusal:
        eex_ttf_ngp_market_observations(result, gas_day_calendar_contract=_gas_day_contract())
    assert refusal.value.code == "index_value_float_overflow"
    assert "eex-ngp-ttf-2026-05-29-20260529T1430-final" in refusal.value.message


def test_a_governed_zone_contract_must_be_evidenced_and_match_source_and_dataset() -> None:
    payload = _csv("29/05/2026;31.4;10;Final NGP;29/05/2026 14:30")

    unattested = SourceTimezoneContract(
        source_system="EEX",
        datasets=(SOURCE_DATASET,),
        declared_zone=ZoneInfo("UTC"),
    )
    with pytest.raises(EexNgpParseError) as refusal:
        parse_eex_ttf_ngp_csv(payload, retrieved_at_utc=RETRIEVED_AT, timezone_contract=unattested)
    assert refusal.value.code == "unattested_timezone_contract"

    other_source = SourceTimezoneContract(
        source_system="ENTSOG",
        datasets=(SOURCE_DATASET,),
        declared_zone=ZoneInfo("Europe/Berlin"),
        evidence="synthetic test contract",
    )
    with pytest.raises(EexNgpParseError) as refusal:
        parse_eex_ttf_ngp_csv(
            payload, retrieved_at_utc=RETRIEVED_AT, timezone_contract=other_source
        )
    assert refusal.value.code == "timezone_contract_source_mismatch"

    other_dataset = SourceTimezoneContract(
        source_system="EEX",
        datasets=("some-other-eex-dataset",),
        declared_zone=ZoneInfo("Europe/Berlin"),
        evidence="synthetic test contract",
    )
    with pytest.raises(EexNgpParseError) as refusal:
        parse_eex_ttf_ngp_csv(
            payload, retrieved_at_utc=RETRIEVED_AT, timezone_contract=other_dataset
        )
    assert refusal.value.code == "timezone_contract_dataset_mismatch"


def test_a_naive_retrieval_timestamp_is_refused_not_read_as_utc() -> None:
    with pytest.raises(EexNgpParseError) as refusal:
        parse_eex_ttf_ngp_csv(
            _csv("29/05/2026;31.4;10;Final NGP;29/05/2026 14:30"),
            retrieved_at_utc=datetime(2026, 5, 29, 15, 5),
        )

    assert refusal.value.code == "naive_retrieval_timestamp"


def test_the_adapter_stays_pure() -> None:
    """No network, no database, no scheduler and no host-clock timestamp in the adapter."""

    source = MODULE_PATH.read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint(
        {
            "httpx",
            "requests",
            "socket",
            "sqlalchemy",
            "psycopg",
            "subprocess",
            "urllib",
            # Host-clock / host-platform readers: no implicit host assumption.
            "time",
            "platform",
            "os",
        }
    )
    assert "datetime.now(UTC)" in source
    assert "datetime.now()" not in source
