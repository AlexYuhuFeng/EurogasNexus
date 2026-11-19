"""Dispatch due notifications once (for cron where the monitoring worker does not run).

    python scripts/ops/dispatch_notifications.py

Mirrors open monitoring alerts into the outbox, then sends every due outbox row to the
matching channels (email, webhook, SMS) and prints the counts. Safe to repeat.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from eurogas_nexus.application.notifications import dispatch, mirror_monitoring_alerts
from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def main() -> int:
    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        queued = mirror_monitoring_alerts(session, now=now)
        try:
            from eurogas_nexus.application.gas_day_checklist import queue_deadline_notifications

            queued += queue_deadline_notifications(session, now=now)
        except Exception as exc:  # noqa: BLE001 - the alerts still go out
            print(json.dumps({"status": "gas_day_deadlines_failed",
                              "error_type": exc.__class__.__name__}))
        counts = dispatch(session, now=now)
        session.commit()
    print(json.dumps({"status": "ok", "queued": queued, **counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
