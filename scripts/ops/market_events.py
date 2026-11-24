"""Operate the market event outbox (M4/M5): status, staleness, timeline, capture, drain,
replay, listen.

Read-only by default. ``capture``, ``drain`` and ``replay`` write only with ``--commit``;
without it they report what they would do and roll back. ``listen`` (PostgreSQL only) waits on the
``market_events`` notification channel and drains when woken or every ``--interval`` seconds,
so a lost notice costs latency, never an event.

Examples::

    python scripts/ops/market_events.py status
    python scripts/ops/market_events.py staleness
    python scripts/ops/market_events.py timeline mev-...-r1 --consumer opportunities
    python scripts/ops/market_events.py capture --since 2026-11-01T00:00:00Z --commit
    python scripts/ops/market_events.py drain --commit
    python scripts/ops/market_events.py replay opportunities --since 2026-11-24T00:00:00Z --commit
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def _instant(text: str | None) -> datetime | None:
    if not text:
        return None
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _listen(session_factory, interval: float, iterations: int | None) -> int:
    """Drain when a notice arrives (checked every second) or every ``interval`` seconds."""

    from eurogas_nexus.application import market_events

    probe = session_factory()
    bind = probe.get_bind()
    probe.close()
    if bind.dialect.name != "postgresql":
        print(json.dumps({"status": "blocked", "reason": "listen_requires_postgresql"}))
        return 2
    raw = bind.raw_connection()
    try:
        raw.driver_connection.autocommit = True
        cursor = raw.cursor()
        cursor.execute(f"LISTEN {market_events.NOTIFY_CHANNEL}")
        notices = getattr(raw.driver_connection, "notifications", None)
        done = 0
        last = 0.0
        while iterations is None or done < iterations:
            time.sleep(1.0)
            cursor.execute("SELECT 1")  # pg8000 collects notices on any round trip
            woken = bool(notices)
            if notices:
                notices.clear()
            if not woken and time.monotonic() - last < interval:
                continue
            last = time.monotonic()
            batches = market_events.drain(session_factory)
            print(json.dumps({"status": "ok", "woken": woken, "batches": batches}, default=str))
            done += 1
    finally:
        raw.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("staleness")
    timeline = sub.add_parser("timeline")
    timeline.add_argument("event_id")
    timeline.add_argument("--consumer", default="opportunities")
    capture = sub.add_parser("capture")
    capture.add_argument("--since")
    capture.add_argument(
        "--kind",
        action="append",
        choices=("prices", "fx", "outages", "contracts", "assumptions"),
    )
    capture.add_argument("--commit", action="store_true")
    drain = sub.add_parser("drain")
    drain.add_argument("--commit", action="store_true")
    drain.add_argument("--limit", type=int, default=100)
    replay = sub.add_parser("replay")
    replay.add_argument("consumer")
    replay.add_argument("--from-seq", type=int)
    replay.add_argument("--since")
    replay.add_argument("--event-id", action="append")
    replay.add_argument("--commit", action="store_true")
    listen = sub.add_parser("listen")
    listen.add_argument("--interval", type=float, default=30.0)
    listen.add_argument("--iterations", type=int)
    args = parser.parse_args(argv)

    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2
    from eurogas_nexus.application import market_events

    session_factory = get_session_factory()
    if args.command == "listen":
        return _listen(session_factory, max(1.0, args.interval), args.iterations)
    with session_factory() as session:
        if args.command == "status":
            report = market_events.status(session)
        elif args.command == "staleness":
            report = {"subjects": market_events.staleness(session)}
        elif args.command == "timeline":
            report = market_events.timeline(session, args.event_id, args.consumer) or {
                "status": "not_found"
            }
        elif args.command == "capture":
            from eurogas_nexus.application import market_event_capture

            report = market_event_capture.capture(
                session,
                since_utc=_instant(args.since),
                kinds=tuple(args.kind or market_event_capture.KINDS),
            )
            report["committed"] = args.commit
        elif args.command == "drain":
            report = {
                "batches": [
                    market_events.process(session, item.name, limit=args.limit)
                    for item in market_events.consumers()
                ],
                "committed": args.commit,
            }
        else:
            report = market_events.replay(
                session,
                args.consumer,
                from_seq=args.from_seq,
                since_utc=_instant(args.since),
                event_ids=args.event_id,
            )
            report["committed"] = args.commit
        if getattr(args, "commit", False):
            session.commit()
        else:
            session.rollback()
    print(json.dumps(report, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
