"""A read answered without a runtime database says so (backend audit 2026-11-26, A3)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base

TOKEN = {"X-Eurogas-Api-Key": "test-public-api-token"}


def _no_store(monkeypatch) -> None:
    for name in ("RUNTIME_STORE_DATABASE_URL", "DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(name, raising=False)


def test_every_enveloped_read_without_a_store_is_marked(monkeypatch) -> None:
    _no_store(monkeypatch)
    client = TestClient(create_app(Settings(api_profile="development")))
    # Previously silent: an empty list with no warning, read as "nothing there".
    for path in (
        "/api/portfolio/books",
        "/api/research/spread-series",
        "/api/physical/outages",
        "/api/market/quotes",
    ):
        response = client.get(path, headers=TOKEN)
        assert response.status_code == 200, path
        meta = response.json()["meta"]
        assert meta["runtime_store"] == {
            "state": "not_configured",
            "code": "runtime_db_required",
        }, path
        assert int(response.headers["content-length"]) == len(response.content)


def test_a_refusal_without_a_store_uses_the_one_code(monkeypatch) -> None:
    _no_store(monkeypatch)
    client = TestClient(create_app(Settings(api_profile="development")))
    # Each of these raised its own spelling (runtime_database_required,
    # runtime_database_not_configured, runtime_db_not_configured).
    for path in ("/api/functional-runs", "/api/monitoring/alerts", "/api/support/reports"):
        response = client.get(path, headers=TOKEN)
        assert response.status_code == 503, path
        assert response.json()["error"] == "runtime_db_required", path


def test_a_deployment_with_a_store_is_never_marked(tmp_path, monkeypatch) -> None:
    url = f"sqlite+pysqlite:///{(tmp_path / 'store.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    _no_store(monkeypatch)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    client = TestClient(create_app(Settings(api_profile="development")))
    response = client.get("/api/portfolio/books", headers=TOKEN)
    assert response.status_code == 200
    assert "runtime_store" not in response.json()["meta"]
