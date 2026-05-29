"""Public source ingestion parsing tests (no live network calls)."""

from datetime import UTC, datetime

from eurogas_nexus.ingestion.public_sources import (
    ecb_market_observations_from_xml,
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
                "updatedAt": "2026-05-29 12:00:00",
            }
        ]
    }

    rows = gie_storage_observations_from_json(payload)

    assert rows[0]["observation_id"] == "gie-agsi-EU-2026-05-29"
    assert rows[0]["source_system"] == "GIE"
    assert rows[0]["source_dataset"] == "AGSI"
    assert rows[0]["inventory_twh"] == 650.25
    assert rows[0]["fill_pct"] == 59.1
    assert rows[0]["freshness"] == "live"


def test_gie_alsi_json_is_normalized_into_lng_observations() -> None:
    payload = {
        "data": [
            {
                "code": "EU",
                "name": "EU LNG",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "inventory": "42.5",
                "sendOut": "3.4",
                "dtmi": "65.0",
                "updatedAt": "2026-05-29 12:00:00",
            }
        ]
    }

    rows = gie_lng_observations_from_json(payload)

    assert rows[0]["observation_id"] == "gie-alsi-EU-2026-05-29"
    assert rows[0]["source_system"] == "GIE"
    assert rows[0]["source_dataset"] == "ALSI"
    assert rows[0]["inventory_twh"] == 42.5
    assert rows[0]["send_out_twh_d"] == 3.4
    assert rows[0]["freshness"] == "live"
