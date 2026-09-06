"""Temporal leakage validator for point-in-time datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class LeakageSeverity(StrEnum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"


@dataclass(frozen=True)
class LeakageIssue:
    severity: LeakageSeverity
    code: str
    detail: str
    row: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "detail": self.detail,
            "row": self.row,
        }


class LeakageValidator:
    """Detect future knowledge in dataset rows."""

    def __init__(self, *, mode: str = "STRICT") -> None:
        self.mode = mode
        self.issues: list[LeakageIssue] = []

    def validate(
        self,
        rows: list[dict[str, Any]],
        *,
        target_ids: set[str] | None = None,
    ) -> list[LeakageIssue]:
        self.issues = []
        target_set = target_ids or set()
        for index, row in enumerate(rows):
            origin = row.get("forecast_origin")
            available = row.get("available_at")
            issued = row.get("forecast_issued_at")
            if origin is not None and available is not None:
                if _utc(available) > _utc(origin):
                    self._issue(
                        LeakageSeverity.BLOCKER,
                        "OBSERVATION_AVAILABLE_AFTER_ORIGIN",
                        f"row {index}: available_at after forecast origin",
                        row,
                    )
            if origin is not None and issued is not None:
                if _utc(issued) > _utc(origin):
                    self._issue(
                        LeakageSeverity.BLOCKER,
                        "FORECAST_ISSUED_AFTER_ORIGIN",
                        f"row {index}: forecast issued after origin",
                        row,
                    )
            feature_id = str(row.get("feature_id") or "")
            if feature_id in target_set:
                self._issue(
                    LeakageSeverity.BLOCKER,
                    "TARGET_USED_AS_FEATURE",
                    f"row {index}: target id {feature_id} appears as a feature",
                    row,
                )
            if str(row.get("quality_state") or "").upper() == "FORWARD_FILLED":
                age = row.get("source_age_seconds")
                if age is None or float(age) < 0:
                    self._issue(
                        LeakageSeverity.WARNING,
                        "UNBOUNDED_FORWARD_FILL",
                        f"row {index}: forward-filled value lacks bounded age",
                        row,
                    )
            if (
                str(row.get("temporal_integrity") or "").upper()
                == "TEMPORAL_APPROXIMATE"
                and self.mode == "STRICT"
            ):
                self._issue(
                    LeakageSeverity.BLOCKER,
                    "TEMPORAL_APPROXIMATE_IN_STRICT_DATASET",
                    f"row {index}: temporal-approximate source in strict mode",
                    row,
                )
            if str(row.get("temporal_integrity") or "").upper() == "TEMPORAL_INSUFFICIENT":
                if self.mode == "STRICT":
                    self._issue(
                        LeakageSeverity.BLOCKER,
                        "TEMPORAL_INSUFFICIENT_IN_STRICT_DATASET",
                        f"row {index}: temporal-insufficient source in strict mode",
                        row,
                    )
                else:
                    self._issue(
                        LeakageSeverity.WARNING,
                        "TEMPORAL_INSUFFICIENT_EXPLORATORY",
                        f"row {index}: temporal-insufficient source permitted in exploratory mode",
                        row,
                    )
        return self.issues

    def blockers(self) -> list[LeakageIssue]:
        return [issue for issue in self.issues if issue.severity is LeakageSeverity.BLOCKER]

    def _issue(
        self,
        severity: LeakageSeverity,
        code: str,
        detail: str,
        row: dict[str, Any],
    ) -> None:
        self.issues.append(LeakageIssue(severity, code, detail, row))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
