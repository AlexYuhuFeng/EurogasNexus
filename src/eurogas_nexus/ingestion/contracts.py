"""Ingestion and source registry contracts (import-safe shells)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class SourceStatus(StrEnum):
    """Runtime status of a registered source system."""

    REGISTERED = "registered"
    ACTIVE = "active"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class IngestionRunStatus(StrEnum):
    """Status of a single ingestion run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class NormalizationStatus(StrEnum):
    """Normalization state for ingested data."""

    RAW = "raw"
    NORMALIZING = "normalizing"
    NORMALIZED = "normalized"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IngestionPayload:
    """Raw ingestion payload contract with source traceability."""

    source_name: str
    source_reference: str = ""
    collected_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    raw_blob_path: str = ""
    source_system: str = ""
    dataset: str = ""
    raw_data: list[dict] = field(default_factory=list)
    retrieval_ts_utc: str = ""
    source_reference_id: str = ""


@dataclass(frozen=True)
class SourceRegistryEntry:
    """A registered data source known to the ingestion control plane."""

    source_id: str
    source_system: str
    datasets: tuple[str, ...] = field(default_factory=tuple)
    status: SourceStatus = SourceStatus.UNKNOWN
    entitlement_scope: str = "internal-research"
    freshness_expectation_minutes: int = 60
    description: str = ""
    credential_requirements: tuple[str, ...] = field(default_factory=tuple)
    export_restrictions: tuple[str, ...] = field(default_factory=tuple)
    created_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


@dataclass(frozen=True)
class IngestionRun:
    """A single ingestion execution record."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    source_id: str = ""
    status: IngestionRunStatus = IngestionRunStatus.QUEUED
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    records_ingested: int = 0
    records_failed: int = 0
    normalization: NormalizationStatus = NormalizationStatus.UNKNOWN
    error_message: str | None = None
    source_reference: str = ""


@dataclass(frozen=True)
class NormalizedRecord:
    """A single record after normalization with traceability preserved."""

    source_system: str
    dataset: str
    normalized_data: dict
    source_reference_id: str
    normalization_status: NormalizationStatus = NormalizationStatus.NORMALIZED
    quality_checks_passed: int = 0
    quality_checks_failed: int = 0
