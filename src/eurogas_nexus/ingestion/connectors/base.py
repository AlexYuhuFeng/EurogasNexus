"""Base connector protocol and mock implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eurogas_nexus.ingestion.contracts import IngestionPayload


@dataclass(frozen=True)
class ConnectorMetadata:
    """Metadata about a connector's capabilities and requirements."""

    source_system: str
    datasets: tuple[str, ...] = ()
    entitlement_required: bool = True
    credential_fields: tuple[str, ...] = ()
    polling_supported: bool = False
    request_mode_supported: bool = False
    freshness_expectation_minutes: int = 60
    export_restricted: bool = True
    research_only: bool = True


class Connector(Protocol):
    """Protocol for source connectors.

    Connectors fetch only — they do not analyze, rank, recommend, or calculate.
    """

    @property
    def metadata(self) -> ConnectorMetadata: ...

    def fetch(self, dataset: str) -> IngestionPayload: ...


class MockConnector:
    """Mock connector that returns empty payloads. Used when credentials or
    live access are unavailable. Never calls external APIs."""

    def __init__(self, source_system: str, datasets: tuple[str, ...] = ()) -> None:
        self._metadata = ConnectorMetadata(
            source_system=source_system,
            datasets=datasets,
            entitlement_required=True,
            research_only=True,
        )

    @property
    def metadata(self) -> ConnectorMetadata:
        return self._metadata

    def fetch(self, dataset: str) -> IngestionPayload:
        from datetime import UTC, datetime

        return IngestionPayload(
            source_name=f"mock-{self._metadata.source_system}",
            source_system=self._metadata.source_system,
            dataset=dataset,
            raw_data=[],
            retrieval_ts_utc=datetime.now(UTC).isoformat(),
            source_reference_id=f"mock-{self._metadata.source_system}-{dataset}",
        )
