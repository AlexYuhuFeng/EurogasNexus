"""PostgreSQL-only source-entitlement checks for normalized market reads."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord
from eurogas_nexus.db.repositories.market_intelligence import list_normalized_market_view
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    principal_allows_source_family,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL"),
    reason="RUNTIME_STORE_DATABASE_URL not configured; use the PostgreSQL test DB",
)


def _create_tables(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE market_observations (
                observation_id VARCHAR(64) PRIMARY KEY,
                market_venue VARCHAR(32) NOT NULL,
                product VARCHAR(32) NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                unit VARCHAR(16) NOT NULL,
                currency VARCHAR(8) NOT NULL,
                period_start_utc TIMESTAMPTZ NOT NULL,
                period_end_utc TIMESTAMPTZ NOT NULL,
                observed_at_utc TIMESTAMPTZ NOT NULL,
                source_system VARCHAR(64) NOT NULL,
                source_reference VARCHAR(128) NOT NULL,
                source_record_id VARCHAR(128),
                freshness VARCHAR(16) NOT NULL,
                quality_score DOUBLE PRECISION NOT NULL,
                research_only BOOLEAN NOT NULL,
                metadata_json JSONB
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE fx_observations (
                observation_id VARCHAR(64) PRIMARY KEY,
                pair VARCHAR(16) NOT NULL,
                base_currency VARCHAR(8) NOT NULL,
                quote_currency VARCHAR(8) NOT NULL,
                rate DOUBLE PRECISION NOT NULL,
                rate_type VARCHAR(32) NOT NULL,
                value_date VARCHAR(16) NOT NULL,
                observed_at_utc TIMESTAMPTZ NOT NULL,
                source_system VARCHAR(64) NOT NULL,
                source_reference VARCHAR(128) NOT NULL,
                source_record_id VARCHAR(128),
                freshness VARCHAR(16) NOT NULL,
                research_only BOOLEAN NOT NULL,
                metadata_json JSONB
            )
            """
        )
    )


def _principal(*scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="postgres-entitlement-test",
        name="postgres-entitlement-test",
        principal_type="USER",
        role="VIEWER",
        status="ACTIVE",
        data_scopes=scopes,
        roles=("VIEWER",),
        auth_method="identity_key",
    )


def _market_row(
    observation_id: str,
    source_system: str,
    observed_at_utc: datetime,
    *,
    currency: str = "EUR",
    unit: str = "EUR/MWh",
    product: str = "NBP day-ahead",
    price: float = 33.0,
) -> MarketObservationRecord:
    return MarketObservationRecord(
        observation_id=observation_id,
        market_venue=source_system,
        product=product,
        price=price,
        unit=unit,
        currency=currency,
        period_start_utc=observed_at_utc,
        period_end_utc=observed_at_utc + timedelta(days=1),
        observed_at_utc=observed_at_utc,
        source_system=source_system,
        source_reference=f"test:{source_system}",
        source_record_id=observation_id,
        freshness="fresh",
        quality_score=1.0,
        research_only=True,
        metadata_json={"hub": "NBP", "tenor": "day-ahead"},
    )


def _fx_row(
    observation_id: str,
    source_system: str,
    pair: str,
    base_currency: str,
    quote_currency: str,
    rate: float,
    observed_at_utc: datetime,
) -> FxObservationRecord:
    return FxObservationRecord(
        observation_id=observation_id,
        pair=pair,
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=rate,
        rate_type="reference",
        value_date=observed_at_utc.date().isoformat(),
        observed_at_utc=observed_at_utc,
        source_system=source_system,
        source_reference=f"test:{source_system}",
        source_record_id=observation_id,
        freshness="fresh",
        research_only=True,
    )


def test_normalized_market_view_filters_sources_fx_and_ecb_fallback_in_isolated_schema() -> None:
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    schema = f"ent_{uuid4().hex}"
    principal = _principal("EEX")
    def source_filter(source: str) -> bool:
        return principal_allows_source_family(principal, source)

    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            assert connection.scalar(text("SELECT current_schema()")) == schema
            _create_tables(connection)

            with Session(bind=connection) as session:
                session.add_all(
                    [
                        _market_row(
                            f"ice-new-{index}",
                            "ICE_OCM",
                            now - timedelta(minutes=index),
                        )
                        for index in range(8)
                    ]
                    + [
                        _market_row(
                            "eex-daily-old-usd",
                            "EEX",
                            now - timedelta(days=2),
                            currency="USD",
                            unit="USD/MWh",
                        ),
                        _market_row(
                            "eex-daily-old-eur",
                            "EEX",
                            now - timedelta(days=3),
                        ),
                        _market_row(
                            "entsog-public-old",
                            "ENTSOG",
                            now - timedelta(days=4),
                        ),
                        _market_row(
                            "ecb-market-fallback",
                            "ECB",
                            now - timedelta(days=5),
                            product="EUR/GBP",
                            price=0.85,
                            unit="rate",
                            currency="GBP",
                        ),
                    ]
                )
                session.add_all(
                    [
                        _fx_row(
                            "ice-usd-gbp",
                            "ICE_OCM",
                            "USDGBP",
                            "USD",
                            "GBP",
                            0.8,
                            now,
                        ),
                        _fx_row(
                            "ecb-eur-gbp",
                            "ECB",
                            "EURGBP",
                            "EUR",
                            "GBP",
                            0.85,
                            now,
                        ),
                    ]
                )
                session.flush()

                view = list_normalized_market_view(session, limit=4, source_filter=source_filter)
                rows_by_id = {row["observation_id"]: row for row in view["rows"]}

                assert "ice-new-0" not in rows_by_id
                assert "eex-daily-old-usd" in rows_by_id
                assert "entsog-public-old" in rows_by_id
                assert rows_by_id["eex-daily-old-usd"]["price_gbp_mwh"] is None
                assert any("USD->GBP" in warning for warning in view["warnings"])

                empty_view = list_normalized_market_view(
                    session,
                    limit=4,
                    source_filter=lambda _source: False,
                )
                assert empty_view == {"rows": [], "warnings": []}

                session.query(FxObservationRecord).delete()
                session.flush()
                fallback_view = list_normalized_market_view(
                    session,
                    limit=8,
                    source_filter=source_filter,
                )
                fallback_rows = {
                    row["observation_id"]: row for row in fallback_view["rows"]
                }
                assert fallback_rows["eex-daily-old-eur"]["price_gbp_mwh"] == pytest.approx(
                    33.0 * 0.85
                )
                assert fallback_rows["eex-daily-old-usd"]["price_gbp_mwh"] is None
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
