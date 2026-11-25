"""Operate the tariff book (TAR-1): status, sync, import capacity notices.

Read-only by default. ``sync`` and ``import-notices`` write only with ``--commit``; without it
they report what they would do and roll back.

* ``status``: every publisher in the registry, how it is read, when it was last read, what is
  held, and whether an expected update was missed.
* ``sync``: version every register row now (the scheduler does this each cycle when the
  registers changed, and at least hourly) and refresh the rule-derived auction calendar. Run
  it once after deploying migration 0083: the first pass records every tariff held as version
  1 and publishes one ``tariff.changed`` event each (about 77 s for 12,670 ENTSOG rows on
  PostgreSQL 16).
* ``import-notices``: capacity notices a publisher published (LNG slot offers, secondary
  capacity windows, a moved auction date), from a CSV or JSON file with the columns of
  ``application/tariff_book.NOTICE_COLUMNS``. Each row needs the publisher's own https page.
  One refused row refuses the file.

Examples::

    python scripts/ops/tariff_book.py status
    python scripts/ops/tariff_book.py sync --commit
    python scripts/ops/tariff_book.py import-notices slots.csv --publisher gate-terminal --commit
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def _rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        rows = data.get("notices", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("a JSON notice file is a list of rows or {'notices': [...]}")
        return [dict(row) for row in rows]
    return list(csv.DictReader(io.StringIO(text)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sync = sub.add_parser("sync")
    sync.add_argument("--commit", action="store_true")
    notices = sub.add_parser("import-notices")
    notices.add_argument("path", type=Path)
    notices.add_argument("--publisher", required=True)
    notices.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)

    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2
    from eurogas_nexus.application import tariff_book

    with get_session_factory()() as session:
        if args.command == "status":
            report = {"publishers": tariff_book.publisher_status(session)}
        elif args.command == "sync":
            report = tariff_book.capture_tariffs(session)
            report["committed"] = args.commit
        else:
            try:
                report = tariff_book.import_capacity_notices(
                    session, _rows(args.path), publisher_id=args.publisher
                )
            except tariff_book.NoticeImportError as exc:
                print(json.dumps({"status": "refused", "code": exc.code, "message": exc.message}))
                return 1
            report["committed"] = args.commit and report["stored"]
        if getattr(args, "commit", False) and report.get("committed"):
            session.commit()
        else:
            session.rollback()
    print(json.dumps(report, default=str, indent=2))
    return 0 if report.get("stored", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
