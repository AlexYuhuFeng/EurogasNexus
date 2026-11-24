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


class GovernedAuditError(RuntimeError):
    """The audit row of a governed write could not be written, so the write must not happen.

    受治理写入的审计行无法写入；调用方不得提交事务。
    """

    code = "audit_unavailable"

    def __init__(self, action: str, cause: BaseException | None = None) -> None:
        self.action = action
        self.cause_type = cause.__class__.__name__ if cause is not None else None
        super().__init__(f"audit row for {action} could not be written")
