"""SQLite tests for the bounded ECMWF forecast read repository."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.research import ForecastObservationRecord
from eurogas_nexus.db.repositories.ecmwf_forecast_reads import (
    EcmwfForecastReadOverflowError,
    EcmwfForecastReadValidationError,
    read_ecmwf_forecasts,
)
from eurogas_nexus.db.repositories.research import upsert_forecast_observation

ORIGIN = datetime(2026, 1, 3, tzinfo=UTC)
VALID_FROM = datetime(2026, 1, 3, tzinfo=UTC)
VALID_TO = datetime(2026, 1, 5, tzinfo=UTC)


@pytest.fixture()
def sqlite_db() -> Iterator[tuple[Session, Engine]]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ForecastObservationRecord.__table__.create(engine)
    with Session(engine) as session:
        yield session, engine
    engine.dispose()


def _append(
    session: Session,
    record_id: str,
    *,
    issued: datetime = datetime(2026, 1, 2, tzinfo=UTC),
    valid_start: datetime = VALID_FROM,
    available: datetime = datetime(2026, 1, 2, 6, tzinfo=UTC),
    series_id: str = "series-1",
    entity_id: str = "entity-1",
    source_system: str = "ECMWF_OPEN_DATA",
    model_provider: str = "ECMWF",
    quality_state: str = "FORECAST",
    unit: str = "degC",
    value: float = 1.0,
    valid_end: datetime | None = None,
) -> ForecastObservationRecord:
    return upsert_forecast_observation(
        session,
        forecast_observation_id=record_id,
        series_id=series_id,
        entity_id=entity_id,
        forecast_issued_at=issued,
        forecast_valid_start=valid_start,
        forecast_valid_end=valid_end or valid_start,
        horizon="24h",
        value=value,
        unit=unit,
        source_system=source_system,
        available_at_utc=available,
        model_provider=model_provider,
        provenance={"fixture": record_id},
        quality_state=quality_state,
    )


def _read(session: Session, **overrides: Any) -> list[ForecastObservationRecord]:
    request: dict[str, Any] = {
        "explicit_series_ids": ("series-1",),
        "entity_ids": ("entity-1",),
        "prediction_origin": ORIGIN,
        "valid_from": VALID_FROM,
        "valid_to": VALID_TO,
        "limit": 10,
    }
    request.update(overrides)
    return read_ecmwf_forecasts(session, **request)


def _seed_versions(session: Session) -> None:
    _append(
        session,
        "issued-1",
        issued=datetime(2026, 1, 1, tzinfo=UTC),
        available=datetime(2026, 1, 1, 6, tzinfo=UTC),
        value=1.0,
    )
    _append(
        session,
        "issued-2",
        issued=datetime(2026, 1, 2, tzinfo=UTC),
        available=datetime(2026, 1, 2, 6, tzinfo=UTC),
        value=2.0,
    )
    _append(
        session,
        "receipt-after-origin",
        available=datetime(2026, 1, 3, 1, tzinfo=UTC),
        value=3.0,
    )
    _append(
        session,
        "future-valid",
        valid_start=VALID_FROM + timedelta(days=1),
        available=datetime(2026, 1, 2, 6, tzinfo=UTC),
        value=4.0,
    )
    _append(session, "valid-at-end", valid_start=VALID_TO, value=5.0)
    _append(
        session,
        "period-starts-before",
        valid_start=VALID_FROM - timedelta(hours=1),
        valid_end=VALID_FROM + timedelta(hours=1),
        value=6.0,
    )


def test_keeps_all_versions_with_half_open_start_window(sqlite_db) -> None:
    session, _ = sqlite_db
    _seed_versions(session)
    session.flush()

    rows = _read(session, limit=8)

    assert [row.forecast_observation_id for row in rows] == [
        "issued-1",
        "issued-2",
        "future-valid",
    ]
    assert [row.value for row in rows] == [1.0, 2.0, 4.0]
    assert all(isinstance(row, ForecastObservationRecord) for row in rows)
    assert rows[2].forecast_valid_end == rows[2].forecast_valid_start


def test_excludes_wrong_source_unit_series_entity_provider_quality(
    sqlite_db,
) -> None:
    session, _ = sqlite_db
    _append(session, "ok")
    _append(session, "wrong-source", source_system="ERA5")
    _append(session, "wrong-provider", model_provider="GFS")
    _append(session, "wrong-quality", quality_state="OBSERVED")
    _append(session, "wrong-unit", unit="K")
    _append(session, "wrong-series", series_id="series-2")
    _append(session, "wrong-entity", entity_id="entity-2")
    session.flush()

    rows = _read(session, limit=8)

    assert [row.forecast_observation_id for row in rows] == ["ok"]


def test_limit_refuses_to_truncate(sqlite_db) -> None:
    session, _ = sqlite_db
    for index in range(3):
        _append(
            session,
            f"row-{index}",
            valid_start=VALID_FROM + timedelta(hours=index),
        )
    session.flush()

    with pytest.raises(EcmwfForecastReadOverflowError):
        _read(session, limit=2)
    assert len(_read(session, limit=3)) == 3


@pytest.mark.parametrize(
    "overrides",
    [
        {"explicit_series_ids": None},
        {"explicit_series_ids": "series-1"},
        {"explicit_series_ids": ()},
        {"explicit_series_ids": ("series-1",) * 257},
        {"explicit_series_ids": ("",)},
        {"explicit_series_ids": (1,)},
        {"entity_ids": ()},
        {"prediction_origin": datetime(2026, 1, 3)},
        {"valid_from": datetime(2026, 1, 3)},
        {"valid_to": VALID_FROM},
        {"valid_to": VALID_FROM + timedelta(days=32, seconds=1)},
        {"limit": 0},
        {"limit": 257},
        {"limit": True},
    ],
)
def test_invalid_requests_fail_closed(sqlite_db, overrides) -> None:
    session, _ = sqlite_db
    with pytest.raises(EcmwfForecastReadValidationError):
        _read(session, **overrides)


def test_32_day_window_is_allowed(sqlite_db) -> None:
    session, _ = sqlite_db
    assert _read(session, valid_to=VALID_FROM + timedelta(days=32)) == []


def test_read_is_one_select_and_does_not_mutate(sqlite_db) -> None:
    session, engine = sqlite_db
    _append(session, "row-1", value=7.0)
    session.flush()
    before = session.scalar(
        select(func.count()).select_from(ForecastObservationRecord)
    )
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        rows = _read(session)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert len(statements) == 1
    assert [row.forecast_observation_id for row in rows] == ["row-1"]
    assert rows[0].value == 7.0
    assert rows[0] in session
    assert not session.new and not session.dirty and not session.deleted
    after = session.scalar(
        select(func.count()).select_from(ForecastObservationRecord)
    )
    assert after == before
