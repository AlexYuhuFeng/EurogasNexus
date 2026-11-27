"""Import exchange trade exports into a book, or check a format against a file.

    python scripts/ops/import_deal_files.py --book desk-a --file ice-2026-11-26.csv
    python scripts/ops/import_deal_files.py --book desk-a --file eex.csv --format eex_trades
    python scripts/ops/import_deal_files.py --folder /srv/eurogas-nexus/deal-drop [--watch]

``--folder`` imports every file in ``<folder>/<book id>/`` (the watched folder the monitoring
worker also reads when EUROGAS_NEXUS_DEAL_DROP_DIR is set) and moves each to ``imported/`` or
``refused/`` with a result note. Runs as the configured service principal. Nothing is
ordered, nominated or booked: the deals are the desk's record before the ETRM close.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--book")
    parser.add_argument("--file")
    parser.add_argument("--format", default=None, help="format name; omitted: by headers")
    parser.add_argument("--folder")
    parser.add_argument("--watch", action="store_true", help="keep reading the folder")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2
    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.application.deal_capture import (
        DealCaptureError,
        import_drop_folder,
        import_file,
    )
    from eurogas_nexus.application.service_identity import resolve_service_authority

    factory = get_session_factory()
    with factory() as session:
        authority = resolve_service_authority(session)
        caller = firm_caller(authority.principal, session=session)
    if args.folder:
        while True:
            print(json.dumps({"status": "ok",
                              "files": import_drop_folder(factory, caller, args.folder)}),
                  flush=True)
            if not args.watch:
                return 0
            time.sleep(max(5.0, args.interval_seconds))
    if not (args.book and args.file):
        parser.error("--book and --file, or --folder")
    path = Path(args.file)
    try:
        with factory() as session:
            result = import_file(session, caller, path.read_bytes(), file_name=path.name,
                                 book_id=args.book, format_name=args.format, origin="upload")
            session.commit()
    except DealCaptureError as exc:
        print(json.dumps({"status": "refused", **exc.detail()}, default=str))
        return 2
    print(json.dumps({"status": "ok", **result.as_dict()}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
