"""Ingestion contract shell types."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionPayload:
    """Raw ingestion payload contract with source traceability."""

    source_name: str
    source_reference: str
    collected_at_utc: str
    raw_blob_path: str
