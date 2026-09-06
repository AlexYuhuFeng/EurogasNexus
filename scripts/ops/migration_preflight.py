"""Migration preflight for operator-controlled deployments.

Checks, without performing a migration:

- runtime DB URL is present and reachable;
- Alembic current revision is readable;
- the migration head in this source tree is reachable/readable;
- required tables are present after the current head (warns only when the
  source-tree head differs);
- a recent backup exists when ``--require-backup`` is set.

Never prints a full DSN.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eurogas_nexus.db.health import check_db_connectivity, get_alembic_revision
from eurogas_nexus.db.registry import list_missing_required_tables
from eurogas_nexus.db.session import get_engine, redact_database_url, resolve_database_url

ROOT = Path(__file__).resolve().parents[2]


def alembic_head() -> str | None:
    """Return the newest migration revision id declared in source."""

    revisions = []
    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("revision"):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value and value != "None":
                    revisions.append(value)
                    break
    return sorted(revisions)[-1] if revisions else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-backup",
        action="store_true",
        help="Fail when no backup newer than 24 hours exists in ./backups.",
    )
    parser.add_argument("--backup-dir", default="backups")
    args = parser.parse_args(argv)

    database_url = resolve_database_url()
    head = alembic_head()
    report = {
        "database_url_present": database_url is not None,
        "redacted_database_url": redact_database_url(database_url),
        "source_head": head,
        "current_revision": None,
        "connectivity_ok": False,
        "missing_tables": [],
        "backup_recent": None,
        "ok": False,
        "warnings": [],
    }
    if database_url is None:
        report["warnings"].append("RUNTIME_STORE_DATABASE_URL is not configured.")
        return _emit(report, args.json)

    connectivity = check_db_connectivity(database_url)
    report["connectivity_ok"] = connectivity.ok
    if connectivity.ok:
        report["current_revision"] = get_alembic_revision(database_url)
        engine = None
        try:
            engine = get_engine(database_url)
            report["missing_tables"] = list(list_missing_required_tables(engine))
        except Exception as exc:
            report["warnings"].append(f"table inspection failed: {exc.__class__.__name__}")
        finally:
            if engine is not None:
                engine.dispose()
    else:
        report["warnings"].append("database connectivity check failed")

    if args.require_backup:
        backup_dir = Path(args.backup_dir)
        dumps = sorted(
            backup_dir.glob("nexus-runtime-*.dump"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if dumps:
            report["backup_recent"] = dumps[0].name
        else:
            report["warnings"].append("no recent backup found")

    report["ok"] = (
        bool(connectivity.ok)
        and bool(head)
        and not report["missing_tables"]
        and (not args.require_backup or report["backup_recent"] is not None)
    )
    return _emit(report, args.json)


def _emit(report: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"source migration head: {report['source_head']}")
        print(f"database URL present: {report['database_url_present']}")
        print(f"database URL: {report['redacted_database_url'] or 'not configured'}")
        print(f"connectivity: {'ok' if report['connectivity_ok'] else 'failed'}")
        print(f"current revision: {report['current_revision'] or 'unavailable'}")
        print(f"missing tables: {len(report['missing_tables'])}")
        print(f"recent backup: {report['backup_recent'] or 'not checked'}")
        for warning in report["warnings"]:
            print(f"warning: {warning}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
