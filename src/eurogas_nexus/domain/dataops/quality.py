"""Structured data-quality framework for ingestion runs.

Quality issues are persisted with stable codes, never free-text-only errors.
Outlier checks are WARNING/REVIEW, never automatic deletion.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from eurogas_nexus.domain.dataops.contracts import (
    QualityIssue,
    QualityResult,
    QualitySeverity,
    QualitySummary,
)

QUALITY_CODES = frozenset(
    {
        "REQUIRED_FIELD",
        "TYPE",
        "UNIT",
        "CURRENCY",
        "TIMESTAMP",
        "DUPLICATE",
        "RANGE",
        "NEGATIVE_VALUE",
        "SEQUENCE_GAP",
        "DELIVERY_WINDOW",
        "HUB_MAPPING",
        "PRODUCT_MAPPING",
        "OUTLIER",
        "CROSS_SOURCE_CONSISTENCY",
    }
)

_ALLOWED_UNITS = frozenset(
    {"EUR/MWh", "GBP/MWh", "MWh/d", "mcm/d", "kWh/d", "TWh", "percent"}
)
_ALLOWED_CURRENCIES = frozenset({"EUR", "GBP", "USD", "CHF", "NOK", "DKK", "PLN"})


def make_issue(
    code: str,
    severity: QualitySeverity | str,
    *,
    field: str = "",
    observation_reference: str = "",
    message: str = "",
    rule_version: str = "dataops-quality/1",
) -> QualityIssue:
    """Build one structured quality issue (unknown codes become TYPE)."""

    normalized = str(code).strip().upper()
    if normalized not in QUALITY_CODES:
        normalized = "TYPE"
    return QualityIssue(
        quality_code=normalized,
        severity=(
            severity
            if isinstance(severity, QualitySeverity)
            else QualitySeverity(str(severity).upper())
        ),
        field=field,
        observation_reference=observation_reference,
        message=message or normalized.lower(),
        rule_version=rule_version,
    )


def summarize_quality(issues: Iterable[QualityIssue]) -> QualitySummary:
    """Summarize issues into PASSED / PASSED_WITH_WARNINGS / FAILED."""

    collected = tuple(issues)
    error_count = sum(issue.severity == QualitySeverity.ERROR for issue in collected)
    warning_count = sum(issue.severity == QualitySeverity.WARNING for issue in collected)
    if error_count:
        result = QualityResult.FAILED
    elif warning_count:
        result = QualityResult.PASSED_WITH_WARNINGS
    else:
        result = QualityResult.PASSED
    return QualitySummary(
        result=result,
        warning_count=warning_count,
        error_count=error_count,
        issues=collected,
    )


def validate_market_row(
    row: dict[str, Any],
    *,
    observation_reference: str = "",
) -> list[QualityIssue]:
    """Apply canonical checks to one normalized market-observation row.

    Outliers are WARNING only. Valid extreme market values are never deleted
    by this validator.
    """

    issues: list[QualityIssue] = []
    required = ("price", "unit", "currency", "period_start_utc", "period_end_utc", "source_system")
    for field in required:
        if row.get(field) in (None, ""):
            issues.append(
                make_issue(
                    "REQUIRED_FIELD",
                    QualitySeverity.ERROR,
                    field=field,
                    observation_reference=observation_reference,
                    message=f"Missing required field {field}.",
                )
            )
    if not isinstance(row.get("price"), (int, float)) and row.get("price") is not None:
        issues.append(
            make_issue(
                "TYPE",
                QualitySeverity.ERROR,
                field="price",
                observation_reference=observation_reference,
                message="price must be numeric.",
            )
        )
    if row.get("unit") not in _ALLOWED_UNITS and row.get("unit") not in (None, ""):
        issues.append(
            make_issue(
                "UNIT",
                QualitySeverity.ERROR,
                field="unit",
                observation_reference=observation_reference,
                message=f"Unsupported unit {row.get('unit')!r}.",
            )
        )
    if row.get("currency") not in _ALLOWED_CURRENCIES and row.get("currency") not in (None, ""):
        issues.append(
            make_issue(
                "CURRENCY",
                QualitySeverity.ERROR,
                field="currency",
                observation_reference=observation_reference,
                message=f"Unsupported currency {row.get('currency')!r}.",
            )
        )
    for field in ("period_start_utc", "period_end_utc", "observed_at_utc"):
        value = row.get(field)
        if value is None:
            continue
        if not isinstance(value, datetime):
            issues.append(
                make_issue(
                    "TIMESTAMP",
                    QualitySeverity.ERROR,
                    field=field,
                    observation_reference=observation_reference,
                    message=f"{field} must be an aware datetime.",
                )
            )
            continue
        if value.tzinfo is None:
            issues.append(
                make_issue(
                    "TIMESTAMP",
                    QualitySeverity.WARNING,
                    field=field,
                    observation_reference=observation_reference,
                    message=f"{field} is naive; normalized rows require UTC.",
                )
            )
    if isinstance(row.get("price"), (int, float)) and float(row["price"]) < 0:
        issues.append(
            make_issue(
                "NEGATIVE_VALUE",
                QualitySeverity.ERROR,
                field="price",
                observation_reference=observation_reference,
                message="Negative prices must be reviewed before acceptance.",
            )
        )
    if isinstance(row.get("price"), (int, float)) and float(row["price"]) > 5000:
        issues.append(
            make_issue(
                "OUTLIER",
                QualitySeverity.WARNING,
                field="price",
                observation_reference=observation_reference,
                message="Unusually high value; WARNING/REVIEW only, not deleted.",
            )
        )
    return issues
