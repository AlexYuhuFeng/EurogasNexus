"""Audit event model — import-safe shell for future persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class AuditSeverity(StrEnum):
    """Severity classification for audit events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AuditEvent:
    """An immutable record of a governed runtime action.

    This is a contract shell. Persistence (DB table, log sink, etc.) is
    added in a later milestone. The model must remain import-safe and
    never import web, client, or vendor-specific modules.
    """

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    event_type: str = "governance.action"
    severity: AuditSeverity = AuditSeverity.INFO
    principal: str = ""
    action: str = ""
    resource: str = ""
    outcome: str = ""
    detail: str = ""
    event_ts_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    source_system: str = ""
    human_review_required: bool = True
