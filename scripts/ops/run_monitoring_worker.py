"""Run the PostgreSQL-backed monitoring and DeepSeek enrichment loop."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

from eurogas_nexus.api.routes.public.reports import balance_reader as report_balance_reader
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.application.notifications import dispatch, mirror_monitoring_alerts
from eurogas_nexus.application.reports.schedule import run_due as run_due_reports
from eurogas_nexus.application.service_identity import (
    configured_service_principal_name,
    resolve_service_authority,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def main() -> int:
    """    Run the monitoring worker loop."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=10.0,
        help="Scan cadence in seconds (minimum 2.0 for near-real-time operation).",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--max-llm-enrichments", type=int, default=3)
    args = parser.parse_args()

    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2

    interval_seconds = max(2.0, args.interval_seconds)
    session_factory = get_session_factory()
    # Owner decision D7: enrichment runs under a named service identity, resolved once at start-up
    # and reported in every status line. Without one the worker still scans and persists alerts - it
    # is the *provider call* that is refused - and the operator sees which configuration is missing
    # instead of a pipeline that quietly stopped analysing.
    with session_factory() as session:
        authority = resolve_service_authority(session)
    if not authority.granted and not args.no_llm:
        print(
            json.dumps(
                {
                    "status": "degraded",
                    "enrichment": "refused",
                    "reason": authority.refusal,
                    "detail": authority.detail,
                    "service_principal": configured_service_principal_name(),
                }
            ),
            flush=True,
        )
    while True:
        try:
            with session_factory() as session:
                result = scan_monitoring_conditions(
                    session,
                    enrich_with_llm=not args.no_llm,
                    max_llm_enrichments=max(0, args.max_llm_enrichments),
                    service_authority=authority,
                )
                # New alerts go to the outbox and every due notification is dispatched in
                # the same pass, so a desk hears about a stale source within one cycle.
                now = datetime.now(UTC)
                queued = mirror_monitoring_alerts(session, now=now)
                # Gas-day nominations still open within three hours of their cut-off (or past
                # it), once each (Today's checklist); a failure here never stops the scan.
                try:
                    from eurogas_nexus.application.gas_day_checklist import (
                        queue_deadline_notifications,
                    )

                    queued += queue_deadline_notifications(session, now=now)
                except Exception as exc:  # noqa: BLE001
                    print(json.dumps({"status": "gas_day_deadlines_failed",
                                      "error_type": exc.__class__.__name__}), flush=True)
                # SCHED-1: reconciliation breaks near a cut-off reach scheduling (dedupe,
                # cooldown, withdrawal when they clear); a failure never stops the scan.
                try:
                    from eurogas_nexus.application.gas_day_reconciliation import (
                        queue_break_alerts,
                    )

                    queued += queue_break_alerts(session, now=now)["notified"]
                except Exception as exc:  # noqa: BLE001
                    print(json.dumps({"status": "gas_day_breaks_failed",
                                      "error_type": exc.__class__.__name__}), flush=True)
                # Scheduled reports due this pass run as the service principal (never an
                # administrator); their e-mail rows are dispatched below with the rest.
                reports = run_due_reports(session, now=now, caller=authority.principal,
                                          balance_reader=report_balance_reader)
                sent = dispatch(session, now=now)
                session.commit()
            print(
                json.dumps({"status": "ok", **result, "notified": {"queued": queued, **sent},
                            "reports": reports}),
                flush=True,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error_type": exc.__class__.__name__,
                    }
                ),
                flush=True,
            )
        if args.once:
            return 0
        time.sleep(interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
