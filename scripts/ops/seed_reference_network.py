"""Load the shipped NWE reference network bundle into the runtime store (no network needed).

Runs after ``alembic upgrade head`` on a fresh installation so the map shows the north-west
Europe network before ENTSOG is first read, or ever, on an installation without outbound
network. Idempotent: a repeat run converges on the same rows. A store that already holds a
live ENTSOG reference read is left unchanged (``skipped_live_reference_present``). The bundle
is real ENTSOG reference metadata, not simulated data, so it is allowed in every environment.

    RUNTIME_STORE_DATABASE_URL=... python scripts/ops/seed_reference_network.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.reference_data.network_bundle import seed_reference_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args(argv)
    if not resolve_database_url():
        print("RUNTIME_STORE_DATABASE_URL is required", file=sys.stderr)
        return 2
    with get_session_factory()() as session:
        summary = seed_reference_bundle(session)
        session.commit()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif summary["status"] == "seeded":
        print(
            f"reference network bundle {summary['bundle_version']} seeded: "
            f"{summary['nodes']['upserted']} points, {summary['edges']['upserted']} schematic "
            f"links, {summary['unlocated_points']} points without a published position"
        )
    else:
        print(f"reference network bundle {summary['bundle_version']}: {summary['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
