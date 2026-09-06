"""API tests for CR-15 capabilities and governed research orchestration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CanonicalEntityRecord,
    MarketObservationRecord,
    SeriesDefinitionRecord,
)
from eurogas_nexus.security.permissions import Permission, permission_for_path


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'agents-api.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    now = datetime.now(UTC)
    with Session(engine) as session:
        for code in ("NBP", "TTF"):
            session.add(
                CanonicalEntityRecord(
                    canonical_entity_id=f"ent:market_hub:{code}",
                    entity_type="market_hub",
                    canonical_code=code,
                    display_name=code,
                    created_at_utc=now,
                )
            )
        for series_id in (
            "market.price.NBP.DAY_AHEAD",
            "market.price.TTF.DAY_AHEAD",
            "market.fx.EUR.GBP",
        ):
            session.add(
                SeriesDefinitionRecord(
                    series_id=series_id,
                    name=series_id,
                    metric_type="price" if "price" in series_id else "fx",
                    entity_type="market_hub",
                    entity_id="ent:market_hub:NBP",
                    source_class="EEX_Sim",
                    native_frequency="1h",
                    native_unit="EUR/MWh",
                    temporal_type="OBSERVED",
                    availability_semantics="available_at_required",
                    created_at_utc=now,
                )
            )
        for index, (hub, value) in enumerate([("NBP", 30.0), ("TTF", 28.0)]):
            observed = now - timedelta(hours=1)
            session.add(
                MarketObservationRecord(
                    observation_id=f"obs-{index}",
                    market_venue=hub,
                    product="DAY_AHEAD",
                    price=value,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=observed,
                    period_end_utc=observed + timedelta(hours=1),
                    observed_at_utc=observed,
                    source_system="EEX_Sim",
                    source_reference=f"test:{hub}",
                    freshness="OBSERVED",
                    quality_score=1.0,
                    research_only=True,
                    metadata_json={"hub": hub, "tenor": "day-ahead"},
                )
            )
        session.commit()
    test_client = TestClient(create_app())
    test_client.engine = engine
    return test_client


def test_agent_paths_have_declared_permissions() -> None:
    assert permission_for_path("/api/capabilities") == Permission.READ
    assert permission_for_path("/api/capabilities/x/invoke") == Permission.GOVERNED
    assert permission_for_path("/api/agent/research") == Permission.GOVERNED
    assert permission_for_path("/api/agent/runs/x/replay") == Permission.READ


def test_capability_catalog_and_invoke(client) -> None:
    catalog = client.get("/api/capabilities")
    assert catalog.status_code == 200
    capabilities = catalog.json()["data"]
    assert len(capabilities) >= 30
    ids = {item["capability_id"] for item in capabilities}
    assert "ontology.resolve_entity" in ids
    assert "route.calculate_economics" in ids

    search = client.get("/api/capabilities/search", params={"q": "spread"})
    assert search.status_code == 200
    assert any("spread" in item["capability_id"] for item in search.json()["data"])

    describe = client.get("/api/capabilities/route.calculate_economics")
    assert describe.status_code == 200
    assert describe.json()["data"]["determinism_class"] == "DETERMINISTIC"

    invoke = client.post(
        "/api/capabilities/market.get_spread/invoke",
        json={
            "arguments": {
                "origin_hub": "NBP",
                "destination_hub": "TTF",
                "product": "DAY_AHEAD",
                "origin_value": 30,
                "destination_value": 28,
                "unit": "EUR/MWh",
            }
        },
    )
    assert invoke.status_code == 200
    assert invoke.json()["data"]["data"]["value"] == -2.0

    missing = client.post("/api/capabilities/nope/invoke", json={"arguments": {}})
    assert missing.json()["data"]["failure"]["code"] == "UNKNOWN_CAPABILITY"


def test_human_confirmation_gate_via_api(client) -> None:
    response = client.post(
        "/api/capabilities/strategy.freeze_version/invoke",
        json={"arguments": {"strategy_version_id": "v1"}},
    )
    body = response.json()["data"]
    assert body["failure"]["code"] == "HUMAN_CONFIRMATION_REQUIRED"

    confirmed = client.post(
        "/api/capabilities/strategy.freeze_version/invoke",
        json={
            "arguments": {"strategy_version_id": "v1"},
            "human_confirmation": True,
            "confirmation_note": "reviewed",
        },
    )
    # Confirmation passes policy, then DB lookup fails with a typed code.
    assert confirmed.json()["data"]["status"] == "BLOCKED"


def test_research_run_creates_replay_without_hidden_cot(client) -> None:
    response = client.post(
        "/api/agent/research",
        json={
            "objective": "Is the NBP premium over TTF persistent today?",
            "agent_profile": "STRATEGY_RESEARCHER",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stage"] == "READY_FOR_HUMAN_REVIEW"
    run_id = data["agent_run_id"]

    detail = client.get(f"/api/agent/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "READY_FOR_HUMAN_REVIEW"

    replay = client.get(f"/api/agent/runs/{run_id}/replay")
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    assert replay_data["hidden_chain_of_thought"] is None
    assert "tool_invocations" in replay_data
    assert replay_data["model_provider"] == "DETERMINISTIC"


def test_plan_validation_rejects_unknown_entity(client) -> None:
    response = client.post(
        "/api/agent/plans/validate",
        json={
            "plan": {
                "research_plan_id": "plan-bad-entity",
                "objective": "Test an unavailable entity.",
                "question": "Does Atlantis move the spread?",
                "entities": ["ent:market_hub:ATLANTIS"],
                "horizon": "D1",
                "analyses": [],
                "required_evidence": [],
            }
        },
    )
    body = response.json()["data"]
    assert body["ok"] is False
    assert "ENTITY_NOT_FOUND" in body["blockers"]
