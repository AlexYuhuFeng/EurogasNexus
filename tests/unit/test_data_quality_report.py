"""The data-quality report states what arrived: counts, gaps, repeats, blanks, age."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from eurogas_nexus.application.data_quality_report import (
    DatasetSpec,
    as_text,
    build_report,
    measure,
)

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
SPEC = DatasetSpec(
    "Test flows", "TEST", "flows", "period_start", ("point", "direction"), ("value",),
    1440, 48, received="received",
)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE flows (id TEXT, point TEXT, direction TEXT, period_start TEXT,"
            " value REAL, received TEXT)"
        ))
    with Session(engine) as db:
        yield db


def _add(session, day_offset: int, point: str, value: float | None = 1.0, direction="entry"):
    start = NOW.replace(hour=5) - timedelta(days=day_offset)
    session.execute(
        text("INSERT INTO flows VALUES (:i, :p, :d, :s, :v, :r)"),
        {"i": f"{point}-{day_offset}-{direction}", "p": point, "d": direction,
         "s": start.isoformat(), "v": value, "r": (start + timedelta(hours=30)).isoformat()},
    )


def test_a_complete_current_dataset_is_ok(session):
    for day in range(1, 8):
        for point in ("A", "B", "C"):
            _add(session, day, point)
    result = measure(session, SPEC, NOW)
    assert result.status == "ok"
    assert (result.rows, result.entities, result.duplicate_keys) == (21, 3, 0)
    assert result.median_lateness_hours == 30.0 and result.short_periods == []


def test_an_empty_dataset_is_empty_never_ok(session):
    result = measure(session, SPEC, NOW)
    assert result.status == "empty" and result.rows == 0


def test_a_short_day_a_repeat_a_blank_and_a_stale_feed_are_each_named(session):
    for day in range(4, 10):
        for point in ("A", "B", "C", "D"):
            if day == 6 and point != "A":
                continue  # one day delivered a quarter of its series
            _add(session, day, point, value=None if (day, point) == (5, "B") else 1.0)
    _add(session, 7, "A")  # the same point, direction and day again
    result = measure(session, SPEC, NOW)
    messages = " ".join(finding["message"] for finding in result.findings)
    assert result.status == "critical"  # a repeated natural key
    assert result.duplicate_keys == 1 and result.blank_rows == 1
    assert len(result.short_periods) == 1 and "closed days" in messages
    assert "old; expected within 48 h" in messages  # latest period is four days back


def test_the_report_summarises_by_status_and_prints_one_line_per_dataset(session):
    report = build_report(session, now=NOW)
    assert sum(report["summary"].values()) == len(report["datasets"])
    assert report["summary"].get("empty")  # this store holds none of the product's tables
    printed = as_text(report)
    assert "ENTSOG flows" in printed and "empty" in printed
