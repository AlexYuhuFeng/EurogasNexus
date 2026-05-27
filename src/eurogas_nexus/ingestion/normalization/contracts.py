"""Normalization contract shell types."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedRecord:
    """Normalized record shell preserving traceability."""

    dataset_id: str
    source_name: str
    source_reference: str
    canonical_path: str
    research_only: bool = True
