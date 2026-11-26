#!/usr/bin/env python
"""Report or apply the optional TimescaleDB Community Edition conversion (ADR Decision 39).

    python scripts/ops/timescale.py status                 # read-only, JSON
    python scripts/ops/timescale.py plan                   # the DDL apply would run, read-only
    EUROGAS_NEXUS_TIMESCALE=auto python scripts/ops/timescale.py apply
    python scripts/ops/timescale.py apply --mode require   # fail if the server cannot

Migration ``0090_timescale_optional`` runs the same idempotent ``apply`` once; this script is
for a server that gets the extension after that revision has run. ``apply`` changes three
primary keys and converts three tables in one transaction; on a large table it holds locks
while the rows are copied into chunks, so run it in a maintenance window, after a backup
(docs/deployment/TIMESCALEDB.md). The database URL is never printed.

Exit codes: 0 done, 1 refused or failed, 2 cannot run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("status", "plan", "apply"))
    parser.add_argument("--mode", choices=("off", "auto", "require"), default=None,
                        help="overrides EUROGAS_NEXUS_TIMESCALE for this run")
    parser.add_argument("--url", default=None, help="database URL (default: the runtime store)")
    args = parser.parse_args(argv)

    from eurogas_nexus.db import timescale
    from eurogas_nexus.db.session import default_driver_url, get_engine, resolve_database_url

    url = args.url or resolve_database_url()
    if not url:
        print("no database URL: set RUNTIME_STORE_DATABASE_URL", file=sys.stderr)
        return 2
    try:
        mode = args.mode or timescale.mode_from_env()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    engine = get_engine(default_driver_url(url))
    try:
        if args.command == "status":
            with engine.connect() as connection:
                print(json.dumps(timescale.status(connection, mode=mode), indent=2))
            return 0
        if args.command == "plan":
            with engine.connect() as connection:
                facts = timescale.server_facts(connection)
                decision = timescale.decide(mode if mode != "off" else "auto", facts)
                plan: dict[str, object] = {"would_convert": decision.enabled,
                                           "reason": decision.reason, "tables": {}}
                for item in timescale.HYPERTABLE_PLANS:
                    if facts.dialect != "postgresql":
                        break
                    current = timescale.table_facts(connection, item)
                    blockers = timescale.catalogue_blockers(current, item)
                    plan["tables"][item.table] = (  # type: ignore[index]
                        {"blockers": blockers} if blockers
                        else {"statements": timescale.conversion_statements(item, current)}
                    )
                print(json.dumps(plan, indent=2))
            return 0
        try:
            with engine.begin() as connection:
                report = timescale.apply(connection, mode=mode)
        except timescale.TimescaleRequiredError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(report.as_dict(), indent=2))
        return 1 if report.failed else 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
