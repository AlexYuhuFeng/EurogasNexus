"""Run one bounded shadow-research scheduler scan.

This is a synchronous single-process scheduler appropriate for current scale.
Run it on cadence from the host/CI scheduler; PostgreSQL remains source of
truth. No execution, order or nomination path is invoked.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from eurogas_nexus.application.shadow_runtime import (
    recover_stale_evaluations,
    run_due_shadow_evaluations,
)
from eurogas_nexus.db.session import get_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--stale-after-seconds", type=int, default=300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    now = datetime.now(UTC)
    with get_session_factory()() as session:
        recovered = recover_stale_evaluations(
            session,
            now_utc=now,
            stale_after_seconds=args.stale_after_seconds,
        )
        summary = run_due_shadow_evaluations(
            session, now_utc=now, limit=args.limit
        )
        summary["recovered_stale_evaluations"] = recovered
        session.commit()

    if args.json:
        print(json.dumps(summary, default=str))
    else:
        print(json.dumps(summary, default=str, indent=2))


if __name__ == "__main__":
    main()
