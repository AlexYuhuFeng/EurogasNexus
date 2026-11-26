"""Seed simulated TTF option settlements (ICE_ENDEX_Sim) for the demo.

    python scripts/ops/seed_simulated_option_settlements.py --days 180

Every row is marked simulated and ranks below any licensed exchange or vendor option
settlement. Refused in trial and release environments, like the other simulated sources.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from eurogas_nexus.core.config import simulated_sources_allowed
from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.ingestion.simulated_option_settlements import (
    SIMULATED_OPTION_SOURCE,
    generate_simulated_option_settlements,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--days", type=int, default=120, help="trade days back from today (1..730)")
    args = parser.parse_args(argv)
    if not 1 <= args.days <= 730:
        parser.error("--days must be 1..730")
    if not simulated_sources_allowed():
        print("Simulated sources are not allowed in trial or release environments.")
        return 2
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.models import IngestionRunRecord, OptionSettlementRecord

    now = datetime.now(UTC)
    last = now.date()
    result = generate_simulated_option_settlements(last - timedelta(days=args.days), last)
    with get_session_factory(database_url=database_url)() as session:
        for row in result.rows:
            session.merge(OptionSettlementRecord(**row))
        session.merge(
            IngestionRunRecord(
                run_id=f"sim-ice-endex-sim-options-{now:%Y%m%dT%H%M%S}",
                source_name=SIMULATED_OPTION_SOURCE,
                status="succeeded",
                started_at_utc=now,
                finished_at_utc=now,
                notes=(
                    f"records={len(result.rows)}; source={SIMULATED_OPTION_SOURCE}; "
                    "simulated_option_settlements; normalized=option_settlements"
                ),
            )
        )
        session.commit()
    print(
        f"Stored {len(result.rows)} simulated option settlements "
        f"({result.first_day}..{result.last_day}, contracts {result.contracts})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
