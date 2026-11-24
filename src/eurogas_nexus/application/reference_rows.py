"""One reference row (credit line, mandate, hedge band, terminal terms) planned and written.

The risk routes and the maker-checker approval (P-17) write these rows the same way: each
changed field's before and after on the governed audit row, an evaluation made due (CP-13),
and a hedge band captured with the contract (M5b). Planning computes the same diff without
changing anything, so a proposal shows what its approval will change.

限额与参考数据行的变更计划与写入（风险路由与四眼批准共用）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

#: What each reference write changes for the opportunity evaluators (CP-13).
INPUT_CLASS_BY_ACTION = {
    "risk.credit_line.update": "limits",
    "risk.mandate.update": "limits",
    "risk.hedge_approval.update": "book",
    "lng.terminal_terms.update": "tariffs",
}


def json_safe(value: Any) -> Any:
    """A stored value as JSON for the audit trail and a proposal (dates as ISO text)."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def from_json(record_type: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Values kept as JSON in a proposal, typed again for the record's columns."""

    columns = record_type.__table__.columns
    typed: dict[str, Any] = {}
    for name, value in values.items():
        column = columns.get(name)
        if column is not None and isinstance(value, str):
            try:
                python_type = column.type.python_type
            except NotImplementedError:
                python_type = None
            if python_type is date:
                value = date.fromisoformat(value)
            elif python_type is datetime:
                value = datetime.fromisoformat(value)
        typed[name] = value
    return typed


@dataclass(frozen=True, slots=True)
class PlannedRow:
    """What writing ``values`` to one row would do."""

    created: bool
    values: dict[str, Any]
    changes: dict[str, tuple[Any, Any]]

    def before(self) -> dict[str, Any] | None:
        """Each changed field as stored now, or ``None`` for a new row."""

        if self.created:
            return None
        return {name: json_safe(before) for name, (before, _after) in self.changes.items()}

    def after(self) -> dict[str, Any]:
        return {name: json_safe(after) for name, (_before, after) in self.changes.items()}


def plan_row(
    session: Any,
    record_type: Any,
    key: str,
    values: dict[str, Any],
    defaults: dict[str, Any] | None = None,
) -> PlannedRow:
    """The fields a write would change, without changing anything.

    ``values`` holds the fields the caller sent; ``defaults`` fill the rest only when the row
    is new, so a field left out of a change keeps its stored value.
    """

    row = session.get(record_type, key)
    created = row is None
    merged = {**(defaults or {}), **values} if created else dict(values)
    changes = {
        name: (None if created else getattr(row, name, None), value)
        for name, value in merged.items()
        if created or getattr(row, name, None) != value
    }
    return PlannedRow(created=created, values=merged, changes=changes)


def current_fields(session: Any, record_type: Any, key: str, names: list[str]) -> dict | None:
    """The named fields as stored now (JSON), or ``None`` when the row does not exist."""

    row = session.get(record_type, key)
    if row is None:
        return None
    return {name: json_safe(getattr(row, name, None)) for name in names}


def write_row(
    session: Any,
    *,
    record_type: Any,
    key: str,
    values: dict[str, Any],
    defaults: dict[str, Any] | None,
    action: str,
    resource: str,
    actor: str,
    event_type: str,
    approved_by: str | None = None,
    change_id: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Create or change one reference row, audited with each changed field's before and after.

    ``actor`` set the figures and is recorded as ``updated_by``. When a second person approved
    the change (P-17), ``approved_by`` and ``change_id`` say so: the row keeps the change id
    (its provenance) and the audit row names both people. The caller commits.
    """

    from eurogas_nexus.application.audit_service import record_governed_audit
    from eurogas_nexus.application.opportunities.schedule import note_input_changed

    now = now_utc or datetime.now(UTC)
    planned = plan_row(session, record_type, key, values, defaults)
    row = session.get(record_type, key)
    if row is None:
        row = record_type(**{record_type.__mapper__.primary_key[0].key: key})
        session.add(row)
    for name, value in planned.values.items():
        setattr(row, name, value)
    row.updated_by = actor
    row.updated_at_utc = now
    row.change_id = change_id
    created, changes = planned.created, planned.changes
    detail = "; ".join(
        f"{name}: {before!r} -> {after!r}" if not created else f"{name}={after!r}"
        for name, (before, after) in changes.items()
        if name != "aliases"
    )
    if approved_by:
        detail = f"proposed by {actor}, approved by {approved_by} ({change_id}); {detail}"
    # GOV-1 (P5): the audit row is part of the write; no row, no change.
    record_governed_audit(
        session,
        event_type=event_type,
        principal=approved_by or actor,
        action=action,
        resource=resource,
        outcome="created" if created else "updated",
        severity="info",
        detail=detail[:1000] or "no change",
        before_summary=planned.before(),
        after_summary=planned.after(),
        now_utc=now,
    )
    # CP-13: a limit, hedge band or terminal terms change makes an evaluation due.
    note_input_changed(session, INPUT_CLASS_BY_ACTION[action], reason=action)
    if record_type.__tablename__ == "hedge_approvals":
        from eurogas_nexus.application.market_event_capture import capture_desk

        # M5b: a hedge band is part of the contract an opportunity reads.
        capture_desk(session, contract_ids=[key])
    return {
        "key": key,
        "created": created,
        "updated_by": actor,
        "changed": sorted(changes),
    }


__all__ = [
    "INPUT_CLASS_BY_ACTION",
    "PlannedRow",
    "current_fields",
    "from_json",
    "json_safe",
    "plan_row",
    "write_row",
]
