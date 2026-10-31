"""Check every registered TSO tariff publication page and raise what needs attention.

    python scripts/ops/check_tariff_publications.py           # fetch, compare, notify
    python scripts/ops/check_tariff_publications.py --no-fetch  # deadlines only

Run daily from the scheduler. For each publication with a URL the page is fetched and its
SHA-256 compared with the last check: a change is recorded (``changed_at_utc``) and a
"tariff" notification queued so the desk reviews the new prices. Every publication whose
final tariffs are due soon, overdue or in force without a final is also notified, once per
state. Pages are fetched politely (one request each, 30 s timeout, an identifying user
agent); the product never scrapes tariff values, which come from the TSO's own files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime

from eurogas_nexus.application.notifications import dispatch, queue_notification
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.domain.route_cost.tariff_calendar import publication_state

USER_AGENT = "EurogasNexus-TariffCheck/1.0 (+publication change detection)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args(argv)
    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2
    import httpx

    from eurogas_nexus.db.models import TariffPublicationRecord

    now = datetime.now(UTC)
    summary = {"checked": 0, "changed": 0, "fetch_failed": 0, "notified": 0}
    with get_session_factory()() as session:
        for record in session.query(TariffPublicationRecord).all():
            if record.url and not args.no_fetch:
                try:
                    response = httpx.get(
                        record.url,
                        timeout=30,
                        follow_redirects=True,
                        headers={"User-Agent": USER_AGENT},
                    )
                    response.raise_for_status()
                    digest = hashlib.sha256(response.content).hexdigest()
                    summary["checked"] += 1
                    if record.content_hash and digest != record.content_hash:
                        record.changed_at_utc = now
                        summary["changed"] += 1
                    record.content_hash = digest
                    record.last_checked_at_utc = now
                except httpx.HTTPError:
                    summary["fetch_failed"] += 1
            try:
                state = publication_state(
                    tso=record.tso,
                    gas_year=record.gas_year,
                    status=record.status,
                    today=now.date(),
                    changed_at=record.changed_at_utc,
                    reviewed_at=record.reviewed_at_utc,
                )
            except ValueError:
                continue
            if state.severity == "ok":
                continue
            key_moment = (
                record.changed_at_utc.isoformat() if state.state == "changed" else state.state
            )
            summary["notified"] += queue_notification(
                session,
                category="tariff",
                severity="high" if state.severity == "breach" else "medium",
                title=f"Tariffs: {state.message}",
                body=f"{state.message}\nPublication: {record.url or 'not registered'}",
                dedupe_key=f"tariff:{record.publication_id}:{key_moment}",
                now=now,
            )
        dispatch(session, now=now)
        session.commit()
    print(json.dumps({"status": "ok", **summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
