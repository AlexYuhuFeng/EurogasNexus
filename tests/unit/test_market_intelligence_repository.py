"""Focused repository tests for bounded market-source coverage."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from eurogas_nexus.db.repositories.market_intelligence import (
    _merge_bounded_source_coverage,
)


def _row(observation_id: str, minute: int) -> SimpleNamespace:
    return SimpleNamespace(
        observation_id=observation_id,
        observed_at_utc=datetime(2026, 8, 30, 0, 0, tzinfo=UTC)
        + timedelta(minutes=minute),
        market_venue="fixture",
        product="day-ahead",
    )


def test_source_coverage_is_preserved_without_exceeding_limit() -> None:
    newest = [_row(f"fast-{minute}", minute) for minute in range(10, 5, -1)]
    low_frequency = _row("icis-daily", 1)

    rows = _merge_bounded_source_coverage(
        newest,
        [low_frequency, newest[0]],
        limit=4,
    )

    assert len(rows) == 4
    assert rows[0].observation_id == "fast-10"
    assert rows[-1].observation_id == "icis-daily"
    assert len({row.observation_id for row in rows}) == len(rows)
