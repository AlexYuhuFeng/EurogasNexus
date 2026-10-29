"""Focused RFC 0005 native-unit SDK tests using projector-shaped JSON rows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from eurogas_nexus_sdk import native_physical
from eurogas_nexus_sdk._transport import ResponseMeta, SdkProtocolError
from eurogas_nexus_sdk.native_physical import (
    NativeCapacity,
    NativeFlow,
    NativeRate,
    fetch_native_capacity,
    fetch_native_capacity_result,
    fetch_native_flows,
    fetch_native_flows_result,
)
from pydantic import ValidationError

_LONG_TOKEN = "1234567890.123450000000000000000000000001"
_PADDED_VALUE_TEXT = "  00123.4500e+02  "
_PADDED_UNIT_TEXT = "  kWh/day  "
_PADDED_NATIVE_VALUE = "00123.4500e+02"

_ENERGY_RATE: dict[str, Any] = {
    "value_text": _LONG_TOKEN,
    "unit_text": "kWh/day",
    "native_value": _LONG_TOKEN,
    "normalized_unit": "kWh/day",
    "quantity_kind": "energy",
    "rate_basis": "day",
    "energy_kwh_per_day": _LONG_TOKEN,
    "volume_mcm_per_day": None,
    "normalizer_version": "entsog-native-units-v1",
}

_VOLUME_RATE: dict[str, Any] = {
    "value_text": "0.0000e+03",
    "unit_text": "m3/day",
    "native_value": "0.0000e+03",
    "normalized_unit": "m3/day",
    "quantity_kind": "volume",
    "rate_basis": "day",
    "energy_kwh_per_day": None,
    "volume_mcm_per_day": "0.0000e+03",
    "normalizer_version": "entsog-native-units-v1",
}

_PADDED_ENERGY_RATE: dict[str, Any] = {
    "value_text": _PADDED_VALUE_TEXT,
    "unit_text": _PADDED_UNIT_TEXT,
    "native_value": _PADDED_NATIVE_VALUE,
    "normalized_unit": "kWh/day",
    "quantity_kind": "energy",
    "rate_basis": "day",
    "energy_kwh_per_day": _PADDED_NATIVE_VALUE,
    "volume_mcm_per_day": None,
    "normalizer_version": "entsog-native-units-v1",
}

_FLOW: dict[str, Any] = {
    "observation_id": "obs-0001",
    "source_record_id": "42",
    "point_id": "DE-TSO-0001",
    "point_name": "Deutschland Entry",
    "direction": "entry",
    "kind": "actual",
    "period_start_utc": "2026-01-01T00:00:00+01:00",
    "period_end_utc": "2026-01-02T00:00:00Z",
    "observed_at_utc": None,
    "source_system": "ENTSOG",
    "operator_key": "DE-OP-42",
    "source_reference": "entsog:flow:1",
    "research_only": True,
    "quantity_basis": "native",
    "normalizer_version": "entsog-native-units-v1",
    "native_rate_json": _ENERGY_RATE,
    "raw_archive_id": "17",
    "payload_sha256": "A" * 64,
    "received_at_utc": "2026-01-02T01:02:03+01:00",
    "future_lineage": {"revision": 2},
}

_CAPACITY: dict[str, Any] = {
    "observation_id": "cap-0001",
    "source_record_id": "src-cap-1",
    "point_id": "DE-TSO-0001",
    "point_name": "Deutschland Exit",
    "direction": "exit",
    "capacity_type": "technical",
    "period_start_utc": "2026-02-01T00:00:00Z",
    "period_end_utc": "2026-02-02T00:00:00Z",
    "observed_at_utc": None,
    "source_system": "ENTSOG",
    "source_reference": "entsog:capacity:1",
    "research_only": True,
    "quantity_basis": "native",
    "normalizer_version": "entsog-native-units-v1",
    "native_rate_json": _VOLUME_RATE,
    "raw_archive_id": None,
    "payload_sha256": None,
    "received_at_utc": None,
}


def _flow_payload(**overrides: Any) -> dict[str, Any]:
    payload = deepcopy(_FLOW)
    payload.update(overrides)
    return payload


def _capacity_payload(**overrides: Any) -> dict[str, Any]:
    payload = deepcopy(_CAPACITY)
    payload.update(overrides)
    return payload


def _energy_rate(**overrides: Any) -> dict[str, Any]:
    payload = deepcopy(_ENERGY_RATE)
    payload.update(overrides)
    return payload


def test_native_rate_preserves_long_decimal_and_exponent_zero_tokens() -> None:
    energy = NativeRate.model_validate(_ENERGY_RATE)
    assert energy.value_text == _LONG_TOKEN
    assert energy.native_value == _LONG_TOKEN
    assert energy.energy_kwh_per_day == _LONG_TOKEN
    assert energy.volume_mcm_per_day is None
    assert energy.normalized_unit == "kWh/day"
    assert energy.model_dump()["energy_kwh_per_day"] == _LONG_TOKEN

    volume = NativeRate.model_validate(_VOLUME_RATE)
    assert volume.value_text == "0.0000e+03"
    assert volume.native_value == "0.0000e+03"
    assert volume.volume_mcm_per_day == "0.0000e+03"
    assert volume.energy_kwh_per_day is None
    assert volume.normalized_unit == "m3/day"


def test_native_rate_preserves_padded_backend_lexical_tokens() -> None:
    rate = NativeRate.model_validate(_PADDED_ENERGY_RATE)
    assert rate.value_text == _PADDED_VALUE_TEXT
    assert rate.unit_text == _PADDED_UNIT_TEXT
    assert rate.native_value == _PADDED_NATIVE_VALUE
    assert rate.energy_kwh_per_day == _PADDED_NATIVE_VALUE
    assert rate.normalized_unit == "kWh/day"
    assert rate.model_dump()["value_text"] == _PADDED_VALUE_TEXT
    assert rate.model_dump()["unit_text"] == _PADDED_UNIT_TEXT

    flow = NativeFlow.model_validate(
        _flow_payload(native_rate_json=_PADDED_ENERGY_RATE)
    )
    assert flow.native_rate_json.value_text == _PADDED_VALUE_TEXT
    assert flow.native_rate_json.unit_text == _PADDED_UNIT_TEXT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("value_text", 123),
        ("value_text", 1.25),
        ("value_text", True),
        ("value_text", None),
        ("value_text", "1 000"),
        ("value_text", "1\t000"),
        ("native_value", 0),
        ("native_value", False),
        ("native_value", " 1"),
        ("native_value", "1 "),
        ("energy_kwh_per_day", 123),
        ("energy_kwh_per_day", True),
        ("energy_kwh_per_day", " 1"),
        ("value_text", "NaN"),
        ("native_value", "Infinity"),
        ("energy_kwh_per_day", "-Infinity"),
        ("energy_kwh_per_day", "sNaN"),
        ("value_text", "1_000"),
        ("value_text", "1e"),
        ("value_text", ""),
        ("value_text", "   "),
        ("native_value", "0x10"),
    ],
)
def test_native_rate_rejects_non_string_non_finite_and_malformed_numbers(
    field: str, value: Any
) -> None:
    payload = _energy_rate(**{field: value})
    with pytest.raises(ValidationError):
        NativeRate.model_validate(payload)


def test_native_rate_rejects_unsupported_dimensions_and_mismatched_quantities() -> None:
    for payload in (
        _energy_rate(quantity_kind="mass"),
        _energy_rate(rate_basis="week"),
        _energy_rate(unit_text="m3/day"),
        _energy_rate(unit_text="mcm/h"),
        _energy_rate(normalized_unit="m3"),
        _energy_rate(normalized_unit="kWh"),
        _energy_rate(normalized_unit="kWh/week"),
        _energy_rate(normalized_unit="MW/day"),
        _energy_rate(normalized_unit="m3/day"),
        _energy_rate(normalized_unit="kWh/hour"),
        _energy_rate(rate_basis="hour"),
        _energy_rate(unit_text="kWh/h"),
        _energy_rate(unit_text="kWh/day", rate_basis="hour"),
        _energy_rate(energy_kwh_per_day=None),
        _energy_rate(volume_mcm_per_day="1"),
        _energy_rate(energy_kwh_per_day=None, volume_mcm_per_day="1"),
    ):
        with pytest.raises(ValidationError):
            NativeRate.model_validate(payload)


@pytest.mark.parametrize(
    "unit_text",
    [
        "kW/day",
        "MW/day",
        "MMBtu/day",
        "btu/day",
        "therm/day",
        "m3/week",
        "kWh",
        "energy/day",
        "kWh / day",
    ],
)
def test_native_rate_rejects_unsupported_unit_text_aliases(unit_text: str) -> None:
    with pytest.raises(ValidationError):
        NativeRate.model_validate(_energy_rate(unit_text=unit_text))


@pytest.mark.parametrize(
    ("unit_text", "normalized_unit", "quantity_kind", "rate_basis"),
    [
        ("kWh/d", "kWh/day", "energy", "day"),
        ("kWh/day", "kWh/day", "energy", "day"),
        ("  KWH/DAY  ", "kWh/day", "energy", "day"),
        ("MWh/d", "MWh/day", "energy", "day"),
        ("MWh/day", "MWh/day", "energy", "day"),
        ("mwh/DAY", "MWh/day", "energy", "day"),
        ("kWh/h", "kWh/hour", "energy", "hour"),
        ("MWh/h", "MWh/hour", "energy", "hour"),
        ("MWH/H", "MWh/hour", "energy", "hour"),
        ("m3/d", "m3/day", "volume", "day"),
        ("m3/day", "m3/day", "volume", "day"),
        ("  M³/DAY  ", "m3/day", "volume", "day"),
        ("m3/h", "m3/hour", "volume", "hour"),
        ("M³/H", "m3/hour", "volume", "hour"),
        ("mcm/d", "mcm/day", "volume", "day"),
        ("mcm/day", "mcm/day", "volume", "day"),
        ("MCM/DAY", "mcm/day", "volume", "day"),
        ("mcm/h", "mcm/hour", "volume", "hour"),
    ],
)
def test_native_rate_accepts_all_v1_unit_text_aliases_and_round_trips_lexical_text(
    unit_text: str,
    normalized_unit: str,
    quantity_kind: str,
    rate_basis: str,
) -> None:
    payload = _energy_rate(
        unit_text=unit_text,
        normalized_unit=normalized_unit,
        quantity_kind=quantity_kind,
        rate_basis=rate_basis,
    )
    if quantity_kind == "volume":
        payload["energy_kwh_per_day"] = None
        payload["volume_mcm_per_day"] = "1.000"

    rate = NativeRate.model_validate(payload)
    assert rate.unit_text == unit_text
    assert rate.normalized_unit == normalized_unit
    assert rate.quantity_kind == quantity_kind
    assert rate.rate_basis == rate_basis
    assert rate.model_dump()["unit_text"] == unit_text


def test_native_rate_requires_exact_payload_keys_and_normalizer_version() -> None:
    for missing in (
        "value_text",
        "unit_text",
        "native_value",
        "normalized_unit",
        "quantity_kind",
        "rate_basis",
        "energy_kwh_per_day",
        "volume_mcm_per_day",
        "normalizer_version",
    ):
        payload = _energy_rate()
        payload.pop(missing)
        with pytest.raises(ValidationError):
            NativeRate.model_validate(payload)

    with pytest.raises(ValidationError):
        NativeRate.model_validate(_energy_rate(unexpected="future"))
    with pytest.raises(ValidationError):
        NativeRate.model_validate(_energy_rate(normalizer_version="v2"))


def test_native_flow_projection_preserves_actual_shape_and_normalizes_utc() -> None:
    flow = NativeFlow.model_validate(_FLOW)

    assert isinstance(flow, NativeFlow)
    assert flow.observation_id == "obs-0001"
    assert flow.source_record_id == "42"
    assert flow.point_id == "DE-TSO-0001"
    assert flow.point_name == "Deutschland Entry"
    assert flow.direction == "entry"
    assert flow.kind == "actual"
    assert flow.period_start_utc == "2025-12-31T23:00:00Z"
    assert flow.period_end_utc == "2026-01-02T00:00:00Z"
    assert flow.observed_at_utc is None
    assert flow.source_system == "ENTSOG"
    assert flow.operator_key == "DE-OP-42"
    assert flow.source_reference == "entsog:flow:1"
    assert flow.research_only is True
    assert flow.quantity_basis == "native"
    assert flow.normalizer_version == flow.native_rate_json.normalizer_version
    assert flow.native_rate_json.energy_kwh_per_day == _LONG_TOKEN
    assert flow.raw_archive_id == "17"
    assert flow.payload_sha256 == "a" * 64
    assert flow.received_at_utc == "2026-01-02T00:02:03Z"
    assert flow.model_extra == {"future_lineage": {"revision": 2}}

    dumped = flow.model_dump()
    assert dumped["quantity_basis"] == "native"
    assert "flow_mcm_d" not in dumped
    assert "volume_mcm_d" not in dumped
    for obsolete in (
        "observation",
        "source_record",
        "point",
        "name",
        "period_start",
        "period_end",
        "observed_at",
    ):
        assert obsolete not in dumped


def test_native_capacity_projection_uses_capacity_type_and_volume_zero() -> None:
    capacity = NativeCapacity.model_validate(_CAPACITY)

    assert isinstance(capacity, NativeCapacity)
    assert capacity.observation_id == "cap-0001"
    assert capacity.source_record_id == "src-cap-1"
    assert capacity.capacity_type == "technical"
    assert capacity.operator_key is None
    assert capacity.observed_at_utc is None
    assert capacity.period_start_utc == "2026-02-01T00:00:00Z"
    assert capacity.native_rate_json.value_text == "0.0000e+03"
    assert capacity.native_rate_json.volume_mcm_per_day == "0.0000e+03"
    assert capacity.native_rate_json.energy_kwh_per_day is None
    assert capacity.native_rate_json.normalized_unit == "m3/day"
    assert capacity.raw_archive_id is None
    assert capacity.payload_sha256 is None
    assert capacity.received_at_utc is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("observation_id", 1),
        ("observation_id", True),
        ("source_record_id", 42),
        ("point_id", 7),
        ("point_id", False),
        ("operator_key", 1),
        ("raw_archive_id", 17),
        ("point_name", 3),
        ("direction", 1),
        ("kind", 1),
        ("source_reference", 9),
    ],
)
def test_native_projection_ids_and_text_are_not_coerced(
    field: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        NativeFlow.model_validate(_flow_payload(**{field: value}))


def test_operator_key_defaults_to_none_when_absent() -> None:
    payload = _flow_payload()
    payload.pop("operator_key")
    flow = NativeFlow.model_validate(payload)
    assert flow.operator_key is None
    assert flow.model_dump()["operator_key"] is None


def test_native_flow_requires_basis_version_and_entsog_source() -> None:
    for missing in (
        "observation_id",
        "source_record_id",
        "point_id",
        "point_name",
        "direction",
        "kind",
        "period_start_utc",
        "period_end_utc",
        "source_system",
        "source_reference",
        "research_only",
        "quantity_basis",
        "normalizer_version",
        "native_rate_json",
    ):
        payload = _flow_payload()
        payload.pop(missing)
        with pytest.raises(ValidationError):
            NativeFlow.model_validate(payload)

    with pytest.raises(ValidationError):
        NativeFlow.model_validate(_flow_payload(quantity_basis="legacy"))
    with pytest.raises(ValidationError):
        NativeFlow.model_validate(_flow_payload(normalizer_version="v2"))
    with pytest.raises(ValidationError):
        NativeFlow.model_validate(_flow_payload(source_system="OTHER"))

    nested_missing = _energy_rate()
    nested_missing.pop("normalizer_version")
    with pytest.raises(ValidationError):
        NativeFlow.model_validate(_flow_payload(native_rate_json=nested_missing))

    # Current projects omit freshness: it must remain an optional future field.
    assert "freshness" not in NativeFlow.model_validate(_FLOW).model_dump()


def test_native_flow_time_constraints_and_offset_normalization() -> None:
    for overrides in (
        {
            "period_start_utc": "2026-01-02T00:00:00Z",
            "period_end_utc": "2026-01-02T00:00:00Z",
        },
        {
            "period_start_utc": "2026-01-03T00:00:00Z",
            "period_end_utc": "2026-01-02T00:00:00Z",
        },
        {"period_start_utc": "2026-01-01T00:00:00"},
        {"period_end_utc": "2026-01-02T00:00:00"},
        {"observed_at_utc": "2026-01-01T00:00:00"},
        {"received_at_utc": "2026-01-02T00:00:00"},
        {"period_start_utc": "not-a-date"},
    ):
        with pytest.raises(ValidationError):
            NativeFlow.model_validate(_flow_payload(**overrides))

    flow = NativeFlow.model_validate(
        _flow_payload(
            observed_at_utc="2026-01-01T05:30:00+05:30",
            received_at_utc="2026-01-02T01:02:03+01:00",
        )
    )
    assert flow.observed_at_utc == "2026-01-01T00:00:00Z"
    assert flow.received_at_utc == "2026-01-02T00:02:03Z"


def test_native_flow_sha256_constraints_when_present() -> None:
    for value in (None, "0" * 64, "f" * 64, "A" * 64):
        flow = NativeFlow.model_validate(_flow_payload(payload_sha256=value))
        assert flow.payload_sha256 == (value.lower() if value is not None else None)

    for value in ("a" * 63, "a" * 65, "g" * 64, 123, True):
        with pytest.raises(ValidationError):
            NativeFlow.model_validate(_flow_payload(payload_sha256=value))


def test_fetch_native_flows_passes_query_and_preserves_extra_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_get_envelope(
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[Any, ResponseMeta]:
        calls.append((url, params))
        assert timeout_seconds == 10.0
        return (
            [deepcopy(_FLOW)],
            ResponseMeta.model_validate(
                {
                    "research_only": False,
                    "warnings": ["native"],
                    "future_meta": {"revision": 3},
                }
            ),
        )

    monkeypatch.setattr(native_physical, "get_envelope", fake_get_envelope)
    result = fetch_native_flows_result(
        "https://example.test/", point_id="DE-TSO-0001", limit=17
    )

    assert calls == [
        (
            "https://example.test/api/physical/flows",
            {"quantity_basis": "native", "limit": 17, "point_id": "DE-TSO-0001"},
        )
    ]
    assert len(result.data) == 1
    assert isinstance(result.data[0], NativeFlow)
    assert result.meta.research_only is False
    assert result.meta.warnings == ["native"]
    assert result.meta.model_extra == {"future_meta": {"revision": 3}}


def test_fetch_native_capacity_uses_capacity_path_and_default_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_get_envelope(
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[Any, ResponseMeta]:
        calls.append((url, params))
        return [deepcopy(_CAPACITY)], ResponseMeta()

    monkeypatch.setattr(native_physical, "get_envelope", fake_get_envelope)
    result = fetch_native_capacity_result("https://example.test")

    assert calls == [
        (
            "https://example.test/api/physical/capacity",
            {"quantity_basis": "native", "limit": 200},
        )
    ]
    assert isinstance(result.data[0], NativeCapacity)
    assert result.meta.research_only is True


def test_data_only_helpers_return_typed_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get_envelope(
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[Any, ResponseMeta]:
        if url.endswith("/physical/flows"):
            return [deepcopy(_FLOW)], ResponseMeta()
        return [deepcopy(_CAPACITY)], ResponseMeta()

    monkeypatch.setattr(native_physical, "get_envelope", fake_get_envelope)
    flows = fetch_native_flows("https://example.test", limit=1)
    capacities = fetch_native_capacity("https://example.test", limit=2000)
    assert isinstance(flows[0], NativeFlow)
    assert isinstance(capacities[0], NativeCapacity)


@pytest.mark.parametrize("data", [{}, None, "not-a-list", 7])
def test_native_response_data_must_be_a_list(
    monkeypatch: pytest.MonkeyPatch, data: Any
) -> None:
    def fake_get_envelope(
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[Any, ResponseMeta]:
        return data, ResponseMeta()

    monkeypatch.setattr(native_physical, "get_envelope", fake_get_envelope)
    with pytest.raises(SdkProtocolError):
        fetch_native_flows_result("https://example.test")
    with pytest.raises(SdkProtocolError):
        fetch_native_capacity_result("https://example.test")


@pytest.mark.parametrize(
    ("point_id", "limit"),
    [
        ("", 200),
        ("   ", 200),
        ("x" * 129, 200),
        (5, 200),
        (None, 0),
        (None, 2001),
        (None, True),
        (None, 1.5),
        (None, "200"),
    ],
)
def test_invalid_native_queries_do_not_call_transport(
    monkeypatch: pytest.MonkeyPatch, point_id: Any, limit: Any
) -> None:
    calls: list[object] = []

    def fail_if_called(*args: object, **kwargs: object) -> tuple[Any, ResponseMeta]:
        calls.append((args, kwargs))
        raise AssertionError("transport must not be called for invalid queries")

    monkeypatch.setattr(native_physical, "get_envelope", fail_if_called)
    with pytest.raises(ValueError):
        fetch_native_flows_result(
            "https://example.test", point_id=point_id, limit=limit
        )
    with pytest.raises(ValueError):
        fetch_native_capacity_result(
            "https://example.test", point_id=point_id, limit=limit
        )
    assert calls == []


def test_transport_errors_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom(RuntimeError):
        pass

    def boom(*args: object, **kwargs: object) -> tuple[Any, ResponseMeta]:
        raise Boom("upstream HTTP failure")

    monkeypatch.setattr(native_physical, "get_envelope", boom)
    with pytest.raises(Boom):
        fetch_native_flows_result("https://example.test")
    with pytest.raises(Boom):
        fetch_native_capacity_result("https://example.test")
