"""Import a subscriber's licensed FX fixing export (WM/Reuters or Bloomberg BFIX).

WMR (LSEG) and BFIX (Bloomberg) are licensed benchmarks. This tool never fetches
them: the operator exports the fixes from their own entitled terminal or data
service (Workspace/DataScope, Bloomberg BFIX/Data License) as CSV with
``date,pair,rate`` columns and imports the file here. Rows are upserted by
(fixing, pair, value date) and served only to principals holding the ``WMR`` or
``BFIX`` data-scope grant.

    python scripts/ops/import_fx_fixings.py --source WMR --file wmr_4pm.csv
    python scripts/ops/import_fx_fixings.py --fixing BFIX_1600_LDN --file bfix.csv --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from eurogas_nexus.db.session import (
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.domain.market.fx_fixings import (
    FX_FIXINGS,
    FxFixingError,
    parse_fixing_export,
    resolve_fixing,
)

MAX_EXPORT_BYTES = 8 * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    """Parse, validate and upsert one fixing export; returns a process exit code."""

    args = _parse_args(argv)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_EXPORT_BYTES:
        print(f"Export file missing or larger than {MAX_EXPORT_BYTES} bytes: {path}")
        return 2
    try:
        fixing = resolve_fixing(args.source, args.fixing)
        if not fixing.licensed:
            print("ECB reference rates are ingested by ingest_public_sources.py, not imported.")
            return 2
        rows = parse_fixing_export(
            path.read_text(encoding="utf-8"),
            fixing,
            source_reference=args.source_reference or f"operator-export:{path.name}",
        )
    except FxFixingError as exc:
        print(f"Refused: {exc}")
        return 2
    print(
        f"{fixing.label}: {len(rows)} fixes, pairs={sorted({row.pair for row in rows})}, "
        f"{rows[0].value_date}..{rows[-1].value_date}"
    )
    if args.dry_run:
        return 0
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.models import FxObservationRecord

    with get_session_factory(database_url=database_url)() as session:
        for row in rows:
            session.merge(FxObservationRecord(**row.as_record()))
        session.commit()
    print(f"Upserted {len(rows)} {fixing.source_system} fixes.")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True, help="CSV export with date,pair,rate")
    parser.add_argument("--source", choices=("WMR", "BFIX"), default=None)
    parser.add_argument("--fixing", choices=sorted(FX_FIXINGS), default=None)
    parser.add_argument("--source-reference", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.source and not args.fixing:
        parser.error("one of --source or --fixing is required")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
