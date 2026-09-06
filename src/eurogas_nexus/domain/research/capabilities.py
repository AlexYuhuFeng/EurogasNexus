"""Typed capability contracts for future agent adapters.

MCP is an adapter later (CR-15). These contracts keep agents away from DB
tables and UI internals while giving them typed, permission-aware,
provenance-aware analytical entry points.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CapabilityReadWriteClass(StrEnum):
    READ = "read"
    READ_ONLY_COMPUTE = "read_only_compute"
    WRITE_MATERIALIZED = "write_materialized"
    EXPORT = "export"


class CapabilitySideEffectClass(StrEnum):
    NONE = "none"
    PERSISTS_SNAPSHOT = "persists_snapshot"
    PERSISTS_DEFINITION = "persists_definition"


class CapabilityContract(BaseModel):
    """Metadata contract for one agent-callable analytical capability."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    read_write_class: CapabilityReadWriteClass
    deterministic: bool = True
    side_effect_class: CapabilitySideEffectClass = CapabilitySideEffectClass.NONE
    required_permission: str = "research.read"
    required_entitlement: str | None = None
    freshness_requirements: str = "none"
    provenance_behavior: str = "returns_source_references"
    timeout_seconds: int = 30
    error_codes: list[str] = Field(default_factory=list)

    def public_metadata(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


REGISTERED_RESEARCH_CAPABILITIES: tuple[CapabilityContract, ...] = (
    CapabilityContract(
        name="ontology.resolve_entity",
        description="Resolve a source-specific entity identifier to a canonical entity.",
        input_schema={
            "type": "object",
            "properties": {
                "source_id": {"type": "string"},
                "source_entity_type": {"type": "string"},
                "source_identifier": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "canonical_entity_id": {"type": "string"},
                "confidence": {"type": "string"},
            },
        },
        read_write_class=CapabilityReadWriteClass.READ_ONLY_COMPUTE,
    ),
    CapabilityContract(
        name="ontology.describe_entity",
        description="Return semantic description and relationships for a canonical entity.",
        input_schema={"type": "object", "properties": {"canonical_entity_id": {"type": "string"}}},
        output_schema={
            "type": "object",
            "properties": {"entity_type": {"type": "string"}, "relationships": {"type": "array"}},
        },
        read_write_class=CapabilityReadWriteClass.READ,
    ),
    CapabilityContract(
        name="data.get_series_metadata",
        description="Return canonical series metadata, never raw DB schema.",
        input_schema={"type": "object", "properties": {"series_id": {"type": "string"}}},
        output_schema={
            "type": "object",
            "properties": {"series_id": {"type": "string"}, "unit": {"type": "string"}},
        },
        read_write_class=CapabilityReadWriteClass.READ,
    ),
    CapabilityContract(
        name="data.get_observations_as_of",
        description="Return point-in-time eligible observations at a cutoff.",
        input_schema={
            "type": "object",
            "properties": {
                "series_id": {"type": "string"},
                "cutoff": {"type": "string", "format": "date-time"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "observations": {"type": "array"},
                "temporal_integrity": {"type": "string"},
            },
        },
        read_write_class=CapabilityReadWriteClass.READ_ONLY_COMPUTE,
        freshness_requirements="source_freshness_checked",
    ),
    CapabilityContract(
        name="analytics.get_feature_definition",
        description="Return one versioned feature definition and dependencies.",
        input_schema={"type": "object", "properties": {"feature_id": {"type": "string"}}},
        output_schema={
            "type": "object",
            "properties": {
                "feature_id": {"type": "string"},
                "availability_class": {"type": "string"},
            },
        },
        read_write_class=CapabilityReadWriteClass.READ,
    ),
    CapabilityContract(
        name="dataset.validate_spec",
        description="Validate a DatasetSpec without building it.",
        input_schema={"type": "object", "properties": {"spec": {"type": "object"}}},
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}, "issues": {"type": "array"}},
        },
        read_write_class=CapabilityReadWriteClass.READ_ONLY_COMPUTE,
    ),
    CapabilityContract(
        name="dataset.build",
        description="Build an immutable DatasetSnapshot from a validated spec.",
        input_schema={"type": "object", "properties": {"spec": {"type": "object"}}},
        output_schema={
            "type": "object",
            "properties": {"snapshot_id": {"type": "string"}, "row_count": {"type": "integer"}},
        },
        read_write_class=CapabilityReadWriteClass.WRITE_MATERIALIZED,
        side_effect_class=CapabilitySideEffectClass.PERSISTS_SNAPSHOT,
        required_permission="research.dataset.build",
        timeout_seconds=120,
    ),
    CapabilityContract(
        name="dataset.inspect_snapshot",
        description="Inspect snapshot metadata, quality, and provenance.",
        input_schema={"type": "object", "properties": {"dataset_snapshot_id": {"type": "string"}}},
        output_schema={
            "type": "object",
            "properties": {
                "dataset_snapshot_id": {"type": "string"},
                "row_count": {"type": "integer"},
            },
        },
        read_write_class=CapabilityReadWriteClass.READ,
    ),
    CapabilityContract(
        name="dataset.temporal_integrity_report",
        description="Return machine-readable temporal leakage/integrity report.",
        input_schema={"type": "object", "properties": {"dataset_snapshot_id": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"issues": {"type": "array"}}},
        read_write_class=CapabilityReadWriteClass.READ,
    ),
    CapabilityContract(
        name="dataset.export",
        description="Export a snapshot to Parquet/CSV under entitlement checks.",
        input_schema={
            "type": "object",
            "properties": {
                "dataset_snapshot_id": {"type": "string"},
                "format": {"enum": ["parquet", "csv"]},
            },
        },
        output_schema={
            "type": "object",
            "properties": {"artifact_id": {"type": "string"}, "format": {"type": "string"}},
        },
        read_write_class=CapabilityReadWriteClass.EXPORT,
        side_effect_class=CapabilitySideEffectClass.PERSISTS_SNAPSHOT,
        required_permission="research.dataset.export",
        required_entitlement="dataset_sources_export_allowed",
        error_codes=["EXPORT_DENIED_ENTITLEMENT", "EXPORT_DENIED_UNKNOWN_POLICY"],
    ),
)
