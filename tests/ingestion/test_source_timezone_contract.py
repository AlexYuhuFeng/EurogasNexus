"""The source timezone contract (commercial readiness item M1-P0).

The defect this file pins: the parser read any timestamp without an offset as UTC, so an ENTSOG gas
day published as ``06:00`` on the Central European clock became ``06:00Z`` - an hour early in winter
and two hours early in summer. That is not a formatting detail; it moves every flow and capacity
period off the gas day the rest of the platform uses.

The rule now has one home and both halves are tested here: an instant that can be placed in time is
placed on the strength of the declaration, and an instant whose zone cannot be proven is **refused**
rather than assumed to be UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eurogas_nexus.domain.ingestion.source_timezone import (
    SOURCE_TIMEZONE_CONTRACTS,
    SourceTimezoneError,
    contract_for,
    parse_source_instant,
    resolve_payload_zone,
)
from eurogas_nexus.ingestion.public_sources import (
    entsog_capacity_observations_from_json,
    entsog_flow_observations_from_json,
    gie_storage_observations_from_json,
)

ENTSOG = contract_for("ENTSOG", "operationaldatas")


def _record(**overrides: str) -> dict[str, str]:
    record = {
        "id": "1",
        "pointKey": "be-zee",
        "pointLabel": "Zeebrugge",
        "directionKey": "entry",
        "indicator": "Physical Flow",
        "unit": "kWh/d",
        "value": "10550000",
        "periodFrom": "2026-01-15T06:00:00",
        "periodTo": "2026-01-16T06:00:00",
    }
    record.update(overrides)
    return record


def test_every_declared_source_states_its_evidence() -> None:
    for contract in SOURCE_TIMEZONE_CONTRACTS:
        assert contract.evidence.strip(), contract.source_system
        assert contract.source_system.strip(), contract


def test_the_entsog_zone_is_the_central_european_clock_the_gas_day_uses() -> None:
    """Winter 06:00 CET is 05:00Z and summer 06:00 CEST is 04:00Z - the CAM gas-day boundaries."""

    # CET (fixture: winter).
    assert parse_source_instant(
        "2026-01-15T06:00:00", contract=ENTSOG, zone=ENTSOG.declared_zone
    ) == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)

    # CEST (fixture: summer).
    assert parse_source_instant(
        "2026-05-29T06:00:00", contract=ENTSOG, zone=ENTSOG.declared_zone
    ) == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)


def test_a_naive_value_is_read_in_the_declared_zone_never_as_utc() -> None:
    winter = parse_source_instant("2026-01-15T06:00:00", contract=ENTSOG, zone=ENTSOG.declared_zone)
    summer = parse_source_instant("2026-05-29T06:00:00", contract=ENTSOG, zone=ENTSOG.declared_zone)

    # The old parser produced exactly these two values, and they are wrong:
    assert winter != datetime(2026, 1, 15, 6, 0, tzinfo=UTC)
    assert summer != datetime(2026, 5, 29, 6, 0, tzinfo=UTC)
    assert winter == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
    assert summer == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)


def test_an_explicit_offset_is_trusted_and_never_reinterpreted() -> None:
    """WET and any other stated offset are the provider's own statement."""

    # +00:00 (WET, winter) - an offset of zero is still an explicit statement.
    assert parse_source_instant(
        "2026-01-15T06:00:00+00:00", contract=ENTSOG, zone=ENTSOG.declared_zone
    ) == datetime(2026, 1, 15, 6, 0, tzinfo=UTC)
    # +01:00 (CET stated) and +02:00 (CEST stated).
    assert parse_source_instant(
        "2026-01-15T06:00:00+01:00", contract=ENTSOG, zone=ENTSOG.declared_zone
    ) == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
    assert parse_source_instant(
        "2026-05-29T06:00:00+02:00", contract=ENTSOG, zone=ENTSOG.declared_zone
    ) == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    # Z is UTC, whatever the declaration says.
    assert parse_source_instant(
        "2026-01-15T06:00:00Z", contract=ENTSOG, zone=ENTSOG.declared_zone
    ) == datetime(2026, 1, 15, 6, 0, tzinfo=UTC)


def test_the_daylight_saving_boundaries_are_handled_by_the_zone_not_by_an_offset() -> None:
    """The EU rule, not a fixed +01:00: 2026 switches on 29 March and 25 October."""

    zone = ENTSOG.declared_zone
    day_before = parse_source_instant("2026-03-28T06:00:00", contract=ENTSOG, zone=zone)
    day_of = parse_source_instant("2026-03-29T06:00:00", contract=ENTSOG, zone=zone)
    autumn = parse_source_instant("2026-10-25T06:00:00", contract=ENTSOG, zone=zone)

    assert day_before == datetime(2026, 3, 28, 5, 0, tzinfo=UTC)
    # 06:00 local on the switch day is already CEST.
    assert day_of == datetime(2026, 3, 29, 4, 0, tzinfo=UTC)
    # ... and on the autumn switch day it is already CET again.
    assert autumn == datetime(2026, 10, 25, 5, 0, tzinfo=UTC)

    # A local time inside the spring-forward gap does not exist; zoneinfo resolves it forward, and
    # the result is documented rather than silently dropped.
    gap = parse_source_instant("2026-03-29T02:30:00", contract=ENTSOG, zone=zone)
    assert gap == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)

    # An ambiguous autumn local time resolves to the first (summer) offset, as zoneinfo specifies.
    ambiguous = parse_source_instant("2026-10-25T02:30:00", contract=ENTSOG, zone=zone)
    assert ambiguous == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_a_payload_that_declares_an_unsupported_zone_is_refused_whole() -> None:
    """WET is why this matters: its winter offset is zero and its summer offset is not."""

    with pytest.raises(SourceTimezoneError) as refusal:
        resolve_payload_zone(ENTSOG, {"timeZone": "WET"})
    assert refusal.value.code == "unsupported_source_timezone"
    assert "WET" in refusal.value.message

    for token in ("America/New_York", "CEST+1", "local", "  "):
        if not token.strip():
            # A blank declaration is not a declaration: the contract's own zone applies.
            assert resolve_payload_zone(ENTSOG, {"timeZone": token}) is not None
            continue
        with pytest.raises(SourceTimezoneError) as refusal:
            resolve_payload_zone(ENTSOG, {"timeZone": token})
        assert refusal.value.code == "unsupported_source_timezone"

    # A supported token is honoured, including the platform's own zone name.
    assert resolve_payload_zone(ENTSOG, {"timeZone": "UTC"}).key == "UTC"
    assert resolve_payload_zone(ENTSOG, {"timeZone": "cet"}).key == "Europe/Berlin"


def test_an_instant_with_no_provable_zone_is_refused_not_assumed() -> None:
    undeclared = contract_for("SOME-FEED", "whatever")
    with pytest.raises(SourceTimezoneError) as refusal:
        parse_source_instant(
            "2026-01-15T06:00:00", contract=undeclared, zone=undeclared.declared_zone
        )
    assert refusal.value.code == "unprovable_source_timezone"

    # The GIE freshness stamp is the live example: no proven zone, so a bare value is refused while
    # an offset-bearing one is accepted.
    gie = contract_for("GIE", "agsi")
    with pytest.raises(SourceTimezoneError) as gie_refusal:
        parse_source_instant(
            "2026-05-29 12:00:00", contract=gie, zone=gie.declared_zone
        )
    assert gie_refusal.value.code == "unprovable_source_timezone"
    assert parse_source_instant(
        "2026-05-29T12:00:00+02:00", contract=gie, zone=gie.declared_zone
    ) == datetime(2026, 5, 29, 10, 0, tzinfo=UTC)


def test_an_empty_or_unreadable_value_is_none_rather_than_a_refusal() -> None:
    """A row-level problem is skipped by its caller; an unplaceable one is raised."""

    assert parse_source_instant(None, contract=ENTSOG, zone=ENTSOG.declared_zone) is None
    assert parse_source_instant("", contract=ENTSOG, zone=ENTSOG.declared_zone) is None
    assert parse_source_instant("not-a-time", contract=ENTSOG, zone=ENTSOG.declared_zone) is None


def test_the_entsog_normalizers_agree_about_a_naive_gas_day() -> None:
    """Flow and capacity rows covering one gas day must not disagree about which hour it started."""

    payload = {
        "operationaldatas": [
            {**_record(id="flow", indicator="Physical Flow"), "value": "10550000"},
            {**_record(id="cap", indicator="Firm Technical Capacity"), "value": "21100000"},
        ]
    }

    flow_rows = entsog_flow_observations_from_json(payload)
    capacity_rows = entsog_capacity_observations_from_json(payload)

    assert flow_rows[0]["period_start_utc"] == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
    assert capacity_rows[0]["period_start_utc"] == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
    assert flow_rows[0]["period_end_utc"] == datetime(2026, 1, 16, 5, 0, tzinfo=UTC)
    assert capacity_rows[0]["period_end_utc"] == datetime(2026, 1, 16, 5, 0, tzinfo=UTC)


def test_the_entsog_normalizers_refuse_a_payload_in_an_unsupported_zone() -> None:
    payload = {"timeZone": "WET", "operationaldatas": [_record()]}

    with pytest.raises(SourceTimezoneError) as flow_refusal:
        entsog_flow_observations_from_json(payload)
    assert flow_refusal.value.code == "unsupported_source_timezone"

    with pytest.raises(SourceTimezoneError) as capacity_refusal:
        entsog_capacity_observations_from_json(payload)
    assert capacity_refusal.value.code == "unsupported_source_timezone"

    # A payload that declares UTC is read as UTC, including for a naive value.
    utc_payload = {"timeZone": "UTC", "operationaldatas": [_record()]}
    assert entsog_flow_observations_from_json(utc_payload)[0]["period_start_utc"] == datetime(
        2026, 1, 15, 6, 0, tzinfo=UTC
    )


def test_a_gie_row_with_a_naive_freshness_stamp_is_refused() -> None:
    """The gas day is calendar-derived and fine; the freshness stamp is the unproven instant."""

    payload = {
        "data": [
            {
                "code": "EU",
                "name": "EU",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "gasInStorage": "650.25",
                "updatedAt": "2026-05-29 12:00:00",
            }
        ]
    }

    with pytest.raises(SourceTimezoneError) as refusal:
        gie_storage_observations_from_json(payload)
    assert refusal.value.code == "unprovable_source_timezone"
