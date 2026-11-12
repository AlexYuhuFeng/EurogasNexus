"""Print the data-quality report for the runtime store (text, or --json).

    python scripts/ops/data_quality_report.py
    python scripts/ops/data_quality_report.py --json > quality.json

Exit code 1 when any dataset is critical, so a scheduler can alert on it.
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
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from eurogas_nexus.application.data_quality_report import as_text, build_report
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        print("RUNTIME_STORE_DATABASE_URL is not set.", file=sys.stderr)
        return 2
    with get_session_factory()() as session:
        report = build_report(session)
    print(json.dumps(report, indent=2, default=str) if args.json else as_text(report), end="")
    return 1 if report["summary"].get("critical") else 0


if __name__ == "__main__":
    raise SystemExit(main())
