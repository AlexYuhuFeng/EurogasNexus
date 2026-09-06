#!/usr/bin/env python
"""Deterministic UAT fixture pack for CR-13 (development/test only).

The fixture is clearly simulated and never activates in trial/release:
``EUROGAS_NEXUS_ENV`` must be development/test and
``EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1`` must be set. It seeds 60 days of
source-shaped simulated market observations so backtest/shadow workflows have
deterministic historical evidence, and never writes real licensed vendor data.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eurogas_nexus.db.models import (  # noqa: E402
    FxObservationRecord,
    MarketObservationRecord,
)
from eurogas_nexus.db.session import (  # noqa: E402
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.ingestion.simulated_market_prices import (  # noqa: E402
    SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS,
    generate_simulated_market_observations,
)

FIXTURE_DAYS = 60


def main() -> int:
    environment = os.getenv("EUROGAS_NEXUS_ENV", "development").strip().lower()
    if environment in {"trial", "release"}:
        print("UAT fixtures are blocked in trial/release environments.")
        return 2
    if os.getenv("EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED", "").strip() != "1":
        print("Set EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1 to acknowledge simulated UAT data.")
        return 2
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2

    print(f"Runtime DB: {redact_database_url(database_url)}")
    now = datetime.now(UTC).replace(microsecond=0)
    session_factory = get_session_factory(database_url=database_url)
    inserted = 0
    with session_factory() as session:
        for days_ago in range(FIXTURE_DAYS - 1, -1, -1):
            observed_at = (now - timedelta(days=days_ago)).replace(hour=4, minute=0, second=0)
            rows = generate_simulated_market_observations(
                observed_at_utc=observed_at,
                source_systems=SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS,
            )
            for row in rows:
                session.merge(MarketObservationRecord(**row))
                inserted += 1
            # SAP-style NBP day-ahead series required by the default
            # OCM_VS_DAY_AHEAD strategy component. Clearly synthetic test data.
            session.merge(
                FxObservationRecord(
                    observation_id=f"uat-fx-eurgbp-{observed_at:%Y%m%d}",
                    pair="EURGBP",
                    base_currency="EUR",
                    quote_currency="GBP",
                    rate=0.86,
                    rate_type="reference",
                    value_date=observed_at.strftime("%Y-%m-%d"),
                    observed_at_utc=observed_at,
                    source_system="ECB_UAT_Sim",
                    source_reference=f"uat-sim:ecb:{observed_at:%Y-%m-%d}",
                    source_record_id=None,
                    freshness="simulated_live",
                    research_only=True,
                    metadata_json={"simulated": True},
                )
            )
            session.merge(
                MarketObservationRecord(
                    observation_id=(f"uat-sap-sim-nbp-dayahead-{observed_at:%Y%m%dT%H%M%S}"),
                    market_venue="SAP_Sim",
                    product="NBP day-ahead",
                    price=33.2,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=observed_at,
                    period_end_utc=observed_at + timedelta(days=1),
                    observed_at_utc=observed_at,
                    source_system="SAP_Sim",
                    source_reference=f"uat-sim:sap:{observed_at:%Y-%m-%d}",
                    source_record_id=None,
                    freshness="simulated_live",
                    quality_score=0.6,
                    research_only=True,
                    metadata_json={
                        "hub": "NBP",
                        "tenor": "day-ahead",
                        "price_name": "SAP",
                        "simulated": True,
                    },
                )
            )
            inserted += 1
        session.commit()
    print(
        f"Seeded {inserted} simulated UAT market observations across "
        f"{FIXTURE_DAYS} days (source systems marked *_Sim)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
