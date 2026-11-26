"""Retention by data class: schedule, dry run, run, policy, archives and restore.

Replaces ``prune_runtime_data.py`` (which deleted quotes after 30 days and observations after
90, archiving nothing). The scheduler runs the same pass once a day
(``EUROGAS_NEXUS_RETENTION_MODE``, ``EUROGAS_NEXUS_RETENTION_HOUR_UTC``); this script is for an
operator. Every command prints JSON; secrets are never printed.

    python scripts/ops/retention.py schedule
    python scripts/ops/retention.py plan                      # dry run: what a run would do
    python scripts/ops/retention.py run --principal ops.jane  # enforce (archive, verify, remove)
    python scripts/ops/retention.py run --until-done          # work through a backlog
    python scripts/ops/retention.py set-policy --class live_ticks --hot-days 365 \\
        --principal ops.jane --reason "surveillance asked for a year of ticks"
    python scripts/ops/retention.py archives [--class live_ticks]
    python scripts/ops/retention.py show --archive-id arc-... [--limit 20]
    python scripts/ops/retention.py restore --archive-id arc-... --principal ops.jane
    python scripts/ops/retention.py inline-raw-pages          # only before a downgrade below 0095

Configuration: the runtime database URL as for every script, and the object store
(``EUROGAS_NEXUS_OBJECT_STORE_URL`` and friends, ``runtime_store/object_store.py``). Without an
object store a run archives nothing and removes nothing, and says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _path in (_ROOT / "src", _ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def _json(value) -> str:
    def default(item):
        if isinstance(item, datetime | date):
            return item.isoformat()
        return str(item)

    return json.dumps(value, indent=2, sort_keys=True, default=default)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schedule", help="The retention schedule in force.")
    commands.add_parser("plan", help="Dry run: what an enforced run would do now.")
    run = commands.add_parser("run", help="Enforced run: archive, verify, then remove.")
    run.add_argument("--principal", default="operator")
    run.add_argument("--until-done", action="store_true", help="Repeat until nothing is due.")
    run.add_argument("--days-per-class", type=int, default=7)
    policy = commands.add_parser("set-policy", help="Raise a hot period or switch an action.")
    policy.add_argument("--class", dest="data_class", required=True)
    policy.add_argument("--hot-days", type=int)
    policy.add_argument("--disable", action="store_true")
    policy.add_argument("--principal", required=True)
    policy.add_argument("--reason", required=True)
    archives = commands.add_parser("archives", help="Archived ranges.")
    archives.add_argument("--class", dest="data_class")
    show = commands.add_parser("show", help="Read an archive without loading it.")
    show.add_argument("--archive-id", required=True)
    show.add_argument("--limit", type=int, default=20)
    restore = commands.add_parser("restore", help="Load an archived range back.")
    restore.add_argument("--archive-id", required=True)
    restore.add_argument("--principal", required=True)
    commands.add_parser("inline-raw-pages", help="Put raw pages back on their receipts.")
    args = parser.parse_args(argv)

    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        print(_json({"status": "blocked", "reason": "database_url_missing"}))
        return 2

    from eurogas_nexus.application import retention

    factory = get_session_factory()
    if args.command == "schedule":
        with factory() as session:
            print(_json(retention.schedule_rows(session)))
        return 0
    if args.command == "plan":
        print(_json(retention.run_retention(factory, mode="dry_run", principal="operator")))
        return 0
    if args.command == "run":
        limits = retention.RunLimits(days_per_class=max(1, args.days_per_class))
        while True:
            report = retention.run_retention(
                factory, mode="enforce", principal=args.principal, limits=limits
            )
            print(_json(report), flush=True)
            if report["status"] != "ok" or not args.until_done or not _more_due(report):
                return 0 if report["status"] in {"ok", "skipped_locked"} else 1
    if args.command == "set-policy":
        with factory() as session:
            try:
                effective = retention.set_policy(
                    session,
                    data_class=args.data_class,
                    hot_days=args.hot_days,
                    enabled=not args.disable,
                    principal=args.principal,
                    reason=args.reason,
                )
            except retention.RetentionPolicyError as exc:
                print(_json({"status": "refused", "reason": str(exc)}))
                return 2
            session.commit()
        print(_json({"status": "ok", "data_class": args.data_class,
                     "hot_days": effective.hot_days, "enabled": effective.enabled}))
        return 0
    if args.command == "archives":
        from eurogas_nexus.db.models import RetentionArchiveRecord

        with factory() as session:
            query = session.query(RetentionArchiveRecord).order_by(
                RetentionArchiveRecord.data_class, RetentionArchiveRecord.range_start_utc
            )
            if args.data_class:
                query = query.filter(RetentionArchiveRecord.data_class == args.data_class)
            print(_json([
                {
                    column.name: getattr(row, column.name)
                    for column in RetentionArchiveRecord.__table__.columns
                }
                for row in query.all()
            ]))
        return 0
    if args.command == "show":
        with factory() as session:
            rows = []
            for row in retention.read_archive_rows(session, args.archive_id):
                rows.append(row)
                if len(rows) >= args.limit:
                    break
        print(_json(rows))
        return 0
    if args.command == "restore":
        with factory() as session:
            result = retention.restore_archive(
                session, args.archive_id, principal=args.principal
            )
            session.commit()
        print(_json({"status": "ok", **result}))
        return 0
    if args.command == "inline-raw-pages":
        from eurogas_nexus.db.repositories.raw_archive import restore_inline_payloads

        total = 0
        while True:
            with factory() as session:
                done = restore_inline_payloads(session)
                session.commit()
            total += done
            if done == 0:
                break
        print(_json({"status": "ok", "receipts_inlined": total}))
        return 0
    return 2


def _more_due(report: dict) -> bool:
    for entry in report["classes"].values():
        if entry.get("days_pending_after_run"):
            return True
        if entry.get("receipts_deduplicated") or entry.get("pages_offloaded"):
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
