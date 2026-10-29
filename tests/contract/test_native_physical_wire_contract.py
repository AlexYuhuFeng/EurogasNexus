"""Wire contract from the actual backend projector into the Python SDK models.

The backend is imported only by this contract test. The SDK module must remain a
standalone consumer of the projected JSON wire shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from eurogas_nexus_sdk.native_physical import NativeCapacity, NativeFlow

from eurogas_nexus.application.physical_native_rates import (
    project_native_rate_row,
    serialize_native_rate,
)
from eurogas_nexus.ingestion.entsog_native_units import parse_entsog_native_rate

_LONG_VALUE = "1234567890.123450000000000000000000000001"
_PADDED_LONG_VALUE = f"  {_LONG_VALUE}  "
_PADDED_ENERGY_UNIT = "  kWh/day  "
_ZERO_VALUE = "0.0000e+03"
_OPERATOR_KEY = "DE-OP-42"
_ARCHIVE_ID = "archive-flow-1"
_PAYLOAD_SHA256 = "a" * 64

_FLOW_KEYS = {
    "observation_id",
    "source_record_id",
    "point_id",
    "point_name",
    "direction",
    "kind",
    "period_start_utc",
    "period_end_utc",
    "observed_at_utc",
    "source_system",
    "operator_key",
    "flow_status",
    "period_type",
    "source_reference",
    "research_only",
    "quantity_basis",
    "normalizer_version",
    "native_rate_json",
    "raw_archive_id",
    "payload_sha256",
    "received_at_utc",
}

_CAPACITY_KEYS = (_FLOW_KEYS - {"kind"}) | {"capacity_type"}


def _serialized_rate(value_text: str, unit_text: str) -> dict[str, str | None]:
    parsed = parse_entsog_native_rate(value_text, unit_text)
    serialized = serialize_native_rate(parsed)

    assert parsed.value_text == value_text
    assert parsed.unit_text == unit_text
    assert serialized["value_text"] == value_text
    assert serialized["unit_text"] == unit_text
    assert serialized["native_value"] == str(parsed.native_value)
    assert serialized["normalizer_version"] == parsed.normalizer_version
    return serialized


def test_actual_projector_energy_flow_is_sdk_wire_compatible() -> None:
    rate_json = _serialized_rate(_PADDED_LONG_VALUE, _PADDED_ENERGY_UNIT)
    row = SimpleNamespace(
        observation_id="obs-flow-wire-1",
        source_record_id="source-flow-wire-1",
        point_id="DE-TSO-0001",
        point_name="Deutschland Entry",
        direction="entry",
        kind="actual",
        period_start_utc=datetime(
            2026, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=1))
        ),
        period_end_utc=datetime(2026, 1, 2, tzinfo=UTC),
        observed_at_utc=datetime(
            2026,
            1,
            1,
            5,
            30,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        ),
        source_system="ENTSOG",
        source_reference="entsog:flow:wire-1",
        research_only=True,
        normalizer_version=rate_json["normalizer_version"],
        native_rate_json=rate_json,
        metadata_json={
            "operatorKey": _OPERATOR_KEY,
            "flowStatus": "Confirmed",
            "periodType": "day",
            "raw_archive_id": _ARCHIVE_ID,
            "payload_sha256": _PAYLOAD_SHA256,
            "received_at_utc": datetime(
                2026, 1, 2, 1, 2, 3, tzinfo=timezone(timedelta(hours=1))
            ),
        },
    )

    projected = project_native_rate_row(row, volume_field="flow_mcm_d")

    assert set(projected) == _FLOW_KEYS
    assert projected["native_rate_json"] == rate_json
    assert projected["observation_id"] == "obs-flow-wire-1"
    assert projected["source_record_id"] == "source-flow-wire-1"
    assert projected["point_id"] == "DE-TSO-0001"
    assert projected["point_name"] == "Deutschland Entry"
    assert projected["operator_key"] == _OPERATOR_KEY
    assert projected["period_start_utc"] == "2026-01-01T00:00:00+00:00"
    assert projected["period_end_utc"] == "2026-01-02T00:00:00+00:00"
    assert projected["observed_at_utc"] == "2026-01-01T00:00:00+00:00"
    assert projected["received_at_utc"] == "2026-01-02T00:02:03+00:00"

    flow = NativeFlow.model_validate(projected)

    assert flow.observation_id == "obs-flow-wire-1"
    assert flow.source_record_id == "source-flow-wire-1"
    assert flow.point_id == "DE-TSO-0001"
    assert flow.point_name == "Deutschland Entry"
    assert flow.direction == "entry"
    assert flow.kind == "actual"
    assert flow.operator_key == _OPERATOR_KEY
    assert flow.flow_status == "Confirmed"
    assert flow.period_type == "day"
    assert flow.raw_archive_id == _ARCHIVE_ID
    assert flow.payload_sha256 == _PAYLOAD_SHA256
    assert flow.period_start_utc == "2026-01-01T00:00:00Z"
    assert flow.period_end_utc == "2026-01-02T00:00:00Z"
    assert flow.observed_at_utc == "2026-01-01T00:00:00Z"
    assert flow.received_at_utc == "2026-01-02T00:02:03Z"
    assert flow.quantity_basis == "native"
    assert flow.normalizer_version == "entsog-native-units-v1"
    assert flow.native_rate_json.value_text == _PADDED_LONG_VALUE
    assert flow.native_rate_json.unit_text == _PADDED_ENERGY_UNIT
    assert flow.native_rate_json.native_value == _LONG_VALUE
    assert flow.native_rate_json.energy_kwh_per_day == _LONG_VALUE
    assert flow.native_rate_json.volume_mcm_per_day is None
    assert flow.native_rate_json.model_dump() == rate_json
    assert flow.model_dump()["native_rate_json"] == rate_json


def test_actual_projector_volume_capacity_is_sdk_wire_compatible() -> None:
    rate_json = _serialized_rate(_ZERO_VALUE, "m3/day")
    row = SimpleNamespace(
        observation_id="obs-capacity-wire-1",
        source_record_id="source-capacity-wire-1",
        point_id="DE-TSO-0002",
        point_name="Deutschland Exit",
        direction="exit",
        capacity_type="technical",
        period_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        period_end_utc=datetime(2026, 2, 2, tzinfo=UTC),
        observed_at_utc=None,
        source_system="ENTSOG",
        source_reference="entsog:capacity:wire-1",
        research_only=True,
        normalizer_version=rate_json["normalizer_version"],
        native_rate_json=rate_json,
        capacity_mcm_d=0.0,
        metadata_json={"operatorKey": None},
    )

    projected = project_native_rate_row(row, volume_field="capacity_mcm_d")

    assert set(projected) == _CAPACITY_KEYS
    assert projected["native_rate_json"] == rate_json
    assert projected["capacity_type"] == "technical"
    assert projected["operator_key"] is None
    assert projected["raw_archive_id"] is None
    assert projected["payload_sha256"] is None
    assert projected["observed_at_utc"] is None
    assert projected["received_at_utc"] is None
    assert projected["period_start_utc"] == "2026-02-01T00:00:00+00:00"
    assert projected["period_end_utc"] == "2026-02-02T00:00:00+00:00"

    capacity = NativeCapacity.model_validate(projected)

    assert capacity.observation_id == "obs-capacity-wire-1"
    assert capacity.source_record_id == "source-capacity-wire-1"
    assert capacity.point_id == "DE-TSO-0002"
    assert capacity.point_name == "Deutschland Exit"
    assert capacity.direction == "exit"
    assert capacity.capacity_type == "technical"
    assert capacity.operator_key is None
    assert capacity.raw_archive_id is None
    assert capacity.payload_sha256 is None
    assert capacity.period_start_utc == "2026-02-01T00:00:00Z"
    assert capacity.period_end_utc == "2026-02-02T00:00:00Z"
    assert capacity.observed_at_utc is None
    assert capacity.received_at_utc is None
    assert capacity.quantity_basis == "native"
    assert capacity.native_rate_json.value_text == _ZERO_VALUE
    assert Decimal(capacity.native_rate_json.native_value) == Decimal("0")
    assert Decimal(capacity.native_rate_json.volume_mcm_per_day) == Decimal("0")
    assert capacity.native_rate_json.energy_kwh_per_day is None
    assert capacity.native_rate_json.model_dump() == rate_json
    assert capacity.model_dump()["native_rate_json"] == rate_json
