"""Focused operator-CLI tests for National Gas REST demand ingestion."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from eurogas_nexus.db.repositories.demand_rest import DemandRestPersistenceError
from eurogas_nexus.ingestion.national_gas_rest import (
    EVIDENCE_BASIS,
    NationalGasRestError,
)
from scripts.ops import ingest_national_gas_rest as cli

RECEIVED = datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
RAW_HASH = "a" * 64
SECRET_URL = "postgresql+pg8000://operator:never-print-this@db.example/nexus"
IDS = ("PUBOB637", "PUBOB652")


def _download() -> SimpleNamespace:
    rows = (
        SimpleNamespace(
            source_publication_id="publication-a",
            unit="mscm",
            applicable_for=date(2026, 9, 1),
        ),
        SimpleNamespace(
            source_publication_id="publication-b",
            unit="mscm",
            applicable_for=date(2026, 10, 25),
        ),
    )
    return SimpleNamespace(rows=rows, raw_sha256=RAW_HASH, received_at_utc=RECEIVED)


def _summary() -> SimpleNamespace:
    return SimpleNamespace(rows_seen=2, inserted=1, duplicates=1, publications=2)


def _argv(*extra: str) -> list[str]:
    return [
        "--date-from",
        "2026-10-20",
        "--date-to",
        "2026-10-26",
        "--ids",
        *IDS,
        *extra,
    ]


class _Transaction:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> _Transaction:
        self.events.append("transaction_enter")
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.events.append("rollback" if exc_type is not None else "commit")
        return False


class _Session:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> _Session:
        self.events.append("session_enter")
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.events.append("session_exit")
        return False

    def begin(self) -> _Transaction:
        self.events.append("begin")
        return _Transaction(self.events)


def _install_session(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> list[str]:
    calls: list[str] = []

    def get_session_factory(*, database_url: str):
        calls.append(database_url)
        events.append("factory")

        def factory() -> _Session:
            events.append("factory_called")
            return _Session(events)

        return factory

    monkeypatch.setattr(cli, "get_session_factory", get_session_factory)
    return calls


@pytest.mark.parametrize(
    ("date_from", "date_to", "expected_code"),
    [
        ("2026-10-26", "2026-10-20", "INVALID_WINDOW"),
        ("2026-09-01", "2026-10-26", "INVALID_WINDOW"),
        ("not-a-date", "2026-10-26", "INVALID_DATE"),
    ],
)
def test_invalid_dates_are_refused_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    date_from: str,
    date_to: str,
    expected_code: str,
) -> None:
    def must_not_run(*args, **kwargs):
        raise AssertionError("invalid dates must not fetch or touch the database")

    monkeypatch.setattr(cli, "fetch_national_gas_rest", must_not_run)
    monkeypatch.setattr(cli, "resolve_database_url", must_not_run)
    monkeypatch.setattr(cli, "get_session_factory", must_not_run)

    assert (
        cli.main(
            [
                "--date-from",
                date_from,
                "--date-to",
                date_to,
                "--ids",
                *IDS,
            ]
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload == {
        "status": "error",
        "code": expected_code,
        "type": "NationalGasRestError",
    }


@pytest.mark.parametrize(
    ("ids", "expected_code"),
    [
        (("PUBOB999",), "UNKNOWN_PUBLICATION"),
        (("PUBOB637", "PUBOB637"), "DUPLICATE_PUBLICATION_ID"),
    ],
)
def test_unapproved_or_duplicate_ids_are_refused_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ids: tuple[str, ...],
    expected_code: str,
) -> None:
    def must_not_run(*args, **kwargs):
        raise AssertionError("invalid ids must not fetch or touch the database")

    monkeypatch.setattr(cli, "fetch_national_gas_rest", must_not_run)
    monkeypatch.setattr(cli, "resolve_database_url", must_not_run)
    monkeypatch.setattr(cli, "get_session_factory", must_not_run)

    assert (
        cli.main(
            [
                "--date-from",
                "2026-10-20",
                "--date-to",
                "2026-10-26",
                "--ids",
                *ids,
            ]
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "error",
        "code": expected_code,
        "type": "NationalGasRestError",
    }


def test_dry_run_fetches_without_resolving_or_touching_the_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    download = _download()
    fetch_calls: list[tuple[date, date, tuple[str, ...]]] = []

    def fetch(date_from: date, date_to: date, *, publication_ids: tuple[str, ...]):
        fetch_calls.append((date_from, date_to, publication_ids))
        return download

    def must_not_run(*args, **kwargs):
        raise AssertionError("dry run must not resolve or touch the database")

    monkeypatch.setattr(cli, "fetch_national_gas_rest", fetch)
    monkeypatch.setattr(cli, "resolve_database_url", must_not_run)
    monkeypatch.setattr(cli, "get_session_factory", must_not_run)
    monkeypatch.setattr(cli, "insert_demand_rest_rows", must_not_run)

    assert cli.main(_argv("--dry-run")) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "ok",
        "dry_run": True,
        "persisted": False,
        "publication_date_from": "2026-10-20",
        "publication_date_to": "2026-10-26",
        "publication_ids": list(IDS),
        "rows_seen": 2,
        "inserted": 0,
        "duplicates": 0,
        "publications": 2,
        "unit": "mscm",
        "raw_sha256": RAW_HASH,
        "received_at_utc": RECEIVED.isoformat(),
        "evidence_basis": EVIDENCE_BASIS,
    }
    assert fetch_calls == [(date(2026, 10, 20), date(2026, 10, 26), IDS)]


def test_success_persists_all_revisions_in_one_committed_transaction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    events: list[str] = []
    download = _download()
    summary = _summary()
    insert_calls: list[tuple[_Session, tuple[object, ...]]] = []

    def fetch(date_from: date, date_to: date, *, publication_ids: tuple[str, ...]):
        return download

    def insert(session: _Session, rows: tuple[object, ...]):
        events.append("insert")
        insert_calls.append((session, rows))
        return summary

    monkeypatch.setattr(cli, "fetch_national_gas_rest", fetch)
    monkeypatch.setattr(cli, "resolve_database_url", lambda: SECRET_URL)
    factory_calls = _install_session(monkeypatch, events)
    monkeypatch.setattr(cli, "insert_demand_rest_rows", insert)

    assert cli.main(_argv()) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "ok",
        "dry_run": False,
        "persisted": True,
        "publication_date_from": "2026-10-20",
        "publication_date_to": "2026-10-26",
        "publication_ids": list(IDS),
        "rows_seen": 2,
        "inserted": 1,
        "duplicates": 1,
        "publications": 2,
        "unit": "mscm",
        "raw_sha256": RAW_HASH,
        "received_at_utc": RECEIVED.isoformat(),
        "evidence_basis": EVIDENCE_BASIS,
    }
    assert factory_calls == [SECRET_URL]
    assert len(insert_calls) == 1
    assert insert_calls[0][1] is download.rows
    assert [row.applicable_for for row in insert_calls[0][1]] == [
        date(2026, 9, 1),
        date(2026, 10, 25),
    ]
    assert [row.unit for row in insert_calls[0][1]] == ["mscm", "mscm"]
    assert events == [
        "factory",
        "factory_called",
        "session_enter",
        "begin",
        "transaction_enter",
        "insert",
        "commit",
        "session_exit",
    ]


def test_persistence_failure_rolls_back_and_reports_only_a_stable_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    events: list[str] = []

    def fetch(date_from: date, date_to: date, *, publication_ids: tuple[str, ...]):
        return _download()

    def insert(session: _Session, rows: tuple[object, ...]):
        events.append("insert")
        raise DemandRestPersistenceError(f"conflict while writing {SECRET_URL}")

    monkeypatch.setattr(cli, "fetch_national_gas_rest", fetch)
    monkeypatch.setattr(cli, "resolve_database_url", lambda: SECRET_URL)
    _install_session(monkeypatch, events)
    monkeypatch.setattr(cli, "insert_demand_rest_rows", insert)

    assert cli.main(_argv()) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "error",
        "code": "DEMAND_REST_PERSISTENCE_ERROR",
        "type": "DemandRestPersistenceError",
    }
    assert SECRET_URL not in captured.err
    assert "never-print-this" not in captured.err
    assert "rollback" in events
    assert "commit" not in events


def test_unexpected_database_failure_does_not_leak_url_or_exception_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fetch(date_from: date, date_to: date, *, publication_ids: tuple[str, ...]):
        return _download()

    def get_session_factory(*, database_url: str):
        raise RuntimeError(f"cannot open {database_url}")

    monkeypatch.setattr(cli, "fetch_national_gas_rest", fetch)
    monkeypatch.setattr(cli, "resolve_database_url", lambda: SECRET_URL)
    monkeypatch.setattr(cli, "get_session_factory", get_session_factory)

    assert cli.main(_argv()) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "error",
        "code": "INGESTION_FAILED",
        "type": "RuntimeError",
    }
    assert "cannot open" not in captured.err
    assert SECRET_URL not in captured.err


def test_fetch_failure_is_reported_without_touching_the_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fetch(date_from: date, date_to: date, *, publication_ids: tuple[str, ...]):
        raise NationalGasRestError("HTTP_TIMEOUT", "provider detail must not be printed")

    def must_not_run(*args, **kwargs):
        raise AssertionError("fetch failure must not touch the database")

    monkeypatch.setattr(cli, "fetch_national_gas_rest", fetch)
    monkeypatch.setattr(cli, "resolve_database_url", must_not_run)
    monkeypatch.setattr(cli, "get_session_factory", must_not_run)

    assert cli.main(_argv()) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "error",
        "code": "HTTP_TIMEOUT",
        "type": "NationalGasRestError",
    }
    assert "provider detail" not in captured.err
