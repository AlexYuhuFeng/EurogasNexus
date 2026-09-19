"""The nomination-window read: the desk's clock, and what it says when it has nothing to say.

The route exists because ``nomination_window_masters`` was read by the engine and by nobody else.
Its whole value is the distinction these tests pin: an unconfigured runtime database is an *unread*
input, a configured database that declares no active master is a *measured* zero carrying the
composition's own blocker name, and neither may be rendered as the other.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.storage_nomination import NominationWindowMasterRecord
from eurogas_nexus.security.permissions import (
    Permission,
    permission_for_path,
    serves_commercial_data,
)

PATH = "/api/optimization/nomination-windows"


def _client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="development")))


def _prepare_store(tmp_path, monkeypatch) -> str:
    """Configure an empty runtime store (no window masters declared)."""

    db_path = tmp_path / "windows.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    Base.metadata.create_all(create_engine(database_url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _add_window(
    database_url: str,
    *,
    window_id: str,
    opens_at: time,
    closes_at: time,
    active: bool = True,
    maximum_change_mwh: float | None = None,
    valid_from_utc: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    valid_to_utc: datetime | None = None,
) -> None:
    with Session(create_engine(database_url, future=True)) as session:
        session.add(
            NominationWindowMasterRecord(
                window_id=window_id,
                name=f"{window_id} window",
                country="DE",
                opens_at=opens_at,
                closes_at=closes_at,
                maximum_change_mwh=maximum_change_mwh,
                maximum_change_pct=None,
                valid_from_utc=valid_from_utc,
                valid_to_utc=valid_to_utc,
                source_system="cam",
                source_reference=f"cam:{window_id}",
                active=active,
                created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()


def test_windows_read_keeps_the_read_floor() -> None:
    """Reading the declaration is reference data; running an assessment stays governed."""

    assert permission_for_path(PATH) is Permission.READ
    assert permission_for_path("/api/optimization/nomination-window") is Permission.GOVERNED


def test_windows_read_stays_inside_the_commercial_boundary() -> None:
    """A declared renomination limit is a trading rule, so it is not administrative metadata.

    The prefix is what keeps a platform-administration identity with no commercial role out; it
    holds automatically today, and this pins it so a later move of the route out of the family
    cannot quietly widen who may read the desk's clock.
    """

    assert serves_commercial_data(PATH) is True


def test_unconfigured_runtime_db_is_an_unread_input_not_an_empty_schedule() -> None:
    response = _client().get(PATH, params={"gas_day": "2026-01-15"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["windows"] == []
    assert payload["data"]["window_masters_declared"] == 0
    assert payload["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert payload["meta"]["missing_inputs"] == [
        "RUNTIME_STORE_DATABASE_URL",
        "nomination_window_masters",
    ]
    assert payload["meta"]["warnings"]
    # The clock declaration itself does not depend on the store, so it is still stated.
    assert payload["data"]["gas_day"] == "2026-01-15"
    assert payload["data"]["time_basis"] == "utc-clock-on-gas-day"


def test_configured_store_without_masters_is_a_measured_zero(tmp_path, monkeypatch) -> None:
    _prepare_store(tmp_path, monkeypatch)

    response = _client().get(PATH, params={"gas_day": "2026-01-15"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["windows"] == []
    assert payload["data"]["window_masters_declared"] == 0
    assert payload["meta"]["source_references"] == ["nomination_window_masters"]
    assert payload["meta"]["missing_inputs"] == []
    assert payload["meta"]["warnings"] == ["NOMINATION_WINDOWS_MISSING"]


def test_declared_windows_carry_resolved_deadlines(tmp_path, monkeypatch) -> None:
    database_url = _prepare_store(tmp_path, monkeypatch)
    _add_window(
        database_url,
        window_id="de-renom-1",
        opens_at=time(5, 0),
        closes_at=time(5, 30),
        maximum_change_mwh=150.0,
    )
    _add_window(
        database_url,
        window_id="de-renom-wrap",
        opens_at=time(23, 0),
        closes_at=time(1, 0),
    )

    response = _client().get(PATH, params={"gas_day": "2026-01-15"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["window_masters_declared"] == 2
    assert payload["data"]["calendar"] == "EU-CAM-UTC-2025"
    assert payload["data"]["gas_day_start_utc"].startswith("2026-01-15T05:00:00")
    assert payload["data"]["gas_day_end_utc"].startswith("2026-01-16T05:00:00")
    assert payload["meta"]["warnings"] == []
    assert payload["meta"]["missing_inputs"] == []

    by_id = {row["window_id"]: row for row in payload["data"]["windows"]}
    assert set(by_id) == {"de-renom-1", "de-renom-wrap"}
    inside = by_id["de-renom-1"]
    assert inside["opens_at"] == "05:00:00"
    assert inside["closes_at"] == "05:30:00"
    assert inside["opens_at_utc"].startswith("2026-01-15T05:00:00")
    assert inside["closes_at_utc"].startswith("2026-01-15T05:30:00")
    assert inside["closes_after_utc_midnight"] is False
    assert inside["maximum_change_mwh"] == 150.0
    # A limit the deployment did not declare stays undeclared rather than becoming a zero.
    assert inside["maximum_change_pct"] is None
    assert inside["source_reference"] == "cam:de-renom-1"
    # The daily rule's next occurrence, resolved by the route: a desk needs the instant the next
    # window opens once this gas day's window has closed.
    assert inside["next_gas_day"] == "2026-01-16"
    assert inside["next_opens_at_utc"].startswith("2026-01-16T05:00:00")
    assert inside["next_closes_at_utc"].startswith("2026-01-16T05:30:00")
    wrapping = by_id["de-renom-wrap"]
    assert wrapping["opens_at_utc"].startswith("2026-01-15T23:00:00")
    assert wrapping["closes_at_utc"].startswith("2026-01-16T01:00:00")
    assert wrapping["closes_after_utc_midnight"] is True
    assert wrapping["next_opens_at_utc"].startswith("2026-01-16T23:00:00")
    assert wrapping["next_closes_at_utc"].startswith("2026-01-17T01:00:00")
    assert payload["meta"]["lineage"] == [
        "nomination_window_master:de-renom-1",
        "nomination_window_master:de-renom-wrap",
    ]


def test_inactive_and_expired_masters_are_not_declared_for_the_gas_day(
    tmp_path, monkeypatch
) -> None:
    database_url = _prepare_store(tmp_path, monkeypatch)
    _add_window(
        database_url,
        window_id="retired",
        opens_at=time(5, 0),
        closes_at=time(5, 30),
        active=False,
    )
    _add_window(
        database_url,
        window_id="future",
        opens_at=time(5, 0),
        closes_at=time(5, 30),
        valid_from_utc=datetime(2027, 1, 1, tzinfo=UTC),
    )

    payload = _client().get(PATH, params={"gas_day": "2026-01-15"}).json()

    assert payload["data"]["windows"] == []
    assert payload["meta"]["warnings"] == ["NOMINATION_WINDOWS_MISSING"]


def test_default_gas_day_states_the_interval_it_resolved_against() -> None:
    """No parameter: the answer must still declare which gas day it answered for."""

    payload = _client().get(PATH).json()

    data = payload["data"]
    assessed_at = datetime.fromisoformat(data["assessed_at_utc"])
    start = datetime.fromisoformat(data["gas_day_start_utc"])
    end = datetime.fromisoformat(data["gas_day_end_utc"])
    assert start <= assessed_at < end
    assert data["gas_day"] == start.astimezone(UTC).date().isoformat()
    assert payload["meta"]["gas_day"] == data["gas_day"]


def test_malformed_gas_day_is_refused() -> None:
    response = _client().get(PATH, params={"gas_day": "not-a-date"})

    assert response.status_code == 422


def test_explicit_gas_day_bounds_are_the_calendar_bounds() -> None:
    payload = _client().get(PATH, params={"gas_day": "2026-10-24"}).json()

    # The 25-hour gas day: this is the row a board must not compute for itself.
    assert payload["data"]["gas_day_start_utc"].startswith("2026-10-24T04:00:00")
    assert payload["data"]["gas_day_end_utc"].startswith("2026-10-25T05:00:00")


def test_next_occurrence_follows_the_daylight_saving_boundary(tmp_path, monkeypatch) -> None:
    """The next window is a calendar answer, not "today's instant plus 24 hours"."""

    database_url = _prepare_store(tmp_path, monkeypatch)
    _add_window(
        database_url, window_id="de-renom-1", opens_at=time(6, 0), closes_at=time(6, 30)
    )

    # 2026-03-28 is the last winter gas day: the next boundary is 04:00 UTC, not 05:00.
    payload = _client().get(PATH, params={"gas_day": "2026-03-28"}).json()
    row = payload["data"]["windows"][0]
    assert row["opens_at_utc"].startswith("2026-03-28T06:00:00")
    assert row["next_gas_day"] == "2026-03-29"
    assert row["next_opens_at_utc"].startswith("2026-03-29T06:00:00")
    assert payload["data"]["gas_day_end_utc"].startswith("2026-03-29T04:00:00")


def test_window_rows_are_ordered_by_declared_opening_time(tmp_path, monkeypatch) -> None:
    database_url = _prepare_store(tmp_path, monkeypatch)
    _add_window(
        database_url, window_id="late", opens_at=time(20, 0), closes_at=time(20, 30)
    )
    _add_window(
        database_url, window_id="early", opens_at=time(5, 0), closes_at=time(5, 30)
    )

    payload = _client().get(PATH, params={"gas_day": "2026-01-15"}).json()

    assert [row["window_id"] for row in payload["data"]["windows"]] == ["early", "late"]


def test_gas_day_label_matches_the_declared_interval_for_a_winter_date() -> None:
    """A regression guard for the label/boundary pair the client renders together."""

    payload = _client().get(PATH, params={"gas_day": date(2026, 1, 15).isoformat()}).json()

    assert payload["data"]["gas_day"] == "2026-01-15"
    assert payload["data"]["gas_day_start_utc"].startswith("2026-01-15T05:00:00")
