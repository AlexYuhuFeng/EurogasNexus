"""GOV-1, AI controls stage 2 through the API: the switch, its audit, and call provenance."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
import eurogas_nexus.llm as llm
from eurogas_nexus.application import explain as explain_module
from eurogas_nexus.application.caller import firm_caller
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord
from eurogas_nexus.domain.ai.register import ai_use
from eurogas_nexus.llm.deepseek import DeepSeekCallResult
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
    # Security M10 removed the default provider: a model call now needs an endpoint the
    # installation has chosen. This test is about the provenance of a running AI use, so it
    # configures one (the recorded provider fixture still answers, no network).
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_BASE_URL", "https://model.example/v1")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, NOW)
        session.commit()
    explain_module._CACHE.clear()
    return engine


@pytest.fixture
def provider(monkeypatch):
    """A recorded provider: no network, no real key; counts the calls it answers."""

    calls: list[list[dict]] = []

    def answer(*, api_key, messages, **_budget):
        calls.append(messages)
        return DeepSeekCallResult(status="success", content="not JSON, so the rule text stands")

    monkeypatch.setattr(provider_keys, "load_provider_api_key", lambda _provider: "recorded")
    monkeypatch.setattr(llm, "invoke_deepseek", answer)
    return calls


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


def _explain(counterparty: str):
    from eurogas_nexus.api.app import create_app

    explain_module._CACHE.clear()
    return TestClient(create_app()).post(
        "/api/analysis/explain", json={"subject": "credit", "id": counterparty}
    )


def _audits(engine, action: str) -> list[AuditEventRecord]:
    with Session(engine) as session:
        return list(
            session.scalars(select(AuditEventRecord).where(AuditEventRecord.action == action))
        )


def test_a_switched_off_use_makes_no_provider_call_and_shows_the_rule_text(desk, provider):
    counterparty = _breach()
    admin = _admin(desk)

    on = _explain(counterparty)
    assert on.status_code == 200, on.text
    assert len(provider) == 1  # the model was asked (and its note refused by the checks)

    off = admin.put("/api/settings/organisation", json={"ai_features": {"explain": False}})
    assert off.status_code == 200, off.text
    assert off.json()["data"]["ai_features"] == {"explain": False}
    # Switches merge: turning another use off leaves this one off.
    merged = admin.put("/api/settings/organisation", json={"ai_features": {"brief": False}})
    assert merged.json()["data"]["ai_features"] == {"explain": False, "brief": False}

    shown = _explain(counterparty)
    assert shown.status_code == 200, shown.text
    assert shown.json()["data"]["basis"] == "rule"
    assert len(provider) == 1  # no further provider call

    rows = _audits(desk, "settings.organisation.update")
    assert len(rows) == 2
    assert rows[0].after_summary == {"ai_features": {"explain": False}}
    assert rows[1].before_summary == {"ai_features": {"explain": False}}

    admin.put("/api/settings/organisation", json={"ai_features": {"explain": True}})
    _explain(counterparty)
    assert len(provider) == 2


def test_the_audit_row_carries_prompt_version_model_id_and_hashes(desk, provider):
    response = _explain(_breach())
    assert response.status_code == 200, response.text
    (row,) = _audits(desk, "ai.explain")
    ai = row.after_summary["ai"]
    assert ai["use"] == "explain"
    assert ai["prompt_version"] == ai_use("explain").prompt_version
    assert ai["model_id"] and ai["calls"] == 1
    assert ai["model_evaluated"] is True  # the default model is in the evaluation record
    (hashes,) = ai["hashes"]
    assert hashes["status"] == "success"
    assert len(hashes["input_sha256"]) == 64 and len(hashes["output_sha256"]) == 64
    assert "rule text" not in json.dumps(row.after_summary)  # hashes, never the text


@pytest.mark.parametrize(
    "body",
    [
        {"ai_features": {"free_text": False}},
        {"ai_features": {"explain": "off"}},
        {"ai_features": ["explain"]},
    ],
)
def test_invalid_switches_are_refused(desk, body):
    response = _admin(desk).put("/api/settings/organisation", json=body)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "setting_invalid"
