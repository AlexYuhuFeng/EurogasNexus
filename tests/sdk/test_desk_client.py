"""SDK coverage for the Today read (``GET /api/desk/today``)."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from eurogas_nexus_sdk.desk import DeskToday, fetch_desk_today, fetch_desk_today_result
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 7, 7, tzinfo=UTC)


def _server_payload(tmp_path, monkeypatch) -> dict:
    """The server's own Today read over the demo desk, as the route would return it."""

    import eurogas_nexus.db.models  # noqa: F401  (registers every table)
    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.desk_today import build_today
    from eurogas_nexus.db.base import Base
    from eurogas_nexus.security.identity import AuthenticatedPrincipal

    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location(
        "seed_demo_desk", ROOT / "scripts" / "demo" / "seed_demo_desk.py"
    )
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    caller = Caller(AuthenticatedPrincipal(
        principal_id="p-analyst", name="analyst", principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=("DEMO", "BOOKS:*"), roles=("ANALYST",),
    ))
    with Session(engine) as session:
        seed.seed(session, NOW)
        session.commit()
        data = build_today(session, caller, now=NOW, balance_reader=lambda: None)
    return json.loads(json.dumps(data, default=str))


def _respond(captured: dict, data: dict):
    def fake_get(url: str, **kwargs) -> httpx.Response:
        captured["url"] = url
        captured["timeout"] = kwargs.get("timeout")
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"data": data, "meta": {"research_only": True, "human_review_required": True,
                                         "source_references": ["runtime-postgresql:desk-today"],
                                         "warnings": data.get("warnings", [])}},
        )

    return fake_get


def test_the_sdk_reads_the_servers_today_payload(tmp_path, monkeypatch) -> None:
    data = _server_payload(tmp_path, monkeypatch)
    captured: dict = {}
    monkeypatch.setattr(httpx, "get", _respond(captured, data))

    result = fetch_desk_today_result("http://testserver/")

    assert captured["url"] == "http://testserver/api/desk/today"
    assert captured["timeout"] == 15.0
    today = result.data
    assert isinstance(today, DeskToday)
    # Every top-level field the server returns is a typed field of the model.
    assert set(data) == set(DeskToday.model_fields)
    assert [row["key"] for row in today.rows] == ["key_figures", "changes", "book",
                                                  "fundamentals", "needs_me"]
    assert today.row("book") is today.rows[2] and today.row("nope") is None  # type: ignore[arg-type]
    assert today.simulated and today.simulated_notice
    assert result.meta.source_references == ["runtime-postgresql:desk-today"]
    assert fetch_desk_today("http://testserver").gas_day == today.gas_day


def test_an_empty_read_is_an_error_not_a_today_with_defaults(monkeypatch) -> None:
    from pydantic import ValidationError

    monkeypatch.setattr(httpx, "get", _respond({}, {}))
    with pytest.raises(ValidationError):
        fetch_desk_today("http://testserver")
