"""Data-quality contract shells (deterministic, read-only)."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class QualityCheckResult:
    """Deterministic read-only quality-check result."""

    check_name: str
    passed: bool
    details: str
    research_only: bool = True


class QualityCheck(Protocol):
    """Data-quality check contract."""

    def evaluate(self, dataset_id: str) -> QualityCheckResult: ...
