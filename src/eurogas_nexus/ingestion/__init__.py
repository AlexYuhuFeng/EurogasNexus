"""Ingestion package — source registry, connector contracts, and run tracking."""

from eurogas_nexus.ingestion.contracts import (
    IngestionPayload,
    IngestionRun,
    IngestionRunStatus,
    NormalizationStatus,
    NormalizedRecord,
    SourceRegistryEntry,
    SourceStatus,
)

__all__ = [
    "IngestionPayload",
    "IngestionRun",
    "IngestionRunStatus",
    "NormalizationStatus",
    "NormalizedRecord",
    "SourceRegistryEntry",
    "SourceStatus",
]
