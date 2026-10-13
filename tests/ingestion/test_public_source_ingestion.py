"""Public source ingestion parsing tests (no live network calls)."""

from datetime import UTC, datetime

import pytest

from eurogas_nexus.domain.ingestion.source_timezone import SourceTimezoneError
from eurogas_nexus.ingestion.public_sources import (
    ecb_market_observations_from_xml,
    entsog_capacity_observations_from_json,
    entsog_flow_observations_from_json,
    gie_lng_observations_from_json,
    gie_storage_observations_from_json,
)


def test_ecb_xml_is_normalized_into_market_observations() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <gesmes:Envelope
      xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
      xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
      <Cube>
        <Cube time="2026-05-29">
          <Cube currency="USD" rate="1.0850"/>
          <Cube currency="GBP" rate="0.8510"/>
        </Cube>
      </Cube>
    </gesmes:Envelope>
    """

    rows = ecb_market_observations_from_xml(
        xml,
        observed_at_utc=datetime(2026, 5, 29, 15, 0, tzinfo=UTC),
    )

    assert [row["observation_id"] for row in rows] == [
        "ecb-fx-2026-05-29-GBP",
        "ecb-fx-2026-05-29-USD",
    ]
    assert rows[0]["source_system"] == "ECB"
    assert rows[0]["market_venue"] == "ECB"
    assert rows[0]["product"] == "EUR/GBP"
    assert rows[0]["price"] == 0.851
    assert rows[0]["freshness"] == "live"


def test_entsog_json_is_normalized_into_flow_observations() -> None:
    payload = {
        "operationaldatas": [
            {
                "id": "123",
                "pointKey": "be-zee",
                "pointLabel": "Zeebrugge",
                "directionKey": "entry",
                "indicator": "Physical Flow",
                "unit": "kWh/d",
                "value": "10550000",
                "periodFrom": "2026-05-29T06:00:00+02:00",
                "periodTo": "2026-05-30T06:00:00+02:00",
                "lastUpdateDateTime": "2026-05-29T07:00:00+02:00",
            }
        ]
    }

    rows = entsog_flow_observations_from_json(payload)

    assert len(rows) == 1
    assert rows[0]["observation_id"] == "entsog-flow-123"
    assert rows[0]["source_system"] == "ENTSOG"
    assert rows[0]["point_id"] == "be-zee"
    assert rows[0]["point_name"] == "Zeebrugge"
    assert rows[0]["flow_mcm_d"] == 1.0
    assert rows[0]["freshness"] == "live"
    # Offset input is converted to UTC. The naive/CET/CEST/WET cases, and the fail-closed rule for a
    # zone the contract does not support, are asserted in
    # `tests/ingestion/test_source_timezone_contract.py` (M1-P0).
    assert rows[0]["period_start_utc"] == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert rows[0]["period_end_utc"] == datetime(2026, 5, 30, 4, 0, tzinfo=UTC)


def test_entsog_naive_periods_are_read_on_the_central_european_clock() -> None:
    """The defect M1-P0 named: a bare 06:00 is 05:00Z in winter, not 06:00Z."""

    payload = {
        "operationaldatas": [
            {
                "id": "123",
                "pointKey": "be-zee",
                "pointLabel": "Zeebrugge",
                "directionKey": "entry",
                "indicator": "Physical Flow",
                "unit": "kWh/d",
                "value": "10550000",
                "periodFrom": "2026-01-15T06:00:00",
                "periodTo": "2026-01-16T06:00:00",
            }
        ]
    }

    rows = entsog_flow_observations_from_json(payload)

    assert rows[0]["period_start_utc"] == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
    assert rows[0]["period_end_utc"] == datetime(2026, 1, 16, 5, 0, tzinfo=UTC)


def test_entsog_operational_indicators_are_not_mixed_between_flow_and_capacity() -> None:
    common = {
        "pointKey": "be-zee",
        "pointLabel": "Zeebrugge",
        "directionKey": "entry",
        "unit": "kWh/d",
        "periodFrom": "2026-05-29T06:00:00+02:00",
        "periodTo": "2026-05-30T06:00:00+02:00",
        "lastUpdateDateTime": "2026-05-29T07:00:00+02:00",
    }
    payload = {
        "operationaldatas": [
            {**common, "id": "flow", "indicator": "Physical Flow", "value": "10550000"},
            {
                **common,
                "id": "technical",
                "indicator": "Firm Technical Capacity",
                "value": "21100000",
            },
            {**common, "id": "booked", "indicator": "Firm Booked", "value": "15825000"},
            {**common, "id": "gcv", "indicator": "GCV", "value": "11.2"},
        ]
    }

    flow_rows = entsog_flow_observations_from_json(payload)
    capacity_rows = entsog_capacity_observations_from_json(payload)

    assert [row["observation_id"] for row in flow_rows] == ["entsog-flow-flow"]
    assert [row["capacity_type"] for row in capacity_rows] == [
        "firm_technical",
        "firm_booked",
    ]
    assert capacity_rows[0]["capacity_mcm_d"] == 2.0
    assert capacity_rows[1]["capacity_mcm_d"] == 1.5


def test_gie_agsi_json_is_normalized_into_storage_observations() -> None:
    payload = {
        "data": [
            {
                "code": "EU",
                "name": "EU",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "gasInStorage": "650.25",
                "workingGasVolume": "1100.50",
                "full": "59.1",
                "injection": "2.5",
                "withdrawal": "1.2",
                "updatedAt": "2026-05-29T14:00:00+02:00",
            }
        ]
    }

    rows = gie_storage_observations_from_json(payload)

    assert rows[0]["observation_id"] == "gie-agsi-EU-2026-05-29"
    assert rows[0]["source_system"] == "GIE"
    assert rows[0]["source_dataset"] == "AGSI"
    assert rows[0]["inventory_twh"] == 650.25
    assert rows[0]["fill_pct"] == 59.1
    assert rows[0]["injection_twh_d"] == 0.0025
    assert rows[0]["withdrawal_twh_d"] == 0.0012
    assert rows[0]["freshness"] == "live"
    assert rows[0]["period_start_utc"] == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert rows[0]["period_end_utc"] == datetime(2026, 5, 30, 4, 0, tzinfo=UTC)
    assert rows[0]["metadata_json"]["calendar_version"] == "EU-CAM-UTC-2025"


def _gie_agsi_payload(*, updated_at: str) -> dict:
    return {
        "data": [
            {
                "code": "EU",
                "name": "EU",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "gasInStorage": "650.25",
                "workingGasVolume": "1100.50",
                "full": "59.1",
                "updatedAt": updated_at,
            }
        ]
    }


def _gie_alsi_payload(*, updated_at: str) -> dict:
    return {
        "data": [
            {
                "code": "EU",
                "name": "EU LNG",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "inventory": {"lng": "9.5", "gwh": "42.5"},
                "sendOut": "3.4",
                "dtmi": {"lng": "14.4", "gwh": "65.0"},
                "updatedAt": updated_at,
            }
        ]
    }


def test_gie_agsi_bare_updated_at_is_not_read_as_utc_and_uses_the_receipt() -> None:
    """The live provider sends a bare ``updatedAt``; the receipt substitutes, visibly."""

    receipt = datetime(2026, 10, 9, 22, 45, tzinfo=UTC)

    rows = gie_storage_observations_from_json(
        _gie_agsi_payload(updated_at="2026-05-29 12:00:00"),
        observed_at_utc=receipt,
    )

    assert rows[0]["observed_at_utc"] == receipt
    assert rows[0]["observed_at_utc"] != datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    assert rows[0]["metadata_json"]["availability_basis"] == "response_receipt"
    assert rows[0]["metadata_json"]["provider_updated_at_zone"] == "unproven"
    # The provider's own stamp is preserved verbatim for later reconciliation.
    assert rows[0]["metadata_json"]["updatedAt"] == "2026-05-29 12:00:00"


def test_gie_agsi_offset_updated_at_is_trusted_and_marked_proven() -> None:
    receipt = datetime(2026, 10, 9, 22, 45, tzinfo=UTC)

    rows = gie_storage_observations_from_json(
        _gie_agsi_payload(updated_at="2026-05-29T14:00:00+02:00"),
        observed_at_utc=receipt,
    )

    assert rows[0]["observed_at_utc"] == datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    assert rows[0]["metadata_json"]["availability_basis"] == "provider_updated_at"
    assert rows[0]["metadata_json"]["provider_updated_at_zone"] == "provider_offset"


def test_gie_alsi_bare_updated_at_uses_the_receipt() -> None:
    receipt = datetime(2026, 10, 9, 22, 45, tzinfo=UTC)

    rows = gie_lng_observations_from_json(
        _gie_alsi_payload(updated_at="2026-05-29 12:00:00"),
        observed_at_utc=receipt,
    )

    assert rows[0]["observed_at_utc"] == receipt
    assert rows[0]["metadata_json"]["availability_basis"] == "response_receipt"


def test_gie_alsi_bare_updated_at_without_a_receipt_is_refused() -> None:
    """No receipt means no substitute: the M1-P0 refusal is preserved."""

    with pytest.raises(SourceTimezoneError) as refusal:
        gie_lng_observations_from_json(
            _gie_alsi_payload(updated_at="2026-05-29 12:00:00")
        )

    assert refusal.value.code == "unprovable_source_timezone"


def test_gie_duplicate_and_revised_records_share_one_natural_key() -> None:
    """A revised record is not a new row: the natural key is product+code+gas day."""

    receipt = datetime(2026, 10, 9, 22, 45, tzinfo=UTC)
    original = _gie_agsi_payload(updated_at="2026-05-29T10:00:00+02:00")["data"][0]
    revised = {**original, "gasInStorage": "700.00", "updatedAt": "2026-05-29T14:00:00+02:00"}

    rows = gie_storage_observations_from_json(
        {"data": [original, revised]}, observed_at_utc=receipt
    )

    assert len(rows) == 2
    assert {row["observation_id"] for row in rows} == {"gie-agsi-EU-2026-05-29"}
    assert {row["inventory_twh"] for row in rows} == {650.25, 700.0}
    assert {row["period_start_utc"] for row in rows} == {
        datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    }


def test_gie_alsi_json_is_normalized_into_lng_observations() -> None:
    payload = {
        "data": [
            {
                "code": "EU",
                "name": "EU LNG",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "inventory": {"lng": "9.5", "gwh": "42.5"},
                "sendOut": "3.4",
                "dtmi": {"lng": "14.4", "gwh": "65.0"},
                "updatedAt": "2026-05-29T14:00:00+02:00",
            }
        ]
    }

    rows = gie_lng_observations_from_json(payload)

    assert rows[0]["observation_id"] == "gie-alsi-EU-2026-05-29"
    assert rows[0]["source_system"] == "GIE"
    assert rows[0]["source_dataset"] == "ALSI"
    assert rows[0]["inventory_twh"] == 0.0425
    assert rows[0]["send_out_twh_d"] == 0.0034
    assert rows[0]["dtmi_twh"] == 0.065
    assert rows[0]["freshness"] == "live"
    assert rows[0]["period_start_utc"] == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert rows[0]["period_end_utc"] == datetime(2026, 5, 30, 4, 0, tzinfo=UTC)
    assert rows[0]["metadata_json"]["calendar_version"] == "EU-CAM-UTC-2025"
