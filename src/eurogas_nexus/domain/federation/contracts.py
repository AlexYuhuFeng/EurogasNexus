"""Version-one exchange metadata and offline integrity checks.

An envelope is untrusted input. Passing these checks does not authorize an export,
prove an approval, authenticate a peer, or establish regional residency. No network,
filesystem or database operation is performed by this module.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "eurogas.exchange/1"
MAX_ENVELOPE_LIFETIME = timedelta(days=7)
DEFAULT_MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
Identifier = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
]
Reference = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^\S+$")]


class Region(StrEnum):
    """Deployment labels, not a geographic authorization or compliance assertion."""

    EUROPE = "EU"
    CHINA = "CN"
    CANADA = "CA"
    SINGAPORE = "SG"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DeploymentRef(ContractModel):
    deployment_id: Identifier
    region: Region


class PrincipalRef(ContractModel):
    """A local principal identifier always qualified by its issuing deployment."""

    deployment_id: Identifier
    principal_id: Identifier


class ResourceRef(ContractModel):
    origin_deployment_id: Identifier
    kind: Literal["strategy", "dataset"]
    resource_id: Identifier
    revision: Identifier


class PayloadDescriptor(ContractModel):
    schema_id: Reference
    media_type: Literal["application/json", "application/vnd.apache.parquet", "text/csv"]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    byte_length: Annotated[int, Field(strict=True, ge=0)]


class ExchangeEnvelope(ContractModel):
    """Metadata for one explicitly approved, immutable resource revision.

    Evidence references must be resolved and verified by a future trusted receiver.
    Merely filling them in is never sufficient to grant access.
    """

    contract_version: Literal["eurogas.exchange/1"]
    transfer_id: UUID
    idempotency_key: Identifier
    source: DeploymentRef
    destination: DeploymentRef
    actor: PrincipalRef
    owner: PrincipalRef
    resource: ResourceRef
    purpose: Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
    source_visibility: Literal["PRIVATE", "PUBLIC", "GROUPS"]
    provenance_refs: Annotated[tuple[Reference, ...], Field(min_length=1, max_length=64)]
    policy_ref: Reference
    owner_approval_ref: Reference
    entitlement_ref: Reference
    created_at: datetime
    expires_at: datetime
    payload: PayloadDescriptor

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("exchange timestamps must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def consistent_metadata(self) -> ExchangeEnvelope:
        if self.source.deployment_id == self.destination.deployment_id:
            raise ValueError("exchange requires distinct source and destination deployments")
        if self.actor.deployment_id != self.source.deployment_id:
            raise ValueError("actor must be qualified by the sending deployment")
        if self.owner.deployment_id != self.resource.origin_deployment_id:
            raise ValueError("owner must be qualified by the resource origin deployment")
        lifetime = self.expires_at - self.created_at
        if lifetime <= timedelta(0) or lifetime > MAX_ENVELOPE_LIFETIME:
            raise ValueError("envelope lifetime must be positive and at most seven days")
        if len(set(self.provenance_refs)) != len(self.provenance_refs):
            raise ValueError("provenance references must be unique")
        return self


def verify_delivery_integrity(
    envelope: ExchangeEnvelope,
    payload: bytes,
    *,
    expected_source: DeploymentRef,
    expected_destination: DeploymentRef,
    supported_payload_schemas: frozenset[str],
    now: datetime,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> None:
    """Check offline binding, freshness, schema identifier, size and exact bytes.

    Expected peer bindings and supported schemas must come from trusted receiver
    configuration, never from the submitted envelope. This function does not parse
    the payload against its resource schema or validate policy/approval references.
    A future receiver must perform those checks and authentication/authorization
    before accepting, persisting or returning any payload.
    """

    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("verification time must be timezone-aware UTC")
    if isinstance(max_payload_bytes, bool) or not isinstance(max_payload_bytes, int):
        raise ValueError("payload limit must be a nonnegative integer")
    if max_payload_bytes < 0:
        raise ValueError("payload limit must be a nonnegative integer")
    if envelope.source != expected_source or envelope.destination != expected_destination:
        raise ValueError("exchange deployment binding mismatch")
    if envelope.created_at > now + timedelta(minutes=5) or envelope.expires_at <= now:
        raise ValueError("exchange is future-dated or expired")
    if envelope.payload.schema_id not in supported_payload_schemas:
        raise ValueError("unsupported payload schema")
    if envelope.payload.byte_length > max_payload_bytes or len(payload) > max_payload_bytes:
        raise ValueError("payload exceeds receiver limit")
    if len(payload) != envelope.payload.byte_length:
        raise ValueError("payload length mismatch")
    if sha256(payload).hexdigest() != envelope.payload.sha256:
        raise ValueError("payload digest mismatch")
