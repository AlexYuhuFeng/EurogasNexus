"""Recover ingestion and shadow jobs left QUEUED/RUNNING by a process crash.

Dry-run by default. With ``--commit``, stale ingestion runs are marked FAILED
with INTERNAL:STALE_RUN and stale shadow evaluations are marked FAILED with
INTERNAL_ERROR / OPERATIONAL_FAILURE:STALE_EVALUATION.
"""

from __future__ import annotations

import argparse
import json
import sys

from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument(
        "--ingestion-stale-seconds", type=int, default=900,
    )
    parser.add_argument(
        "--shadow-stale-seconds", type=int, default=300,
    )
    args = parser.parse_args(argv)

    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2

    session_factory = get_session_factory()
    with session_factory() as session:
        from eurogas_nexus.application.dataops_runtime import scan_scheduler

        scan = scan_scheduler(
            session,
            stale_after_seconds=max(30, args.ingestion_stale_seconds),
        )
        from eurogas_nexus.application.shadow_runtime import recover_stale_evaluations

        shadow_recovered = recover_stale_evaluations(
            session,
            stale_after_seconds=max(30, args.shadow_stale_seconds),
        )
        summary = {
            "status": "ok",
            "committed": False,
            "ingestion": {
                "recovered_stale_runs": scan["recovered_stale_runs"],
                "claimed_runs": len(scan["claimed_runs"]),
            },
            "shadow": {"recovered_stale_evaluations": shadow_recovered},
        }
        if args.commit:
            session.commit()
            summary["committed"] = True
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
