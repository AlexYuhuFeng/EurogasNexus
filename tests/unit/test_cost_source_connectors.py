"""Cost-source connector skeleton and strict JSON adapter tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from eurogas_nexus.ingestion.connectors.cost_source import (
    COST_SOURCE_MAX_RECORDS,
    CostSourceConfigurationRefusal,
    CostSourceHttpRefusal,
    CostSourceJsonRefusal,
    CostSourceTransportRefusal,
    JsonCostObservationConnector,
    lng_slot_skeleton,
    tso_tariff_skeleton,
)

_FEED_URL = "https://example.test/tariff.json?token=synthetic-secret"


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "cost-json-1",
        "scope_type": "ROUTE",
        "scope_id": "TTF-NBP",
        "observation_type": "TSO_PUBLISHED",
        "value": 1.23,
        "currency": "EUR",
        "unit": "MWh",
        "effective_from_utc": "2026-01-01T00:00:00+00:00",
        "source_system": "TSO_TARIFFS",
        "source_reference": _FEED_URL,
    }
    record.update(overrides)
    return record


class _Response:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


class _BrokenJsonResponse:
    status_code = 200

    def json(self) -> Any:
        raise ValueError("provider body with synthetic-secret must not leak")


def _connector(
    payload: Any,
    *,
    source_system: str = "TSO_TARIFFS",
    status_code: int = 200,
) -> JsonCostObservationConnector:
    return JsonCostObservationConnector(
        source_system=source_system,
        datasets=("published_tariffs",),
        url=_FEED_URL,
        http_get=lambda _url: _Response(payload, status_code),
    )


def test_tso_tariff_skeleton_declares_metadata() -> None:
    connector = tso_tariff_skeleton()

    assert connector.metadata.source_system == "TSO_TARIFFS"
    assert "published_tariffs" in connector.metadata.datasets
    assert connector.metadata.entitlement_required is True


def test_lng_slot_skeleton_declares_metadata() -> None:
    connector = lng_slot_skeleton()

    assert connector.metadata.source_system == "LNG_SLOTS"
    assert "terminal_tariffs" in connector.metadata.datasets
    assert "slot_auctions" in connector.metadata.datasets


def test_skeletons_return_no_fabricated_observations() -> None:
    assert tso_tariff_skeleton().fetch_cost_observations() == ()
    assert lng_slot_skeleton().fetch_cost_observations() == ()


def test_json_connector_normalizes_public_feed() -> None:
    observations = _connector([_record()]).fetch_cost_observations()

    assert len(observations) == 1
    observation = observations[0]
    assert observation.observation_id == "cost-json-1"
    assert observation.scope_type == "ROUTE"
    assert observation.scope_id == "TTF-NBP"
    assert observation.observation_type == "TSO_PUBLISHED"
    assert observation.value == 1.23
    assert observation.currency == "EUR"
    assert observation.unit == "MWh"
    assert observation.effective_from_utc == "2026-01-01T00:00:00+00:00"
    assert observation.source_system == "TSO_TARIFFS"
    assert observation.source_reference == _FEED_URL
    assert observation.created_at_utc == ""


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "scope_type",
        "scope_id",
        "observation_type",
        "value",
        "currency",
        "unit",
        "effective_from_utc",
        "source_reference",
    ],
)
def test_required_field_missing_is_refused(field: str) -> None:
    record = _record()
    del record[field]

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector([record]).fetch_cost_observations()

    expected_field = "observation_id" if field == "id" else field
    assert excinfo.value.code == "COST_SOURCE_FIELD_MISSING"
    assert excinfo.value.record_index == 0
    assert excinfo.value.field == expected_field


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "scope_type",
        "scope_id",
        "observation_type",
        "value",
        "currency",
        "unit",
        "effective_from_utc",
        "source_reference",
    ],
)
def test_required_field_null_is_refused(field: str) -> None:
    record = _record(**{field: None})

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector([record]).fetch_cost_observations()

    expected_field = "id" if field == "id" else field
    assert excinfo.value.code == "COST_SOURCE_FIELD_MISSING"
    assert excinfo.value.record_index == 0
    assert excinfo.value.field == expected_field


def test_explicit_numeric_zero_is_valid() -> None:
    observations = _connector([_record(value=0)]).fetch_cost_observations()

    assert len(observations) == 1
    assert observations[0].value == 0.0


def test_decimal_zero_is_a_valid_explicit_value() -> None:
    observations = _connector(
        [_record(value=Decimal("0"))]
    ).fetch_cost_observations()

    assert observations[0].value == 0.0


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        float("nan"),
        float("inf"),
        float("-inf"),
        -1.0,
        "1.5",
        [],
    ],
)
def test_invalid_financial_value_is_refused(value: Any) -> None:
    record = _record(value=value)

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector([record]).fetch_cost_observations()

    assert excinfo.value.record_index == 0
    assert excinfo.value.field == "value"
    assert excinfo.value.code in {
        "COST_SOURCE_FIELD_INVALID",
        "COST_SOURCE_VALUE_NOT_FINITE",
        "COST_SOURCE_VALUE_NEGATIVE",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"items": None},
        {"items": "not-a-list"},
        "not-a-list",
        42,
    ],
)
def test_bad_envelope_is_refused(payload: Any) -> None:
    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector(payload).fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_ENVELOPE_INVALID"
    assert excinfo.value.record_index is None


def test_provider_error_envelope_is_refused() -> None:
    payload = {"items": [], "error": {"code": "access_denied"}}

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector(payload).fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_PROVIDER_ERROR"
    assert excinfo.value.field == "error"


@pytest.mark.parametrize("payload", [[], {"items": []}])
def test_empty_success_is_not_a_refusal(payload: Any) -> None:
    assert _connector(payload).fetch_cost_observations() == ()


def test_no_content_is_empty_success() -> None:
    connector = _connector([], status_code=204)

    assert connector.fetch_cost_observations() == ()


def test_http_failure_is_a_typed_refusal_not_empty_success() -> None:
    connector = _connector([], status_code=503)

    with pytest.raises(CostSourceHttpRefusal) as excinfo:
        connector.fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_HTTP_REFUSED"
    assert excinfo.value.status_code == 503
    assert excinfo.value.field == "response"


def test_malformed_json_is_a_safe_typed_refusal() -> None:
    connector = JsonCostObservationConnector(
        source_system="TSO_TARIFFS",
        datasets=("published_tariffs",),
        url=_FEED_URL,
        http_get=lambda _url: _BrokenJsonResponse(),
    )

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        connector.fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_JSON_MALFORMED"
    assert "synthetic-secret" not in str(excinfo.value)


def test_transport_failure_is_a_safe_typed_refusal() -> None:
    def _fail(_url: str) -> Any:
        raise RuntimeError("synthetic-secret at " + _FEED_URL)

    connector = JsonCostObservationConnector(
        source_system="TSO_TARIFFS",
        datasets=("published_tariffs",),
        url=_FEED_URL,
        http_get=_fail,
    )

    with pytest.raises(CostSourceTransportRefusal) as excinfo:
        connector.fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_TRANSPORT_FAILED"
    assert "synthetic-secret" not in str(excinfo.value)
    assert _FEED_URL not in str(excinfo.value)


def test_declared_source_cannot_override_the_connector() -> None:
    record = _record(source_system="LNG_SLOTS")

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector([record], source_system="TSO_TARIFFS").fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_SOURCE_MISMATCH"
    assert excinfo.value.field == "source_system"


def test_matching_declared_source_uses_the_connector_identity() -> None:
    record = _record(source_system="tso_tariffs")

    observations = _connector(
        [record], source_system="TSO_TARIFFS"
    ).fetch_cost_observations()

    assert observations[0].source_system == "TSO_TARIFFS"


def test_absent_declared_source_uses_the_connector_identity() -> None:
    record = _record()
    del record["source_system"]

    observations = _connector(
        [record], source_system="LNG_SLOTS"
    ).fetch_cost_observations()

    assert observations[0].source_system == "LNG_SLOTS"


def test_missing_connector_source_is_refused() -> None:
    connector = _connector([_record()], source_system="")

    with pytest.raises(CostSourceConfigurationRefusal) as excinfo:
        connector.fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_SOURCE_MISSING"
    assert excinfo.value.field == "source_system"


def test_missing_provenance_reference_is_refused_without_echoing_values() -> None:
    record = _record()
    del record["source_reference"]

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector([record]).fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_FIELD_MISSING"
    assert excinfo.value.field == "source_reference"
    assert _FEED_URL not in str(excinfo.value)
    assert "synthetic-secret" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("unit", "bananas", "COST_SOURCE_UNIT_UNSUPPORTED"),
        ("unit", "EUR/MWh", "COST_SOURCE_UNIT_UNSUPPORTED"),
        ("unit", "", "COST_SOURCE_FIELD_MISSING"),
        ("currency", "EURO", "COST_SOURCE_CURRENCY_INVALID"),
        ("currency", "€", "COST_SOURCE_CURRENCY_INVALID"),
        ("currency", "", "COST_SOURCE_FIELD_MISSING"),
    ],
)
def test_invalid_unit_or_currency_is_refused(
    field: str, value: str, code: str
) -> None:
    record = _record(**{field: value})

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector([record]).fetch_cost_observations()

    assert excinfo.value.code == code
    assert excinfo.value.record_index == 0
    assert excinfo.value.field == field


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("mwh", "MWh"),
        ("MMBtu", "MMBtu"),
        ("therm/day", "therm/day"),
        ("m3", "m3"),
    ],
)
def test_recognized_units_are_normalized(unit: str, expected: str) -> None:
    observations = _connector([_record(unit=unit)]).fetch_cost_observations()

    assert observations[0].unit == expected


@pytest.mark.parametrize(
    "effective_from",
    ["2026-01-01T00:00:00", "not-a-time", "2026-01-01"],
)
def test_naive_or_malformed_effective_from_is_refused(
    effective_from: str,
) -> None:
    record = _record(effective_from_utc=effective_from)

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector([record]).fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_TIMESTAMP_INVALID"
    assert excinfo.value.field == "effective_from_utc"


def test_effective_to_before_effective_from_is_refused() -> None:
    record = _record(effective_to_utc="2025-12-31T00:00:00+00:00")

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector([record]).fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_TIMESTAMP_INVALID"
    assert excinfo.value.field == "effective_to_utc"


def test_effective_to_null_is_a_valid_open_window() -> None:
    observations = _connector(
        [_record(effective_to_utc=None)]
    ).fetch_cost_observations()

    assert observations[0].effective_to_utc is None


def test_invalid_later_record_refuses_the_whole_batch() -> None:
    records = [_record(), _record(id="cost-json-2", value=None)]

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector(records).fetch_cost_observations()

    assert excinfo.value.record_index == 1
    assert excinfo.value.field == "value"


def test_record_count_is_bounded() -> None:
    records = [
        _record(id=f"cost-json-{index}")
        for index in range(COST_SOURCE_MAX_RECORDS + 1)
    ]

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        _connector(records).fetch_cost_observations()

    assert excinfo.value.code == "COST_SOURCE_RECORD_LIMIT_EXCEEDED"


def test_extended_cost_source_skeletons_exist() -> None:
    from eurogas_nexus.ingestion.connectors.cost_source import (
        COST_SOURCE_SKELETONS,
        lng_auction_skeleton,
        secondary_transfer_skeleton,
    )

    assert secondary_transfer_skeleton().metadata.source_system == "SECONDARY_TRANSFER"
    assert lng_auction_skeleton().metadata.source_system == "LNG_AUCTIONS"
    assert set(COST_SOURCE_SKELETONS) >= {
        "TSO_TARIFFS",
        "LNG_SLOTS",
        "SECONDARY_TRANSFER",
        "LNG_AUCTIONS",
    }
