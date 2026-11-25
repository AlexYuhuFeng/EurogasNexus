"""Stable scheduler invalidation schema and UTC normalization."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from eurogas_nexus.streaming.contracts import IngestionInvalidationV1


def _wire():
    return {
        "event_type": "opportunity.input.invalidated",
        "schema_version": 1,
        "source_id": "src-entsog-umm",
        "run_id": "run-42",
        "input_class": "outages",
        "noticed_at_utc": "2026-11-25T16:00:00+01:00",
    }


def test_invalidations_have_transport_neutral_identity_and_utc_wire_representation():
    raw = _wire()
    event = IngestionInvalidationV1.model_validate_json(json.dumps(raw))
    assert event.noticed_at_utc == datetime(2026, 11, 25, 15, tzinfo=UTC)
    assert json.loads(event.model_dump_json()) == {
        **raw, "noticed_at_utc": "2026-11-25T15:00:00Z"
    }
    assert IngestionInvalidationV1.model_validate_json(event.model_dump_json()) == event


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"event_type": "market.quote"},
        {"noticed_at_utc": "2026-11-25T15:00:00"},
        {"input_class": "not-in-the-catalogue"},
        {"run_id": " "},
        {"price": 1},
    ],
)
def test_rejects_unsupported_or_sensitive_payload_shapes(change):
    with pytest.raises(ValidationError):
        IngestionInvalidationV1.model_validate({**_wire(), **change})


@pytest.mark.parametrize("field", ["event_type", "schema_version"])
def test_consumer_requires_explicit_dispatch_metadata(field):
    message = _wire()
    message.pop(field)
    with pytest.raises(ValidationError, match=field):
        IngestionInvalidationV1.model_validate(message)
