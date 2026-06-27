"""Monitoring alert generation — research-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class MonitoringThreshold:
    field: str
    operator: str  # "gt", "lt", "gte", "lte"
    value: float
    severity: AlertSeverity = AlertSeverity.WARNING
    message_template: str = ""


@dataclass(frozen=True)
class MonitoringInput:
    entity_id: str
    entity_name: str
    observations: dict[str, float] = field(default_factory=dict)
    thresholds: list[MonitoringThreshold] = field(default_factory=list)


@dataclass(frozen=True)
class MonitoringAlert:
    alert_id: str
    entity_id: str
    entity_name: str
    alert_type: str
    severity: AlertSeverity
    message: str
    observed_value: float
    threshold_value: float
    triggered_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


@dataclass(frozen=True)
class MonitoringOutput:
    entity_id: str
    entity_name: str
    alerts: list[MonitoringAlert] = field(default_factory=list)
    total_alerts: int = 0
    assumptions: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


def generate_alerts(input_: MonitoringInput) -> MonitoringOutput:
    """Evaluate observations against thresholds and generate alerts."""

    missing: list[str] = []
    warnings: list[str] = []

    if not input_.entity_id:
        missing.append("entity_id is required.")
    if not input_.observations:
        warnings.append("No observations provided; no alerts generated.")

    alerts: list[MonitoringAlert] = []
    for th in input_.thresholds:
        observed = input_.observations.get(th.field)
        if observed is None:
            warnings.append(f"Field '{th.field}' not found in observations.")
            continue

        triggered = False
        if th.operator == "gt" and observed > th.value:
            triggered = True
        elif th.operator == "lt" and observed < th.value:
            triggered = True
        elif th.operator == "gte" and observed >= th.value:
            triggered = True
        elif th.operator == "lte" and observed <= th.value:
            triggered = True

        if triggered:
            msg = th.message_template.format(
                field=th.field, value=observed, threshold=th.value
            )
            alerts.append(MonitoringAlert(
                alert_id=f"alt-{input_.entity_id}-{th.field}",
                entity_id=input_.entity_id,
                entity_name=input_.entity_name,
                alert_type=f"threshold_{th.field}",
                severity=th.severity,
                message=msg,
                observed_value=observed,
                threshold_value=th.value,
            ))

    return MonitoringOutput(
        entity_id=input_.entity_id,
        entity_name=input_.entity_name,
        alerts=alerts,
        total_alerts=len(alerts),
        assumptions=["Threshold values are research benchmarks only."],
        missing_inputs=missing,
        warnings=warnings,
        source_references=["operator-input"],
        lineage=["monitoring-alert-generation"],
        human_review_required=bool(alerts),
    )
