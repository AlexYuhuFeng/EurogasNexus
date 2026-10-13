"""Repository normalization of CR-04 evidence role and quotation basis.

The target-aware selector only ever compares *declared* semantics. This pins
that the repository assigns an evidence role/basis only from explicit source
metadata, never from a source name, a product label, a period or a unit, and
that a market quote is a deliverable only when it carries a valid half-open
delivery window and an explicit side.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord, MarketQuoteRecord
from eurogas_nexus.db.repositories.backtest import load_backtest_evidence_pool
from eurogas_nexus.domain.backtest.contracts import BacktestPeriod

D1 = datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
D2 = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)


def _version() -> SimpleNamespace:
    return SimpleNamespace(
        strategy_version_id="v1",
        strategy_id="s1",
        version_number=1,
        content_hash="sha256:x",
        definition_json={"components": [], "resource_contexts": []},
    )


def _pool(session: Session):
    return load_backtest_evidence_pool(
        session,
        version=_version(),
        period=BacktestPeriod(start_utc=D1, end_utc=D2),
        max_lookback_seconds=86_400,
    )


def _observation(session: Session, observation_id: str, metadata: dict) -> None:
    session.add(
        MarketObservationRecord(
            observation_id=observation_id,
            market_venue="SAP",
            product="NBP day-ahead",
            price=25.0,
            unit="GBP/MWh",
            currency="GBP",
            period_start_utc=D1,
            period_end_utc=D2,
            observed_at_utc=D1 + timedelta(minutes=30),
            source_system="SAP_Sim",
            source_reference=f"ref:{observation_id}",
            freshness="simulated_live",
            quality_score=0.6,
            research_only=True,
            metadata_json=metadata,
        )
    )


def test_explicit_metadata_is_normalized_and_guessed_metadata_is_not() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _observation(
            session,
            "explicit",
            {
                "hub": "NBP",
                "tenor": "day-ahead",
                "evidence_role": "REFERENCE_LEVEL",
                "price_basis": "assessment",
            },
        )
        # No role/basis of any kind: the source name SAP and the daily assessment
        # timing must not become an inferred role or basis.
        _observation(
            session,
            "guessed",
            {"hub": "NBP", "tenor": "day-ahead", "price_timing": "daily_assessment"},
        )
        session.flush()

        by_id = {row.observation_id: row for row in _pool(session).observations}

    assert by_id["explicit"].evidence_role == "REFERENCE_LEVEL"
    assert by_id["explicit"].price_basis == "ASSESSMENT"
    assert by_id["guessed"].evidence_role is None
    assert by_id["guessed"].price_basis is None
    # The legacy price_type heuristic is untouched; it just never assigns a role.
    assert by_id["guessed"].price_type == "assessment"


def test_a_quote_is_deliverable_only_with_a_valid_window_and_explicit_side() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            MarketQuoteRecord(
                quote_id="q1",
                source_system="ICE_OCM_Sim",
                venue="ICE OCM",
                instrument_id="NBP-WD",
                hub="NBP",
                product="within-day",
                delivery_start_utc=D1,
                delivery_end_utc=D2,
                bid_price=30.0,
                ask_price=32.0,
                last_price=31.5,
                currency="GBP",
                unit="MWh",
                observed_at_utc=D1 + timedelta(minutes=30),
                received_at_utc=D1 + timedelta(minutes=30),
                source_reference="quote:q1",
                freshness="simulated_live",
                quality_score=0.6,
                simulated=True,
            )
        )
        session.flush()

        rows = {row.observation_id: row for row in _pool(session).observations}

    assert rows["q1:bid"].evidence_role == "DELIVERY_PRICE"
    assert rows["q1:bid"].price_basis == "BID"
    assert rows["q1:ask"].price_basis == "ASK"
    assert rows["q1:mid"].price_basis == "MID"
    # A LAST print is an explicit trade price, not a declared side: it stays
    # unknown so it can never stand in for a deliverable side by default.
    assert rows["q1:last"].evidence_role is None
    assert rows["q1:last"].price_basis is None


def test_a_quote_without_a_valid_window_is_not_deliverable() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            MarketQuoteRecord(
                quote_id="q2",
                source_system="ICE_OCM_Sim",
                venue="ICE OCM",
                instrument_id="NBP-WD",
                hub="NBP",
                product="within-day",
                delivery_start_utc=D1,
                delivery_end_utc=D1,
                bid_price=30.0,
                ask_price=32.0,
                last_price=None,
                currency="GBP",
                unit="MWh",
                observed_at_utc=D1 + timedelta(minutes=30),
                received_at_utc=D1 + timedelta(minutes=30),
                source_reference="quote:q2",
                freshness="simulated_live",
                quality_score=0.6,
                simulated=True,
            )
        )
        session.flush()

        rows = list(_pool(session).observations)

    assert rows
    assert all(row.evidence_role is None and row.price_basis is None for row in rows)
