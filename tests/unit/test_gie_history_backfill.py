"""The GIE history backfill (CP-04): bounded windows through the existing ingestion path.

The driver only plans and calls ``ingest_public_sources.py``; these tests hold the plan to
the rules: one gas year per window ending yesterday, the EU total first, unpublished country
products never requested, a complete window skipped (resume), the incremental window
re-reading a week, and the ingestion plan carrying the provider's from/to filter.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.observation import StorageObservationRecord
from eurogas_nexus.ingestion.gie_transport import GieProduct

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module while it executes
    spec.loader.exec_module(module)
    return module


backfill = _load("backfill_gie_history", ROOT / "scripts" / "ops" / "backfill_gie_history.py")
ingest = _load("ingest_public_sources", ROOT / "scripts" / "ops" / "ingest_public_sources.py")


def test_five_complete_gas_years_and_the_current_one_ending_yesterday() -> None:
    windows = backfill.gas_year_windows("agsi", "DE", 5, date(2026, 11, 18))
    assert [(w.first, w.last) for w in windows][0] == (date(2021, 10, 1), date(2022, 9, 30))
    assert (windows[-1].first, windows[-1].last) == (date(2026, 10, 1), date(2026, 11, 17))
    assert len(windows) == 6
    # Early in October the current gas year has its first day only once it has closed.
    assert len(backfill.gas_year_windows("agsi", "DE", 5, date(2026, 10, 1))) == 5


def test_the_eu_total_first_and_no_unpublished_country_is_requested() -> None:
    series = backfill.series_for("agsi", ["DE", "LU", "GB", "EU"])
    assert series == ["eu", "DE"]
    assert "DK" not in backfill.series_for("alsi", ["DK", "NL"])


def test_one_window_is_one_bounded_call_of_the_gated_ingestion_path() -> None:
    window = backfill.Window("agsi", "DE", date(2021, 10, 1), date(2022, 9, 30))
    command = backfill.ingest_command(window)
    assert command[1].endswith("ingest_public_sources.py")
    assert command[command.index("--gie-from") + 1] == "2021-10-01"
    assert command[command.index("--limit") + 1] == "600", "365 days are two 300-day pages"
    assert "--gie-skip-total" in command and command[command.index("--gie-country") + 1] == "DE"
    total = backfill.ingest_command(backfill.Window("agsi", "eu", window.first, window.last))
    assert "--gie-country" not in total and "--gie-skip-total" not in total


def test_a_window_the_store_holds_in_full_is_skipped(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'b.sqlite'}")
    Base.metadata.create_all(engine)
    window = backfill.Window("agsi", "DE", date(2025, 10, 1), date(2025, 10, 10))
    rows = []
    for offset in range(10):
        day = window.first + timedelta(days=offset)
        start = datetime(day.year, day.month, day.day, 4, tzinfo=UTC)
        rows.append({
            "observation_id": f"gie-agsi-DE-{day}", "source_dataset": "AGSI", "facility_id": "DE",
            "facility_name": "Germany", "country": "DE", "inventory_twh": 1.0,
            "working_capacity_twh": 2.0, "fill_pct": 50.0, "period_start_utc": start,
            "period_end_utc": start + timedelta(days=1), "observed_at_utc": start,
            "source_system": "GIE", "source_reference": "t", "freshness": "live",
            "research_only": True,
        })
    with Session(engine) as session:
        session.bulk_insert_mappings(StorageObservationRecord, rows[:9])
        session.commit()
        assert backfill.held_days(session, window) == 9
        session.bulk_insert_mappings(StorageObservationRecord, rows[9:])
        session.commit()
        assert backfill.held_days(session, window) == window.days == 10
        assert backfill.newest_day(session, "agsi", "DE") == date(2025, 10, 10)


def test_the_ingestion_plan_carries_the_window_and_can_skip_the_total() -> None:
    window = (date(2021, 10, 1), date(2022, 9, 30))
    plan = ingest._gie_plan(["DE"], window=window, skip_total=True)
    assert [name for _, _, name in plan] == ["GIE-AGSI-DE", "GIE-ALSI-DE"]
    selector = dict(plan[0][1].selector)
    assert selector == {"country": "DE", "from": "2021-10-01", "to": "2022-09-30"}
    assert plan[0][1].dataset == "EU > DE", "the response identity check is unchanged"
    total = dict(ingest._gie_plan(None, window=window)[0][1].selector)
    assert total == {"type": "eu", "from": "2021-10-01", "to": "2022-09-30"}
    assert ingest._gie_plan(["DE"])[0][2] == "GIE-AGSI", "without a window nothing changes"


def test_a_window_ends_on_or_after_its_first_day() -> None:
    import pytest

    with pytest.raises(ValueError):
        GieProduct.agsi().for_window(date(2022, 1, 2), date(2022, 1, 1))
