"""Run the PostgreSQL-backed monitoring and DeepSeek enrichment loop."""

from __future__ import annotations

import argparse
import json
import time

from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--max-llm-enrichments", type=int, default=3)
    args = parser.parse_args()

    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2

    interval_seconds = max(5.0, args.interval_seconds)
    session_factory = get_session_factory()
    while True:
        try:
            with session_factory() as session:
                result = scan_monitoring_conditions(
                    session,
                    enrich_with_llm=not args.no_llm,
                    max_llm_enrichments=max(0, args.max_llm_enrichments),
                )
            print(json.dumps({"status": "ok", **result}), flush=True)
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
