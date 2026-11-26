"""Proposed changes to limits and reference data awaiting a second person (P-17). Migration 0081.

One row per proposal: what it changes (the write's audit action, the record, each field
before and after), who proposed it, why and when, and what became of it (approved, rejected
or withdrawn, by whom, when, with a note). The values to apply are kept as the proposer sent
them, so an approval applies exactly what the approver saw. A record changed by an approved
proposal carries its ``change_id``, which is how a screen says who proposed and who approved
the figure it shows.

待第二人批准的限额与参考数据变更（四眼原则）。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class ChangeRequestRecord(Base):
    """One proposed change to a limit or a piece of reference data."""

    __tablename__ = "change_requests"
    __table_args__ = (
        Index("ix_change_requests_state", "state", "proposed_at_utc"),
        Index("ix_change_requests_resource", "resource", "state"),
    )

    change_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    #: The governed write's audit action (``risk.credit_line.update``, ...).
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    #: ``credit_line``, ``trader_mandate``, ``hedge_approval``, ``firm_marks``,
    #: ``lng_terminal_terms`` or ``freight_route`` (``governance/four_eyes.py``).
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The record as the audit trail names it (``credit_line:C1``).
    resource: Mapped[str] = mapped_column(String(160), nullable=False)
    target_key: Mapped[str] = mapped_column(String(160), nullable=False)
    #: The record in words (a counterparty's name, a terminal's name, the hubs of a grid).
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    #: What the approval applies, as the proposer sent it.
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    #: Each changed field before (``None`` for a new record) and after.
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    #: ``pending``, ``approved``, ``rejected`` or ``withdrawn``.
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    proposed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PrivilegedChangeRecord(Base):
    """A security-relevant change awaiting a second administrator (security review H7).

    Granting roles or scopes, creating a privileged account, resetting another person's
    password or second factor, switching four eyes off, enabling an AI use, changing alert
    recipients and pruning the audit trail are each requested by one administrator and take
    effect only after a different one approves. The request keeps the exact call (method,
    path and a hash of the body) so the approved change is the one that is made, once.
    Migration 0095.
    """

    __tablename__ = "privileged_changes"
    __table_args__ = (Index("ix_privileged_changes_state", "state", "requested_at_utc"),)

    change_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(200), nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    body_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    #: ``pending``, ``approved``, ``rejected``, ``withdrawn`` or ``applied``.
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_by_name: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decided_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    applied_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
