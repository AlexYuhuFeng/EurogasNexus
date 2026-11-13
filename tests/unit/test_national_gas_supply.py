"""GB storage and LNG from the National Gas portal: parsing rules, no network."""

from __future__ import annotations

from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from eurogas_nexus.ingestion.national_gas_supply import (
    ITEMS,
    NationalGasSupplyError,
    build_supply_url,
    parse_national_gas_supply_csv,
)

HEADER = "Applicable At,Applicable For,Data Item,Value,Generated Time,Quality Indicator\n"
RECEIVED = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)
STOCK = '"Storage, Daily Aggregated Stock level, D+1"'
LNG_STOCK = '"LNG, Daily Aggregated Stock level, D+1"'
ENTRY_ALLOC = '"Allocations, Energy, Storage Entry Total, D+2"'
EXIT_ALLOC = '"Allocations, Energy, Storage Exit Total, D+2"'
LNG_ALLOC = '"Allocations, Energy, LNG Importation Total, D+2"'
ENTRY_NOM = '"Nominations, Aggregate Prevailing Nomination, Storage Entry Total"'
LNG_NOM = '"Nominations, Aggregate Prevailing Nomination, LNG Importation Total"'


def _parse(*lines: str, first=date(2026, 11, 10), last=date(2026, 11, 11)):
    return parse_national_gas_supply_csv(
        HEADER + "\n".join(lines) + "\n",
        first_gas_day=first,
        last_gas_day=last,
        received_at_utc=RECEIVED,
    )


def test_allocations_convert_kwh_to_twh_and_win_over_nominations() -> None:
    storage, lng = _parse(
        f"11/11/2026 04:00:00,10/11/2026,{ENTRY_NOM},437101972,11/11/2026 04:20:12,",
        f"11/11/2026 23:30:00,10/11/2026,{ENTRY_ALLOC},437286082,11/11/2026 23:30:05,",
        f"11/11/2026 23:30:00,10/11/2026,{EXIT_ALLOC},100,11/11/2026 23:30:05,",
        f"11/11/2026 04:00:00,10/11/2026,{LNG_NOM},581252879,11/11/2026 04:20:12,",
        f"11/11/2026 23:30:00,10/11/2026,{LNG_ALLOC},581312357,11/11/2026 23:30:05,",
    )
    (row,) = storage
    assert row["withdrawal_twh_d"] == pytest.approx(0.437286082, abs=0)
    assert row["injection_twh_d"] == pytest.approx(1e-7)
    assert row["metadata_json"]["basis"] == {
        "withdrawal_twh_d": "allocation",
        "injection_twh_d": "allocation",
    }
    assert row["metadata_json"]["publication_ids"]["withdrawal_twh_d"] == "PUBOBJ517"
    assert row["metadata_json"]["provisional"] is False
    assert row["working_capacity_twh"] is None and row["fill_pct"] is None
    assert row["inventory_twh"] is None  # no stock labelled 11/11 in this payload
    (lng_row,) = lng
    assert lng_row["send_out_twh_d"] == 0.581312357
    assert lng_row["dtmi_twh"] is None
    assert lng_row["metadata_json"]["basis"] == {"send_out_twh_d": "allocation"}


def test_nomination_is_used_and_marked_provisional_without_an_allocation() -> None:
    storage, lng = _parse(
        f"12/11/2026 04:00:00,11/11/2026,{ENTRY_NOM},213262033,12/11/2026 04:20:12,",
        f"12/11/2026 04:00:00,11/11/2026,{LNG_NOM},544389790,12/11/2026 04:20:12,",
    )
    assert storage[0]["withdrawal_twh_d"] == 0.213262033
    assert storage[0]["metadata_json"]["basis"] == {"withdrawal_twh_d": "nomination_provisional"}
    assert storage[0]["metadata_json"]["publication_ids"] == {"withdrawal_twh_d": "PUBOBJ1149"}
    assert storage[0]["metadata_json"]["provisional"] is True
    assert lng[0]["metadata_json"]["basis"] == {"send_out_twh_d": "nomination_provisional"}


def test_within_day_nomination_is_not_an_end_of_day_value() -> None:
    storage, lng = _parse(
        f"11/11/2026 09:00:00,11/11/2026,{ENTRY_NOM},62439882,11/11/2026 09:20:11,",
    )
    assert storage == [] and lng == []


def test_stock_labelled_x_is_the_closing_stock_of_gas_day_x_minus_1() -> None:
    storage, lng = _parse(
        # Labelled 10/11: closing stock of 9/11, outside the requested gas days.
        f"10/11/2026 15:30:00,10/11/2026,{STOCK},10406697092,10/11/2026 15:31:00,L",
        f"11/11/2026 15:30:00,11/11/2026,{STOCK},9969071446,11/11/2026 15:31:00,L",
        f"12/11/2026 15:30:00,12/11/2026,{LNG_STOCK},8854288460,12/11/2026 15:31:01,L",
    )
    assert [row["metadata_json"]["gas_day"] for row in storage] == ["2026-11-10"]
    assert storage[0]["inventory_twh"] == 9.969071446
    assert storage[0]["withdrawal_twh_d"] is None  # a day with only stock still yields a row
    assert storage[0]["metadata_json"]["basis"] == {"inventory_twh": "stock_level_d_plus_1"}
    assert storage[0]["metadata_json"]["quality_indicators"] == {"inventory_twh": "L"}
    assert lng[0]["metadata_json"]["gas_day"] == "2026-11-11"
    assert lng[0]["inventory_twh"] == 8.85428846
    start, end = storage[0]["period_start_utc"], storage[0]["period_end_utc"]
    assert start == datetime(2026, 11, 10, 5, tzinfo=UTC)
    assert end == datetime(2026, 11, 11, 5, tzinfo=UTC)


def test_rows_carry_the_gie_shape_and_deterministic_ids() -> None:
    line = f"11/11/2026 23:30:00,10/11/2026,{ENTRY_ALLOC},437286082,11/11/2026 23:30:05,"
    first, _ = _parse(line)
    again, _ = _parse(line)
    row = first[0]
    assert row["observation_id"] == again[0]["observation_id"]
    assert row["observation_id"] == "national-gas-storage-GB-2026-11-10"
    assert len(row["observation_id"]) <= 64 and len(row["source_dataset"]) <= 16
    assert set(row) == {
        "observation_id", "source_dataset", "facility_id", "facility_name", "country",
        "inventory_twh", "working_capacity_twh", "fill_pct", "injection_twh_d",
        "withdrawal_twh_d", "period_start_utc", "period_end_utc", "observed_at_utc",
        "source_system", "source_reference", "source_record_id", "freshness",
        "research_only", "metadata_json",
    }
    assert row["country"] == "GB" and row["source_system"] == "NATIONAL_GAS"
    assert row["facility_id"] == "GB-NTS-STORAGE"
    assert row["observed_at_utc"] == RECEIVED  # receipt, not backdated


def test_latest_applicable_at_wins_for_a_repeated_item() -> None:
    storage, _ = _parse(
        f"11/11/2026 23:30:00,10/11/2026,{ENTRY_ALLOC},400000000,11/11/2026 23:30:05,",
        f"12/11/2026 23:30:00,10/11/2026,{ENTRY_ALLOC},437286082,12/11/2026 23:30:05,A",
    )
    assert storage[0]["withdrawal_twh_d"] == 0.437286082


def test_unknown_label_is_an_error() -> None:
    with pytest.raises(NationalGasSupplyError, match="UNKNOWN_SERIES"):
        _parse('11/11/2026 15:30:00,11/11/2026,"LNG, Daily Aggregated Outflows, D+1",1,'
               "11/11/2026 15:31:00,")


def test_header_drift_and_rows_outside_the_window_are_errors() -> None:
    with pytest.raises(NationalGasSupplyError, match="HEADER_DRIFT"):
        parse_national_gas_supply_csv(
            "Applicable For,Data Item,Value\n",
            first_gas_day=date(2026, 11, 10),
            last_gas_day=date(2026, 11, 11),
            received_at_utc=RECEIVED,
        )
    with pytest.raises(NationalGasSupplyError, match="ROW_OUTSIDE_WINDOW"):
        _parse(f"02/11/2026 23:30:00,01/11/2026,{ENTRY_ALLOC},1,02/11/2026 23:30:05,")


def test_one_request_covers_every_item_and_the_stock_label_day() -> None:
    query = parse_qs(urlsplit(build_supply_url(date(2026, 11, 3), date(2026, 11, 12))).query)
    assert query["dateFrom"] == ["2026-11-03"] and query["dateTo"] == ["2026-11-13"]
    assert query["ids"] == [",".join(item.item_id for item in ITEMS)]
    assert query["latestFlag"] == ["Y"]
