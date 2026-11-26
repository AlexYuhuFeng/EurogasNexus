"""Fetch the firm's own bank's FX and interest rates over its API (TAR-2, ADR Decision 38).

    python scripts/ops/fetch_bank_rates.py --institution SOCGEN --status   # no network call
    python scripts/ops/fetch_bank_rates.py --institution SOCGEN            # dry run
    python scripts/ops/fetch_bank_rates.py --institution SOCGEN --commit --json

Only Société Générale (``SOCGEN``) has a connector in this build. It fetches only when the
organisation setting ``financial_institutions`` holds ``SOCGEN`` with access ``api`` and
``agreement_recorded`` true, the deployment names the endpoint configuration
(``EUROGAS_NEXUS_SOCGEN_API_CONFIG_FILE``) and the firm's own secret is configured
(``EUROGAS_NEXUS_SOCGEN_API_SECRET`` or ``..._SECRET_FILE``, or the credential store).
Otherwise it makes no network call, prints "not connected" with the reason and exits 3.

The rates are stored through the ``bank.fx_rates.v1`` and ``bank.interest_rates.v1``
contracts as ``BANK:SOCGEN`` rows, exactly as the bank's file export would be. Exit codes: 0
stored (or dry run done), 1 a feed failed or was refused, 2 no runtime DB, 3 not connected.
"""

from __future__ import annotations

import argparse
import json
import sys

from eurogas_nexus.application.bank_feeds import (
    CONNECTORS,
    feed_status,
    run_socgen_feed,
    socgen_institution,
)
from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url

NOT_CONNECTED_EXIT = 3


def main(argv: list[str] | None = None) -> int:
    """Run the fetch; returns a process exit code."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--institution", choices=CONNECTORS, required=True)
    parser.add_argument("--status", action="store_true",
                        help="print the connection state only (no network call)")
    parser.add_argument("--commit", action="store_true", help="store (default: dry run)")
    parser.add_argument("--skip-bad-rows", action="store_true",
                        help="store the accepted rows even when some are refused")
    parser.add_argument("--json", action="store_true", help="print a JSON report (scheduler)")
    args = parser.parse_args(argv)
    say = (lambda text: print(text, file=sys.stderr)) if args.json else print

    database_url = resolve_database_url()
    if not database_url:
        say("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    say(f"Runtime DB: {redact_database_url(database_url)}")
    with get_session_factory(database_url=database_url)() as session:
        if args.status:
            bank = socgen_institution(session)
            state = (feed_status(bank) if bank is not None else None) or {
                "connected": False, "state": "not connected",
                "code": "institution_not_configured" if bank is None else "access_not_api",
                "message": "SOCGEN is not configured for a live feed in financial_institutions",
            }
            print(json.dumps(state, indent=None if args.json else 2, sort_keys=True))
            return 0 if state.get("connected") else NOT_CONNECTED_EXIT
        report = run_socgen_feed(
            session,
            commit=args.commit,
            on_error="skip_rows" if args.skip_bad_rows else "reject_file",
        )
        if report["committed"]:
            session.commit()
    if not report["connected"]:
        # The scheduler records a CONFIGURATION refusal, not a failure to retry.
        report["configuration_code"] = f"not_connected:{report['code']}"
        say(f"{report['institution']}: not connected ({report['code']}): {report['message']}")
        if args.json:
            print(json.dumps(report, sort_keys=True))
        return NOT_CONNECTED_EXIT
    for name, detail in report["sources"].items():
        say(
            f"{name}: {detail['records']} rows, {detail['inserted']} new, "
            f"{detail['updated']} updated, {detail['unchanged']} unchanged, "
            f"{detail['refused']} refused; newest {detail['newest_value_date']}"
            + (" (stale)" if detail["stale"] else "")
        )
    for failure in report["failures"]:
        say(f"{failure['dataset']}: failed [{failure['code']}] {failure['message']}")
    if not report["committed"]:
        say("dry run: nothing stored (add --commit)")
    if args.json:
        print(json.dumps(report, sort_keys=True, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
