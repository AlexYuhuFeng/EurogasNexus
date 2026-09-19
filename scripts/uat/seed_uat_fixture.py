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
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eurogas_nexus.db.models import (  # noqa: E402
    CanonicalEntityRecord,
    FxObservationRecord,
    MarketObservationRecord,
    NominationWindowMasterRecord,
    SeriesDefinitionRecord,
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

        # CR-15 deterministic research semantics. These are schema/identity
        # fixtures only; no licensed vendor data is introduced.
        for code in ("NBP", "TTF"):
            session.merge(
                CanonicalEntityRecord(
                    canonical_entity_id=f"ent:market_hub:{code}",
                    entity_type="market_hub",
                    canonical_code=code,
                    display_name=f"{code} UAT hub",
                    description="Deterministic UAT canonical hub.",
                    metadata_json={"simulated": True, "fixture": "browser-uat"},
                    created_at_utc=now,
                )
            )

        series = (
            SeriesDefinitionRecord(
                series_id="market.price.NBP.DAY_AHEAD",
                name="NBP Day-Ahead UAT",
                metric_type="price",
                entity_type="market_hub",
                entity_id="ent:market_hub:NBP",
                product_id="DAY_AHEAD",
                direction=None,
                source_class="EEX_Sim",
                native_frequency="1h",
                native_unit="EUR/MWh",
                currency="EUR",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                created_at_utc=now,
            ),
            SeriesDefinitionRecord(
                series_id="market.price.TTF.DAY_AHEAD",
                name="TTF Day-Ahead UAT",
                metric_type="price",
                entity_type="market_hub",
                entity_id="ent:market_hub:TTF",
                product_id="DAY_AHEAD",
                direction=None,
                source_class="EEX_Sim",
                native_frequency="1h",
                native_unit="EUR/MWh",
                currency="EUR",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                created_at_utc=now,
            ),
            SeriesDefinitionRecord(
                series_id="market.fx.EUR.GBP",
                name="EUR/GBP UAT",
                metric_type="fx",
                entity_type="currency_pair",
                entity_id="EURGBP",
                product_id=None,
                direction=None,
                source_class="ECB_UAT_Sim",
                native_frequency="1d",
                native_unit="GBP/EUR",
                currency="GBP",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                created_at_utc=now,
            ),
        )
        for item in series:
            session.merge(item)

        # The orchestrator deliberately reads the current UTC day. Add several
        # distinct paired observations inside that day so the browser UAT can
        # produce findings and a complete StrategyIR/review-pack chain at any
        # wall-clock time without depending on an external feed.
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        available_microseconds = max(
            int((now - day_start).total_seconds() * 1_000_000),
            6,
        )
        for sample in range(5):
            observed = now - timedelta(
                microseconds=available_microseconds * (sample + 1) // 8
            )
            for hub, base_value in (("NBP", 33.0), ("TTF", 31.0)):
                session.merge(
                    MarketObservationRecord(
                        observation_id=f"uat-agent-{hub.lower()}-{sample}",
                        market_venue=hub,
                        product="DAY_AHEAD",
                        price=base_value + sample * 0.1,
                        unit="EUR/MWh",
                        currency="EUR",
                        period_start_utc=observed,
                        period_end_utc=observed + timedelta(hours=1),
                        observed_at_utc=observed,
                        source_system="EEX_Sim",
                        source_reference=f"uat-sim:agent:{hub}:{sample}",
                        source_record_id=None,
                        freshness="simulated_live",
                        quality_score=0.8,
                        research_only=True,
                        metadata_json={
                            "hub": hub,
                            "tenor": "day-ahead",
                            "simulated": True,
                            "fixture": "browser-uat",
                        },
                    )
                )
                inserted += 1

        # The desk's clock. `nomination_window_masters` is a deployment declaration, so without one
        # the browser UAT can only exercise the *absence* of a window: the nomination task reports
        # `NOMINATION_WINDOWS_MISSING` and the day board has no deadline to show. These two are
        # simulated declarations on the UTC clock the engine matches against, chosen inside the gas
        # day all year (its boundary is 04:00-05:00 UTC), so a deadline exists whatever the run's
        # wall-clock time. 06:00 UTC is the winter boundary's own hour - the moment a gas day starts
        # in the CAM calendar - and 12:00 UTC sits in the middle of the day.
        for window_id, name, opens_at, closes_at, maximum_change_mwh, maximum_change_pct in (
            (
                "uat-window-day-open",
                "UAT simulated window at the gas-day open",
                time(6, 0),
                time(6, 30),
                150.0,
                None,
            ),
            (
                "uat-window-midday",
                "UAT simulated midday renomination window",
                time(12, 0),
                time(12, 30),
                None,
                10.0,
            ),
        ):
            session.merge(
                NominationWindowMasterRecord(
                    window_id=window_id,
                    name=name,
                    country="DE",
                    opens_at=opens_at,
                    closes_at=closes_at,
                    maximum_change_mwh=maximum_change_mwh,
                    maximum_change_pct=maximum_change_pct,
                    valid_from_utc=datetime(2020, 1, 1, tzinfo=UTC),
                    valid_to_utc=None,
                    source_system="CAM_UAT_Sim",
                    source_reference=f"uat-sim:cam:{window_id}",
                    active=True,
                    created_at_utc=now,
                )
            )

        session.commit()
    print(
        f"Seeded {inserted} simulated UAT market observations across "
        f"{FIXTURE_DAYS} days (source systems marked *_Sim)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
