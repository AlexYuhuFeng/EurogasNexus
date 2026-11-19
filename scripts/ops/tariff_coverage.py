"""Print which crossings the tariff register can price (the coverage table); read-only.

For every crossing of the market-area graph and each direction: whether the register holds the
exit, pipeline and entry tariffs of the stated product for the current gas year and the next,
their source and data class; then the corridors outside the graph (CEGH, CZ, PSV, PVB, Swiss
transit) and the supply entry points (LNG, Norwegian landings).
``application/tariff_coverage.py`` holds the rules.

    RUNTIME_STORE_DATABASE_URL=... python scripts/ops/tariff_coverage.py [--product ANNUAL]
        [--firmness FIRM] [--today YYYY-MM-DD] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime

from eurogas_nexus.application.tariff_coverage import coverage_report, render_markdown
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph


def register_rows(session) -> list[dict]:
    from eurogas_nexus.db.models import TsoTariffRecord

    return [
        {
            column: getattr(row, column)
            for column in (
                "tariff_id",
                "tso",
                "point_id",
                "direction",
                "gas_year",
                "tariff_value",
                "currency",
                "unit",
                "effective_from",
                "effective_to",
                "tariff_status",
                "source_table",
                "capacity_product",
                "firmness",
                "market_area",
            )
        }
        for row in session.query(TsoTariffRecord).all()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product", default="ANNUAL")
    parser.add_argument("--firmness", default="FIRM")
    parser.add_argument("--today", type=date.fromisoformat, default=datetime.now(UTC).date())
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    if not resolve_database_url():
        print("RUNTIME_STORE_DATABASE_URL is required", file=sys.stderr)
        return 2
    with get_session_factory()() as session:
        rows = register_rows(session)
    report = coverage_report(
        shipped_market_area_graph(),
        rows,
        today=args.today,
        product=args.product.upper(),
        firmness=args.firmness.upper(),
    )
    print(json.dumps(report, indent=2, default=str) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
