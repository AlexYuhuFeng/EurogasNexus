"""``GET /metrics``: plain Prometheus text for a configured scrape identity, closed by default."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base

_SAMPLE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+(?P<value>\S+)$")
_NUMERIC = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$|^[+-]?Inf$|^NaN$")


@pytest.fixture()
def no_metrics_config(monkeypatch):
    monkeypatch.delenv("EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS", raising=False)
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)


def _client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="release")))


def test_metrics_do_not_exist_unless_configured(no_metrics_config) -> None:
    response = _client().get("/metrics")
    assert response.status_code == 404
    assert "eurogas_" not in response.text


def test_wrong_or_missing_token_is_refused_without_echo(no_metrics_config, monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN", "scrape-secret-123")
    client = _client()
    assert client.get("/metrics").status_code == 401
    refused = client.get("/metrics", headers={"Authorization": "Bearer wrong-token-value"})
    assert refused.status_code == 401
    assert "wrong-token-value" not in refused.text
    assert "scrape-secret-123" not in refused.text


def test_token_scrape_returns_parseable_text_without_sign_in(
    no_metrics_config, monkeypatch
) -> None:
    """The release profile's sign-in and API-key dependencies do not apply to a scrape."""

    monkeypatch.setenv("EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN", "scrape-secret-123")
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "public-token")
    client = _client()
    # A request first, so the latency histogram has a sample.
    client.get("/api/health/live", headers={"X-Eurogas-Api-Key": "public-token"})
    response = client.get("/metrics", headers={"Authorization": "Bearer scrape-secret-123"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    text = response.text
    assert "eurogas_http_request_duration_seconds_bucket" in text
    assert 'route_group="/api/health"' in text
    # No database configured: said so, and the scrape still succeeds.
    assert "eurogas_metrics_database_up 0" in text
    for line in text.splitlines():
        if line and not line.startswith("#"):
            match = _SAMPLE.match(line)
            assert match, line
            assert _NUMERIC.match(match.group("value")), line


def test_network_rule_refuses_outside_addresses(no_metrics_config, monkeypatch) -> None:
    # The test client connects as "testclient", which is no address at all: refused.
    monkeypatch.setenv("EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS", "10.0.0.0/8")
    assert _client().get("/metrics").status_code == 403


def test_network_rule_admits_inside_addresses() -> None:
    from eurogas_nexus.api.middleware.metrics_endpoint import authorise

    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN", raising=False)
        patch.setenv("EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS", "10.0.0.0/8, 192.168.1.5")
        assert authorise({"client": ("10.1.2.3", 5000), "headers": []}) == 200
        assert authorise({"client": ("192.168.1.5", 5000), "headers": []}) == 200
        assert authorise({"client": ("192.168.1.6", 5000), "headers": []}) == 403
        # Both configured: both are needed.
        patch.setenv("EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN", "tok-abcdefgh")
        assert authorise({"client": ("10.1.2.3", 5000), "headers": []}) == 401
        assert (
            authorise(
                {
                    "client": ("10.1.2.3", 5000),
                    "headers": [(b"authorization", b"Bearer tok-abcdefgh")],
                }
            )
            == 200
        )


def test_database_metrics_are_in_the_scrape(no_metrics_config, monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "metrics.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", f"sqlite+pysqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN", "scrape-secret-123")
    response = _client().get("/metrics", headers={"Authorization": "Bearer scrape-secret-123"})
    assert response.status_code == 200
    text = response.text
    assert "eurogas_metrics_database_up 1" in text
    # Never beat: +Inf, so "heartbeat missing" fires on a store no scheduler ever ran on.
    assert 'eurogas_scheduler_heartbeat_age_seconds{scheduler="dataops"} +Inf' in text
    assert "eurogas_db_pool_size" in text


def test_metrics_path_is_not_in_the_public_api_surface() -> None:
    app = create_app(Settings(api_profile="release"))
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/metrics" not in paths
