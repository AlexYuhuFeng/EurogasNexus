"""Runtime-store interface shells (import-safe)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Generic, Protocol, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Research-safe result envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultEnvelope(Generic[T]):
    """Research-safe result envelope with required metadata fields.

    Every runtime-store read that surfaces research data must wrap its payload
    in this envelope so consumers cannot ignore assumptions, missing inputs,
    warnings, lineage, or the research-only / human-review markers.
    """

    payload: T | None = None
    assumptions: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


# ---------------------------------------------------------------------------
# Freshness and quality
# ---------------------------------------------------------------------------


class FreshnessState(StrEnum):
    """Runtime freshness classification for any observation or derived result."""

    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class DataQualityRecord:
    """A single data-quality check result tied to a source reference."""

    check_name: str
    severity: str  # "error", "warning", or "info"
    passed: bool
    detail: str = ""
    source_reference_id: str = ""
    checked_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


# ---------------------------------------------------------------------------
# Source reference and lineage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceReference:
    """Provenance reference linking a runtime record to its origin."""

    reference_id: str
    source_system: str
    source_dataset: str = ""
    dataset_product: str = ""
    retrieval_ts_utc: str | None = None
    load_ts_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    schema_version: str = "1.0.0"
    freshness: FreshnessState = FreshnessState.UNKNOWN
    quality_results: tuple[DataQualityRecord, ...] = field(default_factory=tuple)
    is_test_fixture: bool = False
    raw_retention_path: str = ""
    entitlement_scope: str = "internal-research"


@dataclass(frozen=True)
class LineageRecord:
    """A single edge in the data lineage graph."""

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    event_type: str = "load"
    source_reference_id: str = ""
    target_reference_id: str = ""
    detail: str = ""
    event_ts_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


# ---------------------------------------------------------------------------
# Repository pattern
# ---------------------------------------------------------------------------


class RepositoryFactory(Protocol):
    """Protocol for runtime-store repository construction.

    Concretions receive a SQLAlchemy session and return typed repositories.
    """

    def __call__(self, session: Any) -> Any: ...


class RuntimeStoreRepository(ABC):
    """Abstract base for typed runtime-store repositories.

    Every concrete repository must wrap results in ResultEnvelope and
    reject file-fallback in trial/release environments.
    """

    @abstractmethod
    def list_all(self) -> ResultEnvelope[list[Any]]: ...


# ---------------------------------------------------------------------------
# Ephemeral runtime state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeartbeatRecord:
    """Ephemeral service heartbeat record."""

    service_name: str
    instance_id: str
    observed_at_utc: str


class RuntimeStore(Protocol):
    """Optional runtime-store abstraction for ephemeral state."""

    def get_heartbeat(self, service_name: str, instance_id: str) -> HeartbeatRecord | None: ...


# ---------------------------------------------------------------------------
# File-fallback policy markers (no-op at runtime; consumed by policy tests).
# ---------------------------------------------------------------------------


def _no_file_fallback_in_trial_or_release(environment: str) -> None:
    """Contract: trial and release modes must never fall back to local files.

    This is a placeholder read by policy-contract tests. Runtime store
    implementations in trial/release mode must raise or return a clearly
    marked PARTIAL envelope rather than silently reading a local file.
    """
    if environment in ("trial", "release"):
        raise RuntimeError(
            "Runtime store file fallback is forbidden in trial and release modes."
        )
