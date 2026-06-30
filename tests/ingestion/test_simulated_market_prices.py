"""Simulated market price source tests."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IngestionRunRecord, MarketObservationRecord
from eurogas_nexus.ingestion.simulated_market_prices import (
    DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS,
    SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS,
    due_simulated_market_price_sources,
    generate_simulated_market_observations,
    run_simulated_market_price_loop,
    upsert_simulated_market_observations,
)


def test_simulated_market_prices_generate_exchange_and_daily_assessment_rows() -> None:
    observed_at = datetime(2026, 7, 1, 10, 15, tzinfo=UTC)

    rows = generate_simulated_market_observations(observed_at_utc=observed_at)

    source_systems = {row["source_system"] for row in rows}
    assert {"EEX_Sim", "ICE_OCM_Sim", "ICIS_Sim"}.issubset(source_systems)
    assert any(
        row["source_system"] == "EEX_Sim"
        and row["metadata_json"]["tenor"] == "month-ahead"
        and row["metadata_json"]["simulated"] is True
        for row in rows
    )
    assert any(
        row["source_system"] == "ICE_OCM_Sim"
        and row["metadata_json"]["price_timing"] == "instant"
        and row["freshness"] == "simulated_live"
        for row in rows
    )
    assert any(
        row["source_system"] == "ICIS_Sim"
        and row["metadata_json"]["assessment_format"] == "ICIS Heren daily assessment"
        and row["metadata_json"]["tenor"] == "day-ahead"
        for row in rows
    )


def test_simulated_market_price_upsert_uses_runtime_observation_and_ingestion_tables(
    tmp_path,
) -> None:
    db_path = tmp_path / "simulated-market.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    observed_at = datetime(2026, 7, 1, 10, 15, tzinfo=UTC)

    with Session(engine) as session:
        summary = upsert_simulated_market_observations(session, observed_at_utc=observed_at)
        session.commit()

    with Session(engine) as session:
        rows = session.query(MarketObservationRecord).all()
        runs = session.query(IngestionRunRecord).all()

    assert summary["rows_upserted"] == len(rows)
    assert summary["rows_upserted"] >= 20
    assert {row.source_system for row in rows}.issuperset(
        {"EEX_Sim", "ICE_OCM_Sim", "ICIS_Sim"}
    )
    assert {run.source_name for run in runs} == {"EEX_Sim", "ICE_OCM_Sim", "ICIS_Sim"}
    assert all(run.status == "succeeded" for run in runs)
    assert all("records=" in (run.notes or "") for run in runs)


def test_simulated_market_prices_can_upsert_only_due_sources(tmp_path) -> None:
    db_path = tmp_path / "simulated-market-due-source.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    observed_at = datetime(2026, 7, 1, 10, 15, tzinfo=UTC)

    with Session(engine) as session:
        summary = upsert_simulated_market_observations(
            session,
            observed_at_utc=observed_at,
            source_systems=("ICE_OCM_Sim",),
        )
        session.commit()

    with Session(engine) as session:
        rows = session.query(MarketObservationRecord).all()
        runs = session.query(IngestionRunRecord).all()

    assert summary["source_counts"] == {"ICE_OCM_Sim": 2}
    assert {row.source_system for row in rows} == {"ICE_OCM_Sim"}
    assert {run.source_name for run in runs} == {"ICE_OCM_Sim"}


def test_simulated_market_price_cadence_marks_due_sources_independently() -> None:
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    intervals = {
        "EEX_Sim": 60,
        "ICE_OCM_Sim": 15,
        "ICIS_Sim": 86_400,
    }

    due_sources = due_simulated_market_price_sources(
        {
            "EEX_Sim": datetime(2026, 7, 1, 9, 59, tzinfo=UTC),
            "ICE_OCM_Sim": datetime(2026, 7, 1, 9, 59, 55, tzinfo=UTC),
            "ICIS_Sim": datetime(2026, 6, 30, 9, 59, tzinfo=UTC),
        },
        observed_at_utc=now,
        intervals_seconds=intervals,
    )

    assert due_sources == ("EEX_Sim", "ICIS_Sim")
    assert DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS["ICE_OCM_Sim"] < (
        DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS["EEX_Sim"]
    )
    assert set(SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS) == {"EEX_Sim", "ICE_OCM_Sim", "ICIS_Sim"}


def test_simulated_market_price_loop_runs_continuous_ticks(tmp_path) -> None:
    db_path = tmp_path / "simulated-market-loop.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)

    def session_factory() -> Session:
        return Session(engine)

    clock_values = iter(
        [
            datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
            datetime(2026, 7, 1, 10, 0, 15, tzinfo=UTC),
            datetime(2026, 7, 1, 10, 0, 30, tzinfo=UTC),
            datetime(2026, 7, 1, 10, 0, 45, tzinfo=UTC),
            datetime(2026, 7, 1, 10, 1, tzinfo=UTC),
        ]
    )
    sleeps: list[float] = []

    summaries = run_simulated_market_price_loop(
        session_factory,
        max_iterations=5,
        intervals_seconds={"EEX_Sim": 60, "ICE_OCM_Sim": 15, "ICIS_Sim": 86_400},
        now_fn=lambda: next(clock_values),
        sleep_fn=sleeps.append,
        emit=lambda _message: None,
    )

    assert [summary["source_counts"] for summary in summaries] == [
        {"EEX_Sim": 18, "ICE_OCM_Sim": 2, "ICIS_Sim": 6},
        {"ICE_OCM_Sim": 2},
        {"ICE_OCM_Sim": 2},
        {"ICE_OCM_Sim": 2},
        {"EEX_Sim": 18, "ICE_OCM_Sim": 2},
    ]
    assert sleeps == [15.0, 15.0, 15.0, 15.0]
    with Session(engine) as session:
        runs = session.query(IngestionRunRecord).all()
    assert len(runs) == 8


def test_simulated_market_price_cli_exposes_continuous_worker_controls() -> None:
    script = Path("scripts/ops/ingest_simulated_market_prices.py").read_text()

    assert "--loop" in script
    assert "--eex-interval-seconds" in script
    assert "--ice-ocm-interval-seconds" in script
    assert "--icis-interval-seconds" in script
    assert "run_simulated_market_price_loop" in script
