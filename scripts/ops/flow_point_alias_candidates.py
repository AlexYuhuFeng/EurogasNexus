"""List ENTSOG point series that carried the same daily values: alias candidates.

    python scripts/ops/flow_point_alias_candidates.py --days 14
    python scripts/ops/flow_point_alias_candidates.py --days 30 --tolerance 0.0005 --json

A diagnostic only. It reads stored flow rows of closed gas days and prints pairs of
(point, operator, direction) series whose values match on every one of the newest N days.
Nothing is changed: a pair becomes an alias only when a person adds it, with its evidence,
to ``SAME_PHYSICAL_POINT`` in ``application/pipeline_supply.py``. The same point under two
operators is usually the two sides of an interconnection (already handled by the operator
rule); two different points are the case to check.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=14, help="newest closed gas days compared")
    parser.add_argument(
        "--tolerance", type=float, default=0.0,
        help="largest relative difference on any day (0: identical)",
    )
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)
    if not 2 <= args.days <= 120:
        parser.error("--days must be 2..120")
    if not 0.0 <= args.tolerance < 0.05:
        parser.error("--tolerance must be in [0, 0.05)")

    from eurogas_nexus.application.pipeline_supply import load_alias_candidates
    from eurogas_nexus.db.session import get_session_factory

    with get_session_factory()() as session:
        found = load_alias_candidates(session, days=args.days, tolerance=args.tolerance)
    rows = [candidate.as_dict() for candidate in found]
    if args.json:
        print(json.dumps({"days": args.days, "tolerance": args.tolerance, "candidates": rows}))
        return 0
    print(f"{len(rows)} candidate pairs over {args.days} closed gas days "
          f"(tolerance {args.tolerance:g})")
    for row in rows:
        first, second = row["first"], row["second"]
        kind = "same point, two operators" if first["point_id"] == second["point_id"] else (
            "two points"
        )
        print(
            f"{first['point_id']} {first['operator']} = {second['point_id']} "
            f"{second['operator']} ({first['direction']}, mean {row['mean_gwh_d']:.1f} GWh/d, "
            f"max diff {row['max_relative_difference']:.2e}, {kind}"
            f"{', listed' if row['already_listed'] else ''})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
