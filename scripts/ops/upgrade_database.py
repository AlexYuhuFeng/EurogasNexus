#!/usr/bin/env python
"""The gated database upgrade (operator runbook: docs/operations/DATABASE_UPGRADE.md).

Commands:

``plan``
    Print the database's revision, the revision this version needs, and each pending
    revision with whether it can be undone. Changes nothing. Exit 0.
``check``
    As ``plan``; exit 0 when the database is up to date, 1 when revisions are pending
    (the start-up step of a production stack: the API does not start on an old schema).
``upgrade --operator NAME [--without-backup REASON] [--yes]``
    Refuse unless a backup was recorded within ``--max-backup-age-hours`` (default 24) or
    ``--without-backup`` states why not; then migrate with ``lock_timeout`` and
    ``statement_timeout`` (``--lock-timeout``, ``--statement-timeout``; default 10s and 1h)
    and record who ran it, the revisions and the outcome in the audit trail. Asks for
    confirmation unless ``--yes``. Exit 0 done, 1 failed, 2 refused.
``record-backup --operator NAME --reference REF [--kind KIND]``
    Record a backup taken outside this product (pgBackRest, a managed database snapshot),
    so ``upgrade`` accepts it. ``scripts/ops/backup_runtime.py`` records its own dumps.
``on-start``
    The stack's start-up step. With ``EUROGAS_NEXUS_AUTO_MIGRATE`` in force (development
    and demo by default; never in trial or release) it upgrades, recorded as
    ``auto-migrate``; otherwise it is ``check``.

Never prints the database URL or a credential.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurogas_nexus.application import database_upgrade as upgrade  # noqa: E402
from eurogas_nexus.db.session import resolve_database_url  # noqa: E402

AUTO_OPERATOR = "auto-migrate"


def _database_url() -> str:
    url = resolve_database_url()
    if not url:
        print("the runtime database URL is not configured (RUNTIME_STORE_DATABASE_URL)")
        raise SystemExit(2)
    return url


def _plan() -> upgrade.UpgradePlan:
    from sqlalchemy import create_engine

    from eurogas_nexus.db.connection_url import pg8000_ssl_arguments
    from eurogas_nexus.db.session import default_driver_url

    url, ssl_arguments = pg8000_ssl_arguments(default_driver_url(_database_url()))
    engine = create_engine(url, connect_args=ssl_arguments or {}, future=True)
    try:
        return upgrade.build_plan(
            engine, upgrade.alembic_config(url.render_as_string(hide_password=False))
        )
    finally:
        engine.dispose()


def cmd_plan(_args) -> int:
    for line in upgrade.plan_lines(_plan()):
        print(line)
    return 0


def cmd_check(_args) -> int:
    plan = _plan()
    for line in upgrade.plan_lines(plan):
        print(line)
    if plan.up_to_date:
        return 0
    print(
        "the database needs the upgrade above before this version can start; run "
        "`python scripts/ops/upgrade_database.py upgrade --operator \"<your name>\"` "
        "(docs/operations/DATABASE_UPGRADE.md)"
    )
    return 1


def cmd_upgrade(args) -> int:
    if not args.yes:
        if not sys.stdin.isatty():
            print("refusing to upgrade without confirmation: pass --yes in a script")
            return 2
        for line in upgrade.plan_lines(_plan()):
            print(line)
        answer = input("upgrade the database now? type 'upgrade' to continue: ").strip()
        if answer != "upgrade":
            print("not upgraded")
            return 2
    try:
        return upgrade.run_upgrade(
            _database_url(),
            operator=args.operator,
            max_backup_age_hours=args.max_backup_age_hours,
            override_reason=args.without_backup,
            lock_timeout=args.lock_timeout,
            statement_timeout=args.statement_timeout,
        )
    except (upgrade.UpgradeRefused, ValueError) as refusal:
        print(f"REFUSED: {refusal}")
        return 2


def cmd_record_backup(args) -> int:
    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            upgrade.record_backup(
                session, operator=args.operator, reference=args.reference, kind=args.kind
            )
            session.commit()
    except upgrade.UpgradeRefused as refusal:
        print(f"REFUSED: {refusal}")
        return 2
    print(f"backup {args.reference} ({args.kind}) recorded")
    return 0


def cmd_on_start(_args) -> int:
    if upgrade.auto_migrate_refused_in_production():
        print(
            "EUROGAS_NEXUS_AUTO_MIGRATE is ignored in trial and release: upgrades there are "
            "the gated step (docs/operations/DATABASE_UPGRADE.md)"
        )
    if not upgrade.auto_migrate_enabled():
        return cmd_check(_args)
    return upgrade.run_upgrade(
        _database_url(),
        operator=AUTO_OPERATOR,
        override_reason="automatic upgrade at start (EUROGAS_NEXUS_AUTO_MIGRATE, "
        "development or demo)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="print the pending revisions; change nothing").set_defaults(
        func=cmd_plan
    )
    sub.add_parser("check", help="exit 1 when revisions are pending").set_defaults(
        func=cmd_check
    )
    run = sub.add_parser("upgrade", help="the gated upgrade")
    run.add_argument("--operator", required=True, help="who runs it (recorded in the audit)")
    run.add_argument(
        "--without-backup",
        metavar="REASON",
        help="upgrade without a recent recorded backup; the reason is audited",
    )
    run.add_argument(
        "--max-backup-age-hours",
        type=float,
        default=upgrade.DEFAULT_BACKUP_MAX_AGE_HOURS,
        help="how old the newest recorded backup may be (default 24)",
    )
    run.add_argument("--lock-timeout", help="per-statement lock wait, e.g. 10s (default 10s)")
    run.add_argument("--statement-timeout", help="per-statement limit, e.g. 2h (default 1h)")
    run.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    run.set_defaults(func=cmd_upgrade)
    backup = sub.add_parser("record-backup", help="record a backup taken outside the product")
    backup.add_argument("--operator", required=True)
    backup.add_argument("--reference", required=True, help="backup label, file or snapshot id")
    backup.add_argument(
        "--kind",
        default="external",
        choices=("pg_dump", "pgbackrest", "managed-snapshot", "external"),
    )
    backup.set_defaults(func=cmd_record_backup)
    sub.add_parser("on-start", help="the stack's start-up step").set_defaults(func=cmd_on_start)
    return parser


def main(argv: list[str] | None = None) -> int:
    from eurogas_nexus.core.structured_logging import configure_logging

    configure_logging(service="eurogas-nexus-upgrade")
    args = build_parser().parse_args(argv)
    from eurogas_nexus.security.portfolio_scope import system_scope

    # An operator's schema step reads and writes across every book (data migrations, the
    # backup marker and the audit row): it runs in the explicit system scope, so book
    # isolation (db/book_scope.py) never narrows or denies what a migration sees.
    with system_scope():
        return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
