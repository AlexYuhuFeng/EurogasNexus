"""The gated database upgrade: plan, backup gate, timeouts, audit (plan section 3.10).

Production never migrates on start. An operator runs ``scripts/ops/upgrade_database.py
upgrade``, which

1. prints the pending revisions, each with its reversibility declaration (can it be undone,
   does it refuse when data would be lost, or does going back need the backup);
2. refuses unless a backup was recorded within the allowed age (``record-backup``, written
   by ``scripts/ops/backup_runtime.py`` after a good dump) or the operator overrides with a
   stated reason; an empty store needs none;
3. runs the migrations with ``lock_timeout`` and ``statement_timeout`` set
   (``alembic/env.py``), so a migration waiting for a lock fails and rolls back instead of
   stalling the desk behind it;
4. records who ran it, from which revision to which, the backup it relied on or the
   override reason, and the outcome, in the audit trail.

The development and demo profiles may keep upgrading on start
(``EUROGAS_NEXUS_AUTO_MIGRATE``, on by default outside trial and release); trial and release
refuse it even when set.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

BACKUP_ACTION = "database.backup.recorded"
UPGRADE_ACTION = "database.upgrade"
AUDIT_SOURCE = "database-upgrade"
DEFAULT_BACKUP_MAX_AGE_HOURS = 24.0
_PRODUCTION_ENVIRONMENTS = frozenset({"trial", "release", "production"})

REVERSIBILITY_TEXT = {
    "reversible": "yes: the downgrade undoes it",
    "conditional": "yes, unless data recorded since would be lost (it then refuses)",
    "no-op": "nothing to undo: the previous version works on the upgraded schema",
    "irreversible": "no: going back means restoring the backup",
}


class UpgradeRefused(RuntimeError):
    """The upgrade was not started; the message says why and what to do."""


@dataclass(frozen=True)
class PendingRevision:
    revision: str
    description: str
    reversibility: str
    note: str | None = None

    @property
    def downgrade_text(self) -> str:
        return REVERSIBILITY_TEXT.get(self.reversibility, "undeclared")


@dataclass
class UpgradePlan:
    current: str | None
    head: str | None
    pending: list[PendingRevision] = field(default_factory=list)
    empty_store: bool = False

    @property
    def up_to_date(self) -> bool:
        return not self.pending


def auto_migrate_enabled(environ: Any = None) -> bool:
    """Whether the start-up step may upgrade by itself (never in trial or release)."""

    env = os.environ if environ is None else environ
    environment = (env.get("EUROGAS_NEXUS_ENV") or "development").strip().lower()
    if environment in _PRODUCTION_ENVIRONMENTS:
        return False
    raw = (env.get("EUROGAS_NEXUS_AUTO_MIGRATE") or "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    return True


def auto_migrate_refused_in_production(environ: Any = None) -> bool:
    """True when auto-migrate was asked for where it is not allowed (for a clear message)."""

    env = os.environ if environ is None else environ
    environment = (env.get("EUROGAS_NEXUS_ENV") or "development").strip().lower()
    raw = (env.get("EUROGAS_NEXUS_AUTO_MIGRATE") or "").strip().lower()
    return environment in _PRODUCTION_ENVIRONMENTS and raw in {"1", "true", "on", "yes"}


def alembic_config(database_url: str, **attributes: Any):
    """An Alembic config for this source tree, bound to ``database_url``."""

    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    # alembic/env.py migrates this URL, not the environment's (they differ when the upgrade
    # runs as the schema owner from a shell that also names the application role).
    config.attributes["explicit_database_url"] = True
    config.attributes.update(attributes)
    return config


def _description(module_path: str | None, fallback: str) -> str:
    if not module_path:
        return fallback
    try:
        docstring = ast.get_docstring(ast.parse(Path(module_path).read_text(encoding="utf-8")))
    except (OSError, SyntaxError):
        return fallback
    first = (docstring or "").strip().splitlines()
    return first[0].strip() if first else fallback


def build_plan(engine, config) -> UpgradePlan:
    """Current revision, head, and the pending revisions in the order they would run."""

    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect

    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
        tables = [
            name for name in inspect(connection).get_table_names() if name != "alembic_version"
        ]
    pending: list[PendingRevision] = []
    if current != head:
        for script in reversed(list(scripts.iterate_revisions(head, current))):
            module = script.module
            pending.append(
                PendingRevision(
                    revision=script.revision,
                    description=_description(script.path, script.doc or script.revision),
                    reversibility=str(getattr(module, "reversibility", "undeclared")),
                    note=getattr(module, "reversibility_note", None),
                )
            )
    return UpgradePlan(
        current=current, head=head, pending=pending, empty_store=current is None and not tables
    )


def plan_lines(plan: UpgradePlan) -> list[str]:
    lines = [
        f"database revision : {plan.current or '(none: empty store)'}",
        f"this version needs: {plan.head}",
    ]
    if plan.up_to_date:
        lines.append("pending revisions : none (up to date)")
        return lines
    lines.append(f"pending revisions : {len(plan.pending)}, in this order")
    for item in plan.pending:
        lines.append(f"  {item.revision}  {item.description}")
        lines.append(f"      can be undone: {item.downgrade_text}")
        if item.note:
            lines.append(f"      note: {item.note}")
    irreversible = [item.revision for item in plan.pending if item.reversibility == "irreversible"]
    if irreversible:
        lines.append(
            "going back below " + ", ".join(irreversible) + " needs the pre-upgrade backup"
        )
    return lines


OWNER_ROLE_HINT = (
    "connect as the schema owner: the migrate service uses EUROGAS_NEXUS_OWNER_DB_USER "
    "(docs/security/DATABASE_ROLES.md); the application role cannot change the schema"
)


def ddl_refusal(engine) -> str | None:
    """Why the connected role cannot run the migrations, or None (PostgreSQL only).

    With the roles split (``deploy/runtime/database_roles.sql``) the services connect as
    ``eurogas_app``, which has no CREATE on the schema and owns no table: a migration run as it
    would fail at its first DDL statement. The upgrade refuses before it starts instead.
    """

    if engine.dialect.name != "postgresql":
        return None
    from sqlalchemy import text

    with engine.connect() as connection:
        role, may_create, owns_version = connection.execute(
            text(
                "SELECT current_user, has_schema_privilege(current_user, 'public', 'CREATE'), "
                "COALESCE((SELECT pg_has_role(current_user, tableowner, 'USAGE') "
                "FROM pg_tables WHERE schemaname = 'public' AND tablename = 'alembic_version'),"
                " true)"
            )
        ).one()
    if may_create and owns_version:
        return None
    return f"the database role {role!r} may not change the schema; {OWNER_ROLE_HINT}"


def _audit_table_exists(engine) -> bool:
    from sqlalchemy import inspect

    with engine.connect() as connection:
        return "audit_events" in inspect(connection).get_table_names()


@dataclass(frozen=True)
class BackupMarker:
    reference: str
    recorded_by: str
    recorded_at_utc: datetime
    kind: str

    def age_hours(self, now: datetime) -> float:
        return max(0.0, (now - self.recorded_at_utc).total_seconds() / 3600.0)


def latest_backup(session) -> BackupMarker | None:
    from eurogas_nexus.db.models.observation import AuditEventRecord
    from eurogas_nexus.domain.dataops.contracts import as_utc

    row = (
        session.query(AuditEventRecord)
        .filter(AuditEventRecord.action == BACKUP_ACTION, AuditEventRecord.outcome == "success")
        .order_by(AuditEventRecord.event_ts_utc.desc())
        .first()
    )
    if row is None:
        return None
    summary = row.after_summary or {}
    return BackupMarker(
        reference=str(summary.get("reference") or row.resource),
        recorded_by=row.principal,
        recorded_at_utc=as_utc(row.event_ts_utc),
        kind=str(summary.get("kind") or "unknown"),
    )


def record_backup(
    session, *, operator: str, reference: str, kind: str, now_utc: datetime | None = None
) -> None:
    """The backup marker the gated upgrade looks for: one audit event."""

    from eurogas_nexus.db.repositories.audit import record_audit_event

    record_audit_event(
        session,
        event_type="governance.operations",
        principal=_principal(operator),
        action=BACKUP_ACTION,
        resource=f"backup:{reference}"[:128],
        outcome="success",
        detail=f"kind={kind}; reference={reference}"[:2000],
        source_system=AUDIT_SOURCE,
        now_utc=now_utc,
        after_summary={"reference": reference, "kind": kind},
    )


def _principal(operator: str) -> str:
    text = " ".join(str(operator or "").split())
    if not text:
        raise UpgradeRefused("name the operator (--operator) so the audit trail records who ran it")
    return text[:64]


def check_backup(
    session,
    *,
    plan: UpgradePlan,
    max_age_hours: float,
    override_reason: str | None,
    now_utc: datetime,
) -> tuple[str, BackupMarker | None]:
    """``(basis, marker)``: why the upgrade may start; raises :class:`UpgradeRefused`."""

    if plan.empty_store:
        return "empty store: nothing to back up", None
    marker = latest_backup(session) if session is not None else None
    if marker is not None and marker.age_hours(now_utc) <= max_age_hours:
        return (
            f"backup {marker.reference} ({marker.kind}) recorded "
            f"{marker.recorded_at_utc.isoformat()} by {marker.recorded_by}",
            marker,
        )
    if override_reason and override_reason.strip():
        return f"no recent backup; overridden: {override_reason.strip()}", marker
    found = (
        f"the newest is {marker.reference}, {marker.age_hours(now_utc):.1f} h old"
        if marker
        else "none is recorded"
    )
    raise UpgradeRefused(
        f"no backup recorded in the last {max_age_hours:g} hours ({found}). Take one "
        "(scripts/ops/backup_runtime.py records it), or record an external one with "
        "`upgrade_database.py record-backup --reference ... --operator ...`, or override with "
        "--without-backup \"<reason>\" (recorded in the audit trail)."
    )


def _write_audit(engine, *, operator: str, outcome: str, detail: str, summary: dict) -> bool:
    """One upgrade audit row in its own transaction; False when there is no audit table yet."""

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.repositories.audit import record_audit_event

    if not _audit_table_exists(engine):
        return False
    with Session(engine) as session:
        record_audit_event(
            session,
            event_type="governance.operations",
            principal=_principal(operator),
            action=UPGRADE_ACTION,
            resource="database_schema",
            outcome=outcome,
            severity="warning" if outcome in {"failed", "overridden"} else "info",
            detail=detail[:4000],
            source_system=AUDIT_SOURCE,
            after_summary=summary,
        )
        session.commit()
    return True


def lock_timeout_hit(exc: BaseException) -> bool:
    text = f"{exc!r} {getattr(exc, 'orig', '')!r}".lower()
    return "55p03" in text or "lock timeout" in text or "lock_timeout" in text


def run_upgrade(
    database_url: str,
    *,
    operator: str,
    max_backup_age_hours: float = DEFAULT_BACKUP_MAX_AGE_HOURS,
    override_reason: str | None = None,
    lock_timeout: str | None = None,
    statement_timeout: str | None = None,
    emit=print,
    now_utc: datetime | None = None,
) -> int:
    """Plan, gate, migrate and audit. Returns 0 done/up to date, 1 failed, 2 refused."""

    from sqlalchemy.orm import Session

    from alembic import command
    from eurogas_nexus.db.migration_rules import migration_timeouts
    from eurogas_nexus.db.session import default_driver_url, get_engine

    principal = _principal(operator)
    now = now_utc or datetime.now(UTC)
    timeouts = migration_timeouts(
        {"lock_timeout": lock_timeout, "statement_timeout": statement_timeout}
    )
    # The URL as given (an ``sslmode`` kept): alembic/env.py turns it into pg8000's TLS context.
    url = default_driver_url(database_url)
    # The plan, the backup check and the audit rows: a bounded connect and keepalives, no
    # statement limit (the migrations themselves run under alembic/env.py's limits).
    engine = get_engine(database_url, one_off=True, statement_timeout=None)
    try:
        config = alembic_config(
            url,
            lock_timeout=timeouts[0],
            statement_timeout=timeouts[1],
        )
        plan = build_plan(engine, config)
        for line in plan_lines(plan):
            emit(line)
        if plan.up_to_date:
            return 0
        refusal = ddl_refusal(engine)
        if refusal:
            emit(f"REFUSED: {refusal}")
            return 2
        try:
            if _audit_table_exists(engine):
                with Session(engine) as session:
                    basis, marker = check_backup(
                        session,
                        plan=plan,
                        max_age_hours=max_backup_age_hours,
                        override_reason=override_reason,
                        now_utc=now,
                    )
            else:
                basis, marker = check_backup(
                    None,
                    plan=plan,
                    max_age_hours=max_backup_age_hours,
                    override_reason=override_reason,
                    now_utc=now,
                )
        except UpgradeRefused as refusal:
            emit(f"REFUSED: {refusal}")
            return 2
        emit(f"backup            : {basis}")
        emit(f"timeouts          : lock_timeout={timeouts[0]}, statement_timeout={timeouts[1]}")
        summary = {
            "from_revision": plan.current,
            "to_revision": plan.head,
            "revisions": [item.revision for item in plan.pending],
            "irreversible": [
                item.revision for item in plan.pending if item.reversibility == "irreversible"
            ],
            "backup_reference": marker.reference if marker else None,
            "override_reason": override_reason.strip()
            if override_reason and not (marker and marker.age_hours(now) <= max_backup_age_hours)
            else None,
            "lock_timeout": timeouts[0],
            "statement_timeout": timeouts[1],
        }
        _write_audit(
            engine,
            operator=principal,
            outcome="started",
            detail=f"upgrade {plan.current} -> {plan.head}; {basis}",
            summary=summary,
        )
        try:
            command.upgrade(config, "head")
        except Exception as exc:  # noqa: BLE001 - reported, audited, exit code 1
            reached = build_plan(engine, config).current
            reason = (
                "a migration waited longer than lock_timeout for a lock and was rolled back; "
                "retry when the database is quieter, or stop the writers first"
                if lock_timeout_hit(exc)
                else f"{exc.__class__.__name__}"
            )
            _write_audit(
                engine,
                operator=principal,
                outcome="failed",
                detail=f"upgrade {plan.current} -> {plan.head} stopped at {reached}: {reason}",
                summary={**summary, "reached_revision": reached},
            )
            emit(f"FAILED at {reached}: {reason}")
            return 1
        _write_audit(
            engine,
            operator=principal,
            outcome="succeeded",
            detail=f"upgrade {plan.current} -> {plan.head}; {basis}",
            summary=summary,
        )
        emit(f"upgraded to {plan.head}; recorded in the audit trail as {principal}")
        return 0
    finally:
        engine.dispose()


__all__ = [
    "BACKUP_ACTION",
    "DEFAULT_BACKUP_MAX_AGE_HOURS",
    "UPGRADE_ACTION",
    "BackupMarker",
    "PendingRevision",
    "UpgradePlan",
    "UpgradeRefused",
    "alembic_config",
    "auto_migrate_enabled",
    "auto_migrate_refused_in_production",
    "build_plan",
    "check_backup",
    "latest_backup",
    "plan_lines",
    "record_backup",
    "run_upgrade",
]
