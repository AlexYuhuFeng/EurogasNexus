"""Cost-source refresh application service tests."""

from datetime import UTC, datetime

from eurogas_nexus.application.cost_source_refresh import refresh_cost_source


class _FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False

    def add(self, row) -> None:
        self.added.append(row)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self._session


class _Response:
    status_code = 200

    def json(self):
        return [
            {
                "id": "cost-refresh-1",
                "scope_type": "ROUTE",
                "scope_id": "TTF-NBP",
                "observation_type": "TSO_PUBLISHED",
                "value": 1.5,
                "currency": "EUR",
                "unit": "MWh",
                "effective_from_utc": "2026-01-01T00:00:00+00:00",
                "source_system": "TSO_TARIFFS",
                "source_reference": "https://example.test/tariff.json",
            }
        ]


def test_refresh_cost_source_upserts_observations() -> None:
    session = _FakeSession()
    count = refresh_cost_source(
        _FakeFactory(session),
        url="https://example.test/tariff.json",
        http_get=lambda url: _Response(),
        now_utc=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert count == 1
    assert len(session.added) == 1
    assert session.committed is True
    assert session.added[0].scope_id == "TTF-NBP"
    assert session.added[0].value == 1.5
