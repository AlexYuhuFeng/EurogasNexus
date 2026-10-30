"""REMIT gas UMMs: ACER fields from JSON or CSV, versions, dismissals and the outage view."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.domain.observations.remit_umm import (
    UmmParseError,
    current_messages,
    outage_view,
    parse_umm_export,
)

NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)


def _message(message_id, version, start, stop, status="Active", unavailable=20.0):
    return {
        "messageId": message_id,
        "version": version,
        "publicationDateTime": (NOW - timedelta(hours=10 - version)).isoformat(),
        "eventStatus": status,
        "unavailabilityType": "Unplanned",
        "eventStart": start.isoformat(),
        "eventStop": stop.isoformat() if stop else None,
        "affectedAsset": {"name": "Troll", "eic": "21W000000000001X"},
        "affectedAssetType": "Production facility",
        "balancingZone": ["NO"],
        "unitMeasure": "MSm3/d",
        "technicalCapacity": 120.0,
        "unavailableCapacity": unavailable,
        "unavailabilityReason": "Compressor trip",
        "marketParticipant": {"name": "Equinor"},
    }


def test_json_export_keeps_acer_fields_and_latest_version_wins():
    payload = {
        "messages": [
            _message("GASSCO-1", 1, NOW - timedelta(hours=2), NOW + timedelta(days=1)),
            _message(
                "GASSCO-1", 2, NOW - timedelta(hours=2), NOW + timedelta(days=3), unavailable=35
            ),
            _message("GASSCO-2", 1, NOW + timedelta(days=5), NOW + timedelta(days=6)),
            _message("GASSCO-3", 2, NOW - timedelta(days=1), None, status="Dismissed"),
        ]
    }
    messages = parse_umm_export(json.dumps(payload), source_reference="fixture")
    assert len(messages) == 4
    first = messages[0]
    assert first.asset_name == "Troll" and first.asset_eic == "21W000000000001X"
    assert first.asset_type == "production" and first.unavailability_type == "unplanned"
    assert first.balancing_zone == "NO" and first.market_participant == "Equinor"
    assert first.unavailable_mcm_d == 20.0 and first.unavailable_gwh_d is None

    live = {m.message_id: m for m in current_messages(messages)}
    assert set(live) == {"GASSCO-1", "GASSCO-2"}
    assert live["GASSCO-1"].version == 2 and live["GASSCO-1"].unavailable_capacity == 35

    rows = outage_view(messages, now=NOW)
    assert [(r["event_id"], r["status"]) for r in rows] == [
        ("GASSCO-1", "active"),
        ("GASSCO-2", "scheduled"),
    ]
    assert rows[0]["capacity_impact_mcm_d"] == 35 and rows[0]["source_system"] == "REMIT"


def test_csv_export_energy_units_and_derived_unavailable():
    text = (
        "Message ID,Version,Publication date,Event status,Type of unavailability,Event start,"
        "Event stop,Affected asset name,Affected asset type,Balancing zone,Unit measure,"
        "Technical capacity,Available capacity,Unavailability reason\n"
        "EEX-9,1,2026-10-29T08:00:00Z,Active,Planned,2026-11-02T05:00:00Z,"
        "2026-11-04T05:00:00Z,Rehden,Storage,THE,GWh/d,250,100,Maintenance\n"
    )
    (message,) = parse_umm_export(text, source_reference="eex.csv")
    assert message.unavailable_capacity == 150 and message.unavailable_gwh_d == 150
    assert message.unavailable_mcm_d is None
    assert message.asset_type == "storage" and message.unavailability_type == "planned"
    # Ended or beyond the horizon: not shown.
    assert outage_view([message], now=datetime(2026, 11, 5, tzinfo=UTC)) == []
    assert outage_view([message], now=NOW, horizon_days=1) == []


def test_unreadable_messages_refuse_the_whole_file():
    with pytest.raises(UmmParseError):
        parse_umm_export('[{"eventStart": "2026-11-01T00:00:00Z"}]', source_reference="x")
    with pytest.raises(UmmParseError):
        parse_umm_export('[{"messageId": "a", "eventStart": "tomorrow"}]', source_reference="x")
    with pytest.raises(UmmParseError):
        parse_umm_export("", source_reference="x")
