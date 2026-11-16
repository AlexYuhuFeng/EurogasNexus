"""SDK coverage for market reports: the client talks to the real routes (in-process)."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from eurogas_nexus_sdk import reports
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path, monkeypatch):
    import eurogas_nexus.db.models  # noqa: F401
    from eurogas_nexus.api.app import create_app
    from eurogas_nexus.db.base import Base

    # The SDK conftest clears the deployment token; the in-process server still needs one.
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "sdk-test-token")
    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location(
        "seed_demo_desk", ROOT / "scripts" / "demo" / "seed_demo_desk.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, datetime.now(UTC))
        session.commit()
    app = TestClient(create_app())

    def route(method):
        def call(url, **kwargs):
            path = url.removeprefix("http://testserver")
            kwargs.pop("timeout", None)
            kwargs["headers"] = {**(kwargs.get("headers") or {}),
                                 "X-Eurogas-Api-Key": "sdk-test-token"}
            response = app.request(method, path, **kwargs)
            return httpx.Response(response.status_code, content=response.content,
                                  headers=response.headers, request=httpx.Request(method, url))
        return call

    monkeypatch.setattr(httpx, "get", route("GET"))
    monkeypatch.setattr(httpx, "post", route("POST"))
    return "http://testserver"


def test_the_sdk_generates_lists_and_reopens_a_report(client):
    catalogue = reports.fetch_report_catalogue(client)
    assert "daily" in catalogue["kinds"]
    made = reports.generate_market_report(client, kind="daily", audience="shareable",
                                          use_model=False)
    assert made.audience == "shareable" and made.simulated
    assert made.report_id in {r["report_id"] for r in reports.list_market_reports(client)}
    again = reports.fetch_market_report(client, made.report_id)
    assert again.html_sha256 == made.html_sha256
    html = reports.fetch_market_report_html(client, made.report_id)
    assert html.startswith("<!doctype html>")
    plan = reports.propose_report_plan(client, "Norwegian supply this week", use_model=False)
    assert plan["plan"]["sections"][0] == "pipeline_supply"
