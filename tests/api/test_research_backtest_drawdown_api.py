"""API-level regression tests for the research backtest drawdown reporting.

The research route is the surface a trader actually reads, and it serialises the
drawdown fields itself, so the domain-level golden tests in
``tests/domain/research/test_backtest.py`` are not sufficient: a field that the
domain computes but the route never copies would still be invisible. These tests
pin the route's own response.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'backtest-drawdown.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    test_client = TestClient(create_app())
    test_client.engine = engine
    return test_client


def _post(client, trades: list[dict], **extra) -> dict:
    response = client.post(
        "/api/research/backtest",
        json={"strategy_name": "Drawdown probe", "trades": trades, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_all_losing_strategy_reports_a_drawdown_and_no_fake_zero(client) -> None:
    """A losing-every-trade run must not report a zero drawdown.

    This is the regression: the field used to be computed as 0.0 for any curve
    that never rose above its zero starting equity, so a strategy that lost money
    on every trade was indistinguishable from one that never drew down.
    """

    data = _post(client, [{"pnl_eur": -100.0}, {"pnl_eur": -50.0}, {"pnl_eur": -80.0}])

    assert data["total_return_eur"] == -230.0
    assert data["max_drawdown_eur"] == 230.0
    # No capital base and no positive peak: the percent has no denominator, and
    # must say so rather than reporting 0.0.
    assert data["max_drawdown_pct"] is None
    assert any("capital_base_eur" in warning for warning in data["warnings"])


def test_capital_base_makes_the_percentage_available(client) -> None:
    data = _post(
        client,
        [{"pnl_eur": -100.0}, {"pnl_eur": -50.0}, {"pnl_eur": -80.0}],
        capital_base_eur=1000.0,
    )
    assert data["max_drawdown_eur"] == 230.0
    assert data["max_drawdown_pct"] == 23.0
    assert not any("capital_base_eur" in warning for warning in data["warnings"])


def test_rising_strategy_reports_zero_drawdown_without_a_warning(client) -> None:
    data = _post(client, [{"pnl_eur": 100.0}, {"pnl_eur": 50.0}])
    assert data["max_drawdown_eur"] == 0.0
    assert data["max_drawdown_pct"] == 0.0
    assert not any("capital_base_eur" in warning for warning in data["warnings"])


def test_negative_capital_base_is_refused(client) -> None:
    response = client.post(
        "/api/research/backtest",
        json={
            "strategy_name": "Drawdown probe",
            "trades": [{"pnl_eur": -100.0}],
            "capital_base_eur": -1000.0,
        },
    )
    assert response.status_code == 422


def test_trades_are_replayed_in_date_order(client) -> None:
    data = _post(
        client,
        [
            {"pnl_eur": 100.0, "date": "2026-02-01"},
            {"pnl_eur": -50.0, "date": "2026-01-01"},
        ],
    )
    # Chronological curve: 0 -> -50 -> +50. Falls 50 from the zero start.
    assert data["max_drawdown_eur"] == 50.0
