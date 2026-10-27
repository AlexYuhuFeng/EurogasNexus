"""Regression coverage for the DST-crossing UAT fixture seed."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import Base, MarketObservationRecord
from eurogas_nexus.db.session import get_session_factory

ROOT = Path(__file__).resolve().parents[2]
FIXED_NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
PRE_EXISTING_ID = "preview-existing-market-row"
DST_COLLISION_ID = "sim-icis-sim-nbp-dayahead-2026-10-25"


def _load_seed_module():
    path = ROOT / "scripts" / "uat" / "seed_uat_fixture.py"
    spec = importlib.util.spec_from_file_location("seed_uat_fixture_regression", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seed_fixture = _load_seed_module()


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FIXED_NOW.replace(tzinfo=None)
        return FIXED_NOW.astimezone(tz)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _market_snapshot(session: Session) -> list[tuple[Any, ...]]:
    rows = session.scalars(
        select(MarketObservationRecord).order_by(MarketObservationRecord.observation_id)
    ).all()
    return [
        (
            row.observation_id,
            _as_utc(row.observed_at_utc),
            row.price,
            row.source_system,
            row.source_reference,
        )
        for row in rows
        if row.observation_id != PRE_EXISTING_ID
    ]


def test_main_seeds_dst_crossing_history_idempotently(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    assert seed_fixture.FIXTURE_DAYS == 60
    database_url = f"sqlite+pysqlite:///{tmp_path / 'uat.sqlite3'}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    session_factory = get_session_factory(database_url=database_url)
    period_start = FIXED_NOW - timedelta(days=90)
    with session_factory() as session:
        assert session.autoflush is False
        session.add(
            MarketObservationRecord(
                observation_id=PRE_EXISTING_ID,
                market_venue="PreviewExisting",
                product="preserve-me",
                price=1.25,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=period_start,
                period_end_utc=period_start + timedelta(hours=1),
                observed_at_utc=period_start,
                source_system="PreviewExisting",
                source_reference="preview:existing",
                source_record_id=None,
                freshness="simulated_live",
                quality_score=0.99,
                research_only=False,
                metadata_json={"preserve": True},
            )
        )
        session.commit()

    monkeypatch.setattr(seed_fixture, "datetime", _FrozenDateTime)
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.setenv("EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED", "1")
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_uat_fixture.py"])

    assert seed_fixture.main() == 0

    with session_factory() as session:
        collision_rows = session.scalars(
            select(MarketObservationRecord).where(
                MarketObservationRecord.observation_id == DST_COLLISION_ID
            )
        ).all()
        assert len(collision_rows) == 1
        assert _as_utc(collision_rows[0].observed_at_utc) == datetime(
            2026, 10, 25, 4, 0, tzinfo=UTC
        )

        preserved = session.get(MarketObservationRecord, PRE_EXISTING_ID)
        assert preserved is not None
        assert float(preserved.price) == 1.25
        assert preserved.source_system == "PreviewExisting"
        assert preserved.metadata_json == {"preserve": True}

        seeded_rows = session.scalars(
            select(MarketObservationRecord).where(
                MarketObservationRecord.observation_id != PRE_EXISTING_ID
            )
        ).all()
        assert seeded_rows
        assert all(row.source_system.endswith("_Sim") for row in seeded_rows)
        assert all(
            row.metadata_json is not None and row.metadata_json.get("simulated") is True
            for row in seeded_rows
        )
        seeded_instants = {_as_utc(row.observed_at_utc) for row in seeded_rows}
        assert datetime(2026, 8, 29, 4, 0, tzinfo=UTC) in seeded_instants
        assert datetime(2026, 10, 27, 4, 0, tzinfo=UTC) in seeded_instants

        agent_rows = session.scalars(
            select(MarketObservationRecord).where(
                MarketObservationRecord.observation_id.like("uat-agent-%")
            )
        ).all()
        assert len(agent_rows) == 10
        day_start = FIXED_NOW.replace(hour=0, minute=0, second=0, microsecond=0)
        assert all(
            day_start <= _as_utc(row.observed_at_utc) <= FIXED_NOW for row in agent_rows
        )
        first_snapshot = _market_snapshot(session)
        first_count = session.scalar(
            select(func.count()).select_from(MarketObservationRecord)
        )

    assert seed_fixture.main() == 0

    with session_factory() as session:
        assert _market_snapshot(session) == first_snapshot
        assert (
            session.scalar(select(func.count()).select_from(MarketObservationRecord))
            == first_count
        )
        collision_rows = session.scalars(
            select(MarketObservationRecord).where(
                MarketObservationRecord.observation_id == DST_COLLISION_ID
            )
        ).all()
        assert len(collision_rows) == 1
        preserved = session.get(MarketObservationRecord, PRE_EXISTING_ID)
        assert preserved is not None
        assert preserved.source_system == "PreviewExisting"
        assert preserved.metadata_json == {"preserve": True}

    assert "Seeded" in capsys.readouterr().out
