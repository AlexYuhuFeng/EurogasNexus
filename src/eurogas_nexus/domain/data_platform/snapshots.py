"""Analysis Snapshot descriptor contract (Architecture V2 Wave 4).

``docs/engineering/Architecture-V2/07_DATA_PLATFORM.md`` section 6 makes the
Analysis Snapshot the reproducibility reference that scenario, optimisation,
strategy, report and AI evidence cite: a descriptor naming the as-of instant,
time basis, and the *versions* of every input the analysis was computed
against.

This module is pure Python. It defines:

- the canonical list of descriptor fields (``DESCRIPTOR_FIELDS``);
- :class:`AvailabilityState` / :class:`DescriptorFieldState`, so a field with
  no implementation is recorded as explicitly **unavailable** rather than
  fabricated - and the schema can accept the value later without a shape
  change;
- :class:`SnapshotDescriptor`, the domain-safe descriptor shape;
- :func:`descriptor_payload` and :func:`descriptor_content_hash`, so the same
  descriptor always hashes to the same reproducibility reference.

Nothing here reads a database, a clock or a provider. The application service
(``application/data_platform_snapshots.py``) builds a descriptor from the data
that actually exists at creation time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

#: Descriptor schema version. Bumped when the descriptor shape changes; a
#: reader must be able to consume an older version without a migration.
ANALYSIS_SNAPSHOT_SCHEMA_VERSION = "analysis-snapshot.v1"

#: The 07_DATA_PLATFORM.md section 6 fields, in canonical order. Every snapshot
#: records a state for each one, so "absent" is a declared fact rather than a
#: missing key.
DESCRIPTOR_FIELDS: tuple[str, ...] = (
    "market_data_versions",
    "network_capacity_version",
    "portfolio_version",
    "contract_resource_versions",
    "tariff_fx",
    "weather_demand_assumptions",
    "manual_assumptions",
    "model_calculation_versions",
    "entitlement_context",
)

#: Descriptor facts outside section 6 that belong on the envelope itself.
CONTEXT_FIELDS: tuple[str, ...] = (
    "active_context",
    "gas_day",
    "gas_day_calendar",
    "time_basis",
)

#: Active Context keys the backend accepts today. The Wave 1 contract
#: (``W1-01_SHELL_AND_ACTIVE_CONTEXT_CONTRACT.md`` section 3) names these
#: client-side; the backend stores the subset it can receive and refuses
#: anything else rather than persisting arbitrary keys.
ACTIVE_CONTEXT_KEYS: tuple[str, ...] = (
    "workspace",
    "task",
    "gas_day",
    "product",
    "hub",
    "route_id",
    "resource_id",
    "strategy_id",
    "strategy_version_id",
    "strategy_run_id",
    "portfolio_id",
)

#: Active Context dimensions the V2 target names but the backend cannot express
#: yet. They are declared here so the refusal can tell a caller exactly which
#: dimensions are still missing, instead of dropping them silently.
UNSUPPORTED_ACTIVE_CONTEXT_KEYS: tuple[str, ...] = ("organization", "decision_case")


class AvailabilityState(StrEnum):
    """Whether one descriptor field could be resolved at creation time.

    ``PARTIAL`` means part of the field is real and part is explicitly absent;
    the field's own detail payload then carries the per-part states. No state
    permits inventing a value.
    """

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DescriptorFieldState:
    """Declared availability of one descriptor field.

    Attributes:
        field: Field name from :data:`DESCRIPTOR_FIELDS`.
        state: Resolved availability.
        detail: Non-sensitive explanation of what was resolved.
        unavailable_reason: Stable reason code when the field is not fully
            available (never a missing key, never an empty string by accident).
    """

    field: str
    state: AvailabilityState
    detail: str = ""
    unavailable_reason: str = ""


@dataclass(frozen=True, slots=True)
class SnapshotDescriptor:
    """One Analysis Snapshot descriptor.

    Attributes:
        snapshot_id: Stable reproducibility reference cited by results.
        schema_version: Descriptor schema version.
        as_of_utc: The instant the analysis context is valid as of.
        gas_day: ISO date label of the CAM gas day containing ``as_of_utc``.
        gas_day_calendar: Versioned gas-day calendar used to resolve it.
        time_basis: Declared time basis of the snapshot's values.
        created_at_utc: When the snapshot was recorded.
        created_by: Principal that created it.
        market_data_versions: Market/observation version references.
        network_capacity_version: Network/capacity version reference.
        portfolio_version: Portfolio/position version reference.
        contract_resource_versions: Contract/resource version references.
        tariff_fx: Tariff and FX version references.
        weather_demand_assumptions: Weather/demand assumptions.
        manual_assumptions: Operator-supplied assumptions.
        model_calculation_versions: Model/calculation version references.
        entitlement_context: Entitlement context of the creating principal.
        field_states: Declared availability per descriptor field.
        active_context: The Active Context the snapshot was taken in.
        source_refs: Lineage references to the contributing runtime records.
        warnings: Explicit limitations a reader must see.
    """

    snapshot_id: str
    schema_version: str
    as_of_utc: datetime
    gas_day: str
    gas_day_calendar: str
    time_basis: str
    created_at_utc: datetime
    created_by: str
    market_data_versions: dict[str, Any] = field(default_factory=dict)
    network_capacity_version: dict[str, Any] = field(default_factory=dict)
    portfolio_version: dict[str, Any] = field(default_factory=dict)
    contract_resource_versions: dict[str, Any] = field(default_factory=dict)
    tariff_fx: dict[str, Any] = field(default_factory=dict)
    weather_demand_assumptions: dict[str, Any] = field(default_factory=dict)
    manual_assumptions: dict[str, Any] = field(default_factory=dict)
    model_calculation_versions: dict[str, Any] = field(default_factory=dict)
    entitlement_context: dict[str, Any] = field(default_factory=dict)
    field_states: tuple[DescriptorFieldState, ...] = ()
    active_context: dict[str, Any] = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def content_hash(self) -> str:
        """Return the deterministic hash of this descriptor's content."""

        return descriptor_content_hash(descriptor_payload(self))

    def state_for(self, name: str) -> DescriptorFieldState | None:
        """Return the declared state of one descriptor field, if recorded.

        Args:
            name: Field name from :data:`DESCRIPTOR_FIELDS`.

        Returns:
            The recorded state, or ``None`` when the field was not recorded.
        """

        for state in self.field_states:
            if state.field == name:
                return state
        return None


def descriptor_payload(descriptor: SnapshotDescriptor) -> dict[str, Any]:
    """Serialize a descriptor to its canonical, JSON-safe payload.

    The payload is what the API returns and what the hash is computed over, so
    a reader can recompute the reference from a published response.

    Args:
        descriptor: The descriptor to serialize.

    Returns:
        A dict with every descriptor field, ISO-8601 UTC timestamps and the
        declared per-field availability states.
    """

    return {
        "snapshot_id": descriptor.snapshot_id,
        "schema_version": descriptor.schema_version,
        "as_of_utc": _iso(descriptor.as_of_utc),
        "gas_day": descriptor.gas_day,
        "gas_day_calendar": descriptor.gas_day_calendar,
        "time_basis": descriptor.time_basis,
        "created_at_utc": _iso(descriptor.created_at_utc),
        "created_by": descriptor.created_by,
        "market_data_versions": descriptor.market_data_versions,
        "network_capacity_version": descriptor.network_capacity_version,
        "portfolio_version": descriptor.portfolio_version,
        "contract_resource_versions": descriptor.contract_resource_versions,
        "tariff_fx": descriptor.tariff_fx,
        "weather_demand_assumptions": descriptor.weather_demand_assumptions,
        "manual_assumptions": descriptor.manual_assumptions,
        "model_calculation_versions": descriptor.model_calculation_versions,
        "entitlement_context": descriptor.entitlement_context,
        "active_context": descriptor.active_context,
        "field_availability": [
            {
                "field": state.field,
                "state": state.state.value,
                "detail": state.detail,
                "unavailable_reason": state.unavailable_reason,
            }
            for state in descriptor.field_states
        ],
        "source_refs": list(descriptor.source_refs),
        "warnings": list(descriptor.warnings),
    }


def descriptor_content_hash(payload: dict[str, Any]) -> str:
    """Return a stable SHA-256 over a descriptor payload.

    The hash deliberately excludes ``content_hash`` itself so it can be carried
    on the payload without changing the value it denotes.

    Args:
        payload: A canonical descriptor payload.

    Returns:
        Lowercase hex SHA-256 of the canonical JSON encoding.
    """

    body = {key: value for key, value in payload.items() if key != "content_hash"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    """Return an aware UTC ISO-8601 string for a timestamp."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
