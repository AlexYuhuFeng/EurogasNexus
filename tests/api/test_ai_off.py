"""Small-desk plan 3.6: one administrator setting turns every AI feature off.

With ``ai_enabled`` false no request leaves the server for any model: every network
connection attempt fails this test (the socket layer itself is trapped, so a call that
bypassed the provider adapter would be caught too), and every feature that used AI still
answers, by rule.
"""

from __future__ import annotations

import importlib.util
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application import explain as explain_module
from eurogas_nexus.application.caller import firm_caller
from eurogas_nexus.core.config import get_settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.security import provider_keys

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", "true")
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    # A configured provider and a stored key: everything is ready to call a model.
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_BASE_URL", "https://model.example/v1")
    monkeypatch.setattr(provider_keys, "load_provider_api_key", lambda _provider: "recorded")
    get_settings.cache_clear()
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, NOW)
        session.commit()
    explain_module._CACHE.clear()
    yield engine
    get_settings.cache_clear()


@pytest.fixture
def outbound(monkeypatch):
    """Every attempt to open a network connection, by host; each attempt fails."""

    attempts: list[str] = []

    def resolve(host, *args, **kwargs):
        attempts.append(f"resolve:{host}")
        raise socket.gaierror("network is trapped in this test")

    def connect(self, address):
        attempts.append(f"connect:{address}")
        raise OSError("network is trapped in this test")

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect)
    return attempts


def _admin(engine) -> TestClient:
    from eurogas_nexus.api.app import create_app
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    with Session(engine) as session:
        principal = create_identity_principal(
            session, name="admin", display_name="admin", role="ADMIN", data_scopes=["*"]
        )
        _, bearer = create_identity_api_key(session, principal.principal_id, scopes=["*"])
        session.commit()
    return TestClient(
        create_app(),
        headers={"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer},
    )


def _breach() -> str:
    from eurogas_nexus.application.limits_service import credit_exposure_rows

    rows = credit_exposure_rows(firm_caller(), NOW.date()).rows
    return next(row["counterparty_id"] for row in rows if row["status"] == "breach")


def _desk_client() -> TestClient:
    from eurogas_nexus.api.app import create_app

    return TestClient(create_app())


def test_the_trap_sees_a_model_call_while_ai_is_on(desk, outbound):
    """Control: with AI on the same request does try to reach the model."""

    response = _desk_client().post(
        "/api/analysis/explain", json={"subject": "credit", "id": _breach()}
    )
    assert response.status_code == 200, response.text
    assert any("model.example" in attempt for attempt in outbound), outbound


def test_with_ai_off_no_request_leaves_and_every_feature_still_answers(desk, outbound):
    admin = _admin(desk)
    off = admin.put("/api/settings/organisation", json={"ai_enabled": False})
    assert off.status_code == 200, off.text
    assert off.json()["data"]["ai_enabled"] is False

    client = _desk_client()
    explained = client.post("/api/analysis/explain", json={"subject": "credit", "id": _breach()})
    assert explained.status_code == 200, explained.text
    assert explained.json()["data"]["basis"] == "rule"

    for kind in ("morning", "eod"):
        brief = client.post("/api/analysis/brief", json={"kind": kind})
        assert brief.status_code == 200, brief.text
        assert brief.json()["data"]["lead_basis"] != "model"

    asked = client.post("/api/analysis/ask", json={"question": "Where is TTF trading?"})
    assert asked.status_code == 200, asked.text
    assert asked.json()["data"]["ai"] == "off"

    plan = client.post("/api/reports/plan", json={"question": "Weekly TTF and NBP report"})
    assert plan.status_code == 200, plan.text
    assert plan.json()["data"].get("basis") != "model"

    spread = client.post("/api/research/spreads/interpret", json={"text": "TTF NBP front month"})
    assert spread.status_code == 200, spread.text

    query = client.post(
        "/api/analysis/query",
        json={"question": "What moved TTF today?", "invoke_provider": True},
    )
    assert query.status_code == 200, query.text

    report = client.post("/api/reports/market", json={"kind": "daily", "use_model": True})
    assert report.status_code == 200, report.text

    # The adapter itself refuses, whoever calls it.
    from eurogas_nexus.llm import invoke_deepseek, test_deepseek_connection

    direct = invoke_deepseek(api_key="recorded", messages=[{"role": "user", "content": "x"}])
    assert direct.status == "ai_off" and direct.content is None
    assert test_deepseek_connection(api_key="recorded").status == "ai_off"

    assert outbound == [], f"a request left the server with AI off: {outbound}"

    me_state = _ai_state_for_desk()
    assert me_state == {"available": False, "reason": "switched_off"}


def _ai_state_for_desk() -> dict:
    from eurogas_nexus.api.routes.public.auth import _ai_state
    from eurogas_nexus.security.identity import legacy_public_token_principal

    return _ai_state(legacy_public_token_principal())


def test_the_administrator_sees_the_ai_settings_in_force(desk):
    admin = _admin(desk)
    response = admin.get("/api/settings/ai")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["enabled"] is True
    assert data["provider"] == {"name": "CONFIGURED", "model": "deepseek-v4-flash",
                                "self_hosted": False}
    assert data["timeouts_seconds"] == {"interactive": 3.0, "draft": 240.0}
    # Counterparty names and deal-level data are not sent until an administrator allows it.
    assert {row["category"]: row["allowed"] for row in data["sharing_categories"]} == {
        "counterparty_names": False,
        "deal_level": False,
    }
    assert "key" not in str(data).lower().replace("key_", "")


@pytest.mark.parametrize(
    "body",
    [
        {"ai_enabled": "off"},
        {"ai_data_sharing": {"free_text": True}},
        {"ai_data_sharing": {"deal_level": "yes"}},
    ],
)
def test_invalid_ai_settings_are_refused(desk, body):
    response = _admin(desk).put("/api/settings/organisation", json=body)
    assert response.status_code == 422, response.text
