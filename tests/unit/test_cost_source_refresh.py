"""Cost-source refresh application service tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from eurogas_nexus.application import cost_source_refresh
from eurogas_nexus.application.cost_source_refresh import refresh_cost_source
from eurogas_nexus.ingestion.connectors.cost_source import (
    CostSourceHttpRefusal,
    CostSourceJsonRefusal,
)

_FEED_URL = "https://example.test/tariff.json?token=synthetic-secret"


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "cost-refresh-1",
        "scope_type": "ROUTE",
        "scope_id": "TTF-NBP",
        "observation_type": "TSO_PUBLISHED",
        "value": 1.5,
        "currency": "EUR",
        "unit": "MWh",
        "effective_from_utc": "2026-01-01T00:00:00+00:00",
        "source_system": "TSO_TARIFFS",
        "source_reference": _FEED_URL,
    }
    record.update(overrides)
    return record


class _FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, row) -> None:
        self.added.append(row)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeFactory:
    def __init__(self, session) -> None:
        self._session = session
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._session


class _Response:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


def test_refresh_cost_source_upserts_observations() -> None:
    session = _FakeSession()
    factory = _FakeFactory(session)
    count = refresh_cost_source(
        factory,
        url=_FEED_URL,
        http_get=lambda _url: _Response([_record()]),
        now_utc=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert count == 1
    assert factory.calls == 1
    assert len(session.added) == 1
    assert session.committed is True
    assert session.rolled_back is False
    assert session.added[0].scope_id == "TTF-NBP"
    assert session.added[0].value == 1.5
    assert session.added[0].created_at_utc == datetime(2026, 6, 1, tzinfo=UTC)


@pytest.mark.parametrize("payload", [[], {"items": []}])
def test_refresh_empty_success_does_not_open_a_session(payload: Any) -> None:
    session = _FakeSession()
    factory = _FakeFactory(session)
    count = refresh_cost_source(
        factory,
        url=_FEED_URL,
        http_get=lambda _url: _Response(payload),
    )

    assert count == 0
    assert factory.calls == 0
    assert session.added == []
    assert session.committed is False


def test_refresh_http_failure_is_not_reported_as_success() -> None:
    session = _FakeSession()
    factory = _FakeFactory(session)

    with pytest.raises(CostSourceHttpRefusal) as excinfo:
        refresh_cost_source(
            factory,
            url=_FEED_URL,
            http_get=lambda _url: _Response([], status_code=503),
        )

    assert excinfo.value.status_code == 503
    assert factory.calls == 0
    assert session.added == []
    assert session.committed is False


def test_refresh_missing_value_is_not_coerced_to_zero() -> None:
    session = _FakeSession()
    factory = _FakeFactory(session)

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        refresh_cost_source(
            factory,
            url=_FEED_URL,
            http_get=lambda _url: _Response([_record(value=None)]),
        )

    assert excinfo.value.record_index == 0
    assert excinfo.value.field == "value"
    assert factory.calls == 0
    assert session.added == []
    assert session.committed is False


def test_refresh_corrupt_later_row_persists_nothing() -> None:
    session = _FakeSession()
    factory = _FakeFactory(session)
    records = [_record(), _record(id="cost-refresh-2", value=None)]

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        refresh_cost_source(
            factory,
            url=_FEED_URL,
            http_get=lambda _url: _Response(records),
        )

    assert excinfo.value.record_index == 1
    assert excinfo.value.field == "value"
    assert factory.calls == 0
    assert session.added == []
    assert session.committed is False


def test_refresh_missing_provenance_is_refused_before_persistence() -> None:
    session = _FakeSession()
    factory = _FakeFactory(session)
    record = _record()
    del record["source_reference"]

    with pytest.raises(CostSourceJsonRefusal) as excinfo:
        refresh_cost_source(
            factory,
            url=_FEED_URL,
            http_get=lambda _url: _Response([record]),
        )

    assert excinfo.value.field == "source_reference"
    assert _FEED_URL not in str(excinfo.value)
    assert factory.calls == 0
    assert session.added == []
    assert session.committed is False


def test_refresh_explicit_zero_is_persisted_as_a_value() -> None:
    session = _FakeSession()
    count = refresh_cost_source(
        _FakeFactory(session),
        url=_FEED_URL,
        http_get=lambda _url: _Response([_record(value=0)]),
    )

    assert count == 1
    assert session.added[0].value == 0.0
    assert session.committed is True


def test_refresh_rolls_back_if_a_later_upsert_fails(monkeypatch) -> None:
    session = _FakeSession()
    attempts = {"count": 0}

    def _fail_on_second(session_arg, observation, *, now_utc=None) -> None:
        attempts["count"] += 1
        if attempts["count"] == 2:
            raise RuntimeError("synthetic later-row failure")
        session_arg.add(observation)

    monkeypatch.setattr(
        cost_source_refresh,
        "upsert_cost_observation",
        _fail_on_second,
    )

    with pytest.raises(RuntimeError):
        refresh_cost_source(
            _FakeFactory(session),
            url=_FEED_URL,
            http_get=lambda _url: _Response(
                [_record(), _record(id="cost-refresh-2")]
            ),
        )

    assert attempts["count"] == 2
    assert len(session.added) == 1
    assert session.committed is False
    assert session.rolled_back is True
