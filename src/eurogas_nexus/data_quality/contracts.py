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
    """Data-quality check contract.

    质量检查协议：实现必须是确定性的只读校验，不访问网络/外部服务。
    """

    def evaluate(self, dataset_id: str) -> QualityCheckResult:
        """Run the check against one dataset.

        Args:
            dataset_id: Dataset identifier to check.

        Returns:
            A deterministic QualityCheckResult.
        """

        ...
