"""Normalized monitoring alert contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class MonitoringCandidate:
    """Deterministic condition ready for persistence and optional enrichment."""

    fingerprint: str
    category: str
    alert_type: str
    severity: str
    title_en: str
    title_zh_cn: str
    message_en: str
    message_zh_cn: str
    entity_type: str
    entity_id: str
    event_time_utc: datetime
    evidence_snapshot: dict
    source_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    simulated: bool = False
    human_review_required: bool = True


SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}

__all__ = ["MonitoringCandidate", "SEVERITY_ORDER"]

