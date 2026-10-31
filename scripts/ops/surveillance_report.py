"""Market-abuse surveillance alerts for the compliance function (CSV or JSON).

    python scripts/ops/surveillance_report.py --days 7 --format csv --output alerts.csv

Lines up the firm's decision cases, recorded decisions and ETRM trades against REMIT
disclosure timing (``eurogas_nexus.application.surveillance``). Set
``EUROGAS_NEXUS_REMIT_OWN_PARTICIPANTS`` to the firm's REMIT participant names or ACER
codes so its own outages are recognised. Every run is audited; alerts are decision
support for a compliance officer, not findings.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eurogas_nexus.application.surveillance import (
    SurveillanceAlert,
    alerts_as_rows,
    own_participants,
    surveillance_alerts,
)
from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days", type=int, default=7, help="UMMs first published in the last N days"
    )
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    parser.add_argument("--output", default=None, help="File to write (stdout when omitted)")
    args = parser.parse_args(argv)
    if not 1 <= args.days <= 3650:
        print("--days must be between 1 and 3650")
        return 2
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    own = own_participants()
    if not own:
        print("Note: EUROGAS_NEXUS_REMIT_OWN_PARTICIPANTS is unset; own-asset rules are off.")
    until = datetime.now(UTC)
    since = until - timedelta(days=args.days)
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.repositories.audit import record_audit_event

    with get_session_factory(database_url=database_url)() as session:
        alerts = surveillance_alerts(session, since=since, until=until, own=own)
        record_audit_event(
            session,
            event_type="compliance.surveillance",
            principal="operator",
            action="surveillance.report",
            resource=f"remit_umm:{since.date()}..{until.date()}",
            outcome="generated",
            severity="info",
            detail=f"alerts={len(alerts)}",
            source_system="surveillance-script",
            now_utc=until,
        )
        session.commit()
    rows = alerts_as_rows(alerts)
    if args.format == "json":
        text = json.dumps(rows, indent=2)
    else:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(SurveillanceAlert.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(rows)
        text = buffer.getvalue()
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"{len(rows)} alerts written to {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
