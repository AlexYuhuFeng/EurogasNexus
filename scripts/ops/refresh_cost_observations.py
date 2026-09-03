#!/usr/bin/env python
"""Refresh machine-readable cost observations.

Usage:
    python scripts/ops/refresh_cost_observations.py --url https://.../tariffs.json

For scheduled execution, call this script from systemd, Task Scheduler, or a
Kubernetes CronJob.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("EUROGAS_NEXUS_COST_SOURCE_URL"))
    parser.add_argument(
        "--source-system",
        default=os.environ.get("EUROGAS_NEXUS_COST_SOURCE_SYSTEM", "TSO_TARIFFS"),
    )
    args = parser.parse_args(argv)
    if not args.url:
        print("A --url or EUROGAS_NEXUS_COST_SOURCE_URL is required.")
        return 2

    from eurogas_nexus.application.cost_source_refresh import refresh_cost_source
    from eurogas_nexus.db.session import get_session_factory

    try:
        count = refresh_cost_source(
            get_session_factory(),
            url=args.url,
            source_system=args.source_system,
        )
    except Exception as exc:
        print(f"cost-source refresh failed: {exc.__class__.__name__}: {exc}")
        return 1
    print(f"refreshed {count} cost observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
