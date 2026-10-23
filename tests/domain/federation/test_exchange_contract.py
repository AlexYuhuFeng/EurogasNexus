"""Exchange metadata is a bounded contract, never a transfer authorization."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from eurogas_nexus.domain.federation.contracts import (
    DeploymentRef,
    ExchangeEnvelope,
    Region,
    verify_delivery_integrity,
)

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
PAYLOAD = b'{"synthetic":true}'
SCHEMA_ID = "urn:example:synthetic-strategy:1"


def metadata():
    return {
        "contract_version": "eurogas.exchange/1",
        "transfer_id": "5a0831a9-bcd4-40d1-a74a-389f4d18fc3a",
        "idempotency_key": "owned-export-1",
        "source": {"deployment_id": "gas-europe-a", "region": "EU"},
        "destination": {"deployment_id": "gas-singapore-a", "region": "SG"},
        "actor": {"deployment_id": "gas-europe-a", "principal_id": "trader-1"},
        "owner": {"deployment_id": "gas-europe-a", "principal_id": "trader-1"},
        "resource": {
            "origin_deployment_id": "gas-europe-a",
            "kind": "strategy",
            "resource_id": "s-1",
            "revision": "v-1",
        },
        "purpose": "Approved synthetic research exchange",
        "classification": "CONFIDENTIAL",
        "source_visibility": "PRIVATE",
        "provenance_refs": ["snapshot:synthetic-1"],
        "policy_ref": "policy:synthetic-eu-sg-1",
        "owner_approval_ref": "approval:synthetic-1",
        "entitlement_ref": "entitlement:synthetic-1",
        "created_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "payload": {
            "schema_id": SCHEMA_ID,
            "media_type": "application/json",
            "sha256": sha256(PAYLOAD).hexdigest(),
            "byte_length": len(PAYLOAD),
        },
    }


def check(envelope, payload=PAYLOAD, **overrides):
    kwargs = {
        "expected_source": DeploymentRef(deployment_id="gas-europe-a", region=Region.EUROPE),
        "expected_destination": DeploymentRef(
            deployment_id="gas-singapore-a", region=Region.SINGAPORE
        ),
        "supported_payload_schemas": frozenset({SCHEMA_ID}),
        "now": NOW,
    }
    kwargs.update(overrides)
    verify_delivery_integrity(envelope, payload, **kwargs)


def test_roundtrip_and_integrity_do_not_change_private_visibility():
    envelope = ExchangeEnvelope.model_validate_json(json.dumps(metadata()))
    check(envelope)
    assert envelope.source_visibility == "PRIVATE"
    assert ExchangeEnvelope.model_validate_json(envelope.model_dump_json()) == envelope


@pytest.mark.parametrize("region", ["EU", "CN", "CA", "SG"])
def test_four_region_labels_are_supported_without_claiming_residency(region):
    value = metadata()
    value["destination"]["region"] = region
    envelope = ExchangeEnvelope.model_validate(value)
    check(envelope, expected_destination=envelope.destination)


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract_version", "eurogas.exchange/2"),
        ("owner_approval_ref", ""),
        ("entitlement_ref", ""),
        ("policy_ref", ""),
        ("source_visibility", "ANONYMOUS"),
        ("classification", "UNCLASSIFIED"),
        ("purpose", "   "),
        ("provenance_refs", []),
        ("provenance_refs", ["snapshot:x", "snapshot:x"]),
        ("created_at", "2026-01-01T12:00:00"),
        ("created_at", "2026-01-01T12:00:00+01:00"),
        ("expires_at", "2026-01-01T12:00:00Z"),
        ("expires_at", "2026-02-01T12:00:00Z"),
    ],
)
def test_rejects_unsupported_or_incomplete_metadata(field, value):
    body = metadata()
    body[field] = value
    with pytest.raises(ValidationError):
        ExchangeEnvelope.model_validate(body)


def test_public_does_not_waive_owner_or_entitlement_evidence():
    body = metadata()
    body["source_visibility"] = "PUBLIC"
    del body["owner_approval_ref"]
    with pytest.raises(ValidationError):
        ExchangeEnvelope.model_validate(body)


@pytest.mark.parametrize("field", ["actor", "owner"])
def test_namespace_mismatch_is_rejected(field):
    body = metadata()
    body[field]["deployment_id"] = "unexpected-deployment"
    with pytest.raises(ValidationError):
        ExchangeEnvelope.model_validate(body)


def test_source_and_destination_cannot_be_same_deployment():
    body = metadata()
    body["destination"] = deepcopy(body["source"])
    with pytest.raises(ValidationError):
        ExchangeEnvelope.model_validate(body)


@pytest.mark.parametrize("field,value", [("region", "OTHER"), ("extra", "hidden")])
def test_nested_unknown_values_are_rejected(field, value):
    body = metadata()
    body["source"][field] = value
    with pytest.raises(ValidationError):
        ExchangeEnvelope.model_validate(body)


@pytest.mark.parametrize(
    "change", ["expired", "future", "source", "destination", "schema", "size", "digest", "limit"]
)
def test_delivery_checks_reject_wrong_binding_or_bytes(change):
    body = metadata()
    kwargs = {}
    if change == "expired":
        kwargs["now"] = NOW + timedelta(hours=1)
    elif change == "future":
        kwargs["now"] = NOW - timedelta(minutes=6)
    elif change in {"source", "destination"}:
        kwargs[f"expected_{change}"] = DeploymentRef(deployment_id="other-peer", region="CN")
    elif change == "schema":
        kwargs["supported_payload_schemas"] = frozenset()
    elif change == "size":
        body["payload"]["byte_length"] += 1
    elif change == "digest":
        body["payload"]["sha256"] = "0" * 64
    elif change == "limit":
        kwargs["max_payload_bytes"] = len(PAYLOAD) - 1
    with pytest.raises(ValueError):
        check(ExchangeEnvelope.model_validate(body), **kwargs)


def test_even_same_size_changed_bytes_are_refused():
    with pytest.raises(ValueError, match="digest"):
        check(ExchangeEnvelope.model_validate(metadata()), b"x" * len(PAYLOAD))


def test_schema_is_reproducible_and_forbids_unknown_properties():
    root = Path(__file__).resolve().parents[3]
    stored = json.loads(
        (root / "docs/architecture/schemas/exchange-envelope-v1.schema.json").read_text()
    )
    expected = ExchangeEnvelope.model_json_schema()
    expected["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    expected["$id"] = "urn:eurogas-nexus:exchange-envelope:1"
    assert stored == expected
    assert stored["additionalProperties"] is False
    assert stored["$defs"]["PayloadDescriptor"]["additionalProperties"] is False
