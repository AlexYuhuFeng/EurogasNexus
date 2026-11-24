"""Check, then load, an ETRM or ERP file against its versioned import contract (DATA-1).

    python scripts/ops/import_contract_file.py --list
    python scripts/ops/import_contract_file.py --contract etrm.deals.v1 --system Endur \\
        --file deals.csv                      # dry run: what storing would do
    python scripts/ops/import_contract_file.py --contract etrm.deals.v1 --system Endur \\
        --file deals.csv --commit             # store (refused rows refuse the file)
    ... --commit --skip-bad-rows              # store the good rows, report the others

Each refused row is printed with its line, reason code and message. Re-running the same file
changes nothing. Nothing is booked, nominated, posted or paid: the ETRM and the ERP stay the
books of record. Contracts: ``docs/integration/ETRM_ERP_IMPORT_CONTRACTS.md``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eurogas_nexus.application.import_contracts import (
    REJECT_FILE,
    SKIP_ROWS,
    ImportContractError,
    contracts_catalogue,
    run_import,
)
from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url

MAX_BYTES = 64 * 1024 * 1024


def _print_report(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(
        f"{report['contract_id']} from {report['system']}: {report['rows']} rows, "
        f"{report['accepted']} accepted, {len(report['refused'])} refused"
    )
    for item in report["refused"]:
        print(f"  line {item['line']}: [{item['reason_code']}] {item['message']}")
    print(
        f"created {report['created']}, updated {report['updated']}, "
        f"unchanged {report['unchanged']}, removed {report['removed']}; "
        f"{'stored' if report['committed'] else 'nothing stored'}"
    )
    for note in report["notes"]:
        print(f"  note: {note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="list the contracts and exit")
    parser.add_argument("--contract", help="contract id, e.g. etrm.deals.v1")
    parser.add_argument("--system", help="sending system, e.g. Endur, Allegro, SAP")
    parser.add_argument("--file")
    parser.add_argument("--commit", action="store_true", help="store (default: dry run)")
    parser.add_argument("--skip-bad-rows", action="store_true",
                        help="store the accepted rows even when some are refused")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    if args.list:
        for contract in contracts_catalogue():
            required = [c["name"] for c in contract["columns"] if c["required"]]
            print(f"{contract['contract_id']}: {contract['title']} -> {contract['lands_in']}")
            print(f"  key {contract['key']}; required {', '.join(required)}")
        return 0
    if not (args.contract and args.system and args.file):
        parser.error("--contract, --system and --file are required (or --list)")
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        print(f"File missing or larger than {MAX_BYTES} bytes: {path}")
        return 2
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    text = path.read_text(encoding="utf-8")
    with get_session_factory(database_url=database_url)() as session:
        try:
            report = run_import(
                args.contract,
                text,
                system=args.system,
                file_name=path.name,
                session=session,
                on_error=SKIP_ROWS if args.skip_bad_rows else REJECT_FILE,
                commit=args.commit,
            )
        except ImportContractError as exc:
            print(f"Refused: [{exc.code}] {exc.message}")
            return 2
        if args.commit and report.committed:
            session.commit()
        else:
            session.rollback()
    _print_report(report.as_dict(), args.json)
    return 2 if report.file_refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
