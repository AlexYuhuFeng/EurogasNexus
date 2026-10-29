"""RFC0006 stage A EEX TTF NGP receipt-bound observation tests.

Synthetic CSV only: no network, database, scheduler or captured live price. The delivery calendar
is always supplied explicitly with evidence from the source chain accepted in RFC0006; these test
strings are not source activation, certification or a rights claim.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from eurogas_nexus.domain.ingestion.source_timezone import SourceTimezoneContract
from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.domain.observations.market import ObservationFreshness
from eurogas_nexus.ingestion.eex_ngp import (
    RECEIPT_NORMALIZER_VERSION,
    SOURCE_DATASET,
    EexNgpGasDayCalendarContract,
    EexNgpParseError,
    eex_ttf_ngp_market_observations,
    eex_ttf_ngp_receipt_observations,
    parse_eex_ttf_ngp_csv,
)

RETRIEVED_AT = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)
LATE_RECEIPT = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)
HEADER = "Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let"
CALENDAR_EVIDENCE = (
    "RFC-0006 source chain: EEX Index Description v25 sections 1 and 2.5 describe Central "
    "European seasonal time and daily NGP semantics; EEX Contract Specifications 0105a section "
    "1.2.3 defines the gas delivery day at 06:00 Europe/Berlin, represented by EU-CAM-UTC-2025. "
    "Synthetic test evidence only; no rights certification or source activation."
)
RECEIPT_ID_PATTERN = re.compile(r"^eex-ngp-r1-[0-9a-f]{48}$")


def _csv(*rows: str) -> str:
    return "\ufeff" + "\n".join([HEADER, *rows]) + "\n"


def _parse(
    *rows: str,
    retrieved_at: datetime = RETRIEVED_AT,
    timezone_contract: SourceTimezoneContract | None = None,
):
    return parse_eex_ttf_ngp_csv(
        _csv(*rows),
        retrieved_at_utc=retrieved_at,
        timezone_contract=timezone_contract,
    )


def _governed_contract() -> SourceTimezoneContract:
    return SourceTimezoneContract(
        source_system="EEX",
        datasets=(SOURCE_DATASET,),
        declared_zone=ZoneInfo("Europe/Berlin"),
        evidence="synthetic test contract: exercise a mapped parser clock only",
    )


def _gas_day_contract() -> EexNgpGasDayCalendarContract:
    return EexNgpGasDayCalendarContract(
        calendar_id=EU_CAM_UTC_CALENDAR,
        evidence=CALENDAR_EVIDENCE,
    )


def _receipt_rows(result, *, received_at: datetime | None = None) -> list[dict]:
    return eex_ttf_ngp_receipt_observations(
        result,
        received_at_utc=RETRIEVED_AT if received_at is None else received_at,
        gas_day_calendar_contract=_gas_day_contract(),
    )


def test_receipt_mapping_uses_explicit_capture_availability_without_a_publication_clock() -> None:
    result = _parse("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30")

    row = _receipt_rows(result)[0]

    assert RECEIPT_ID_PATTERN.fullmatch(row["observation_id"])
    assert row["observation_id"] != result.records[0].observation_id
    assert row["source_record_id"] == "2026-05-29-20260529T1430-final"
    assert row["observed_at_utc"] == RETRIEVED_AT
    assert row["price"] == 31.4
    assert row["research_only"] is True

    metadata = row["metadata_json"]
    assert metadata["available_at_utc"] == RETRIEVED_AT.isoformat()
    assert metadata["availability_basis"] == "response_receipt"
    assert metadata["publication_time_basis"] == "unknown"
    assert metadata["publication_time_utc"] is None
    assert metadata["gas_day_raw"] == "29/05/2026"
    assert metadata["publication_timestamp_raw"] == "29/05/2026 14:30"
    assert metadata["revision_status"] == "final"
    assert metadata["revision_status_raw"] == "Final NGP"
    assert metadata["normalizer_version"] == RECEIPT_NORMALIZER_VERSION
    assert metadata["retrieved_at_utc"] == RETRIEVED_AT.isoformat()

    # A reference index, never an executable quote, with unearned freshness/quality withheld.
    assert metadata["contract_type"] == "index"
    assert metadata["price_type"] == "index"
    assert metadata["executable_quote"] is False
    assert metadata["research_only"] is True
    assert row["freshness"] == ObservationFreshness.UNKNOWN.value
    assert row["quality_score"] == 0.0
    assert metadata["quality_assessed"] is False
    assert metadata["quality_score_basis"] == "unassessed"

    # The independent delivery contract is explicit, not a defaulted calendar.
    assert metadata["gas_day_calendar"] == EU_CAM_UTC_CALENDAR
    assert metadata["gas_day_calendar_evidence"] == CALENDAR_EVIDENCE


def test_pending_publication_timezone_is_accepted_but_a_mapped_parser_clock_is_withheld() -> None:
    pending = _parse("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30")
    assert pending.records[0].normalization_status == "pending_source_timezone"
    assert pending.records[0].publication_time_utc is None
    assert _receipt_rows(pending)[0]["metadata_json"]["publication_time_utc"] is None

    mapped = _parse(
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
        timezone_contract=_governed_contract(),
    )
    assert mapped.records[0].publication_time_utc == datetime(2026, 5, 29, 12, 30, tzinfo=UTC)

    receipt_row = _receipt_rows(mapped)[0]
    assert receipt_row["observed_at_utc"] == RETRIEVED_AT
    assert receipt_row["metadata_json"]["publication_time_utc"] is None
    assert receipt_row["metadata_json"]["publication_time_basis"] == "unknown"

    # The old strict mapper still uses the proven publication clock and its original id namespace.
    strict_row = eex_ttf_ngp_market_observations(
        mapped, gas_day_calendar_contract=_gas_day_contract()
    )[0]
    assert strict_row["observed_at_utc"] == datetime(2026, 5, 29, 12, 30, tzinfo=UTC)
    assert strict_row["observation_id"] == "eex-ngp-ttf-2026-05-29-20260529T1430-final"
    assert strict_row["metadata_json"]["publication_time_utc"] == "2026-05-29T12:30:00+00:00"


def test_receipt_must_be_explicit_aware_and_match_the_parse_capture() -> None:
    result = _parse("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30")

    with pytest.raises(EexNgpParseError) as naive:
        _receipt_rows(result, received_at=RETRIEVED_AT.replace(tzinfo=None))
    assert naive.value.code == "naive_receipt_timestamp"

    with pytest.raises(EexNgpParseError) as mismatch:
        _receipt_rows(result, received_at=RETRIEVED_AT + timedelta(seconds=1))
    assert mismatch.value.code == "receipt_timestamp_mismatch"

    # A non-UTC aware receipt matching the same instant is normalized, not rejected.
    offset_receipt = RETRIEVED_AT.astimezone(ZoneInfo("Europe/Berlin"))
    normalized = _receipt_rows(result, received_at=offset_receipt)[0]
    assert normalized["observed_at_utc"] == RETRIEVED_AT
    assert normalized["observed_at_utc"].tzinfo is UTC
    assert normalized["metadata_json"]["available_at_utc"] == RETRIEVED_AT.isoformat()

    with pytest.raises(EexNgpParseError) as invalid:
        _receipt_rows(result, received_at="2026-05-29T15:05:00Z")  # type: ignore[arg-type]
    assert invalid.value.code == "receipt_timestamp_invalid"

    forged = replace(result, retrieved_at_utc=RETRIEVED_AT.replace(tzinfo=None))
    with pytest.raises(EexNgpParseError) as forged_refusal:
        _receipt_rows(forged)
    assert forged_refusal.value.code == "invalid_parse_result_receipt"

    signature = inspect.signature(eex_ttf_ngp_receipt_observations)
    assert signature.parameters["received_at_utc"].default is inspect.Parameter.empty


def test_requires_an_explicit_evidenced_registered_delivery_calendar() -> None:
    result = _parse("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30")

    with pytest.raises(EexNgpParseError) as missing:
        eex_ttf_ngp_receipt_observations(
            result,
            received_at_utc=RETRIEVED_AT,
            gas_day_calendar_contract=None,  # type: ignore[arg-type]
        )
    assert missing.value.code == "unproven_gas_day_calendar"

    unregistered = EexNgpGasDayCalendarContract(
        calendar_id="EEX-NGP-ASSUMED", evidence=CALENDAR_EVIDENCE
    )
    with pytest.raises(EexNgpParseError) as unknown:
        eex_ttf_ngp_receipt_observations(
            result,
            received_at_utc=RETRIEVED_AT,
            gas_day_calendar_contract=unregistered,
        )
    assert unknown.value.code == "unregistered_gas_day_calendar"

    unattested = EexNgpGasDayCalendarContract(
        calendar_id=EU_CAM_UTC_CALENDAR, evidence="   "
    )
    with pytest.raises(EexNgpParseError) as blank:
        eex_ttf_ngp_receipt_observations(
            result,
            received_at_utc=RETRIEVED_AT,
            gas_day_calendar_contract=unattested,
        )
    assert blank.value.code == "unattested_gas_day_calendar"


def test_exact_long_precision_and_negative_published_prices_survive() -> None:
    result = _parse(
        "29/05/2026;31.123456789012345678901234567890;1200.500000000000000001;"
        "Final NGP;29/05/2026 14:30",
        "29/05/2026;-12.5000000000000000001;42.25;Temporary NGP;29/05/2026 14:45",
    )

    positive, negative = _receipt_rows(result)

    assert positive["price"] == float(Decimal("31.123456789012345678901234567890"))
    assert positive["metadata_json"]["index_value_raw"] == (
        "31.123456789012345678901234567890"
    )
    assert positive["metadata_json"]["index_value_exact"] == (
        "31.123456789012345678901234567890"
    )
    assert positive["metadata_json"]["index_volume_mwh_exact"] == "1200.500000000000000001"

    # A negative published index is valid source evidence, not a missing/zero price.
    assert negative["price"] == float(Decimal("-12.5000000000000000001"))
    assert negative["price"] < 0
    assert negative["metadata_json"]["revision_status"] == "temporary"
    assert negative["metadata_json"]["provisional"] is True
    assert negative["metadata_json"]["index_value_exact"] == "-12.5000000000000000001"


def test_unavailable_rows_stay_unavailable_and_empty_or_all_zero_payloads_refuse() -> None:
    result = _parse(
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
        "29/05/2026;0;0;Temporary NGP;29/05/2026 14:45",
        "29/05/2026;;1200.5;Final NGP;29/05/2026 15:00",
        "29/05/2026;31.5;;Final NGP;29/05/2026 15:15",
    )

    assert [record.unavailable_reason for record in result.records] == [
        None,
        "zero_volume",
        "missing_index_value",
        "missing_index_volume",
    ]
    assert [row["source_record_id"] for row in _receipt_rows(result)] == [
        "2026-05-29-20260529T1430-final"
    ]

    all_unavailable = _parse("29/05/2026;0;0;Temporary NGP;29/05/2026 14:45")
    with pytest.raises(EexNgpParseError) as no_price:
        _receipt_rows(all_unavailable)
    assert no_price.value.code == "no_priced_rows"

    empty = _parse()
    assert empty.records == ()
    with pytest.raises(EexNgpParseError) as empty_refusal:
        _receipt_rows(empty)
    assert empty_refusal.value.code == "no_priced_rows"

    rejected = _parse("29/05/2026;not-a-number;1200.5;Final NGP;29/05/2026 14:30")
    assert rejected.rejections
    with pytest.raises(EexNgpParseError) as rejected_rows:
        _receipt_rows(rejected)
    assert rejected_rows.value.code == "rejected_rows_present"


def test_an_exact_decimal_that_overflows_the_canonical_float_is_refused() -> None:
    result = _parse(f"29/05/2026;1{'0' * 1000};10;Final NGP;29/05/2026 14:30")

    with pytest.raises(EexNgpParseError) as overflow:
        _receipt_rows(result)
    assert overflow.value.code == "index_value_float_overflow"


def test_receipt_bound_delivery_days_preserve_the_23_and_25_hour_dst_windows() -> None:
    result = _parse(
        "28/03/2026;31.4;10;Final NGP;28/03/2026 12:00",
        "24/10/2026;31.5;10;Final NGP;24/10/2026 12:00",
        retrieved_at=LATE_RECEIPT,
    )

    spring, autumn = _receipt_rows(result, received_at=LATE_RECEIPT)

    assert spring["period_start_utc"] == datetime(2026, 3, 28, 5, 0, tzinfo=UTC)
    assert spring["period_end_utc"] == datetime(2026, 3, 29, 4, 0, tzinfo=UTC)
    assert spring["period_end_utc"] - spring["period_start_utc"] == timedelta(hours=23)

    assert autumn["period_start_utc"] == datetime(2026, 10, 24, 4, 0, tzinfo=UTC)
    assert autumn["period_end_utc"] == datetime(2026, 10, 25, 5, 0, tzinfo=UTC)
    assert autumn["period_end_utc"] - autumn["period_start_utc"] == timedelta(hours=25)


def test_receipt_identity_is_deterministic_and_independent_of_receipt_and_price() -> None:
    first = _parse(
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
        retrieved_at=RETRIEVED_AT,
    )
    replay = _parse(
        "29/05/2026;31.900;1300.0;Final NGP;29/05/2026 14:30",
        retrieved_at=RETRIEVED_AT + timedelta(days=2),
    )
    other_minute = _parse(
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:31",
        retrieved_at=RETRIEVED_AT,
    )

    first_row = _receipt_rows(first)[0]
    replay_row = _receipt_rows(replay, received_at=RETRIEVED_AT + timedelta(days=2))[0]
    other_row = _receipt_rows(other_minute)[0]

    assert first_row["observation_id"] == replay_row["observation_id"]
    assert first_row["source_record_id"] == replay_row["source_record_id"]
    assert first_row["price"] != replay_row["price"]
    assert first_row["observed_at_utc"] != replay_row["observed_at_utc"]
    assert first_row["observation_id"] != other_row["observation_id"]

    assert RECEIPT_ID_PATTERN.fullmatch(first_row["observation_id"])
    assert RECEIPT_ID_PATTERN.fullmatch(other_row["observation_id"])
    # Original and receipt-bound representations never share an id.
    assert first_row["observation_id"] != first.records[0].observation_id

    # Replaying the same capture yields equal rows; no receipt/price enters the identity hash.
    assert _receipt_rows(first) == _receipt_rows(first)


def test_strict_mapper_remains_publication_bound_and_refuses_a_pending_zone() -> None:
    result = _parse("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30")

    assert result.timezone_contract.declared_zone is None
    with pytest.raises(EexNgpParseError) as pending:
        eex_ttf_ngp_market_observations(
            result, gas_day_calendar_contract=_gas_day_contract()
        )
    assert pending.value.code == "unproven_publication_timezone"
    assert result.records[0].publication_time_utc is None
